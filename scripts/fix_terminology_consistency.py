#!/usr/bin/env python3
"""Read-only, explicitly selected work-rule preview over candidate segments.

No default historical literals, asset-approved inference or direct target writes.
Production canonical apply remains subject to P2.R03 version/export acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.work_rules import (WorkRules, add_work_rule_arguments,
    policy_from_arguments, selected_chapter_range, read_target_document)  # noqa: E402
from review_workspace_storage import reroute_legacy_review_path  # noqa: E402

DOUBLE_QUOTE_OPEN = "「"
DOUBLE_QUOTE_CLOSE = "」"
SINGLE_QUOTE_OPEN = "『"
SINGLE_QUOTE_CLOSE = "』"
ELLIPSIS_RE = re.compile(r"\.\.\.")

Rule = tuple[str, str, str]
TARGET_TEXT_FIELDS = ("draft_text", "refined_text", "target_text", "translation")

def _normalize_ascii_double_quotes(text: str) -> str:
    out: list[str] = []
    is_open = True
    for ch in text:
        if ch == '"' or ch == "“":
            out.append(DOUBLE_QUOTE_OPEN if is_open else DOUBLE_QUOTE_CLOSE)
            is_open = not is_open
            continue
        if ch == "”":
            out.append(DOUBLE_QUOTE_CLOSE)
            is_open = False
            continue
        out.append(ch)
    return "".join(out)


def _normalize_ascii_single_quotes(text: str) -> str:
    out: list[str] = []
    is_open = True
    n = len(text)
    for idx, ch in enumerate(text):
        if ch == "\'" or ch == "‘":
            prev_char = text[idx - 1] if idx > 0 else ""
            next_char = text[idx + 1] if idx + 1 < n else ""
            if prev_char.isalnum() and next_char.isalnum():
                out.append(ch)
                continue
            out.append(SINGLE_QUOTE_OPEN if is_open else SINGLE_QUOTE_CLOSE)
            is_open = not is_open
            continue
        if ch == "’":
            out.append(SINGLE_QUOTE_CLOSE)
            is_open = False
            continue
        out.append(ch)
    return "".join(out)


def _normalize_quoted_punctuation(text: str) -> str:
    text = text.replace("《", DOUBLE_QUOTE_OPEN).replace("》", DOUBLE_QUOTE_CLOSE)
    text = _normalize_ascii_double_quotes(text)
    text = _normalize_ascii_single_quotes(text)
    return text


def _normalize_ellipsis(text: str) -> str:
    return ELLIPSIS_RE.sub("……", text)


def normalize_text_punctuation(text: str) -> str:
    text = _normalize_quoted_punctuation(text)
    text = _normalize_ellipsis(text)
    return text


_KATAKANA = set(chr(c) for c in range(0x30A0, 0x3100))
_KATAKANA.discard("・")


def _source_occurs(source: str, text: str, work_rules=None) -> bool:
    if not source or source not in text:
        return False
    if not all(ch in _KATAKANA for ch in source):
        return True
    start = 0
    excluded = work_rules.get('source_prefix_exclusions', {}).get(source, ()) if work_rules else ()
    while True:
        idx = text.find(source, start)
        if idx == -1:
            return False
        before = text[idx - 1] if idx else ''
        after = text[idx + len(source)] if idx + len(source) < len(text) else ''
        if not any(text.startswith(prefix, idx) for prefix in excluded) and before not in _KATAKANA and after not in _KATAKANA:
            return True
        start = idx + len(source)


def _replace_variant(text: str, variant: str, target: str, work_rules=None) -> tuple[str, int]:
    protected_prefixes = work_rules.get('protected_variant_prefixes', {}).get(variant, ()) if work_rules else ()
    protected_suffixes = work_rules.get('protected_variant_suffixes', {}).get(variant, ()) if work_rules else ()
    target_contexts: list[tuple[str, str]] = []
    target_idx = target.find(variant)
    while target_idx != -1:
        target_contexts.append((target[:target_idx], target[target_idx + len(variant) :]))
        target_idx = target.find(variant, target_idx + 1)

    parts: list[str] = []
    replaced = 0
    start = 0
    while True:
        idx = text.find(variant, start)
        if idx == -1:
            parts.append(text[start:])
            break
        already_canonical = any(
            (not prefix or text[max(0, idx - len(prefix)) : idx] == prefix)
            and (
                not suffix
                or text[idx + len(variant) : idx + len(variant) + len(suffix)] == suffix
            )
            for prefix, suffix in target_contexts
        )
        if already_canonical or any(text[max(0, idx - len(prefix)):idx] == prefix for prefix in protected_prefixes) or any(
            text[idx + len(variant) : idx + len(variant) + len(suffix)] == suffix
            for suffix in protected_suffixes
        ):
            parts.append(text[start : idx + len(variant)])
        else:
            parts.append(text[start:idx])
            parts.append(target)
            replaced += 1
        start = idx + len(variant)
    return "".join(parts), replaced


def apply_rules(text: str, source_text: str, rules: dict[str, list[Rule]], segment_id: str = '',
                *, work_rules: WorkRules | None = None, document=None) -> tuple[str, Counter]:
    """Pure candidate calculation; no ambient instance rules or target writes."""
    if work_rules is not None:
        if not isinstance(work_rules, WorkRules):
            raise ValueError('explicit selected WorkRules required')
        work_rules.require_document(document or {})
    special = work_rules.get('source_rules') if work_rules else ()
    denied = set(work_rules.get('auto_fix_denylist')) if work_rules else set()
    hits = Counter()
    for _pass in range(5):
        pass_hits = Counter()
        before_pass = text
        for row in special:
            variant, target = row['variant'], row['target']
            ids, source = row.get('segment_ids', ()), row.get('source', '')
            if (variant in denied or not variant in text or ids and segment_id not in ids
                    or any(value in text for value in row.get('preserve_if_present', ()))
                    or source and not _source_occurs(source, source_text, work_rules)
                    or any(_source_occurs(value, source_text, work_rules) for value in row.get('blocker_sources', ()))):
                continue
            text, count = _replace_variant(text, variant, target, work_rules)
            if count: pass_hits[variant] += count
        for variant, candidates in sorted(rules.items(), key=lambda kv: -len(kv[0])):
            if not variant or variant in denied or variant not in text:
                continue
            for target, _label, source in candidates:
                if _source_occurs(source, source_text, work_rules):
                    text, count = _replace_variant(text, variant, target, work_rules)
                    if count: pass_hits[variant] += count
                    break
        if not pass_hits or text == before_pass:
            break
        hits.update(pass_hits)
    return text, hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview source-bound work rules without changing target files")
    parser.add_argument("--segments-file", type=Path, required=True)
    parser.add_argument("--chapters", type=int, nargs=2, metavar=("START", "END"), default=None)
    add_work_rule_arguments(parser)
    parser.add_argument("--diff-log", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--update-all-target-fields",
        action="store_true",
        help=(
            "preview all historical target fields; default previews draft_text only"
        ),
    )
    args = parser.parse_args()

    if not args.dry_run:
        parser.error('legacy direct target writes disabled; safe canonical apply is P2.R03')
    try:
        policy = policy_from_arguments(args, REPO_ROOT)
        if policy is None:
            raise ValueError('explicit version-pinned work policy required for legacy preview')
        start, end = selected_chapter_range(args, policy)
    except ValueError as error:
        parser.error(str(error))
    doc = read_target_document(REPO_ROOT, policy, args.segments_file)
    rules = {}  # Old approved/locked YAML claims are not accepted source evidence.
    diffs: list[dict] = []
    rule_hits: Counter = Counter()
    normalization_hits: Counter = Counter()
    skipped_hits: Counter = Counter()
    changed_segments = 0
    changed_fields = 0
    total_segments = 0

    for ch in doc.get("chapters", []):
        num_str = ch.get("chapter_id", "").split("-")[-1]
        try:
            num = int(num_str)
        except ValueError:
            continue
        if not (start <= num <= end):
            continue
        for seg in ch.get("segments", []):
            total_segments += 1
            if args.update_all_target_fields:
                field_values = [
                    (field, seg.get(field) or "")
                    for field in TARGET_TEXT_FIELDS
                    if isinstance(seg.get(field), str) and (seg.get(field) or "")
                ]
            else:
                field_values = [("draft_text", seg.get("draft_text") or "")]

            segment_changed = False
            for field, base in field_values:
                fixed, hits = apply_rules(base, seg.get("source_text") or "", rules, seg.get("segment_id") or "", work_rules=policy, document=doc)
                normalized = normalize_text_punctuation(fixed) if policy.get('normalize_punctuation', False) and policy.language_direction == 'JP_TO_CN' else fixed
                if normalized != fixed:
                    normalization_hits["normalized_text_punctuation"] += 1
                fixed = normalized
                for variant in policy.get('auto_fix_denylist'):
                    if variant in fixed:
                        skipped_hits[variant] += fixed.count(variant)
                if fixed == base:
                    continue
                if hits:
                    rule_hits.update(hits)
                changed_fields += 1
                segment_changed = True
                diffs.append(
                    {
                        "chapter_id": ch["chapter_id"],
                        "segment_id": seg["segment_id"],
                        "field": field,
                        "before": base,
                        "after": fixed,
                        "hits": dict(hits),
                    }
                )
            if segment_changed:
                changed_segments += 1

    summary = {
        "segments_file": str(args.segments_file.relative_to(REPO_ROOT))
        if args.segments_file.is_absolute()
        else str(args.segments_file),
        "chapter_range": [start, end],
        "total_segments": total_segments,
        "changed_segments": changed_segments,
        "changed_fields": changed_fields,
        "rule_hits": dict(sorted(rule_hits.items(), key=lambda kv: -kv[1])),
        "normalization_hits": dict(sorted(normalization_hits.items(), key=lambda kv: -kv[1])),
        "skipped_ambiguous_hits": dict(sorted(skipped_hits.items(), key=lambda kv: -kv[1])),
        "target_field_mode": "historical_preview_all_fields" if args.update_all_target_fields else "draft_preview",
        "work_rules_sha256": policy.sha256,
        "work_rules_mode": "review_only",
        "auto_fix_denylist_count": len(policy.get('auto_fix_denylist')),
        "special_source_rules_count": len(policy.get('source_rules')),
        "dry_run": args.dry_run,
    }
    if args.diff_log:
        diff_log_path = reroute_legacy_review_path(args.diff_log)
        diff_log_path.parent.mkdir(parents=True, exist_ok=True)
        diff_log_path.write_text(
            json.dumps({"summary": summary, "diffs": diffs}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
