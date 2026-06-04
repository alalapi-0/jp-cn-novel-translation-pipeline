"""HTTP handler for static frontend + /api workbench endpoints."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from workbench.project_registry import (
    get_active_project_id,
    get_project_manifest,
    list_project_manifests,
    seed_example_manifests,
    set_active_project_id,
)


def make_handler(repo_root: Path, frontend_root: Path) -> type[SimpleHTTPRequestHandler]:
    class WorkbenchHTTPRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(frontend_root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            if str(args[0]).startswith("GET /api/"):
                super().log_message(format, *args)

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api_get(parsed.path)
                return
            super().do_GET()

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/projects/active":
                try:
                    body = self._read_json_body()
                    project_id = str(body.get("project_id") or "").strip()
                    manifest = set_active_project_id(repo_root, project_id)
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "active_project_id": manifest.project_id,
                            "project": manifest.to_summary(),
                        },
                    )
                except KeyError as exc:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _handle_api_get(self, path: str) -> None:
            seed_example_manifests(repo_root)
            if path == "/api/projects":
                projects = [m.to_summary() for m in list_project_manifests(repo_root)]
                active = get_active_project_id(repo_root)
                self._send_json(
                    HTTPStatus.OK,
                    {"projects": projects, "active_project_id": active},
                )
                return
            if path == "/api/projects/active":
                active = get_active_project_id(repo_root)
                if not active:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "no manifests registered"})
                    return
                manifest = get_project_manifest(repo_root, active)
                if manifest is None:
                    self._send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": f"unknown active project: {active}"},
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "active_project_id": manifest.project_id,
                        "project": manifest.to_summary(),
                    },
                )
                return
            prefix = "/api/projects/"
            if path.startswith(prefix):
                rest = path[len(prefix) :]
                if rest.endswith("/workbench-data"):
                    project_id = rest[: -len("/workbench-data")].strip("/")
                    manifest = get_project_manifest(repo_root, project_id)
                    if manifest is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown project_id: {project_id}"},
                        )
                        return
                    self._send_json(HTTPStatus.OK, manifest.to_workbench_payload())
                    return
            self.send_error(HTTPStatus.NOT_FOUND)

    return WorkbenchHTTPRequestHandler


def serve(repo_root: Path, frontend_root: Path, *, host: str, port: int) -> None:
    handler_cls = make_handler(repo_root, frontend_root)
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"serving {frontend_root} + /api at http://{host}:{port}/")
    server.serve_forever()
