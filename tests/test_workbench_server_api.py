"""Tests for Workbench HTTP API (in-process handler)."""

from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.server import make_handler  # noqa: E402


@pytest.fixture()
def api_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    yield f"127.0.0.1:{port}"
    server.shutdown()


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
