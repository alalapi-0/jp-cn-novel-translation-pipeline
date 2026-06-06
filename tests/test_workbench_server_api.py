"""Tests for Workbench HTTP API (in-process handler)."""

from __future__ import annotations

import json
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


def test_review_state_patch(api_server: str) -> None:
    _post(
        api_server,
        "/api/projects",
        {"project_id": "review-state-test", "name": "RS", "language_direction": "JP_TO_CN"},
    )
    host, port = api_server.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    patch = json.dumps({"segments": {"seg-001": {"status": "approved"}}}).encode("utf-8")
    conn.request(
        "PATCH",
        "/api/projects/review-state-test/review-state",
        body=patch,
        headers={"Content-Type": "application/json"},
    )
    res = conn.getresponse()
    assert res.status == 200
    body = json.loads(res.read().decode("utf-8"))
    assert body["review_state"]["segments"]["seg-001"]["status"] == "approved"
    conn.close()

    code, loaded = _get(api_server, "/api/projects/review-state-test/review-state")
    assert code == 200
    assert loaded["review_state"]["segments"]["seg-001"]["status"] == "approved"


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
    host, port = api_server.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    patch = json.dumps(
        {
            "segments": {
                "seg-001": {"status": "approved"},
                "seg-002": {"status": "rejected"},
            }
        }
    ).encode("utf-8")
    conn.request(
        "PATCH",
        f"/api/projects/{project_id}/review-state",
        body=patch,
        headers={"Content-Type": "application/json"},
    )
    res = conn.getresponse()
    assert res.status == 200
    _ = res.read()
    conn.close()

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
    host, port = api_server.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    patch = json.dumps(
        {
            "segments": {
                "seg-001": {"status": "approved"},
                "seg-002": {"status": "rejected"},
            }
        }
    ).encode("utf-8")
    conn.request(
        "PATCH",
        f"/api/projects/{project_id}/review-state",
        body=patch,
        headers={"Content-Type": "application/json"},
    )
    res = conn.getresponse()
    assert res.status == 200
    _ = res.read()
    conn.close()

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


def test_translation_assets_external_api_reports_clear_error(api_server: str) -> None:
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
    host, port = api_server.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    patch = json.dumps({"segments": {"seg-001": {"status": "approved"}}}).encode("utf-8")
    conn.request(
        "PATCH",
        f"/api/projects/{project_id}/review-state",
        body=patch,
        headers={"Content-Type": "application/json"},
    )
    res = conn.getresponse()
    assert res.status == 200
    _ = res.read()
    conn.close()

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


def test_project_lifecycle_delete_requires_test_and_confirm(
    api_server: str,
) -> None:
    user_project = "lifecycle-user-delete-blocked"
    _post(
        api_server,
        "/api/projects",
        {"project_id": user_project, "name": "User", "language_direction": "JP_TO_CN"},
    )
    code, forbidden = _post(
        api_server,
        f"/api/projects/{user_project}/lifecycle",
        {"action": "delete", "confirm_delete": True, "confirm_phrase": f"DELETE {user_project}"},
    )
    assert code == 403
    assert "restricted to test projects" in forbidden["error"]

    test_project = "pw-lifecycle-delete-ok"
    _post(
        api_server,
        "/api/projects",
        {"project_id": test_project, "name": "Delete", "language_direction": "JP_TO_CN"},
    )
    _post(
        api_server,
        f"/api/projects/{test_project}/dry-run-generate",
        {"sample_text": "cleanup"},
    )
    _post(
        api_server,
        f"/api/projects/{test_project}/lifecycle",
        {"action": "retry"},
    )

    code, missing_confirm = _post(
        api_server,
        f"/api/projects/{test_project}/lifecycle",
        {"action": "delete"},
    )
    assert code == 400
    assert "confirm_delete" in missing_confirm["error"]

    code, wrong_phrase = _post(
        api_server,
        f"/api/projects/{test_project}/lifecycle",
        {"action": "delete", "confirm_delete": True, "confirm_phrase": "DELETE wrong"},
    )
    assert code == 400
    assert "confirm_phrase" in wrong_phrase["error"]

    code, deleted = _post(
        api_server,
        f"/api/projects/{test_project}/lifecycle",
        {
            "action": "delete",
            "confirm_delete": True,
            "confirm_phrase": f"DELETE {test_project}",
        },
    )
    assert code == 200
    assert deleted["deleted_project_id"] == test_project

    code, payload = _get(api_server, "/api/projects?include_test=true&include_history=true")
    assert code == 200
    ids = {p["project_id"] for p in payload["projects"]}
    assert test_project not in ids


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

