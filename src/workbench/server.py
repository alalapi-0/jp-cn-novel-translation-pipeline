"""HTTP handler for static frontend + /api workbench endpoints."""

from __future__ import annotations

import json
import traceback
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, parse_qs, urlparse

from workbench.api_status import build_api_status
from workbench.dry_run_generate import generate_segments_from_sample
from workbench.export_service import export_status, run_export
from workbench.project_id import InvalidProjectIdError, is_test_project_id, validate_project_id
from workbench.project_registry import (
    create_project_manifest,
    get_active_project_id,
    get_project_manifest,
    list_project_manifests,
    refresh_example_manifests,
    set_active_project_id,
    update_project_segments,
)
from workbench.review_state import get_project_review_state, patch_project_review_state


def _query_flag(parsed: ParseResult, name: str, *, default: bool = False) -> bool:
    raw = parse_qs(parsed.query).get(name, ["false" if not default else "true"])[0]
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def make_handler(repo_root: Path, frontend_root: Path) -> type[SimpleHTTPRequestHandler]:
    class WorkbenchHTTPRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(frontend_root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            if str(args[0]).startswith(("GET /api/", "POST /api/", "PUT /api/", "PATCH /api/")):
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

        def _bad_request(self, message: str) -> None:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": message})

        def _invalid_project_id(self, exc: InvalidProjectIdError) -> None:
            self._bad_request(str(exc))

        def _parse_project_id(self, raw: str) -> str:
            return validate_project_id(raw.strip("/"))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_get(parsed)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_post(parsed.path)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_put(parsed.path)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_patch(parsed.path)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _ensure_manifests(self) -> None:
            refresh_example_manifests(repo_root)
            if get_active_project_id(repo_root) is None:
                manifests = list_project_manifests(repo_root, include_test=True)
                if manifests:
                    set_active_project_id(repo_root, manifests[0].project_id)

        def _handle_api_get(self, parsed: ParseResult) -> None:
            path = parsed.path
            self._ensure_manifests()
            if path == "/api/runtime/api-status":
                self._send_json(HTTPStatus.OK, build_api_status(repo_root))
                return
            if path == "/api/export/status":
                self._send_json(HTTPStatus.OK, export_status(repo_root))
                return
            if path == "/api/projects":
                include_test = _query_flag(parsed, "include_test", default=False)
                projects = [
                    m.to_summary() for m in list_project_manifests(repo_root, include_test=include_test)
                ]
                active = get_active_project_id(repo_root)
                if not include_test and active and is_test_project_id(active):
                    visible = list_project_manifests(repo_root, include_test=False)
                    active = visible[0].project_id if visible else None
                self._send_json(
                    HTTPStatus.OK,
                    {"projects": projects, "active_project_id": active, "include_test": include_test},
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
                if rest.endswith("/review-state"):
                    project_id = self._parse_project_id(rest[: -len("/review-state")])
                    if get_project_manifest(repo_root, project_id) is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown project_id: {project_id}"},
                        )
                        return
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "project_id": project_id,
                            "review_state": get_project_review_state(repo_root, project_id),
                        },
                    )
                    return
                if rest.endswith("/workbench-data"):
                    project_id = self._parse_project_id(rest[: -len("/workbench-data")])
                    manifest = get_project_manifest(repo_root, project_id)
                    if manifest is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown project_id: {project_id}"},
                        )
                        return
                    self._send_json(HTTPStatus.OK, manifest.to_workbench_payload())
                    return
                if rest.endswith("/quality-review"):
                    project_id = self._parse_project_id(rest[: -len("/quality-review")])
                    manifest = get_project_manifest(repo_root, project_id)
                    if manifest is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown project_id: {project_id}"},
                        )
                        return
                    from quality_review.workbench_adapter import (  # noqa: WPS433
                        run_review_for_workbench,
                    )

                    report = run_review_for_workbench(
                        project_id=manifest.project_id,
                        language_direction=manifest.language_direction,
                        segments=list(manifest.segments),
                    )
                    self._send_json(HTTPStatus.OK, report.to_dict())
                    return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _handle_api_post(self, path: str) -> None:
            self._ensure_manifests()
            try:
                body = self._read_json_body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._bad_request(str(exc))
                return

            if path == "/api/projects":
                try:
                    manifest = create_project_manifest(
                        repo_root,
                        project_id=str(body.get("project_id") or ""),
                        name=str(body.get("name") or ""),
                        language_direction=str(
                            body.get("language_direction") or body.get("direction") or "JP_TO_CN"
                        ),
                        segments=body.get("segments") if isinstance(body.get("segments"), list) else [],
                    )
                    active_id = get_active_project_id(repo_root)
                    if not is_test_project_id(manifest.project_id):
                        set_active_project_id(repo_root, manifest.project_id)
                        active_id = manifest.project_id
                    self._send_json(
                        HTTPStatus.CREATED,
                        {"project": manifest.to_summary(), "active_project_id": active_id},
                    )
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except ValueError as exc:
                    self._bad_request(str(exc))
                return

            if path == "/api/export/run":
                source = str(body.get("source") or "manifest").strip().lower()
                if source not in {"manifest", "runs"}:
                    self._bad_request("source must be 'manifest' or 'runs'")
                    return
                try:
                    project_id: str | None = None
                    if source == "manifest":
                        project_id = validate_project_id(str(body.get("project_id") or ""))
                    result = run_export(
                        repo_root,
                        source=source,
                        project_id=project_id,
                        require_refined=bool(body.get("require_refined")),
                        overwrite=body.get("overwrite", True) is not False,
                    )
                    self._send_json(HTTPStatus.OK, result)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    self._bad_request(str(exc))
                return

            prefix = "/api/projects/"
            if path.startswith(prefix) and path.endswith("/dry-run-generate"):
                raw_id = path[len(prefix) : -len("/dry-run-generate")].strip("/")
                project_id = validate_project_id(raw_id)
                manifest = get_project_manifest(repo_root, project_id)
                if manifest is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown project_id: {project_id}"})
                    return
                sample_text = str(body.get("sample_text") or body.get("text") or "").strip()
                if not sample_text:
                    self._bad_request("sample_text is required")
                    return
                segments = generate_segments_from_sample(
                    sample_text=sample_text,
                    language_direction=manifest.language_direction,
                )
                updated = update_project_segments(
                    repo_root,
                    project_id,
                    segments,
                    status="review_pending",
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "project_id": project_id,
                        "segments_created": len(segments),
                        "project": updated.to_summary(),
                        "review_url": f"/review.html?project={project_id}",
                    },
                )
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def _handle_api_put(self, path: str) -> None:
            self._ensure_manifests()
            if path == "/api/projects/active":
                try:
                    body = self._read_json_body()
                    project_id = validate_project_id(str(body.get("project_id") or ""))
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
                except (ValueError, json.JSONDecodeError, InvalidProjectIdError) as exc:
                    self._bad_request(str(exc))
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _handle_api_patch(self, path: str) -> None:
            self._ensure_manifests()
            try:
                body = self._read_json_body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._bad_request(str(exc))
                return

            prefix = "/api/projects/"
            if path.startswith(prefix) and path.endswith("/review-state"):
                project_id = validate_project_id(path[len(prefix) : -len("/review-state")].strip("/"))
                if get_project_manifest(repo_root, project_id) is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown project_id: {project_id}"})
                    return
                segments = body.get("segments") if isinstance(body.get("segments"), dict) else None
                issues = body.get("issues") if isinstance(body.get("issues"), dict) else None
                if not segments and not issues:
                    self._bad_request("segments or issues patch required")
                    return
                review_state = patch_project_review_state(
                    repo_root,
                    project_id,
                    segments=segments,
                    issues=issues,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"project_id": project_id, "review_state": review_state},
                )
                return

            self.send_error(HTTPStatus.NOT_FOUND)

    return WorkbenchHTTPRequestHandler


def serve(repo_root: Path, frontend_root: Path, *, host: str, port: int) -> None:
    handler_cls = make_handler(repo_root, frontend_root)
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"serving {frontend_root} + /api at http://{host}:{port}/")
    server.serve_forever()
