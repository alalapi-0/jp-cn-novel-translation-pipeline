"""Tests for Workbench HTTP API (in-process handler)."""

from __future__ import annotations

import json
import hashlib
import sys
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.server import make_handler  # noqa: E402


@pytest.fixture()
def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "workspace").mkdir()
    examples = REPO_ROOT / "data" / "examples"
    for example in examples.glob("workbench_project.*.example.json"):
        target = tmp_path / "data" / "examples" / example.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    frontend = REPO_ROOT / "frontend"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    handler = make_handler(tmp_path, frontend)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"base": f"127.0.0.1:{port}", "repo_root": tmp_path}
    server.shutdown()


@pytest.fixture()
def api_server(api_env: dict[str, Path | str]) -> str:
    return str(api_env["base"])


@pytest.fixture()
def api_repo_root(api_env: dict[str, Path | str]) -> Path:
    root = api_env["repo_root"]
    assert isinstance(root, Path)
    return root


def _get(base: str, path: str) -> tuple[int, dict]:
    host, port = base.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    conn.request("GET", path)
    res = conn.getresponse()
    body = res.read().decode("utf-8")
    conn.close()
    return res.status, json.loads(body) if body else {}


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    host, port = base.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    data = json.dumps(payload).encode("utf-8")
    conn.request("POST", path, body=data, headers={"Content-Type": "application/json"})
    res = conn.getresponse()
    body = res.read().decode("utf-8")
    conn.close()
    return res.status, json.loads(body) if body else {}


def test_candidate_recovery_http_origin_confirmation_exact_fields_and_stale(api_env):
    from workbench.canonical_service import import_sources,import_candidates
    root=api_env['repo_root'];base=str(api_env['base'])
    state=import_sources(root,project_id='api-recovery',name='Synthetic',language_direction='JP_TO_CN',
        chapters=[{'filename':'003-synthetic.md','text':'# 章\n\n合成原文。'}])
    state=import_candidates(root,'api-recovery',expected_manifest_sha256=state['manifest_sha256'],
        source_inventory_sha256=state['source_inventory_sha256'],candidates=[{'segment_id':r['segment_id'],'target_text':'合成候选。'} for r in state['segments']])
    path=root/'workspace/manifests/api-recovery.json';raw=path.read_bytes()
    body={'expected_manifest_sha256':state['manifest_sha256'],'confirm_restore':True}
    def post(payload,origin):
        host,port=base.split(':');conn=HTTPConnection(host,int(port),timeout=10)
        headers={'Content-Type':'application/json'}
        if origin is not None:headers['Origin']=origin
        conn.request('POST','/api/projects/api-recovery/candidate-restore',body=json.dumps(payload),headers=headers)
        response=conn.getresponse();result=(response.status,json.loads(response.read()));conn.close();return result
    for origin in [None,'https://example.invalid','http://127.0.0.1:1']:
        assert post(body,origin)[0]==403 and path.read_bytes()==raw
    for forged in [{**body,'actor_type':'agent'},{**body,'snapshot_path':'../outside'},
                   {**body,'confirm_restore':False},{**body,'expected_manifest_sha256':'../outside'}]:
        assert post(forged,'http://'+base)[0]==400 and path.read_bytes()==raw
    status,result=post(body,'http://'+base)
    assert status==200 and result['action']=='restore_unreviewed_drafts' and not result['approval_issued']
    assert not result['selection']['can_select'] and result['selection']['segments_with_target']==0
    restored=path.read_bytes();assert post(body,'http://'+base)[0]==409 and path.read_bytes()==restored


def _patch(base: str, path: str, payload: dict, headers: dict | None = None) -> tuple[int, dict]:
    host, port = base.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    data = json.dumps(payload).encode("utf-8")
    conn.request("PATCH", path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
    res = conn.getresponse()
    body = res.read().decode("utf-8")
    conn.close()
    return res.status, json.loads(body) if body else {}


def _accept_as_agent(root: Path, project_id: str, segment_id: str, identity: str):
    # Trusted synthetic service setup; an HTTP request cannot supply this context.
    from workbench.project_registry import patch_project_review_state_cas
    from workbench.review_state import DecisionActor
    return patch_project_review_state_cas(root, project_id,
        decision_actor=DecisionActor("agent", "synthetic-test-agent"),
        segments={segment_id: {"status": "approved", "expected_identity": identity}})


def test_canonical_and_native_status_reads_do_not_enter_native_admission(api_server,monkeypatch):
    from workbench import native_agent
    def forbidden(*a,**k):raise AssertionError('native work on ordinary HTTP read')
    monkeypatch.setattr(native_agent,'_configuration_input',forbidden)
    monkeypatch.setattr(native_agent,'_metadata',forbidden)
    monkeypatch.setattr(native_agent.subprocess,'Popen',forbidden)
    pid='status-read-only'
    assert _post(api_server,'/api/projects',{'project_id':pid,'name':'Synthetic','language_direction':'JP_TO_CN'})[0]==201
    code,value=_get(api_server,f'/api/projects/{pid}/canonical-selection')
    assert code==200 and value['native_status']['admission']['attempts']==0
    code,value=_get(api_server,f'/api/projects/{pid}/native-agent-status')
    assert code==200 and value['admission']['attempts']==0


@pytest.mark.parametrize("kind", ["corrupt", "leaf_link", "hardlink", "unsupported"])
def test_review_unavailable_is_consistent_and_never_saves(api_env, monkeypatch, kind):
    import os
    from assets import translation_memory as memory
    from workbench import review_state
    base = str(api_env["base"])
    root = api_env["repo_root"]
    project = "review-unavailable"
    assert _post(base, "/api/projects", {"project_id": project, "name": "Synthetic",
        "language_direction": "JP_TO_CN"})[0] == 201
    manifest = root / "workspace" / "manifests" / f"{project}.json"
    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    leaf = root / "workspace" / "review_state.json"
    if kind == "corrupt":
        leaf.write_bytes(b"{ synthetic private fixture")
    elif kind == "unsupported":
        leaf.write_bytes(b'{"projects":{}}')
        monkeypatch.setattr(memory, "_open_at2", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("unsupported")))
    else:
        outside = root / "review-outside-fixture"
        outside.write_bytes(b'{"projects":{}}')
        target = outside.stat()
        if kind == "leaf_link": leaf.symlink_to(outside)
        else: os.link(outside, leaf)
        original_read = os.read
        def read(fd, count):
            current = os.fstat(fd)
            assert (current.st_dev, current.st_ino) != (target.st_dev, target.st_ino)
            return original_read(fd, count)
        monkeypatch.setattr(os, "read", read)
    saves = []
    monkeypatch.setattr(review_state, "save_review_state", lambda *_a, **_k: saves.append(True))
    responses = [
        _get(base, f"/api/projects/{project}/review-state"),
        _get(base, f"/api/projects/{project}/canonical-selection"),
        _patch(base, f"/api/projects/{project}/review-state", {"issues": {"i": {"status": "open"}}}),
        _post(base, f"/api/projects/{project}/canonical-export", {"expected_manifest_sha256": expected,
            "confirm_replace": True}),
    ]
    assert all(status == 503 for status, _ in responses)
    assert all(body == {"error": "review_state_unavailable", "message": "审核状态暂不可用；请检查后重试。"}
               for _, body in responses[:3])
    assert responses[3][1] == {"error": "review_state_unavailable", "message": "工作区或审核状态暂不可用，本次未写入。",
                              "effect_applied": False, "mutation_committed": False}
    assert str(root) not in json.dumps(responses)
    assert saves == []


@pytest.mark.parametrize("route", ["source-import", "candidate-import", "candidate-restore",
                                   "select-version", "canonical-export", "native-agent-job"])
def test_canonical_http_preflight_reports_no_effect(api_env, monkeypatch, route):
    import workbench.server as server
    base = str(api_env["base"]); root = api_env["repo_root"]; project = "preflight-http"
    assert _post(base, "/api/projects", {"project_id": project, "name": "Synthetic",
        "language_direction": "JP_TO_CN"})[0] == 201
    manifest = root / "workspace" / "manifests" / f"{project}.json"
    before = manifest.read_bytes(); digest = hashlib.sha256(before).hexdigest()
    (root / "workspace" / "review_state.json").write_bytes(b"{")
    calls=[]
    def forbidden(*_args, **_kwargs):
        calls.append(True); raise AssertionError("unexpected setup or write")
    monkeypatch.setattr(server, "refresh_example_manifests", forbidden)
    body = {"expected_manifest_sha256":digest,"confirm_restore":True,"confirm_replace":True,
            "action":"generate","request_id":"synthetic","project_id":"another-project",
            "language_direction":"JP_TO_CN","chapters":[{"filename":"001-test.md","text":"# synthetic\n\ntest"}]}
    if route == 'candidate-restore': body = {"expected_manifest_sha256":digest,"confirm_restore":True}
    if route == 'native-agent-job': body = {"expected_manifest_sha256":digest,"action":"generate","request_id":"synthetic"}
    path = "/api/source-import" if route == "source-import" else f"/api/projects/{project}/{route}"
    host, port = base.split(":"); conn = HTTPConnection(host, int(port), timeout=10)
    conn.request("POST",path,body=json.dumps(body),headers={"Content-Type":"application/json","Origin":"http://"+base})
    res=conn.getresponse(); status=res.status; payload=json.loads(res.read()); conn.close()
    if route == 'native-agent-job':
        assert status==503 and payload=={"error":"native_request_history_unknown",
            "message":"本次调用未执行；无法安全确认同一请求此前是否已完成，请勿自动重试，待安全回执能力具备后核查。",
            "invocation_effect_applied":False,"request_effect_status":"unknown","idempotent_replay":"unknown",
            "selection_status_available":False,"retry_operation":False}
    else:
        assert status==503 and payload=={"error":"review_state_unavailable",
            "message":"工作区或审核状态暂不可用，本次未写入。","effect_applied":False,"mutation_committed":False}
    assert manifest.read_bytes()==before and calls==[]
    assert not (root/'input_jp'/'another-project').exists()


def test_native_replay_http_reports_history_unknown_without_reading_job(api_env,monkeypatch):
    from workbench import generation_jobs, native_revision
    base=str(api_env['base']);root=api_env['repo_root'];project='native-replay-fixture'
    assert _post(base,'/api/projects',{'project_id':project,'name':'Synthetic','language_direction':'JP_TO_CN'})[0]==201
    digest='a'*64;job=root/'workspace/generation_jobs.json'
    job.write_text(json.dumps({'projects':{project:{'current':{'request_id':'prior','project_id':project,
        'status':'succeeded','response_payload':{'action':'generate','input_manifest_sha256':digest,
        'selection':{'segments':[{'source':'synthetic secret fixture'}]}}},'history':[]}}}))
    (root/'workspace/review_state.json').write_text('{')
    calls=[]
    def forbidden(*_a,**_k):calls.append(True);raise AssertionError('job history read')
    monkeypatch.setattr(generation_jobs,'find_generation_job',forbidden)
    monkeypatch.setattr(generation_jobs,'_load_state_unlocked',forbidden)
    monkeypatch.setattr(native_revision,'completed',forbidden)
    original_open=Path.open
    def guarded_open(path,*args,**kwargs):
        if path==job:return forbidden()
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded_open)
    host,port=base.split(':');conn=HTTPConnection(host,int(port),timeout=10)
    conn.request('POST',f'/api/projects/{project}/native-agent-job',body=json.dumps({
        'expected_manifest_sha256':digest,'action':'generate','request_id':'prior'}),
        headers={'Content-Type':'application/json','Origin':'http://'+base})
    res=conn.getresponse();status=res.status;payload=json.loads(res.read());conn.close()
    assert status==503 and payload['request_effect_status']=='unknown' and payload['idempotent_replay']=='unknown'
    assert payload['invocation_effect_applied'] is False and payload['retry_operation'] is False
    assert 'effect_applied' not in payload and 'mutation_committed' not in payload and 'selection' not in payload
    assert 'synthetic secret fixture' not in json.dumps(payload) and calls==[]


def test_http_actor_body_and_headers_cannot_grant_approval(api_server):
    project_id = "http-provenance-test"
    _post(api_server, "/api/projects", {"project_id": project_id, "name": "Provenance", "language_direction": "JP_TO_CN"})
    _post(api_server, f"/api/projects/{project_id}/dry-run-generate", {"sample_text": "風が吹く。"})
    identity = _segment_identity(api_server, project_id, "seg-001")
    code, body = _patch(api_server, f"/api/projects/{project_id}/review-state", {
        "decision_actor": {"actor_type": "agent", "actor_ref": "forged"},
        "segments": {"seg-001": {"status": "approved", "expected_identity": identity,
            "actor_type": "human", "human_reviewed": True, "human_approved_final": True,
            "decision_provenance": {"actor_type": "agent", "approval_identity": identity}}}},
        headers={"X-Review-Actor": "human", "X-Native-User": "unverified"})
    assert code == 200
    state = body["review_state"]; entry = state["segments"]["seg-001"]
    assert entry["decision_provenance"]["actor_type"] == "unknown"
    assert "human_reviewed" not in entry and "human_approved_final" not in entry
    decision = state["decision_summaries"]["seg-001"]
    assert decision["candidate_accepted"] is False and decision["human_approved_final"] is False
    code, loaded = _get(api_server, f"/api/projects/{project_id}/review-state")
    assert code == 200 and loaded["review_state"]["decision_summaries"] == state["decision_summaries"]
    for path, request in [("/api/export/run", {"source": "manifest", "project_id": project_id}),
                          ("/api/translation-assets/build", {"project_id": project_id})]:
        code, error = _post(api_server, path, request)
        assert code == 400 and "no approved" in error["error"]
    code, _ = _patch(api_server, f"/api/projects/{project_id}/review-state", {"segments": {
        "seg-001": {"status": "human_approved_final", "expected_identity": identity}}})
    assert code == 409


def test_quality_review_http_uses_frozen_input_scope(api_env):
    from workbench.project_registry import get_project_manifest, update_project_segments
    base = str(api_env["base"]); root = api_env["repo_root"]
    code, _ = _post(base, "/api/projects", {"project_id": "source-coverage-test", "name": "Source", "language_direction": "JP_TO_CN"})
    assert code == 201
    code, _ = _post(base, "/api/projects/source-coverage-test/dry-run-generate", {"sample_text": "風が吹く。\n\n雨が降る。"})
    assert code == 200
    original = get_project_manifest(root, "source-coverage-test")
    assert len(original.source_inventory["entries"]) == 2
    update_project_segments(root, original.project_id, [{**original.segments[0], "draft": "风吹过。"}])
    code, report = _get(base, "/api/projects/source-coverage-test/quality-review")
    assert code == 200 and report["review_status"] == "review_needed"
    assert report["summary"]["source_inventory_status"] == "pinned_source_import"
    assert report["summary"]["glossary_source"] == "none_no_project_glossary"
    assert any(i["segment_id"] == "seg-002" and i["evidence"].get("rule") == "missing_target_id" for i in report["issues"])


def _segment_identity(base: str, project_id: str, segment_id: str) -> str:
    code, payload = _get(base, f"/api/projects/{project_id}/workbench-data")
    assert code == 200
    segment = next(item for item in payload["segments"] if item["id"] == segment_id)
    identity = segment["approval_identity"]
    assert identity.startswith("sha256:")
    return identity


def test_api_status_missing_key(api_server: str) -> None:
    code, payload = _get(api_server, "/api/runtime/api-status")
    assert code == 200
    assert payload["api_mode"] == "missing_api_key"
    assert payload["has_api_key"] is False


def test_quickstart_create_and_dry_run(api_server: str) -> None:
    code, _created = _post(
        api_server,
        "/api/projects",
        {
            "project_id": "quickstart-test",
            "name": "Quickstart",
            "language_direction": "JP_TO_CN",
        },
    )
    assert code == 201
    code, gen = _post(
        api_server,
        "/api/projects/quickstart-test/dry-run-generate",
        {"sample_text": "Line one.\n\nLine two."},
    )
    assert code == 200
    assert gen["segments_created"] == 2


def test_workbench_api_projects_canonical_alias_text_for_approval(api_server: str) -> None:
    project_id = "projection-api-test"
    code, _ = _post(
        api_server,
        "/api/projects",
        {
            "project_id": project_id,
            "name": "Projection",
            "language_direction": "JP_TO_CN",
            "segments": [
                {
                    "segment_id": "seg-001",
                    "source": "   ",
                    "source_text": "  fallback source  ",
                    "draft_text": "  fallback target  ",
                    "target_text": "ignored target",
                }
            ],
        },
    )
    assert code == 201
    code, payload = _get(api_server, f"/api/projects/{project_id}/workbench-data")
    assert code == 200
    segment = payload["segments"][0]
    assert (segment["id"], segment["source"], segment["draft"]) == (
        "seg-001",
        "  fallback source  ",
        "  fallback target  ",
    )

    code, approved = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {
                    "status": "approved",
                    "expected_identity": segment["approval_identity"],
                }
            }
        },
    )
    assert code == 200
    assert (
        approved["review_state"]["segments"]["seg-001"]["approval_identity"]
        == segment["approval_identity"]
    )


def test_review_state_patch(api_server: str) -> None:
    _post(
        api_server,
        "/api/projects",
        {"project_id": "review-state-test", "name": "RS", "language_direction": "JP_TO_CN"},
    )
    _post(
        api_server,
        "/api/projects/review-state-test/dry-run-generate",
        {"sample_text": "Alpha"},
    )
    identity = _segment_identity(api_server, "review-state-test", "seg-001")
    code, body = _patch(
        api_server,
        "/api/projects/review-state-test/review-state",
        {"segments": {"seg-001": {"status": "approved", "expected_identity": identity}}},
    )
    assert code == 200
    assert body["review_state"]["segments"]["seg-001"]["status"] == "approved"
    assert body["review_state"]["segments"]["seg-001"]["approval_identity"] == identity

    code, loaded = _get(api_server, "/api/projects/review-state-test/review-state")
    assert code == 200
    assert loaded["review_state"]["segments"]["seg-001"]["status"] == "approved"


def test_approval_identity_cas_rejects_stale_content_without_partial_write(
    api_server: str,
    api_repo_root: Path,
) -> None:
    project_id = "pw-approval-cas"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "CAS", "language_direction": "JP_TO_CN"},
    )
    _post(
        api_server,
        f"/api/projects/{project_id}/dry-run-generate",
        {"sample_text": "Source A"},
    )
    identity_a = _segment_identity(api_server, project_id, "seg-001")
    code, _ = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {
                    "status": "approved",
                    "expected_identity": identity_a,
                    "note": "preserve me",
                }
            }
        },
    )
    assert code == 200

    _post(
        api_server,
        f"/api/projects/{project_id}/dry-run-generate",
        {"sample_text": "Source B"},
    )
    identity_b = _segment_identity(api_server, project_id, "seg-001")
    assert identity_b != identity_a

    code, stale = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {
                    "status": "approved",
                    "expected_identity": identity_a,
                    "note": "must not be written",
                }
            },
            "issues": {"issue-stale": {"status": "resolved"}},
        },
    )
    assert code == 409
    assert stale["error_code"] == "approval_identity_stale"
    assert stale["current_identity"] == identity_b

    code, state = _get(api_server, f"/api/projects/{project_id}/review-state")
    assert code == 200
    saved = state["review_state"]
    assert saved["segments"]["seg-001"]["approval_identity"] == identity_a
    assert saved["segments"]["seg-001"]["note"] == "preserve me"
    assert "issue-stale" not in saved["issues"]

    code, export_error = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": project_id},
    )
    assert code == 400
    assert "no approved segments" in export_error["error"]
    code, assets = _post(
        api_server,
        "/api/translation-assets/build",
        {"project_id": project_id},
    )
    assert code == 400
    assert "no approved translation pairs" in assets["error"]

    code, fresh = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {"status": "approved", "expected_identity": identity_b},
            }
        },
    )
    assert code == 200
    assert fresh["review_state"]["segments"]["seg-001"]["approval_identity"] == identity_b
    assert fresh["review_state"]["segments"]["seg-001"]["note"] == "preserve me"
    assert fresh["review_state"]["decision_summaries"]["seg-001"]["candidate_accepted"] is False
    code, error = _post(api_server, "/api/export/run", {"source": "manifest", "project_id": project_id})
    assert code == 400 and "no approved segments" in error["error"]
    _accept_as_agent(api_repo_root, project_id, "seg-001", identity_b)

    code, metadata = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {
                    "review_result": "PASS",
                    "note": "metadata update",
                    "reviewed_at": "2026-09-08T00:00:00Z",
                }
            }
        },
    )
    assert code == 200
    metadata_entry = metadata["review_state"]["segments"]["seg-001"]
    assert metadata_entry["status"] == "approved"
    assert metadata_entry["approval_identity"] == identity_b
    assert metadata_entry["review_result"] == "PASS"
    assert metadata_entry["note"] == "metadata update"

    code, exported = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": project_id},
    )
    assert code == 200
    assert exported["segments_exported"] == 1
    code, assets = _post(
        api_server,
        "/api/translation-assets/build",
        {"project_id": project_id},
    )
    assert code == 200
    assert assets["stats"]["pairs"] == 1

    code, stale_rejection = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {
                    "status": "rejected",
                    "expected_identity": identity_a,
                    "note": "stale rejection must not win",
                }
            },
            "issues": {"stale-rejection": {"status": "resolved"}},
        },
    )
    assert code == 409
    assert stale_rejection["error_code"] == "approval_identity_stale"
    code, state = _get(api_server, f"/api/projects/{project_id}/review-state")
    assert code == 200
    saved = state["review_state"]
    assert saved["segments"]["seg-001"]["status"] == "approved"
    assert saved["segments"]["seg-001"]["approval_identity"] == identity_b
    assert saved["segments"]["seg-001"]["note"] == "metadata update"
    assert "stale-rejection" not in saved["issues"]

    code, exported = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": project_id},
    )
    assert code == 200
    assert exported["segments_exported"] == 1
    code, assets = _post(
        api_server,
        "/api/translation-assets/build",
        {"project_id": project_id},
    )
    assert code == 200
    assert assets["stats"]["pairs"] == 1

    code, rejected = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {"status": "rejected", "expected_identity": identity_b},
            }
        },
    )
    assert code == 200
    rejected_entry = rejected["review_state"]["segments"]["seg-001"]
    assert rejected_entry["status"] == "rejected"
    assert rejected_entry["approval_identity"] == identity_b
    assert rejected_entry["note"] == "metadata update"
    code, export_error = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": project_id},
    )
    assert code == 400
    assert "no approved segments" in export_error["error"]
    code, assets_error = _post(
        api_server,
        "/api/translation-assets/build",
        {"project_id": project_id},
    )
    assert code == 400
    assert "no approved translation pairs" in assets_error["error"]


def test_approval_requires_valid_expected_identity(api_server: str) -> None:
    project_id = "pw-approval-required"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Required", "language_direction": "JP_TO_CN"},
    )
    _post(
        api_server,
        f"/api/projects/{project_id}/dry-run-generate",
        {"sample_text": "Source"},
    )
    code, missing = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {"segments": {"seg-001": {"status": "approved"}}},
    )
    assert code == 409
    assert missing["error_code"] == "approval_identity_required"
    code, invalid = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {"segments": {"seg-001": {"status": "approved", "expected_identity": "bad"}}},
    )
    assert code == 409
    assert invalid["error_code"] == "approval_identity_invalid"


def test_duplicate_segment_ids_return_actionable_conflict(
    api_server: str,
    api_repo_root: Path,
) -> None:
    manifest_dir = api_repo_root / "workspace" / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "duplicate-api.json").write_text(
        json.dumps(
            {
                "project_id": "duplicate-api",
                "name": "Duplicate",
                "language_direction": "JP_TO_CN",
                "segments": [
                    {"id": "seg-1", "source": "A", "draft": "甲"},
                    {"id": "seg-1", "source": "B", "draft": "乙"},
                ],
            }
        ),
        encoding="utf-8",
    )

    code, payload = _get(api_server, "/api/projects?include_test=true")
    assert code == 409
    assert payload["error_code"] == "duplicate_segment_id"
    assert "seg-1" in payload["error"]


def test_create_project_rejects_invalid_id(api_server: str) -> None:
    code, payload = _post(
        api_server,
        "/api/projects",
        {"project_id": "../bad", "name": "x", "language_direction": "JP_TO_CN"},
    )
    assert code == 400
    assert "error" in payload


def test_projects_list_hides_test_projects_by_default(api_server: str) -> None:
    _post(
        api_server,
        "/api/projects",
        {"project_id": "pw-hidden-api", "name": "Hidden", "language_direction": "JP_TO_CN"},
    )
    code, payload = _get(api_server, "/api/projects")
    assert code == 200
    ids = {p["project_id"] for p in payload["projects"]}
    assert "pw-hidden-api" not in ids
    assert payload["include_test"] is False
    assert payload["active_project_id"] != "pw-hidden-api"

    code, all_payload = _get(api_server, "/api/projects?include_test=true")
    all_ids = {p["project_id"] for p in all_payload["projects"]}
    assert "pw-hidden-api" in all_ids


def test_projects_list_hides_history_by_default(api_server: str) -> None:
    _post(
        api_server,
        "/api/projects",
        {"project_id": "round8-user-flow-test", "name": "History", "language_direction": "JP_TO_CN"},
    )
    code, payload = _get(api_server, "/api/projects")
    assert code == 200
    ids = {p["project_id"] for p in payload["projects"]}
    assert "round8-user-flow-test" not in ids
    code, all_payload = _get(api_server, "/api/projects?include_history=true")
    all_ids = {p["project_id"] for p in all_payload["projects"]}
    assert "round8-user-flow-test" in all_ids


def test_export_manifest_requires_existing_project(api_server: str) -> None:
    code, payload = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": "missing-export-target"},
    )
    assert code == 400
    assert "unknown project_id" in payload["error"]


def test_export_manifest_approved_only_uses_review_state(
    api_server: str,
    api_repo_root: Path,
) -> None:
    project_id = "pw-export-approved-only"
    code, _ = _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Export", "language_direction": "JP_TO_CN"},
    )
    assert code == 201
    code, _ = _post(
        api_server,
        f"/api/projects/{project_id}/dry-run-generate",
        {"sample_text": "Alpha line.\n\nBeta line."},
    )
    assert code == 200
    identity = _segment_identity(api_server, project_id, "seg-001")
    rejected_identity = _segment_identity(api_server, project_id, "seg-002")
    code, _ = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {"status": "approved", "expected_identity": identity},
                "seg-002": {
                    "status": "rejected",
                    "expected_identity": rejected_identity,
                },
            }
        },
    )
    assert code == 200

    _accept_as_agent(api_repo_root, project_id, "seg-001", identity)
    code, payload = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": project_id},
    )
    assert code == 200
    assert payload["status_mode"] == "approved"
    assert payload["segments_total"] == 2
    assert payload["segments_exported"] == 1
    assert payload["segments_skipped_status"]["rejected"] == 1
    translated_path = api_repo_root / payload["translated_path"]
    text = translated_path.read_text(encoding="utf-8")
    assert "Alpha line." in text
    assert "Beta line." not in text


def test_build_translation_assets_api_uses_approved_only(
    api_server: str,
    api_repo_root: Path,
) -> None:
    project_id = "pw-assets-approved-only"
    code, _ = _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Assets", "language_direction": "JP_TO_CN"},
    )
    assert code == 201
    code, _ = _post(
        api_server,
        f"/api/projects/{project_id}/dry-run-generate",
        {"sample_text": "アルファの森へ向かう。\n\n【レア】称号を獲得した。"},
    )
    assert code == 200
    identity = _segment_identity(api_server, project_id, "seg-001")
    rejected_identity = _segment_identity(api_server, project_id, "seg-002")
    code, _ = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {
            "segments": {
                "seg-001": {"status": "approved", "expected_identity": identity},
                "seg-002": {
                    "status": "rejected",
                    "expected_identity": rejected_identity,
                },
            }
        },
    )
    assert code == 200

    _accept_as_agent(api_repo_root, project_id, "seg-001", identity)
    code, payload = _post(
        api_server,
        "/api/translation-assets/build",
        {"project_id": project_id},
    )
    assert code == 200
    assert payload["mode"] == "agent"
    assert payload["stats"]["api_calls"] == 0
    assert payload["stats"]["pairs"] == 1
    asset_path = api_repo_root / payload["asset_path"]
    doc = json.loads(asset_path.read_text(encoding="utf-8"))
    assert "seg-001" in doc["segment_map"]
    assert "seg-002" not in doc["segment_map"]

    code, status = _get(api_server, f"/api/projects/{project_id}/translation-assets")
    assert code == 200
    assert status["exists"] is True
    assert status["stats"]["pairs"] == 1


def test_translation_assets_external_api_reports_clear_error(api_server: str, api_repo_root: Path) -> None:
    project_id = "pw-assets-external-blocked"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "External", "language_direction": "JP_TO_CN"},
    )
    _post(
        api_server,
        f"/api/projects/{project_id}/dry-run-generate",
        {"sample_text": "アルファ"},
    )
    identity = _segment_identity(api_server, project_id, "seg-001")
    code, _ = _patch(
        api_server,
        f"/api/projects/{project_id}/review-state",
        {"segments": {"seg-001": {"status": "approved", "expected_identity": identity}}},
    )
    assert code == 200

    _accept_as_agent(api_repo_root, project_id, "seg-001", identity)
    code, payload = _post(
        api_server,
        "/api/translation-assets/build",
        {"project_id": project_id, "mode": "external_api"},
    )
    assert code == 409
    assert payload["mode"] == "external_api"
    assert "external_api mode" in payload["error"]


def test_export_manifest_draft_requires_confirmation(api_server: str) -> None:
    project_id = "pw-export-draft-confirm"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Export", "language_direction": "JP_TO_CN"},
    )
    code, payload = _post(
        api_server,
        "/api/export/run",
        {"source": "manifest", "project_id": project_id, "status_mode": "draft"},
    )
    assert code == 400
    assert "confirm_draft" in payload["error"]


def test_real_api_generation_lock_single_execution(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workbench.server as server_mod

    project_id = "pw-lock-realgenerate"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Lock", "language_direction": "JP_TO_CN"},
    )
    calls = {"count": 0}

    def fake_generate(*, sample_text: str, language_direction: str, repo_root: Path):  # noqa: ARG001
        calls["count"] += 1
        time.sleep(0.25)
        return (
            [
                {
                    "id": "seg-001",
                    "segment_id": "seg-001",
                    "source": sample_text,
                    "draft": "stub",
                    "status": "pending",
                    "generated_by": "real_api",
                }
            ],
            {"provider": "stub", "model": "stub-model", "network_calls": 1},
        )

    monkeypatch.setattr(server_mod, "generate_segments_real_api", fake_generate)
    responses: list[tuple[int, dict]] = []

    def _call(req_id: str) -> None:
        responses.append(
            _post(
                api_server,
                f"/api/projects/{project_id}/real-api-generate",
                {"sample_text": "lock test", "request_id": req_id},
            )
        )

    t1 = threading.Thread(target=_call, args=("req-lock-1",))
    t2 = threading.Thread(target=_call, args=("req-lock-2",))
    t1.start()
    time.sleep(0.05)
    code, mid_job = _get(api_server, f"/api/projects/{project_id}/generation-job")
    assert code == 200
    assert mid_job["generation_job"]["status"] in {"queued", "running"}
    t2.start()
    t1.join()
    t2.join()
    codes = sorted(code for code, _payload in responses)
    assert codes == [200, 409]
    assert calls["count"] == 1
    conflict_payload = next(payload for code, payload in responses if code == 409)
    assert conflict_payload["error"] == "generation_in_progress"
    code, job_payload = _get(api_server, f"/api/projects/{project_id}/generation-job")
    assert code == 200
    assert job_payload["generation_job"]["status"] == "succeeded"


def test_real_api_generation_idempotent_request_replay(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workbench.server as server_mod

    project_id = "pw-idempotent-replay"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Replay", "language_direction": "JP_TO_CN"},
    )
    calls = {"count": 0}

    def fake_generate(*, sample_text: str, language_direction: str, repo_root: Path):  # noqa: ARG001
        calls["count"] += 1
        return (
            [
                {
                    "id": "seg-001",
                    "segment_id": "seg-001",
                    "source": sample_text,
                    "draft": "stub",
                    "status": "pending",
                }
            ],
            {"provider": "stub", "model": "stub-model", "network_calls": 1},
        )

    monkeypatch.setattr(server_mod, "generate_segments_real_api", fake_generate)
    request_id = "req-idempotent-1"
    code, first = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": "idempotent", "request_id": request_id},
    )
    assert code == 200
    code, second = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": "idempotent", "request_id": request_id},
    )
    assert code == 200
    assert second["idempotent_replay"] is True
    assert first["request_id"] == second["request_id"] == request_id
    assert calls["count"] == 1


def test_real_api_generation_maps_provider_errors(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workbench.server as server_mod

    project_id = "pw-provider-error-map"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "ErrMap", "language_direction": "JP_TO_CN"},
    )

    def fake_generate(*, sample_text: str, language_direction: str, repo_root: Path):  # noqa: ARG001
        raise RuntimeError("[openrouter] HTTP 429: rate limit exceeded")

    monkeypatch.setattr(server_mod, "generate_segments_real_api", fake_generate)
    code, payload = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": "error", "request_id": "req-error-map"},
    )
    assert code == 429
    assert payload["error_code"] == "rate_limited"
    assert "hint" in payload
    code, job_payload = _get(api_server, f"/api/projects/{project_id}/generation-job")
    assert code == 200
    assert job_payload["generation_job"]["status"] == "failed"
    assert job_payload["generation_job"]["error_code"] == "rate_limited"


def test_project_lifecycle_archive_and_retry(api_server: str) -> None:
    project_id = "pw-lifecycle-archive-retry"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Lifecycle", "language_direction": "JP_TO_CN"},
    )
    code, archived = _post(
        api_server,
        f"/api/projects/{project_id}/lifecycle",
        {"action": "archive"},
    )
    assert code == 200
    assert archived["project"]["status"] == "archived"
    code, retried = _post(
        api_server,
        f"/api/projects/{project_id}/lifecycle",
        {"action": "retry"},
    )
    assert code == 200
    assert retried["project"]["status"] == "draft_pending"
    code, job_payload = _get(api_server, f"/api/projects/{project_id}/generation-job")
    assert code == 200
    assert job_payload["generation_job"] is None


@pytest.mark.parametrize("kind", ["valid", "missing", "corrupt", "link", "unsupported", "concurrent"])
def test_project_deletion_is_unavailable_before_any_effect(api_env, monkeypatch, kind):
    from assets import translation_memory
    from workbench import generation_jobs, project_registry, review_state, server
    root = api_env["repo_root"]
    base = str(api_env["base"])
    project = "pw-deletion-preserved"
    assert _post(base, "/api/projects", {"project_id": project, "name": "Synthetic",
        "language_direction": "JP_TO_CN"})[0] == 201
    manifest = root / "workspace" / "manifests" / f"{project}.json"
    before = manifest.read_bytes()
    leaf = root / "workspace" / "review_state.json"
    if kind in {"valid", "concurrent", "unsupported"}: leaf.write_bytes(b'{"projects":{}}')
    if kind == "corrupt": leaf.write_bytes(b"{")
    if kind == "link":
        outside = root / "outside-fixture"
        outside.write_bytes(b'{"projects":{}}')
        leaf.symlink_to(outside)
    def tree_identity():
        return sorted((str(path.relative_to(root)), path.lstat().st_mode, path.lstat().st_size,
                       path.lstat().st_mtime_ns) for path in (root / "workspace").rglob("*"))
    tree_before = tree_identity()
    calls = []
    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("deletion reached a forbidden effect")
    monkeypatch.setattr(review_state, "load_review_state", forbidden)
    monkeypatch.setattr(review_state, "delete_project_review_state", forbidden)
    monkeypatch.setattr(review_state, "save_review_state", forbidden)
    monkeypatch.setattr(generation_jobs, "delete_project_generation_state", forbidden)
    monkeypatch.setattr(server, "refresh_example_manifests", forbidden)
    monkeypatch.setattr(translation_memory, "_open_at2", forbidden)
    original_unlink = Path.unlink
    def unlink(path, *args, **kwargs):
        if path.is_relative_to(root / "workspace"): return forbidden()
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    completed = []
    def direct():
        with pytest.raises(project_registry.TestProjectDeletionUnavailableError):
            project_registry.delete_test_project(root, project)
        completed.append(True)
    if kind == "concurrent":
        threads = [threading.Thread(target=direct) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
    else:
        direct()
    assert len(completed) == (2 if kind == "concurrent" else 1)
    expected = {"error": "测试项目删除暂不可用，项目及审核记录会保留",
                "error_code": "test_project_deletion_unavailable"}
    for payload in ({"action": "delete"}, {"action": "delete", "confirm_delete": True,
                                            "confirm_phrase": f"DELETE {project}"}):
        assert _post(base, f"/api/projects/{project}/lifecycle", payload) == (503, expected)
    assert manifest.read_bytes() == before
    assert tree_identity() == tree_before
    assert calls == []


def test_project_lifecycle_blocked_when_generation_running(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workbench.server as server_mod

    project_id = "pw-lifecycle-running-blocked"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Busy", "language_direction": "JP_TO_CN"},
    )

    def fake_split(*, sample_text: str, language_direction: str):  # noqa: ARG001
        time.sleep(0.25)
        return [
            {
                "id": "seg-001",
                "segment_id": "seg-001",
                "source": sample_text,
                "draft": "busy",
                "status": "pending",
            }
        ]

    monkeypatch.setattr(server_mod, "generate_segments_from_sample", fake_split)

    response_holder: list[tuple[int, dict]] = []

    def _generate():
        response_holder.append(
            _post(
                api_server,
                f"/api/projects/{project_id}/dry-run-generate",
                {"sample_text": "busy generation", "request_id": "req-busy"},
            )
        )

    t = threading.Thread(target=_generate)
    t.start()
    time.sleep(0.05)
    code, blocked = _post(
        api_server,
        f"/api/projects/{project_id}/lifecycle",
        {"action": "archive"},
    )
    t.join()
    assert code == 409
    assert blocked["error"] == "generation_in_progress"


def test_illegal_project_id_returns_chinese(api_server: str) -> None:
    code, payload = _post(
        api_server,
        "/api/projects",
        {"project_id": "../bad", "name": "x", "language_direction": "JP_TO_CN"},
    )
    assert code == 400
    assert "不能包含" in payload["error"]


def test_real_api_generate_blocked_without_key(api_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    project_id = "pw-real-blocked-no-key"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "NoKey", "language_direction": "JP_TO_CN"},
    )
    code, payload = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": "テスト", "request_id": "req-no-key"},
    )
    assert code == 400
    assert "real_api_unavailable" in payload["error"]


def test_real_api_generate_blocked_when_budget_zero(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("MAX_TEST_COST_USD", "0")
    project_id = "pw-real-blocked-budget"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Budget", "language_direction": "JP_TO_CN"},
    )
    code, payload = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": "テスト", "request_id": "req-budget"},
    )
    assert code == 400
    assert "max_test_cost_usd_zero" in payload["error"]


def test_real_api_generate_rejects_paragraph_too_long(api_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("MAX_TEST_COST_USD", "0.05")
    project_id = "pw-real-para-long"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Long", "language_direction": "JP_TO_CN"},
    )
    long_para = "あ" * 401
    code, payload = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": long_para, "request_id": "req-long"},
    )
    assert code == 400
    assert "paragraph too long" in payload["error"]


def test_real_api_generate_cost_guard_token_limit_not_success(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workbench.server as server_mod
    from providers.cost_guard import CostGuardError

    project_id = "pw-real-token-limit"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Token", "language_direction": "JP_TO_CN"},
    )

    def fake_generate(*, sample_text: str, language_direction: str, repo_root: Path):  # noqa: ARG001
        raise CostGuardError(
            "blocked",
            report={"reason": "max_tokens_per_run_exceeded", "projected_tokens": 999, "max_tokens_per_run": 10},
        )

    monkeypatch.setattr(server_mod, "generate_segments_real_api", fake_generate)
    code, payload = _post(
        api_server,
        f"/api/projects/{project_id}/real-api-generate",
        {"sample_text": "短文本", "request_id": "req-token-limit"},
    )
    assert code == 409
    assert payload["error"] == "max_tokens_per_run_exceeded"
    code, job_payload = _get(api_server, f"/api/projects/{project_id}/generation-job")
    assert code == 200
    assert job_payload["generation_job"]["status"] == "failed"


def test_dry_run_double_click_409_then_recovers(api_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import workbench.server as server_mod

    project_id = "pw-dry-409-recover"
    _post(
        api_server,
        "/api/projects",
        {"project_id": project_id, "name": "Recover", "language_direction": "JP_TO_CN"},
    )
    calls = {"count": 0}

    def fake_split(*, sample_text: str, language_direction: str):  # noqa: ARG001
        calls["count"] += 1
        time.sleep(0.2)
        return [
            {
                "id": "seg-001",
                "segment_id": "seg-001",
                "source": sample_text,
                "draft": "ok",
                "status": "pending",
            }
        ]

    monkeypatch.setattr(server_mod, "generate_segments_from_sample", fake_split)
    responses: list[tuple[int, dict]] = []

    def _call(req_id: str) -> None:
        responses.append(
            _post(
                api_server,
                f"/api/projects/{project_id}/dry-run-generate",
                {"sample_text": "double", "request_id": req_id},
            )
        )

    t1 = threading.Thread(target=_call, args=("req-recover-1",))
    t2 = threading.Thread(target=_call, args=("req-recover-2",))
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join()
    t2.join()
    codes = sorted(code for code, _payload in responses)
    assert codes == [200, 409]
    assert calls["count"] == 1
    code, job_payload = _get(api_server, f"/api/projects/{project_id}/generation-job")
    assert code == 200
    assert job_payload["generation_job"]["status"] == "succeeded"
