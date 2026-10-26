"""Source geometry regressions; examples are synthetic and have no quality oracle."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from translation.source_alignment import SourceDocument, align_group, text_hash


def document(text):
    return SourceDocument(text, revision=text_hash(text), chapter_id="ch-synthetic")


def target(text="测试译文", identity="target-1"):
    return {"text": text, "segment_id": identity, "field": "draft_text"}


def test_unicode_crlf_coordinates_and_headers_are_preserved():
    text = "# 合成标题\r\n\r\n　彼は来た。\r\n\r\n彼女は去った。\r\n"
    doc = document(text); index = doc.to_index(); located = doc.locate("彼は来た。")
    assert len(index["paragraphs"]) == 2 and index["heading_spans"] == [[0, 6]]
    assert "".join(text[a:b] for a,b in located["spans"]) == "彼は来た。"
    assert located["status"] == "unique_exact_source"


def test_explicit_split_merge_and_many_to_many_are_legal():
    doc = document("第一句。\n\n第二句。")
    split = align_group(doc, ["第一句。"], [target("前半", "a"), target("后半", "b")])
    merge = align_group(doc, ["第一句。", "第二句。"], [target()])
    many = align_group(doc, ["第一句。", "第二句。"], [target(identity="a"), target(identity="b")])
    assert len(split["target_spans"]) == 2 and split["status"] == "located"
    assert len(merge["source_spans"]) == 2 and merge["status"] == "located"
    assert len(many["source_spans"]) == len(many["target_spans"]) == 2
    assert not any(x["automatic_acceptance"] for x in (split, merge, many))


def test_inserted_paragraph_preserves_content_anchor_but_invalidates_revision():
    old = document("第一句。\n\n第二句。")
    new = document("插入。\n\n第一句。\n\n第二句。")
    assert old.revision != new.revision
    assert old.paragraphs[1]["paragraph_id"] == new.paragraphs[2]["paragraph_id"]
    assert old.locate("第二句。")["spans"] != new.locate("第二句。")["spans"]


def test_same_length_edit_is_not_reused_and_unknown_is_not_semantic_omission():
    before = "彼は来た。"; after = "彼は去る。"
    assert len(before) == len(after)
    result = align_group(document(after), [before], [target()])
    assert result["status"] == "uncertain_source_alignment"
    assert result["source_locations"][0]["status"] == "unmatched_source_version_or_transform"
    assert result["semantic_coverage"] == "not_evaluated"


def test_repeated_source_and_overlapping_parts_do_not_force_alignment():
    assert document("同句。\n\n同句。").locate("同句。")["status"] == "ambiguous_repeated_source"
    result = align_group(document("唯一句。"), ["唯一句。", "唯一句。"], [target()])
    assert result["overlapping_source_parts"] and result["status"] == "uncertain_source_alignment"


def test_reordered_groups_retain_coordinates_and_empty_targets_remain_explicit():
    doc = document("第一句。\n\n第二句。")
    result = align_group(doc, ["第二句。", "第一句。"], [target()])
    assert result["source_parts_reordered"] and result["status"] == "located"
    assert align_group(doc, ["第一句。"], [target("")])["status"] == "empty_target"


def test_whitespace_equivalence_is_flagged_and_not_a_semantic_verdict():
    result = document("a b").locate("ab")
    assert result["status"] == "unique_layout_match_unverified"
    assert result["confidence"]["value"] is None


def test_heading_gap_produces_two_spans_instead_of_translating_heading():
    doc = document("第一句。\n# 小标题\n第二句。")
    loc = doc.locate("第一句。第二句。")
    assert len(loc["spans"]) == 2
    assert "小标题" not in "".join(doc.text[a:b] for a,b in loc["spans"])
