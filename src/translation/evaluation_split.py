"""Source-only grouped sampling and the development data-release policy.

Whole consecutive chapters are the grouping unit, not randomly split sentences.
Groups are a reproducible proxy for narrative sections; actual arc independence
and all semantic phenomenon labels remain unverified. No target is an oracle.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import re

SCHEMA = "optimization-development-holdout/1"
RISKS = (
    "subject_pronoun_object", "speaker_dialogue_monologue", "honorific_relationship",
    "negation_condition_cause_aspect", "polysemy_katakana_names",
    "wordplay_sound_culture", "foreshadow_perspective_revelation",
    "character_voice_rhythm", "long_omission_addition",
)
CUES = {
    RISKS[0]: r"彼女|彼|私|僕|俺|あなた|それ|あれ|誰",
    RISKS[1]: r"「|『|」|』",
    RISKS[2]: r"様|さん|くん|君|殿|閣下|陛下|先生|ございます|おっしゃ|なさ",
    RISKS[3]: r"ない|なかった|ません|ずに|もし|なら|ため|から|ので|たら|ている",
    RISKS[4]: r"[ァ-ヴー]{3,}",
    RISKS[5]: r"どきどき|ドキドキ|ふわふわ|フワフワ|わくわく|ワクワク|祭|神社|お辞儀",
}
POLICY = {
    "source_context": "all_pinned_source_chapters",
    "target": "development_only_with_exact_registered_lineage",
    "feedback_adjudication_knowledge_tm": "denied_until_separate_verified_lineage_adapter",
    "holdout_release": "not_implemented_in_development_reader",
    "unknown_lineage": "deny",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def key(row: dict) -> tuple[str, str, str]:
    return row["language_direction"], row["chapter_id"], row["source_revision"]


def source_features(document) -> dict:
    """Return source coordinates/counts only, never target or source text."""
    cues = {risk: {"count": 0, "example_spans": []} for risk in RISKS}
    lengths = []
    for paragraph in document.paragraphs:
        lengths.append(sum(b - a for a, b in paragraph["spans"]))
        for a, b in paragraph["spans"]:
            for risk, pattern in CUES.items():
                for match in re.finditer(pattern, document.text[a:b]):
                    entry = cues[risk]; entry["count"] += 1
                    if len(entry["example_spans"]) < 2:
                        entry["example_spans"].append([a + match.start(), a + match.end()])
    return {"paragraphs": len(lengths), "codepoints": len(document.text),
            "min_paragraph_codepoints": min(lengths, default=0),
            "max_paragraph_codepoints": max(lengths, default=0), "cues": cues,
            "semantic_labels": "unverified; lexical cues do not demonstrate the phenomenon"}


def build_split(chapters: list[dict], *, seed: str, group_size: int = 10) -> dict:
    if not seed or not isinstance(group_size, int) or not 1 <= group_size <= 100:
        raise ValueError("nonempty seed and bounded group size required")
    rows = deepcopy(chapters)
    identities = set(); paths = set()
    for row in rows:
        if (row.get("language_direction") not in {"JP_TO_CN", "CN_TO_JP"}
                or not re.fullmatch(r"ch-\d+", row.get("chapter_id", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", row.get("source_revision", ""))
                or not row.get("path") or not isinstance(row.get("features"), dict)):
            raise ValueError("invalid source-only chapter descriptor")
        identity = (row["language_direction"], row["chapter_id"])
        if identity in identities or row["path"] in paths:
            raise ValueError("duplicate chapter identity or source path")
        identities.add(identity); paths.add(row["path"])
    rows.sort(key=lambda r: (r["language_direction"], int(r["chapter_id"][3:])))
    groups = []
    for row in rows:
        number = int(row["chapter_id"][3:])
        if (not groups or groups[-1]["language_direction"] != row["language_direction"]
                or len(groups[-1]["chapters"]) == group_size
                or number != groups[-1]["last_chapter_number"] + 1):
            groups.append({"group_id": f"{row['language_direction']}:block:{number:04d}",
                           "language_direction": row["language_direction"], "chapters": [],
                           "first_chapter_number": number, "last_chapter_number": number})
        group = groups[-1]; group["last_chapter_number"] = number
        group["chapters"].append(row["chapter_id"]); row["group_id"] = group["group_id"]
    # One whole block per chronological stratum of five: approximately 20%.
    # Hash ranking avoids Python/global-RNG state and target-informed selection.
    for direction in sorted({r["language_direction"] for r in rows}):
        local = [g for g in groups if g["language_direction"] == direction]
        if len(local) < 2:
            raise ValueError("at least two chapter groups per direction required")
        for i in range(0, len(local), 5):
            stratum = local[i:i + 5]
            chosen = min(stratum, key=lambda g: digest([seed, direction, i, g["group_id"]]))
            for group in stratum:
                group.update(partition="holdout" if group is chosen else "development",
                             chronological_stratum=i // 5)
    by_group = {g["group_id"]: g for g in groups}
    for row in rows:
        row["partition"] = by_group[row["group_id"]]["partition"]
    samples = {}; coverage = {}
    for partition in ("development", "holdout"):
        local = [r for r in rows if r["partition"] == partition]
        representative = sorted(local, key=lambda r: digest([seed, "sample", *key(r)]))[:8]
        hard = {}; coverage[partition] = {}
        for risk in RISKS:
            hits = [r for r in local if r["features"]["cues"][risk]["count"] > 0]
            selected = sorted(hits, key=lambda r: (-r["features"]["cues"][risk]["count"],
                                                   digest([seed, risk, *key(r)])))[:2]
            hard[risk] = [list(key(r)) for r in selected]
            coverage[partition][risk] = {
                "source_candidate_chapters": len(hits), "confirmed": False,
                "status": "source_cues_only_unverified" if hits else "missing_confirmed_examples",
                "gap": "requires source-grounded semantic calibration; no target inspected",
            }
        samples[partition] = {"representative_random": [list(key(r)) for r in representative],
                              "difficult_source_cue_strata": hard,
                              "continuous_context_unit": "entire chapter group; neighboring source allowed"}
    result = {"schema": SCHEMA, "seed": seed, "group_size": group_size,
              "sampling": "sha256_ranked_one_whole_group_per_five_chronological_groups",
              "grouping": "consecutive chapter proxy; semantic narrative arcs and independence unverified",
              "source_denominator": len(rows), "chapters": rows, "groups": groups,
              "partition_counts": dict(Counter(r["partition"] for r in rows)),
              "samples": samples, "phenomenon_coverage": coverage, "policy": deepcopy(POLICY),
              "limitations": ["Single-work results do not establish cross-work generality.",
                              "Chapter groups can share a narrative arc; no independence/significance claim.",
                              "Lexical/rhythm cues do not establish semantic coverage; all nine need calibration.",
                              "Holdout targets/adjudications/feedback remain sealed for development."]}
    validate_split(result)
    return result


def validate_split(split: dict) -> None:
    if split.get("schema") != SCHEMA or split.get("policy") != POLICY:
        raise ValueError("unsupported split or altered release policy")
    rows = split.get("chapters", []); groups = split.get("groups", [])
    if not rows or len(rows) != split.get("source_denominator"):
        raise ValueError("source denominator changed")
    if len({key(r) for r in rows}) != len(rows):
        raise ValueError("duplicate pinned source identity")
    if (len({(r["language_direction"], r["chapter_id"]) for r in rows}) != len(rows)
            or len({r["path"] for r in rows}) != len(rows)):
        raise ValueError("duplicate chapter or source path")
    group_map = {g["group_id"]: g for g in groups}
    if len(group_map) != len(groups):
        raise ValueError("duplicate group identity")
    expected = set(); actual = set()
    for group in groups:
        if group["partition"] not in {"development", "holdout"} or not group["chapters"]:
            raise ValueError("invalid group partition")
        numbers = [int(c[3:]) for c in group["chapters"]]
        if (numbers != list(range(numbers[0], numbers[-1] + 1))
                or len(numbers) > split["group_size"]
                or numbers[0] != group["first_chapter_number"]
                or numbers[-1] != group["last_chapter_number"]):
            raise ValueError("chapter group is not a bounded consecutive source section")
        for chapter in group["chapters"]:
            identity = (group["language_direction"], chapter)
            if identity in expected:
                raise ValueError("overlapping chapter groups")
            expected.add(identity)
    for row in rows:
        group = group_map.get(row.get("group_id"))
        if (not group or row["partition"] != group["partition"]
                or row["language_direction"] != group["language_direction"]
                or row["chapter_id"] not in group["chapters"]):
            raise ValueError("source/group assignment changed")
        actual.add((row["language_direction"], row["chapter_id"]))
    counts = dict(Counter(r["partition"] for r in rows))
    if actual != expected or counts != split.get("partition_counts") or len(counts) != 2:
        raise ValueError("split omission, duplication or partition denominator changed")


def authorize(split: dict, resource: str, source_anchors: list[tuple[str, str, str]]) -> None:
    """Release check; actual readers derive lineage, callers cannot assert it."""
    if resource not in {"source_context", "target"}:
        raise PermissionError("feedback/derived knowledge require a separately verified lineage adapter")
    if not source_anchors:
        raise PermissionError("unknown source lineage")
    by_key = {key(r): r for r in split["chapters"]}
    for anchor in source_anchors:
        row = by_key.get(tuple(anchor))
        if not row:
            raise PermissionError("unknown or changed source revision")
        if resource == "target" and row["partition"] != "development":
            raise PermissionError("holdout target access is prohibited in development")
