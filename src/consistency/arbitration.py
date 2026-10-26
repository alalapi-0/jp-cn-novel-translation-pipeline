"""Level 4 model arbitration for rule-undecidable glossary conflicts (FS-037).

Only ``shared_target`` and ``divergent_translation`` findings enter arbitration.
Protected-term violations remain deterministic (Level 2). Outputs statistics only —
never source or draft body text in reports.
"""

from __future__ import annotations

import json
import hashlib
import time
import re
from datetime import datetime, timezone
from typing import Any, Callable
from pathlib import Path

from providers.types import GenerateOptions, Message, ModelResult
from providers.controlled_run import atomic_write_json, checkpoint_lock
from translation.content_binding import SourceBindings, validate_round, reserve_round

ARBITRABLE_KINDS: frozenset[str] = frozenset({"shared_target", "divergent_translation"})
DEFAULT_MAX_API_CALLS = 10

SYSTEM_PROMPT = """你是轻小说翻译术语仲裁助手。统计频次不证明原义。
只根据给定的版本绑定原文片段提出局部译法；证据不足返回 resolution=abstain。
允许不同语境的多个译法 alternatives=[{target,condition}]，不能强选全书词面。
单一建议仍是待核候选，不是事实、canonical 或真人批准。
输出 JSON，resolution 为 candidate、alternatives 或 abstain；可含 canonical_target、rationale、confidence。"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_arbitration_candidates(glossary_audit: dict[str, Any]) -> list[dict[str, Any]]:
    """Return rule-undecidable conflicts eligible for Level 4 arbitration."""
    candidates: list[dict[str, Any]] = []
    for row in glossary_audit.get("findings") or []:
        kind = str(row.get("kind") or "")
        if kind not in ARBITRABLE_KINDS:
            continue
        candidates.append(
            {
                "kind": kind,
                "source_term": row.get("source_term"),
                "target_term": row.get("target_term"),
                "source_terms": list(row.get("source_terms") or []),
                "alternate_targets": dict(row.get("alternate_targets") or {}),
                "chapters": list(row.get("chapters") or []),
                "segment_count": len(row.get("segment_ids") or []),
                "source_evidence": row.get("source_evidence") or [],
            }
        )
    candidates.sort(key=lambda row: (row["kind"], str(row.get("source_term") or row.get("target_term"))))
    return candidates


def build_arbitration_messages(candidate: dict[str, Any], language_direction='JP_TO_CN', *, source_evidence=None) -> list[Message]:
    if not source_evidence:raise ValueError("source-grounded arbitration evidence required")
    payload = {
        "kind": candidate["kind"],
        "source_evidence": source_evidence,
        "source_term": candidate.get("source_term"),
        "canonical_glossary_target": candidate.get("target_term"),
        "alternate_source_terms": candidate.get("source_terms"),
        "alternate_targets_with_counts": candidate.get("alternate_targets"),
        "sample_chapters": candidate.get("chapters"),
        "segment_count": candidate.get("segment_count"),
        "instruction": (
            ("Pick one canonical Simplified Chinese target for consistency. "
             if language_direction == 'JP_TO_CN' else 'Pick one canonical Japanese target for consistency. ')
            +
            "A name is only a local unverified proposal. Use the bound original evidence; return contextual alternatives or abstain. Counts and locked labels are not semantic truth."
        ),
    }
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=json.dumps(payload, ensure_ascii=False, indent=2)),
    ]


def _missing_source_evidence(candidate):
    value=candidate.get('source_evidence')
    return value is None or type(value) is list and not value


def _validated_source_evidence(candidate, bindings):
    rows=candidate.get('source_evidence')
    if _missing_source_evidence(candidate):return []
    if type(rows) is not list or len(rows)>8:raise ValueError('invalid arbitration source evidence')
    documents={b['document'].chapter_id:b['document'] for b in bindings};result=[];chars=0
    for row in rows:
        if type(row) is not dict:raise ValueError('invalid arbitration source evidence')
        if type(row.get('chapter_id')) is not str:raise ValueError('invalid arbitration source chapter')
        document=documents.get(row.get('chapter_id'));a=row.get('start_char');b=row.get('end_char');quote=row.get('quote')
        if (document is None or row.get('source_revision')!=document.revision
                or type(a) is not int or type(b) is not int or not 0<=a<b<=len(document.text)
                or type(quote) is not str or quote!=document.text[a:b]):
            raise ValueError('arbitration evidence differs from registered original')
        chars+=len(quote)
        if chars>2400:raise ValueError('arbitration source evidence limit exceeded')
        result.append({'chapter_id':document.chapter_id,'source_revision':document.revision,
            'start_char':a,'end_char':b,'quote':quote,'semantic_truth':'not_verified'})
    return result


_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"canonical_target\"[^{}]*\}", re.DOTALL)


def parse_arbitration_response(raw_output: str) -> dict[str, Any]:
    text = (raw_output or "").strip()
    if not text:
        return {"parse_status": "failed", "error": "empty_response"}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            return {"parse_status": "failed", "error": "json_parse_failed"}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"parse_status": "failed", "error": "json_parse_failed"}
    if not isinstance(data, dict):
        return {"parse_status": "failed", "error": "invalid_response_object"}
    if data.get('resolution')=='abstain':
        return {'parse_status':'abstain','reason':'provider_abstained','canonical_adoption':False,'human_approved_final':False}
    alternatives=data.get('alternatives')
    if alternatives:
        if (type(alternatives) is not list or len(alternatives)>16 or any(type(x) is not dict
                or set(x)!={'target','condition'} or any(type(x[k]) is not str or not x[k].strip()
                    for k in ['target','condition']) for x in alternatives)):
            return {'parse_status':'failed','error':'invalid_contextual_alternatives'}
        return {'parse_status':'ok','resolution':'alternatives','alternatives':alternatives,
            'semantic_truth':'not_verified','canonical_adoption':False,'human_approved_final':False}
    canonical = data.get("canonical_target")
    if not isinstance(canonical, str):
        return {"parse_status": "failed", "error": "invalid_canonical_target"}
    canonical = canonical.strip()
    if not canonical:
        return {"parse_status": "failed", "error": "missing_canonical_target"}
    return {
        "parse_status": "ok",
        "resolution":"candidate","semantic_truth":"not_verified","canonical_adoption":False,"human_approved_final":False,
        "canonical_target": canonical,
        "rationale": str(data.get("rationale") or ""),
        "confidence": str(data.get("confidence") or "medium"),
    }


def run_arbitration(
    candidates: list[dict[str, Any]], *, provider: Any,
    max_api_calls: int = DEFAULT_MAX_API_CALLS, dry_run: bool = False,
    checkpoint_path: Path | None = None, repo_root: Path | None = None,
    language_direction: str = 'JP_TO_CN',
) -> dict[str, Any]:
    """Reserve each generate invocation before dispatch. Real resume requires a checkpoint.

    This cap counts adapter invocations, not hidden provider retries; lower-level
    attempt/token-cost guards must be verified before production adoption.
    """
    cap = int(max_api_calls)
    if cap < 0: raise ValueError("max_api_calls must be nonnegative")
    dry_run = dry_run or getattr(provider, 'provider_id', None) in {'fake', 'dry_run', 'fake_provider', 'dry_run_provider'}
    if dry_run:
        preview = candidates[:cap] if cap else candidates
        decisions = [{"kind": candidate["kind"], "source_term": candidate.get("source_term"),
                      "target_term": candidate.get("target_term"), "parse_status": "simulated", "dry_run": True}
                     for candidate in preview]
        report = {"generated_at": utc_now_iso(), "dry_run": True,
                  "candidate_count": len(candidates), "arbitrated_count": 0,
                  "simulated_count": len(decisions), "preview_truncated": len(preview) < len(candidates),
                  "api_calls": 0, "provider_invocations_used": 0, "max_api_calls": cap,
                  "budget_exhausted": False, "skipped_count": len(candidates) - len(preview),
                  "decisions": decisions}
        report["status"] = arbitration_summary(report)["status"]
        return {**report,"canonical_adoption":False,"human_approved_final":False}
    if checkpoint_path is None:
        if candidates and cap > 0:
            raise ValueError("real arbitration requires a persistent checkpoint_path")
        report = {"dry_run": False, "candidate_count": len(candidates), "arbitrated_count": 0,
                  "api_calls": 0, "provider_invocations_used": 0, "max_api_calls": cap,
                  "budget_exhausted": bool(candidates), "decisions": [], "skipped_count": len(candidates)}
        report["status"] = arbitration_summary(report)["status"]
        return {**report,"canonical_adoption":False,"human_approved_final":False}
    resolver = SourceBindings(repo_root) if repo_root is not None else None
    bindings = []
    for candidate in candidates if cap > 0 else []:
        if _missing_source_evidence(candidate):
            bindings.append([]);continue
        if resolver is None or not candidate.get('chapters'):
            raise ValueError('arbitration requires registered full-source chapter lineage')
        bindings.append([resolver.chapter(chapter, direction=language_direction)
                         for chapter in candidate['chapters']])
    sources = [resolver.identities(rows) for rows in bindings] if resolver else []
    identity = hashlib.sha256(json.dumps({'protocol':'source-grounded-arbitration/2','candidates':candidates,'full_sources':sources},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with checkpoint_lock(checkpoint_path):
        if checkpoint_path.exists():
            cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if cp.get("schema") != "arbitration-progress/1" or cp.get("input_sha256") != identity:
                raise ValueError("unverified or changed arbitration checkpoint")
            if type(cp.get("provider_invocations_used")) is not int or cp["provider_invocations_used"] < 0:
                raise ValueError("invalid persisted arbitration invocation count")
            if not set(cp["completed_item_ids"]).issubset(str(i) for i in range(len(candidates))):
                raise ValueError("arbitration checkpoint completion outside input")
            if cap > cp["max_api_calls"]: raise ValueError("checkpoint budget increase requires authorization")
            validate_round(cp)
        else:
            cp = {"schema": "arbitration-progress/1", "input_sha256": identity,
                  "provider_invocations_used": 0, "completed_item_ids": [], "decisions": [],
                  'content_unit_ids_used': [], 'content_round_started_at': time.time()}
        cp["max_api_calls"] = cap
        before = cp["provider_invocations_used"]
        # Resolve every evidence-free selector item before lineage, budget or
        # dispatch of grounded items can stop the batch. This includes cap/unit
        # stops later in the batch and remains terminal on checkpoint resume.
        for index,candidate in enumerate(candidates):
            item_id=str(index)
            if item_id not in cp['completed_item_ids'] and _missing_source_evidence(candidate):
                cp['decisions'].append({'item_id':item_id,'kind':candidate['kind'],'parse_status':'abstain',
                    'reason':'missing_original_evidence','canonical_adoption':False,'human_approved_final':False})
                cp['completed_item_ids'].append(item_id)
        atomic_write_json(checkpoint_path,cp)
        for index, candidate in enumerate(candidates):
            item_id = str(index)
            if item_id in cp["completed_item_ids"]: continue
            if cp["provider_invocations_used"] >= cap: break
            evidence=_validated_source_evidence(candidate,bindings[index])
            try:
                reserve_round(cp, bindings[index])
            except RuntimeError as error:
                cp['content_stop_reason'] = str(error)
                break
            cp["provider_invocations_used"] += 1
            cp["in_flight_item_id"] = item_id
            atomic_write_json(checkpoint_path, cp)
            try:
                messages = build_arbitration_messages(candidate, language_direction,source_evidence=evidence)
                with resolver.operation(bindings[index], messages, provider,
                        role='review', run_id=str(checkpoint_path), deadline=cp['content_round_started_at']+2400):
                    result: ModelResult = provider.generate(messages,
                        GenerateOptions(project_id="consistency_arbitration", pipeline_stage="consistency_arbitration",
                                        language_direction=language_direction))
                parsed = (parse_arbitration_response(result.raw_output) if result.status == "ok" and not result.dry_run
                          else {"parse_status": "failed", "error": "provider_result_failed"})
            except Exception as exc:
                parsed = {"parse_status": "failed", "error": type(exc).__name__}
            except BaseException:
                cp["status"] = "interrupted"
                atomic_write_json(checkpoint_path, cp)
                raise
            row = {"item_id": item_id, "kind": candidate["kind"],
                   "source_term": candidate.get("source_term"), "target_term": candidate.get("target_term"), **parsed}
            cp["decisions"].append(row)
            if parsed.get("parse_status") in {"ok","abstain"}: cp["completed_item_ids"].append(item_id)
            cp.pop("in_flight_item_id", None)
            atomic_write_json(checkpoint_path, cp)
        remaining = len(candidates) - len(cp["completed_item_ids"])
        report = {"generated_at": utc_now_iso(), "dry_run": False, "candidate_count": len(candidates),
                  "arbitrated_count": sum(row.get("parse_status")=="ok" for row in {r["item_id"]:r for r in cp["decisions"]}.values()),
                  "resolved_count":len(cp["completed_item_ids"]), "api_calls": cp["provider_invocations_used"] - before,
                  "provider_invocations_used": cp["provider_invocations_used"], "max_api_calls": cap,
                  "budget_exhausted": bool(remaining and (cp["provider_invocations_used"] >= cap or cp.get('content_stop_reason'))),
                  "skipped_count": remaining, "decisions": cp["decisions"],
                  "call_count_scope": "durable adapter reservations; denied admission included; physical retries share source/provider ledgers; wire calls unknown"}
        report["status"] = arbitration_summary(report)["status"]
        cp["status"] = report["status"]
        atomic_write_json(checkpoint_path, cp)
        return {**report,"canonical_adoption":False,"human_approved_final":False}


def arbitration_summary(report: dict[str, Any]) -> dict[str, Any]:
    latest = {str(d.get("item_id", i)): d for i, d in enumerate(report.get("decisions") or [])}
    ok = sum(d.get("parse_status") == "ok" for d in latest.values())
    failed = sum(d.get("parse_status") == "failed" for d in latest.values())
    abstained = sum(d.get("parse_status") == "abstain" for d in latest.values())
    total = int(report.get("candidate_count", len(latest)) or 0)
    status = ("SIMULATED" if report.get("dry_run") else "FAIL" if failed
              else "NO_OP" if not total else "ABSTAIN" if abstained and ok+abstained==total else "PASS" if ok == total
              else "BUDGET_EXHAUSTED" if report.get("budget_exhausted") else "PENDING")
    return {"status": status, "candidate_count": total,
            "arbitrated_count": report.get("arbitrated_count"), "api_calls": report.get("api_calls"),
            "max_api_calls": report.get("max_api_calls"), "budget_exhausted": report.get("budget_exhausted"),
            "successful_decisions": ok, "failed_decisions": failed,"abstained_decisions":abstained, "dry_run": report.get("dry_run")}


ProviderFactory = Callable[[Any], Any]
