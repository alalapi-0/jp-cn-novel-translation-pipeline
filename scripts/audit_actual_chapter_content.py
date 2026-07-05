#!/usr/bin/env python3
"""Build a content-first audit for a chapter range.

This report intentionally treats glossary/profile data as hints, not truth.
It starts from the current canonical segments.json files and records what the
source and latest CN text actually contain. Previous QA issues can be
revalidated against current text without assuming the old rules were correct.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary.store import GlossaryStore  # noqa: E402
from run_consistency_fix_all import discover_canonical_files  # noqa: E402

BRACKETS = "【】"
KANA_RUN_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\u30fc]{1,}")
KATAKANA_TERM_RE = re.compile(r"[\u30a1-\u30fa\u30fc]{2,}(?:[A-Za-z0-9]+)?")
PLACEHOLDER_RE = re.compile(r"[□�]")
PLAYER_EN_RE = re.compile(r"(?<![A-Za-z])Player(?![A-Za-z])")
CHAPTER_ID_RE = re.compile(r"ch-(\d+)")
KANA_CHARS = set(chr(c) for c in range(0x3040, 0x3100))
ASCII_QUOTE_RE = re.compile(r"[\"“”‘’]")
ASCII_ELLIPSIS_RE = re.compile(r"\.\.\.")
ENGLISH_TOKEN_RE = re.compile(r"\b([A-Za-z]{3,})\b")
_ENGLISH_IN_QUOTES_OR_PARENS_RE = re.compile(
    r'("[^"]*"|“[^”]*”|‘[^’]*’|\'[^\']*\'|\([^)]*\)|（[^）]*）|「[^」]*」|『[^』]*』|《[^》]*》)',
)
DIALOGUE_MARKERS = ("「", "『", "」", "』")
WORK_ROOT_PROFILE = REPO_ROOT / "workspace" / "configs"
TEMPLATE_PROFILE = REPO_ROOT / "configs"
ENGLISH_RESIDUAL_ALLOWLIST = {
    "HP",
    "MP",
    "AP",
    "DEF",
    "EXP",
    "NPC",
    "PVP",
    "PVE",
    "MMO",
    "RPG",
    "ARPG",
    "Boss",
    "Bosses",
    "boss",
    "bosses",
    "Lv",
    "LV",
    "UI",
    "ATK",
    "SPD",
    "AGI",
    "STR",
    "INT",
    "MVP",
    "GM",
    "DM",
    "MOB",
    "AOE",
    "DPS",
    "MPC",
    "VIT",
    "MND",
    "DEX",
    "RPG",
    "ARPG",
    "PVP",
    "PVE",
    "DPS",
    "BLIZZARD",
    "CRYO",
    "DEUS",
    "MATRIX",
    "ANT",
    "INFANTRY",
    "RAID",
    "RISING",
    "RIVER",
    "MATH",
    "SKELETOY",
    "JAPPER",
    "RICK",
    "LEVELER",
    "OREISO",
    "ENANT",
    "NOUR",
    "SHIMO",
    "SHITA",
    "ITTE",
    "OKONATTE",
    "ITAIKENA",
    "BLANK",
    "MOST",
    "PLAYER",
    "TREMBLE",
    "TAKUMA",
    "AMATEINTEIN",
    "BOOKS",
    "MANY",
    "ORICHALCUM",
    "DIVINE",
    "MAIL",
    "MAGNOSUKE",
    "ORCMAN",
    "RURURU",
    "RURURURU",
    "MAGNA",
    "MERUM",
}
ENGLISH_RESIDUAL_TERM_ALLOWLIST: set[str] = set()
ENGLISH_RESIDUAL_DYNAMIC_BLOCKWORDS = {
    "https",
    "http",
    "www",
    "com",
    "net",
    "viewimagebig",
    "userpageimage",
}
PLAYER_EN_EXEMPTIONS = (
    "Most Valuable Player",
    "Monster Players",
    "プレイするとは",
    "ＭＶＰ",
)
PROTECTED_LITERAL_SOURCE_RESIDUALS = (
    "蛻カ髯占ァ」髯、",
    "カ髯占ァ",
    "縺薙≧縺励※莠コ縺ッ螟ゥ縺ォ譏?ｋ",
)


def source_occurs_as_term(source: str, text: str) -> bool:
    """Return true when a source hint occurs as its own kana term.

    This keeps レア from matching inside アザレア while still allowing
    non-kana source hints such as kanji names to use ordinary substring
    matching.
    """
    if not source or source not in text:
        return False
    if not any(ch in KANA_CHARS for ch in source):
        return True
    start = 0
    while True:
        idx = text.find(source, start)
        if idx == -1:
            return False
        before = text[idx - 1] if idx > 0 else ""
        after_idx = idx + len(source)
        after = text[after_idx] if after_idx < len(text) else ""
        if before not in KANA_CHARS and after not in KANA_CHARS:
            return True
        start = idx + len(source)


def is_registry_hint_noise(hint: dict[str, Any]) -> bool:
    source = hint.get("source") or ""
    return hint.get("kind") == "other" and bool(KANA_RUN_RE.search(source))


def is_allowed_contextual_hint(source: str, src: str, tgt: str) -> bool:
    """Skip correct contextual renderings that should not become fixer aliases."""
    if source == "確定" and "未確定" in src and "未经证实" in tgt:
        return True
    if source == "スケルトン" and "スケルトン系" in src and "骷髅系" in tgt:
        return True
    if source == "完全" and "完全武装" in src and "全副武装" in tgt:
        return True
    if source == "完全" and "完全無欠" in src and "完美无缺" in tgt:
        return True
    if source == "完全" and "完全犯罪" in src and "完美犯罪" in tgt:
        return True
    if source == "完全" and "不完全燃焼" in src and "没尽兴" in tgt:
        return True
    if source == "ホワイト" and "超ホワイト仕様" in src and "终身雇佣制" in tgt:
        return True
    if source == "ヒューマン" and "・ヒューマン" in src and "Human" in tgt:
        return True
    if source == "プレイヤー" and "本戦出場プレイヤー組" in src and "选手组" in tgt:
        return True
    if source == "レア" and "レア自身" in src and any(surface in tgt for surface in ("她自己", "自己")):
        return True
    if source == "リスポーン" and "复活" in tgt:
        return True
    if source == "下級" and "下級吸血鬼" in src and "低阶吸血鬼" in tgt:
        return True
    if source == "ダンジョン" and "ダンジョン実装" in src and "地下城实装" in tgt:
        return True
    if source == "アンデッド" and any(surface in tgt for surface in ("不死族", "亡灵", "不死系", "不死生物", "不死巨人")):
        return True
    if source == "エサ" and "エサ用" in src and any(surface in tgt for surface in ("供食用", "食用", "饵食")):
        return True
    if source == "上級" and "上級者" in src and any(surface in tgt for surface in ("高级玩家", "中高级玩家")):
        return True
    if source == "オーク" and "オーク・オライオン" in src and any(
        surface in tgt for surface in ("奥克·奥莱恩", "奥克·奥赖恩", "兽人·猎户座")
    ):
        return True
    if source == "オーク" and "幻獣王オーク" in src and "奥克" in tgt:
        return True
    return False


def is_protected_literal_source_residual(src: str, tgt: str, tokens: list[str]) -> bool:
    """Allow deliberate in-world opaque literals that appear unchanged in source and target."""
    return any(literal in src and literal in tgt and all(token in literal for token in tokens) for literal in PROTECTED_LITERAL_SOURCE_RESIDUALS)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _collect_english_tokens(text: str) -> set[str]:
    return {token.lower() for token in ENGLISH_TOKEN_RE.findall(text or "")}


def _load_english_term_allowlist() -> set[str]:
    global ENGLISH_RESIDUAL_TERM_ALLOWLIST
    if ENGLISH_RESIDUAL_TERM_ALLOWLIST:
        return ENGLISH_RESIDUAL_TERM_ALLOWLIST

    terms: set[str] = {t.lower() for t in ENGLISH_RESIDUAL_ALLOWLIST}
    terms.update(ENGLISH_RESIDUAL_DYNAMIC_BLOCKWORDS)

    cp = _read_yaml(WORK_ROOT_PROFILE / "character_profile.yaml")
    if not cp:
        cp = _read_yaml(TEMPLATE_PROFILE / "character_profile.yaml")
    for c in cp.get("characters", []) if isinstance(cp, dict) else []:
        if not isinstance(c, dict):
            continue
        terms.update(_collect_english_tokens(str(c.get("name") or "")))
        terms.update(_collect_english_tokens(str(c.get("target_name") or "")))
        for alias in c.get("aliases") or []:
            terms.update(_collect_english_tokens(str(alias or "")))
        terms.update(_collect_english_tokens(str(c.get("first_person") or "")))
        for marker in c.get("speech_tics") or []:
            terms.update(_collect_english_tokens(str(marker or "")))

    store = GlossaryStore(REPO_ROOT / "workspace" / "configs" / "glossary.yaml")
    for entry in store.entries():
        terms.update(_collect_english_tokens(entry.source_term))
        terms.update(_collect_english_tokens(entry.target_term))
        for alias in entry.aliases or []:
            terms.update(_collect_english_tokens(alias))
        if entry.description:
            terms.update(_collect_english_tokens(entry.description))
        if entry.notes:
            terms.update(_collect_english_tokens(entry.notes))
        if entry.category:
            terms.update(_collect_english_tokens(entry.category))

    ENGLISH_RESIDUAL_TERM_ALLOWLIST = terms
    return terms


def _load_style_punctuation_rules() -> list[str]:
    cp = _read_yaml(WORK_ROOT_PROFILE / "style_profile.yaml")
    if cp:
        profiles = cp.get("profiles") or []
    else:
        cp = _read_yaml(TEMPLATE_PROFILE / "style_profile.yaml")
        profiles = cp.get("profiles") or []
    rules: list[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        for rule in profile.get("punctuation_rules") or []:
            text = str(rule or "").strip()
            if text and text not in rules:
                rules.append(text)
    return rules


def _contains_dialogue_markup(text: str) -> bool:
    return any(marker in text for marker in DIALOGUE_MARKERS)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chapter_num(raw: str) -> int | None:
    m = CHAPTER_ID_RE.search(raw or "")
    return int(m.group(1)) if m else None


def cn_text(seg: dict[str, Any]) -> str:
    return seg.get("refined_text") or seg.get("draft_text") or ""


def strip_brackets(raw: str) -> str:
    return (raw or "").strip().strip(BRACKETS).strip()


def clip(text: str, needle: str = "", *, width: int = 140) -> str:
    text = " ".join((text or "").split())
    if not text or len(text) <= width:
        return text
    if needle and needle in text:
        pos = text.find(needle)
        start = max(0, pos - width // 2)
        end = min(len(text), start + width)
        start = max(0, end - width)
        prefix = "..." if start else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end] + suffix
    return text[: width - 3] + "..."


def _mask_quoted_english_for_scan(text: str) -> str:
    def _mask(match: re.Match[str]) -> str:
        block = match.group(0)
        return " " * len(block)

    return _ENGLISH_IN_QUOTES_OR_PARENS_RE.sub(_mask, text)


def load_segments(start: int, end: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(discover_canonical_files()):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for ch in doc.get("chapters", []) or []:
            cid = ch.get("chapter_id") or ""
            num = chapter_num(cid)
            if num is None or not (start <= num <= end):
                continue
            for seg in ch.get("segments", []) or []:
                sid = seg.get("segment_id") or ""
                if not sid:
                    continue
                row = dict(seg)
                row["_chapter_id"] = cid
                row["_run_file"] = str(path.relative_to(REPO_ROOT))
                out[sid] = row
    return out


def target_punctuation_residuals(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for sid, seg in segments.items():
        tgt = cn_text(seg)
        issues: list[str] = []
        if ASCII_QUOTE_RE.search(tgt):
            issues.append("ascii_dialogue_quotes")
        if ASCII_ELLIPSIS_RE.search(tgt) and "…" not in tgt:
            issues.append("ascii_ellipsis")
        if "《" in tgt or "》" in tgt:
            issues.append("system_notice_brackets_present")
            if "《" in tgt and "》" not in tgt:
                issues.append("unmatched_system_brackets")
            if "》" in tgt and "《" not in tgt:
                issues.append("unmatched_system_brackets")
        if not issues:
            continue
        rows.append(
            {
                "chapter_id": seg["_chapter_id"],
                "segment_id": sid,
                "issues": issues,
                "source_ref": clip(seg.get("source_text") or ""),
                "target_ref": clip(tgt),
            }
        )
    return rows


def target_english_residuals(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    allowed_lower = _load_english_term_allowlist()
    for sid, seg in segments.items():
        src = seg.get("source_text") or ""
        tgt = cn_text(seg)
        if not tgt:
            continue
        masked_tgt = _mask_quoted_english_for_scan(tgt)
        tokens = sorted(set(ENGLISH_TOKEN_RE.findall(masked_tgt)))
        src_tokens = _collect_english_tokens(src)
        suspicious = [
            token
            for token in tokens
            if token.lower() not in allowed_lower and token.lower() not in src_tokens
        ]
        player_hits = []
        if "プレイヤー" in src and PLAYER_EN_RE.search(tgt):
            player_hits.append("Player")
        if not player_hits and not suspicious:
            continue
        rows.append(
            {
                "chapter_id": seg["_chapter_id"],
                "segment_id": sid,
                "english_tokens": sorted(set(player_hits + suspicious)),
                "source_ref": clip(src),
                "target_ref": clip(tgt),
                "recommended_action": "review_untranslated_or_overshifted_english",
            }
        )
    return rows


def _load_character_voice_profiles() -> list[dict[str, Any]]:
    cp_path = WORK_ROOT_PROFILE / "character_profile.yaml"
    doc = _read_yaml(cp_path)
    if not doc:
        doc = _read_yaml(TEMPLATE_PROFILE / "character_profile.yaml")
    return [c for c in (doc.get("characters") or []) if isinstance(c, dict)]


def _character_hit(character: dict[str, Any], text: str) -> bool:
    name = str(character.get("name") or "")
    if name and name in text:
        return True
    target = str(character.get("target_name") or "")
    if target and target in text:
        return True
    return any(a and str(a) in text for a in character.get("aliases") or [])


def _voice_markers(character: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    first_person = str(character.get("first_person") or "").strip()
    if first_person:
        markers.append(first_person)
    for tic in character.get("speech_tics") or []:
        t = str(tic or "").strip()
        if t:
            markers.append(t)
    return markers


def detect_voice_style_drift(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    characters = _load_character_voice_profiles()
    if not characters:
        return rows
    for sid, seg in segments.items():
        src = seg.get("source_text") or ""
        tgt = cn_text(seg)
        if not src or not tgt:
            continue
        if not _contains_dialogue_markup(src):
            continue
        char_hits = [c for c in characters if _character_hit(c, src)]
        if not char_hits:
            continue
        for char in char_hits:
            markers = _voice_markers(char)
            source_markers = [m for m in markers if m and m in src]
            if not source_markers:
                continue
            missing = [m for m in source_markers if m not in tgt]
            if not missing:
                continue
            rows.append(
                {
                    "chapter_id": seg["_chapter_id"],
                    "segment_id": sid,
                    "character": char.get("name"),
                    "character_target_name": char.get("target_name") or char.get("name"),
                    "source_markers": source_markers,
                    "missing_markers": missing,
                    "source_ref": clip(src),
                    "target_ref": clip(tgt),
                }
            )
    return rows


def build_registry_hints() -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    cp_path = REPO_ROOT / "workspace" / "configs" / "character_profile.yaml"
    if cp_path.is_file():
        cp = yaml.safe_load(cp_path.read_text(encoding="utf-8")) or {}
        for c in cp.get("characters", []) or []:
            source = strip_brackets(c.get("name") or "")
            target = strip_brackets(c.get("target_name") or "")
            if source and target:
                hints.append(
                    {
                        "kind": "character_profile",
                        "source": source,
                        "target": target,
                        "known_variants": [
                            v.strip() for v in (c.get("forbidden") or []) if v and v.strip()
                        ],
                    }
                )

    store = GlossaryStore(REPO_ROOT / "workspace" / "configs" / "glossary.yaml")
    for entry in store.entries():
        if not (entry.locked and entry.approved_by_user):
            continue
        source = strip_brackets(entry.source_term)
        target = strip_brackets(entry.target_term)
        if source and target:
            hints.append(
                {
                    "kind": entry.category or "glossary",
                    "source": source,
                    "target": target,
                    "known_variants": [
                        strip_brackets(v) for v in (entry.aliases or []) if v and strip_brackets(v)
                    ],
                }
            )
    return hints


def actual_kana_candidates(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for sid, seg in segments.items():
        src = seg.get("source_text") or ""
        tgt = cn_text(seg)
        for token in KATAKANA_TERM_RE.findall(src):
            bucket = buckets.setdefault(
                token,
                {
                    "source_token": token,
                    "count": 0,
                    "chapters": set(),
                    "samples": [],
                },
            )
            bucket["count"] += 1
            bucket["chapters"].add(seg["_chapter_id"])
            if len(bucket["samples"]) < 6:
                bucket["samples"].append(
                    {
                        "segment_id": sid,
                        "source_ref": clip(src, token),
                        "target_ref": clip(tgt),
                    }
                )
    out = []
    for bucket in buckets.values():
        row = dict(bucket)
        row["chapters"] = sorted(row["chapters"])
        out.append(row)
    out.sort(key=lambda r: (-r["count"], r["source_token"]))
    return out


def target_kana_residuals(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for sid, seg in segments.items():
        tgt = cn_text(seg)
        tokens = sorted(set(KANA_RUN_RE.findall(tgt)))
        if not tokens:
            continue
        if is_protected_literal_source_residual(seg.get("source_text") or "", tgt, tokens):
            continue
        rows.append(
            {
                "chapter_id": seg["_chapter_id"],
                "segment_id": sid,
                "kana_tokens": tokens,
                "source_ref": clip(seg.get("source_text") or ""),
                "target_ref": clip(tgt, tokens[0]),
            }
        )
    return rows


def target_placeholder_residuals(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for sid, seg in segments.items():
        tgt = cn_text(seg)
        tokens = sorted(set(PLACEHOLDER_RE.findall(tgt)))
        if not tokens:
            continue
        rows.append(
            {
                "chapter_id": seg["_chapter_id"],
                "segment_id": sid,
                "placeholder_tokens": tokens,
                "source_ref": clip(seg.get("source_text") or ""),
                "target_ref": clip(tgt, tokens[0]),
            }
        )
    return rows


VARIANT_PATTERNS = [
    re.compile(r"forbidden/alias「([^」]+)」"),
    re.compile(r"误译为「([^」]+)」"),
    re.compile(r"仍出现[^「]*「([^」]+)」"),
]
EXPECTED_TARGET_RE = re.compile(r"应译为「([^」]+)」")
RULE_TARGET_RE = re.compile(r"→「([^」]+)」")


def extract_variant(issue: dict[str, Any]) -> str:
    text = issue.get("description") or ""
    for pattern in VARIANT_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return ""


def revalidate_previous_issues(
    segments: dict[str, dict[str, Any]],
    previous_path: Path | None,
) -> dict[str, Any] | None:
    if not previous_path or not previous_path.is_file():
        return None
    issues = json.loads(previous_path.read_text(encoding="utf-8"))
    rows = []
    counts: Counter[str] = Counter()
    for issue in issues:
        sid = issue.get("segment_id") or ""
        seg = segments.get(sid)
        current = cn_text(seg) if seg else ""
        suggested = issue.get("suggested_fix") or ""
        variant = extract_variant(issue)
        expected_match = EXPECTED_TARGET_RE.search(issue.get("description") or "")
        expected_target = expected_match.group(1) if expected_match else ""
        rule_target_match = RULE_TARGET_RE.search(issue.get("description") or "")
        rule_target = rule_target_match.group(1) if rule_target_match else ""
        if not seg:
            status = "missing_current_segment"
        elif suggested and " ".join(current.split()) == " ".join(suggested.split()):
            status = "resolved_exact_suggested"
        elif expected_target and expected_target in current:
            status = "resolved_expected_target_present"
        elif expected_target and expected_target not in current:
            status = "still_open_expected_target_absent"
        elif rule_target and rule_target in current:
            status = "resolved_rule_target_present"
        elif variant and variant not in current:
            status = "resolved_variant_absent"
        elif variant and variant in current:
            status = "still_open_variant_present"
        else:
            status = "needs_manual_recheck"
        counts[status] += 1
        rows.append(
            {
                "issue_id": issue.get("issue_id"),
                "issue_type": issue.get("issue_type"),
                "chapter_id": issue.get("chapter_id"),
                "segment_id": sid,
                "previous_status": issue.get("status"),
                "current_status": status,
                "variant_checked": variant or None,
                "expected_target": expected_target or rule_target or None,
                "auto_fixable": issue.get("auto_fixable"),
                "description": issue.get("description"),
                "current_target_ref": clip(current, variant or expected_target or rule_target),
            }
        )
    return {"summary": dict(sorted(counts.items())), "issues": rows}


def registry_hint_observations(
    segments: dict[str, dict[str, Any]],
    hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for hint in hints:
        if is_registry_hint_noise(hint):
            continue
        source = hint["source"]
        target = hint["target"]
        variants = [v for v in hint.get("known_variants", []) if v and v != target]
        for sid, seg in segments.items():
            src = seg.get("source_text") or ""
            if not source_occurs_as_term(source, src):
                continue
            tgt = cn_text(seg)
            if is_allowed_contextual_hint(source, src, tgt):
                continue
            surfaces = []
            if target in tgt:
                surfaces.append(target)
            surfaces.extend(v for v in variants if v in tgt)
            if not surfaces:
                surfaces.append("UNOBSERVED_BY_HINTS")
            key = f"{hint['kind']}:{source}"
            row = observed.setdefault(
                key,
                {
                    "source": source,
                    "hint_target": target,
                    "hint_kind": hint["kind"],
                    "surface_counts": Counter(),
                    "samples": defaultdict(list),
                },
            )
            for surface in surfaces:
                row["surface_counts"][surface] += 1
                if len(row["samples"][surface]) < 5:
                    row["samples"][surface].append(
                        {
                            "segment_id": sid,
                            "source_ref": clip(src, source),
                            "target_ref": clip(tgt, surface if surface != "UNOBSERVED_BY_HINTS" else ""),
                        }
                    )

    out = []
    for row in observed.values():
        surfaces = dict(row["surface_counts"])
        if len(surfaces) == 1 and row["hint_target"] in surfaces:
            continue
        out.append(
            {
                "source": row["source"],
                "hint_target": row["hint_target"],
                "hint_kind": row["hint_kind"],
                "surface_counts": surfaces,
                "samples": {k: v for k, v in row["samples"].items()},
                "interpretation": "hint_only_not_authoritative",
            }
        )
    out.sort(key=lambda r: (-sum(r["surface_counts"].values()), r["source"]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", type=int, nargs=2, metavar=("START", "END"), required=True)
    parser.add_argument("--previous-issues", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    start, end = args.chapters
    segments = load_segments(start, end)
    previous = revalidate_previous_issues(segments, args.previous_issues)
    kana_residuals = target_kana_residuals(segments)
    punctuation_residuals = target_punctuation_residuals(segments)
    placeholder_residuals = target_placeholder_residuals(segments)
    english_residuals = target_english_residuals(segments)
    voice_residuals = detect_voice_style_drift(segments)
    kana_candidates = actual_kana_candidates(segments)
    registry_observations = registry_hint_observations(segments, build_registry_hints())
    style_rules = _load_style_punctuation_rules()

    report = {
        "schema": "actual_chapter_content_audit.v1",
        "generated_at": utc_now(),
        "chapter_range": [start, end],
        "method": "content_first_current_canonical_segments; glossary/profile are hints only",
        "segments_total": len(segments),
        "previous_issue_revalidation": previous,
        "target_kana_residuals": {
            "count": len(kana_residuals),
            "items": kana_residuals,
        },
        "target_placeholder_residuals": {
            "count": len(placeholder_residuals),
            "items": placeholder_residuals,
        },
        "target_english_residuals": {
            "count": len(english_residuals),
            "items": english_residuals,
        },
        "target_punctuation_residuals": {
            "count": len(punctuation_residuals),
            "items": punctuation_residuals,
        },
        "character_voice_style_residuals": {
            "count": len(voice_residuals),
            "items": voice_residuals,
        },
        "style_profile_snippet": {
            "count": len(style_rules),
            "items": style_rules[:50],
        },
        "source_katakana_candidates": {
            "unique_terms": len(kana_candidates),
            "top": kana_candidates[:80],
        },
        "registry_hint_observations": {
            "count": len(registry_observations),
            "items": registry_observations,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "chapter_range": [start, end],
                "segments_total": len(segments),
                "previous_issue_revalidation": previous["summary"] if previous else None,
                "target_kana_residuals": len(kana_residuals),
                "target_placeholder_residuals": len(placeholder_residuals),
                "target_english_residuals": len(english_residuals),
                "target_punctuation_residuals": len(punctuation_residuals),
                "character_voice_style_residuals": len(voice_residuals),
                "source_katakana_candidates": len(kana_candidates),
                "registry_hint_observations": len(registry_observations),
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
