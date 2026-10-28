"""Tests for FS-032: segment index builder.

Acceptance:
- missing / misalignment detection 100% recall on constructed fixtures;
- streaming build (metadata only, no body text in index);
- incremental rebuild reuses unchanged segment files;
- output path under workspace/indexes/ (gitignored).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.segment_index import (  # noqa: E402
    build_segment_index,
    index_summary,
    iter_chapter_scans,
    parse_segment_id,
    scan_segments_file,
)

SCRIPT = REPO_ROOT / "scripts" / "build_segment_index.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_segment_index_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_segment_index_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_completed_run(
    repo: Path,
    run_id: str,
    chapters: list[tuple[int, list[tuple[str, str, str]]]],
) -> Path:
    """chapters: [(num, [(segment_id, source, draft), ...]), ...]"""
    root = repo / "workspace" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "phase": "draft",
        "chapter_files": [f"input_jp/{num:03d}-sample.md" for num, _ in chapters],
    }
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    seg_doc = {"chapters": []}
    total_segments = 0
    for num, segs in chapters:
        segments = []
        for sid, source, draft in segs:
            segments.append(
                {
                    "segment_id": sid,
                    "source_text": source,
                    "draft_text": draft,
                    "status": "machine_translated",
                }
            )
        total_segments += len(segments)
        seg_doc["chapters"].append(
            {
                "chapter_id": f"ch-{num:03d}",
                "chapter_label": f"第{num}话",
                "source_path": f"input_jp/{num:03d}-sample.md",
                "segments": segments,
            }
        )
    seg_path = root / "segments.json"
    seg_path.write_text(json.dumps(seg_doc, ensure_ascii=False), encoding="utf-8")
    progress = {
        "run_id": run_id,
        "status": "completed",
        "total_segments": total_segments,
        "completed_segments": total_segments,
    }
    (root / "run_progress.json").write_text(json.dumps(progress), encoding="utf-8")
    return seg_path


def _assert_no_body_text(index: dict) -> None:
    blob = json.dumps(index, ensure_ascii=False)
    assert "source_text" not in blob
    assert "draft_text" not in blob
    assert "源文" not in blob
    assert "译文" not in blob


@pytest.fixture()
def clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_clean_draft_stage_b_50ch",
        [
            (
                1,
                [
                    ("ch-001-seg-001", "源文一", "译文一"),
                    ("ch-001-seg-002", "源文二", "译文二"),
                ],
            ),
            (2, [("ch-002-seg-001", "源文", "译文")]),
        ],
    )
    return repo


def test_parse_segment_id() -> None:
    assert parse_segment_id("ch-001-seg-003") == (1, 3)
    assert parse_segment_id("ch-1-seg-2") == (1, 2)
    assert parse_segment_id("bad-id") is None


def test_scan_metadata_only(clean_repo: Path) -> None:
    seg_path = clean_repo / "workspace" / "runs" / "run_clean_draft_stage_b_50ch" / "segments.json"
    bucket = scan_segments_file(seg_path, run_id="run_clean_draft_stage_b_50ch")
    assert bucket[1]["segments"]["ch-001-seg-001"]["source_length"] == 3
    assert bucket[1]["segments"]["ch-001-seg-001"]["draft_length"] == 3
    _assert_no_body_text(bucket)


def test_clean_index_pass(clean_repo: Path) -> None:
    index = build_segment_index(clean_repo)
    _assert_no_body_text(index)
    summary = index_summary(index)
    assert summary["status"] == "PASS"
    assert summary["segments_indexed"] == 3
    assert summary["missing_segments_count"] == 0
    assert summary["misalignment_count"] == 0
    assert index["segments"]["ch-001-seg-001"]["chapter_number"] == 1


def test_missing_segment_gap_recall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_gap_draft_stage_b_50ch",
        [
            (
                5,
                [
                    ("ch-005-seg-001", "a", "A"),
                    ("ch-005-seg-003", "c", "C"),
                ],
            ),
        ],
    )
    index = build_segment_index(repo)
    missing = index["issues"]["missing_segments"]
    assert len(missing) == 1
    assert missing[0]["segment_index"] == 2
    assert missing[0]["expected_segment_id"] == "ch-005-seg-002"
    assert index["chapters"]["ch-005"]["missing_segment_ids"] == ["ch-005-seg-002"]
    assert index_summary(index)["missing_segments_count"] == 1


def test_misalignment_chapter_mismatch_recall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_misalign_draft_stage_b_50ch",
        [
            (3, [("ch-004-seg-001", "x", "X")]),
        ],
    )
    index = build_segment_index(repo)
    mis = index["issues"]["misalignments"]
    assert any(m["issue_type"] == "chapter_mismatch" for m in mis)
    assert index_summary(index)["misalignment_count"] >= 1


def test_misalignment_duplicate_and_order_recall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_dup_draft_stage_b_50ch",
        [
            (
                7,
                [
                    ("ch-007-seg-001", "a", "A"),
                    ("ch-007-seg-001", "b", "B"),
                    ("ch-007-seg-004", "c", "C"),
                ],
            ),
        ],
    )
    index = build_segment_index(repo)
    types = {m["issue_type"] for m in index["issues"]["misalignments"]}
    assert "duplicate_segment_id" in types
    assert "index_order_mismatch" in types
    missing = index["issues"]["missing_segments"]
    assert {m["segment_index"] for m in missing} == {2, 3}


def test_duplicate_chapters_are_unresolved_and_keep_input_denominator(tmp_path: Path) -> None:
    from consistency.draft_structure_audit import _findings_from_segment_index
    repo=tmp_path/'repo'
    _write_completed_run(repo,'duplicate_chapters',[
        (1,[('ch-001-seg-001','synthetic first','first draft')]),
        (1,[('ch-001-seg-001','synthetic second','second draft')]),
        (1,[('ch-001-seg-001','synthetic third','third draft')]),
    ])
    index=build_segment_index(repo)
    assert index_summary(index)['status']=='WARN'
    assert index['chapters']['ch-001']['segment_count']==3
    assert index['chapters']['ch-001']['indexed_segment_count']==0
    assert index['stats']['selected_input_segments']==3
    assert index_summary(index)['selected_input_segments']==3
    assert 'ch-001-seg-001' not in index['segments']
    issue=next(x for x in index['issues']['misalignments'] if x['issue_type']=='duplicate_chapter_number')
    assert issue['occurrences']==3 and issue['input_segment_count']==3
    assert any(x['issue_subtype']=='duplicate_chapter_number' and x['blocking']
               for x in _findings_from_segment_index(index))
    _assert_no_body_text(index)


def test_duplicate_segment_id_is_not_selected_as_a_trusted_index_entry(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    _write_completed_run(repo,'duplicate_segment',[(1,[
        ('ch-001-seg-001','synthetic first','first draft'),
        ('ch-001-seg-001','synthetic second','second draft'),
        ('ch-001-seg-002','synthetic unique','unique draft'),
    ])])
    index=build_segment_index(repo)
    assert index_summary(index)['status']=='WARN'
    assert index['chapters']['ch-001']['segment_count']==3
    assert 'ch-001-seg-001' not in index['segments']
    assert 'ch-001-seg-002' in index['segments']


def test_duplicate_segment_id_across_chapters_is_not_selected(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    _write_completed_run(repo,'duplicate_across_chapters',[
        (1,[('ch-001-seg-001','synthetic first','first draft')]),
        (2,[('ch-001-seg-001','synthetic second','second draft')]),
        (3,[('ch-001-seg-001','synthetic third','third draft')]),
    ])
    index=build_segment_index(repo)
    assert index_summary(index)['status']=='WARN'
    assert 'ch-001-seg-001' not in index['segments']
    issue=next(x for x in index['issues']['misalignments'] if x['issue_type']=='duplicate_segment_across_chapters')
    assert issue['occurrences']==3 and index['stats']['selected_input_segments']==3
    assert all(x['indexed_segment_count']==0 for x in index['chapters'].values())


def test_duplicate_within_one_chapter_stays_ambiguous_in_other_chapters(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    _write_completed_run(repo,'mixed_duplicate',[
        (1,[('ch-001-seg-001','synthetic first','first draft'),
            ('ch-001-seg-001','synthetic second','second draft')]),
        (2,[('ch-001-seg-001','synthetic third','third draft'),
            ('ch-002-seg-002','synthetic unique','unique draft')]),
    ])
    index=build_segment_index(repo)
    assert 'ch-001-seg-001' not in index['segments']
    assert 'ch-002-seg-002' in index['segments']
    assert index['stats']['selected_input_segments']==4 and not index['stats']['clean']


def test_schema_three_index_is_rescanned_after_ambiguity_rule_change(clean_repo: Path) -> None:
    old=build_segment_index(clean_repo)
    old['schema_version']=3
    current=build_segment_index(clean_repo,previous_index=old)
    assert current['schema_version']!=3
    assert current['stats']['files_reused']==0
    assert current['stats']['files_scanned']==1


def test_summary_does_not_pass_obsolete_index_schema(clean_repo: Path) -> None:
    old=build_segment_index(clean_repo)
    old['schema_version']=3
    summary=index_summary(old)
    assert summary['status']=='WARN' and summary['schema_current'] is False


def test_unparseable_chapter_is_reported_and_its_denominator_preserved(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    path=_write_completed_run(repo,'unparseable_chapter',[(1,[
        ('ch-001-seg-001','synthetic source','synthetic draft')])])
    doc=json.loads(path.read_text(encoding='utf-8'));doc['chapters'][0]['chapter_id']='unknown'
    path.write_text(json.dumps(doc),encoding='utf-8')
    index=build_segment_index(repo)
    assert index_summary(index)['status']=='WARN'
    assert index['stats']['selected_input_segments']==0
    assert index['stats']['unresolved_input_segments']==1
    assert index['stats']['unparseable_chapters_count']==1
    assert index_summary(index)['unresolved_input_segments']==1
    assert index['stats']['segments_indexed']==0
    assert any(x['issue_type']=='unparseable_chapter_id' for x in index['issues']['misalignments'])
    reused=build_segment_index(repo,previous_index=index)
    assert reused['stats']['files_reused']==1
    assert reused['stats']['unresolved_input_segments']==1 and not reused['stats']['clean']
    with pytest.raises(ValueError):
        scan_segments_file(path,run_id='unparseable_chapter')
    _assert_no_body_text(index)


def test_unparseable_chapter_with_invalid_segment_collection_is_refused(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    path=_write_completed_run(repo,'invalid_segment_collection',[(1,[('ch-001-seg-001','synthetic','draft')])])
    doc=json.loads(path.read_text(encoding='utf-8'))
    doc['chapters'][0].update(chapter_id='unknown',segments={'not':'a segment list'})
    path.write_text(json.dumps(doc),encoding='utf-8')
    with pytest.raises(ValueError,match='segment list'):
        build_segment_index(repo)


def test_unparseable_chapter_identifier_does_not_leak_raw_value(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    path=_write_completed_run(repo,'unparseable_private_id',[(1,[('ch-001-seg-001','synthetic','draft')])])
    doc=json.loads(path.read_text(encoding='utf-8'))
    doc['chapters'][0]['chapter_id']='synthetic untrusted chapter payload'
    path.write_text(json.dumps(doc),encoding='utf-8')
    index=build_segment_index(repo)
    assert not index['stats']['clean']
    assert 'synthetic untrusted chapter payload' not in json.dumps(index,ensure_ascii=False)


def test_corrupted_cached_issue_cannot_turn_unparseable_input_into_pass(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    path=_write_completed_run(repo,'unparseable_cache',[(1,[('ch-001-seg-001','synthetic','draft')])])
    doc=json.loads(path.read_text(encoding='utf-8'));doc['chapters'][0]['chapter_id']='unknown'
    path.write_text(json.dumps(doc),encoding='utf-8')
    previous=build_segment_index(repo)
    previous['segment_files'][str(path)]['unresolved_inputs']=[]
    current=build_segment_index(repo,previous_index=previous)
    assert current['stats']['files_scanned']==1 and current['stats']['files_reused']==0
    assert current['stats']['unresolved_input_segments']==1 and not current['stats']['clean']


def test_unchanged_cache_reuses_after_json_round_trip(clean_repo: Path) -> None:
    from consistency.segment_index import index_shape_consistent
    previous=json.loads(json.dumps(build_segment_index(clean_repo)))
    assert index_shape_consistent(previous)
    current=build_segment_index(clean_repo,previous_index=previous)
    assert current['stats']['files_reused']==1 and current['stats']['files_scanned']==0
    assert current['stats']['clean'] and index_shape_consistent(current)


def test_index_content_identity_ignores_only_volatile_rebuild_details(clean_repo: Path) -> None:
    from consistency.segment_index import segment_index_digest
    first=build_segment_index(clean_repo)
    second=build_segment_index(clean_repo,previous_index=json.loads(json.dumps(first)))
    second['generated_at']='synthetic later time'
    assert segment_index_digest(first)==segment_index_digest(second)


def test_empty_chapter_is_not_reported_as_clean(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    _write_completed_run(repo,'empty_chapter',[(1,[('ch-001-seg-001','synthetic','draft')]),(2,[])])
    index=build_segment_index(repo)
    assert index_summary(index)['status']=='WARN'
    assert any(x['issue_type']=='empty_chapter' and x['chapter_id']=='ch-002'
               for x in index['issues']['misalignments'])
    assert index['stats']['selected_input_segments']==1


def test_cached_chapter_issue_cannot_be_removed_from_top_level(tmp_path: Path) -> None:
    from consistency.segment_index import index_shape_consistent
    repo=tmp_path/'repo'
    _write_completed_run(repo,'empty_cached_chapter',[(1,[('ch-001-seg-001','synthetic','draft')]),(2,[])])
    index=build_segment_index(repo)
    assert not index['stats']['clean']
    index['issues']['misalignments']=[]
    index['stats']['misalignment_count']=0;index['stats']['clean']=True
    assert not index_shape_consistent(index)
    assert index_summary(index)['status']=='WARN'


def test_top_level_segment_cannot_differ_from_cached_projection(clean_repo: Path) -> None:
    from consistency.segment_index import index_shape_consistent
    index=json.loads(json.dumps(build_segment_index(clean_repo)))
    index['segments']['ch-001-seg-001']['target_sha256']='0'*64
    assert not index_shape_consistent(index)
    assert index_summary(index)['status']=='WARN'


def test_file_order_is_required_and_controls_selected_chapter(tmp_path: Path) -> None:
    from consistency.segment_index import index_shape_consistent, segment_index_digest
    repo=tmp_path/'repo'
    first=_write_completed_run(repo,'first_run',[(1,[('ch-001-seg-001','first','first draft')])])
    second=_write_completed_run(repo,'second_run',[(1,[('ch-001-seg-001','second','second draft')])])
    os.utime(first,(1_600_000_000,1_600_000_000));os.utime(second,(1_600_000_001,1_600_000_001))
    index=json.loads(json.dumps(build_segment_index(repo)))
    assert index['file_order']==[str(first),str(second)] and index_shape_consistent(index)
    assert index['segments']['ch-001-seg-001']['source_run_id']=='second_run'
    tampered=json.loads(json.dumps(index));tampered['file_order'].reverse()
    assert segment_index_digest(tampered)!=segment_index_digest(index)
    assert not index_shape_consistent(tampered) and index_summary(tampered)['status']=='WARN'
    tampered['file_order']=[str(first),str(first)]
    assert not index_shape_consistent(tampered)
    tampered['file_order']=[]
    assert not index_shape_consistent(tampered)


def test_no_segment_files_is_not_reported_as_clean(tmp_path: Path) -> None:
    index=build_segment_index(tmp_path/'empty')
    assert index_summary(index)['status']=='WARN'
    assert any(x['issue_type']=='no_segment_files' for x in index['issues']['misalignments'])


def test_completed_run_without_chapters_is_not_reported_as_clean(tmp_path: Path) -> None:
    repo=tmp_path/'repo'
    path=_write_completed_run(repo,'missing_chapters',[(1,[('ch-001-seg-001','synthetic','draft')])])
    path.write_text(json.dumps({'chapters':[]}),encoding='utf-8')
    index=build_segment_index(repo)
    assert index_summary(index)['status']=='WARN'
    assert any(x['issue_type']=='no_chapters_in_file' for x in index['issues']['misalignments'])


def test_incremental_reuses_unchanged_files(clean_repo: Path) -> None:
    run_dirs = [clean_repo / "workspace" / "runs"]
    first = build_segment_index(clean_repo, run_dirs=run_dirs)
    assert first["stats"]["files_scanned"] >= 1
    second = build_segment_index(clean_repo, previous_index=first, run_dirs=run_dirs)
    assert second["stats"]["files_reused"] >= 1
    assert second["stats"]["files_scanned"] == 0


def test_streaming_iter_does_not_retain_text(clean_repo: Path) -> None:
    seg_path = clean_repo / "workspace" / "runs" / "run_clean_draft_stage_b_50ch" / "segments.json"
    buckets = list(iter_chapter_scans(seg_path, run_id="run_clean_draft_stage_b_50ch"))
    assert len(buckets) == 2
    for _, bucket in buckets:
        _assert_no_body_text(bucket)


def test_cli_json_and_output_path(clean_repo: Path, tmp_path: Path, capsys) -> None:
    mod = _load_script()
    out = tmp_path / "segment_index.json"
    cli_args = [
        "--repo-root",
        str(clean_repo),
        "--output",
        str(out),
        "--runs-dir",
        str(clean_repo / "workspace" / "runs"),
        "--json",
    ]
    rc = mod.main(cli_args)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["segments_indexed"] == 3
    saved = json.loads(out.read_text(encoding="utf-8"))
    _assert_no_body_text(saved)


def test_output_under_gitignored_indexes() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "workspace/indexes/" in gitignore
