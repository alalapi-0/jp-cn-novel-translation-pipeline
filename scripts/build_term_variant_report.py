#!/usr/bin/env python3
"""Build a full-book term/name rendering-variant report (FS-design §4.1).

For every registered character (workspace/configs/character_profile.yaml)
and locked+approved glossary entry (workspace/configs/glossary.yaml), scan
every chapter's source_text for occurrences of the JP source term, then
check what the corresponding CN text (refined_text if present, else
draft_text -- same precedence as export_refined_runs.py::_cn_text) actually
renders it as. Tally the distinct CN renderings observed per term.

This complements scripts/fix_terminology_consistency.py: that script can
only *replace* variants already listed in a `forbidden`/`aliases` list. This
report surfaces UNRECOGNIZED renderings -- spellings nobody has registered
yet -- which is exactly what a rule-replacement pass cannot find on its own.

Output: workspace/review/term_variant_report_full.json (ReviewIssue-shaped).

Usage:
    python3 scripts/build_term_variant_report.py [--chapters START END]
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

import yaml  # noqa: E402

from glossary.store import GlossaryStore  # noqa: E402
from fix_terminology_consistency import AUTO_FIX_DENYLIST  # noqa: E402
from run_consistency_fix_all import discover_canonical_files  # noqa: E402

BRACKETS = "【】"
KANA_RE = set(chr(c) for c in range(0x3040, 0x3100))
KANA_RE.discard("・")


def _strip(s: str) -> str:
    return (s or "").strip().strip(BRACKETS).strip()


def _is_registry_noise(source: str, kind: str) -> bool:
    return kind == "other" and any(ch in KANA_RE for ch in source)


def build_registry(repo_root: Path) -> list[dict]:
    """Return [{term_id, source, canonical, known_variants:set, kind}].

    character_profile.yaml is the authority for person names (per
    docs/translation_pipeline_consistency_redesign_proposal.md §3.4); a
    glossary.yaml entry whose source term duplicates a character_profile
    name is skipped here to avoid reporting the same finding twice.
    """
    registry: list[dict] = []
    person_sources: set[str] = set()

    cp_path = repo_root / "workspace" / "configs" / "character_profile.yaml"
    cp = yaml.safe_load(cp_path.read_text(encoding="utf-8"))
    for c in cp.get("characters", []) or []:
        source = _strip(c.get("name"))
        canonical = _strip(c.get("target_name"))
        if not source or not canonical:
            continue
        known = {v.strip() for v in (c.get("forbidden") or []) if v and v.strip()}
        known.add(canonical)
        person_sources.add(source)
        registry.append({
            "term_id": f"character_profile:{source}",
            "source": source,
            "canonical": canonical,
            "known_variants": known,
            "kind": "person_name",
        })

    store = GlossaryStore(repo_root / "workspace" / "configs" / "glossary.yaml")
    for entry in store.entries():
        if not (entry.locked and entry.approved_by_user):
            continue
        source = _strip(entry.source_term)
        canonical = _strip(entry.target_term)
        if not source or not canonical or source in person_sources:
            continue
        kind = entry.category or "other"
        if _is_registry_noise(source, kind):
            continue
        known = {_strip(a) for a in (entry.aliases or []) if a and a.strip()}
        known.add(canonical)
        registry.append({
            "term_id": f"glossary:{entry.source_term}",
            "source": source,
            "canonical": canonical,
            "known_variants": known,
            "kind": kind,
        })

    return registry


def cn_text(seg: dict) -> str:
    return seg.get("refined_text") or seg.get("draft_text") or ""


_KANA = KANA_RE


def is_allowed_contextual_rendering(term: dict, src: str, cn: str) -> bool:
    """Return true for source/target pairs that are correct contextual renderings.

    These are intentionally checker suppressions rather than glossary aliases:
    adding them as aliases would make the automatic fixer rewrite natural prose
    such as "未经证实" back to the canonical label "确定".
    """
    source = term["source"]
    if source == "確定" and "未確定" in src and "未经证实" in cn:
        return True
    if source == "スケルトン" and "スケルトン系" in src and "骷髅系" in cn:
        return True
    if source == "完全" and "完全武装" in src and "全副武装" in cn:
        return True
    if source == "完全" and "完全無欠" in src and "完美无缺" in cn:
        return True
    if source == "完全" and "完全犯罪" in src and "完美犯罪" in cn:
        return True
    if source == "完全" and "不完全燃焼" in src and "没尽兴" in cn:
        return True
    if source == "ホワイト" and "超ホワイト仕様" in src and "终身雇佣制" in cn:
        return True
    if source == "ヒューマン" and "・ヒューマン" in src and "Human" in cn:
        return True
    if source == "プレイヤー" and "本戦出場プレイヤー組" in src and "选手组" in cn:
        return True
    if source == "レア" and "レア自身" in src and any(surface in cn for surface in ("她自己", "自己")):
        return True
    if source == "リスポーン" and "复活" in cn:
        return True
    if source == "下級" and "下級吸血鬼" in src and "低阶吸血鬼" in cn:
        return True
    if source == "ダンジョン" and "ダンジョン実装" in src and "地下城实装" in cn:
        return True
    if source == "アンデッド" and any(surface in cn for surface in ("不死族", "亡灵", "不死系", "不死生物", "不死巨人")):
        return True
    if source == "エサ" and "エサ用" in src and any(surface in cn for surface in ("供食用", "食用", "饵食")):
        return True
    if source == "上級" and "上級者" in src and any(surface in cn for surface in ("高级玩家", "中高级玩家")):
        return True
    if source == "オーク" and "オーク・オライオン" in src and any(
        surface in cn for surface in ("奥克·奥莱恩", "奥克·奥赖恩", "兽人·猎户座")
    ):
        return True
    if source == "オーク" and "幻獣王オーク" in src and "奥克" in cn:
        return True
    return False


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
    parser.add_argument("--chapters", type=int, nargs=2, metavar=("START", "END"), default=(1, 612))
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "workspace" / "review" / "term_variant_report_full.json")
    args = parser.parse_args()
    start, end = args.chapters

    registry = build_registry(REPO_ROOT)
    print(f"registered terms: {len(registry)}", file=sys.stderr)

    # term_id -> {rendering: {"count": int, "chapters": Counter}}
    stats: dict[str, dict[str, dict]] = {t["term_id"]: {} for t in registry}
    by_id = {t["term_id"]: t for t in registry}

    files = discover_canonical_files()
    print(f"canonical files: {len(files)}", file=sys.stderr)

    for f in sorted(files):
        doc = json.loads(f.read_text(encoding="utf-8"))
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
                    if is_allowed_contextual_rendering(term, src, cn):
                        continue
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
        if non_canonical and all(k in AUTO_FIX_DENYLIST for k in non_canonical):
            continue
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
                else "Only already-known forbidden variants observed (should already be fixed by fix_terminology_consistency.py; if not, that's a sync gap)."
            ),
        })

    issues.sort(key=lambda i: (i["severity"] != "high", -sum(v["count"] for v in i["evidence"]["variants_observed"].values())))

    report = {
        "schema": "term_variant_report_full",
        "chapter_range": [start, end],
        "terms_registered": len(registry),
        "terms_with_variance": len(issues),
        "terms_with_unrecognized_variants": sum(1 for i in issues if i["severity"] == "high"),
        "issues": issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "issues"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
