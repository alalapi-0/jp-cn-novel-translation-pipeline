from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from translation.evaluation_split import RISKS, authorize, build_split, key, source_features, validate_split
from translation.source_alignment import SourceDocument, text_hash


def chapters(count=24):
    rows = []
    for i in range(1, count + 1):
        text = f"# 合成 {i}\n\n彼女は「先生、もしドラゴンが来なかったら」と言った。{i}\n\nどきどき。"
        doc = SourceDocument(text, revision=text_hash(text), chapter_id=f"ch-{i:03d}")
        rows.append({"chapter_id": doc.chapter_id, "source_revision": doc.revision,
                     "language_direction": "JP_TO_CN", "path": f"input_jp/{i:03d}.md",
                     "features": source_features(doc)})
    return rows


def test_whole_chapters_are_disjoint_exhaustive_and_order_independent():
    rows = chapters()
    a = build_split(rows, seed="fixed source-only seed", group_size=4)
    b = build_split(list(reversed(rows)), seed="fixed source-only seed", group_size=4)
    assert a == b
    assert a["source_denominator"] == 24
    assert sum(a["partition_counts"].values()) == 24
    dev = {key(r) for r in a["chapters"] if r["partition"] == "development"}
    holdout = {key(r) for r in a["chapters"] if r["partition"] == "holdout"}
    assert dev and holdout and not dev & holdout
    assert dev | holdout == {key(r) for r in rows}
    for group in a["groups"]:
        assert len({r["partition"] for r in a["chapters"] if r["group_id"] == group["group_id"]}) == 1


def test_holdout_context_allowed_but_targets_feedback_and_unknowns_denied():
    split = build_split(chapters(), seed="test", group_size=4)
    dev = key(next(r for r in split["chapters"] if r["partition"] == "development"))
    held = key(next(r for r in split["chapters"] if r["partition"] == "holdout"))
    authorize(split, "source_context", [held, dev])
    authorize(split, "target", [dev])
    for resource, anchors in (("target", [held]), ("target", [dev, held]),
                              ("target", []), ("target", [(*dev[:2], "0" * 64)]),
                              ("feedback", [dev]), ("tm", [dev]), ("adjudication", [held])):
        with pytest.raises(PermissionError):
            authorize(split, resource, anchors)


def test_nine_coverage_gaps_stay_explicit_and_source_cues_are_only_candidates():
    split = build_split(chapters(), seed="test", group_size=4)
    for partition in ("development", "holdout"):
        cover = split["phenomenon_coverage"][partition]
        assert set(cover) == set(RISKS)
        assert not any(r["confirmed"] for r in cover.values())
        assert cover[RISKS[0]]["source_candidate_chapters"] > 0
        assert cover[RISKS[6]]["status"] == "missing_confirmed_examples"
        assert cover[RISKS[7]]["status"] == "missing_confirmed_examples"
        assert cover[RISKS[8]]["status"] == "missing_confirmed_examples"
    example = split["chapters"][0]["features"]
    assert example["cues"][RISKS[0]]["example_spans"]
    assert "unverified" in example["semantic_labels"]


def test_group_denominator_revision_and_policy_corruption_fail_closed():
    original = build_split(chapters(), seed="test", group_size=4)
    for change in (lambda s: s.update(source_denominator=23),
                   lambda s: s["policy"].update(holdout_release="allow"),
                   lambda s: s["groups"][0]["chapters"].append("ch-005"),
                   lambda s: s["chapters"][0].update(partition="bad")):
        bad = deepcopy(original); change(bad)
        with pytest.raises(ValueError): validate_split(bad)
    with pytest.raises(ValueError, match="at least two"):
        build_split(chapters(1), seed="test")
    with pytest.raises(ValueError, match="duplicate"):
        build_split(chapters() + chapters(1), seed="test")


def test_source_cue_coordinates_use_exact_unicode_revision():
    text = "# 合成\r\n\r\n  私は「こんにちは、先生」と言った。  \r\n"
    doc = SourceDocument(text, revision=text_hash(text), chapter_id="ch-001")
    features = source_features(doc)
    a, b = features["cues"][RISKS[0]]["example_spans"][0]
    assert text[a:b] == "私"
    assert features["codepoints"] == len(text)
    assert features["paragraphs"] == 1
