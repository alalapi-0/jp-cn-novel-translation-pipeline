#!/usr/bin/env python3
"""Read-only term observations for an explicitly selected work/target manifest.

Registry hints are selected policy data, never implicit approved/locked assets.
Contextual explanations are visible alongside observations, not hidden issues.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.work_rules import (add_work_rule_arguments, policy_from_arguments,
    selected_chapter_range, selected_target_paths, read_target_document)  # noqa: E402
from review_workspace_storage import (  # noqa: E402
    reroute_legacy_review_path,
    review_workspace_path,
)

BRACKETS = "【】"
KANA_RE = set(chr(c) for c in range(0x3040, 0x3100))
KANA_RE.discard("・")


def _strip(s: str) -> str:
    return (s or "").strip().strip(BRACKETS).strip()


def _is_registry_noise(source: str, kind: str) -> bool:
    return kind == "other" and any(ch in KANA_RE for ch in source)


def build_registry(repo_root: Path, work_rules=None) -> list[dict]:
    if work_rules is None:
        raise ValueError('explicit selected work registry required; no ambient assets')
    return [{**row, 'known_variants': set(row['aliases']) | {row['canonical']}}
            for row in work_rules.get('term_registry')]


def cn_text(seg: dict) -> str:
    return seg.get("draft_text") or ""


_KANA = KANA_RE


def is_allowed_contextual_rendering(term: dict, src: str, cn: str, work_rules=None) -> bool:
    """A selected contextual explanation never silently removes an observation."""
    return bool(work_rules and any(row['source'] == term['source'] and row['source_contains'] in src
        and any(value in cn for value in row['target_contains_any']) for row in work_rules.get('contextual_variants')))


def find_standalone_occurrences(source: str, text: str) -> int:
    """Count occurrences of `source` in `text` that are NOT fused into a
    longer kana run (e.g. skip the 'レア' inside 'レアスキル' /
    'レアアイテム' so a character name and an unrelated common loanword
    sharing a prefix don't get conflated). A real name reference is
    typically followed/preceded by a particle, punctuation, or kanji/kana
    boundary, not another katakana character."""
    count = 0
    start = 0
    while True:
        idx = text.find(source, start)
        if idx == -1:
            break
        before = text[idx - 1] if idx > 0 else ""
        after_idx = idx + len(source)
        after = text[after_idx] if after_idx < len(text) else ""
        if before not in _KANA and after not in _KANA:
            count += 1
        start = idx + len(source)
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", type=int, nargs=2, metavar=("START", "END"), default=None)
    add_work_rule_arguments(parser)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    try:
        policy=policy_from_arguments(args,REPO_ROOT)
        if policy is None:raise ValueError('explicit version-pinned work policy required')
        start,end=selected_chapter_range(args,policy)
        files=selected_target_paths(REPO_ROOT,policy)
    except ValueError as error:parser.error(str(error))
    output_path = (
        review_workspace_path("term_variant_report_full.json")
        if args.output is None
        else reroute_legacy_review_path(args.output)
    )

    registry = build_registry(REPO_ROOT, policy)
    print(f"registered terms: {len(registry)}", file=sys.stderr)

    # term_id -> {rendering: {"count": int, "chapters": Counter}}
    stats: dict[str, dict[str, dict]] = {t["term_id"]: {} for t in registry}
    by_id = {t["term_id"]: t for t in registry}

    contextual_explanations=[]
    print(f"canonical files: {len(files)}", file=sys.stderr)

    for f in sorted(files):
        doc = read_target_document(REPO_ROOT,policy,f)
        for ch in doc.get("chapters", []):
            try:
                num = int(ch["chapter_id"].split("-")[-1])
            except (KeyError, ValueError):
                continue
            if not (start <= num <= end):
                continue
            for seg in ch.get("segments", []):
                src = seg.get("source_text") or ""
                if not src:
                    continue
                cn = cn_text(seg)
                if not cn:
                    continue
                for term in registry:
                    if find_standalone_occurrences(term["source"], src) == 0:
                        continue
                    rendering = None
                    if is_allowed_contextual_rendering(term, src, cn, policy):
                        contextual_explanations.append({'term_id':term['term_id'],'segment_id':seg.get('segment_id'), 'policy_sha256':policy.sha256})
                    for variant in sorted(term["known_variants"], key=len, reverse=True):
                        if variant in cn:
                            rendering = variant
                            break
                    if rendering is None:
                        rendering = "UNRECOGNIZED"
                    bucket = stats[term["term_id"]].setdefault(
                        rendering, {"count": 0, "chapters": Counter(), "sample_segment_ids": []}
                    )
                    bucket["count"] += 1
                    bucket["chapters"][num] += 1
                    if len(bucket["sample_segment_ids"]) < 40:
                        bucket["sample_segment_ids"].append(seg.get("segment_id"))

    issues = []
    for term_id, renderings in stats.items():
        term = by_id[term_id]
        non_canonical = {k: v for k, v in renderings.items() if k != term["canonical"]}
        if not non_canonical:
            continue
        unrecognized = renderings.get("UNRECOGNIZED")
        issue_type = "TERM_INCONSISTENCY" if term["kind"] != "person_name" else "NAME_INCONSISTENCY"
        issues.append({
            "issue_type": issue_type,
            "term_id": term_id,
            "source": term["source"],
            "canonical": term["canonical"],
            "kind": term["kind"],
            "severity": "high" if unrecognized else "low",
            "evidence": {
                "variants_observed": {
                    k: {
                        "count": v["count"],
                        "chapters": sorted(v["chapters"].keys()),
                        "sample_segment_ids": v["sample_segment_ids"],
                    }
                    for k, v in renderings.items()
                },
            },
            "note": (
                "Contains UNRECOGNIZED renderings not in canonical/known_variants -- new variant, needs review."
                if unrecognized
                else "Selected policy aliases differ from its canonical hint; review the evidence before choosing a rendering."
            ),
        })

    issues.sort(key=lambda i: (i["severity"] != "high", -sum(v["count"] for v in i["evidence"]["variants_observed"].values())))

    report = {
        'mode':'review_only', 'work_rules_sha256':policy.sha256,
        'contextual_explanations':contextual_explanations,
        "schema": "term_variant_report_full",
        "chapter_range": [start, end],
        "terms_registered": len(registry),
        "terms_with_variance": len(issues),
        "terms_with_unrecognized_variants": sum(1 for i in issues if i["severity"] == "high"),
        "issues": issues,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "issues"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
