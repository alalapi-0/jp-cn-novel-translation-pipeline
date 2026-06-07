"""HTTP handler for static frontend + /api workbench endpoints."""

from __future__ import annotations

import json
import traceback
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, parse_qs, urlparse

from providers.cost_guard import CostGuardError
from workbench.api_status import build_api_status
from workbench.pipeline_status import (
    build_pipeline_status,
    list_production_runs,
    production_run_segments_for_review,
)
from workbench.dry_run_generate import generate_segments_from_sample
from workbench.error_mapper import map_provider_error
from workbench.real_api_generate import generate_segments_real_api
from workbench.export_service import export_status, run_export
from workbench.generation_jobs import (
    ACTIVE_JOB_STATUSES,
    GenerationInProgressError,
    find_generation_job,
    get_project_generation_job,
    mark_generation_failed,
    mark_generation_running,
    mark_generation_succeeded,
    prepare_generation_job,
    project_generation_lock,
)
from workbench.project_id import (
    InvalidProjectIdError,
    is_history_project_id,
    is_test_project_id,
    project_id_user_message,
    validate_project_id,
)
from workbench.project_registry import (
    ManifestWriteInProgressError,
    archive_project,
    create_project_manifest,
    delete_test_project,
    get_active_project_id,
    get_project_manifest,
    list_project_manifests,
    refresh_example_manifests,
    retry_project,
    set_active_project_id,
    update_project_segments,
)
from workbench.review_state import get_project_review_state, patch_project_review_state
from assets.translation_memory import (
    ExternalAssetExtractionUnavailable,
    build_translation_memory_assets,
)


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
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        @staticmethod
        def _client_gone(exc: BaseException) -> bool:
            if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                return True
            return isinstance(exc, OSError) and getattr(exc, "errno", None) in {32, 54, 104}

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
            self._bad_request(project_id_user_message(str(exc)))

        def _cost_guard_error(self, exc: CostGuardError) -> None:
            report = exc.report or {}
            reason = str(report.get("reason") or exc)
            self._send_json(
                HTTPStatus.CONFLICT,
                {
                    "error": reason,
                    "cost_guard": report,
                },
            )

        def _manifest_busy(self, exc: ManifestWriteInProgressError) -> None:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})

        def _parse_project_id(self, raw: str) -> str:
            return validate_project_id(raw.strip("/"))

        @staticmethod
        def _parse_request_id(raw: Any) -> str:
            request_id = str(raw or "").strip()
            if not request_id:
                request_id = uuid.uuid4().hex
            if len(request_id) > 96:
                raise ValueError("request_id too long (max 96 chars)")
            if any(ch.isspace() for ch in request_id):
                raise ValueError("request_id must not contain whitespace")
            return request_id

        def _send_generation_conflict(
            self,
            *,
            project_id: str,
            request_id: str,
            current_job: dict[str, Any] | None = None,
        ) -> None:
            self._send_json(
                HTTPStatus.CONFLICT,
                {
                    "error": "generation_in_progress",
                    "project_id": project_id,
                    "request_id": request_id,
                    "generation_job": current_job or get_project_generation_job(repo_root, project_id),
                },
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_get(parsed)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception as exc:  # noqa: BLE001
                    if not self._client_gone(exc):
                        traceback.print_exc()
                        self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                    return
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_post(parsed.path)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception as exc:  # noqa: BLE001
                    if not self._client_gone(exc):
                        traceback.print_exc()
                        self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                    return
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_put(parsed.path)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception as exc:  # noqa: BLE001
                    if not self._client_gone(exc):
                        traceback.print_exc()
                        self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                    return
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                try:
                    self._handle_api_patch(parsed.path)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except Exception as exc:  # noqa: BLE001
                    if not self._client_gone(exc):
                        traceback.print_exc()
                        self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
                    return
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
            if path == "/api/runtime/pipeline-status":
                self._send_json(HTTPStatus.OK, build_pipeline_status(repo_root))
                return
            if path == "/api/runtime/production-runs":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "runs": list_production_runs(repo_root),
                        "checked_at": build_pipeline_status(repo_root).get("checked_at"),
                    },
                )
                return
            if path.startswith("/api/runtime/production-runs/") and path.endswith("/segments"):
                run_id = path.removeprefix("/api/runtime/production-runs/").removesuffix("/segments")
                run_id = run_id.strip("/")
                if not run_id:
                    self._bad_request("run_id required")
                    return
                chapter_raw = parse_qs(parsed.query).get("chapter", [None])[0]
                chapter_filter = int(chapter_raw) if chapter_raw and str(chapter_raw).isdigit() else None
                try:
                    doc = production_run_segments_for_review(
                        repo_root, run_id=run_id, chapter=chapter_filter
                    )
                except FileNotFoundError as exc:
                    self._bad_request(str(exc))
                    return
                self._send_json(HTTPStatus.OK, doc)
                return
            if path == "/api/export/status":
                project_id = parse_qs(parsed.query).get("project_id", [None])[0]
                filter_pid = str(project_id).strip() if project_id else None
                if filter_pid:
                    try:
                        filter_pid = validate_project_id(filter_pid)
                    except InvalidProjectIdError:
                        filter_pid = None
                self._send_json(HTTPStatus.OK, export_status(repo_root, project_id=filter_pid))
                return
            if path == "/api/projects":
                include_test = _query_flag(parsed, "include_test", default=False)
                include_history = _query_flag(parsed, "include_history", default=False)
                projects = [
                    m.to_summary()
                    for m in list_project_manifests(
                        repo_root, include_test=include_test, include_history=include_history
                    )
                ]
                active = get_active_project_id(repo_root)
                if not include_test and active and is_test_project_id(active):
                    visible = list_project_manifests(
                        repo_root, include_test=False, include_history=include_history
                    )
                    active = visible[0].project_id if visible else None
                elif not include_history and active and is_history_project_id(active):
                    visible = list_project_manifests(
                        repo_root, include_test=include_test, include_history=False
                    )
                    active = visible[0].project_id if visible else None
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "projects": projects,
                        "active_project_id": active,
                        "include_test": include_test,
                        "include_history": include_history,
                    },
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
                if rest.endswith("/generation-job"):
                    project_id = self._parse_project_id(rest[: -len("/generation-job")])
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
                            "generation_job": get_project_generation_job(repo_root, project_id),
                        },
                    )
                    return
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
                if rest.endswith("/translation-assets"):
                    project_id = self._parse_project_id(rest[: -len("/translation-assets")])
                    if get_project_manifest(repo_root, project_id) is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown project_id: {project_id}"},
                        )
                        return
                    asset_path = (
                        repo_root
                        / "workspace"
                        / "assets"
                        / "translation_memory"
                        / f"{project_id}.json"
                    )
                    if not asset_path.is_file():
                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "project_id": project_id,
                                "exists": False,
                                "asset_path": str(asset_path.relative_to(repo_root)),
                            },
                        )
                        return
                    data = json.loads(asset_path.read_text(encoding="utf-8"))
                    stats = data.get("stats") if isinstance(data, dict) else {}
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "project_id": project_id,
                            "exists": True,
                            "asset_path": str(asset_path.relative_to(repo_root)),
                            "mode": data.get("mode"),
                            "status_mode": data.get("status_mode"),
                            "stats": stats if isinstance(stats, dict) else {},
                            "created_at": data.get("created_at"),
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
                    status_mode = str(body.get("status_mode") or body.get("mode") or "approved").strip().lower()
                    if source == "manifest":
                        project_id = validate_project_id(str(body.get("project_id") or ""))
                    run_id_filter = str(body.get("run_id") or "").strip() or None
                    result = run_export(
                        repo_root,
                        source=source,
                        project_id=project_id,
                        run_id=run_id_filter,
                        require_refined=bool(body.get("require_refined")),
                        overwrite=body.get("overwrite", True) is not False,
                        status_mode=status_mode,
                        confirm_draft=body.get("confirm_draft") is True,
                    )
                    self._send_json(HTTPStatus.OK, result)
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    self._bad_request(str(exc))
                return

            if path == "/api/translation-assets/build":
                try:
                    project_id = validate_project_id(str(body.get("project_id") or ""))
                    mode = str(body.get("mode") or "agent").strip().lower()
                    status_mode = str(body.get("status_mode") or "approved").strip().lower()
                    doc = build_translation_memory_assets(
                        repo_root=repo_root,
                        project_id=project_id,
                        mode=mode,  # type: ignore[arg-type]
                        status_mode=status_mode,  # type: ignore[arg-type]
                    )
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "project_id": project_id,
                            "asset_path": doc.get("asset_path_relative") or doc.get("asset_path"),
                            "mode": doc.get("mode"),
                            "status_mode": doc.get("status_mode"),
                            "stats": doc.get("stats", {}),
                            "created_at": doc.get("created_at"),
                        },
                    )
                except ExternalAssetExtractionUnavailable as exc:
                    self._send_json(HTTPStatus.CONFLICT, {"error": str(exc), "mode": "external_api"})
                except InvalidProjectIdError as exc:
                    self._invalid_project_id(exc)
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    self._bad_request(str(exc))
                return

            prefix = "/api/projects/"
            if path.startswith(prefix) and path.endswith("/lifecycle"):
                raw_id = path[len(prefix) : -len("/lifecycle")].strip("/")
                project_id = validate_project_id(raw_id)
                manifest = get_project_manifest(repo_root, project_id)
                if manifest is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown project_id: {project_id}"})
                    return
                action = str(body.get("action") or "").strip().lower()
                if action not in {"archive", "retry", "delete"}:
                    self._bad_request("action must be one of: archive, retry, delete")
                    return
                current_job = get_project_generation_job(repo_root, project_id)
                current_status = str((current_job or {}).get("status") or "").strip().lower()
                if current_status in ACTIVE_JOB_STATUSES:
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {
                            "error": "generation_in_progress",
                            "action": action,
                            "project_id": project_id,
                            "generation_job": current_job,
                        },
                    )
                    return
                try:
                    if action == "archive":
                        updated = archive_project(repo_root, project_id)
                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "action": action,
                                "project_id": project_id,
                                "project": updated.to_summary(),
                                "generation_job": current_job,
                            },
                        )
                        return
                    if action == "retry":
                        updated = retry_project(repo_root, project_id)
                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "action": action,
                                "project_id": project_id,
                                "project": updated.to_summary(),
                                "generation_job": get_project_generation_job(repo_root, project_id),
                            },
                        )
                        return

                    # delete
                    if body.get("confirm_delete") is not True:
                        self._bad_request("delete requires confirm_delete=true")
                        return
                    expected_phrase = f"DELETE {project_id}"
                    confirm_phrase = str(body.get("confirm_phrase") or "")
                    if confirm_phrase != expected_phrase:
                        self._bad_request(f"delete requires confirm_phrase exactly '{expected_phrase}'")
                        return
                    result = delete_test_project(repo_root, project_id)
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "action": action,
                            "project_id": project_id,
                            **result,
                        },
                    )
                except ManifestWriteInProgressError as exc:
                    self._manifest_busy(exc)
                except PermissionError as exc:
                    self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
                except KeyError as exc:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                except (ValueError, FileNotFoundError) as exc:
                    self._bad_request(str(exc))
                return

            if path.startswith(prefix) and (
                path.endswith("/dry-run-generate") or path.endswith("/real-api-generate")
            ):
                is_real_api = path.endswith("/real-api-generate")
                suffix = "/real-api-generate" if is_real_api else "/dry-run-generate"
                raw_id = path[len(prefix) : -len(suffix)].strip("/")
                project_id = validate_project_id(raw_id)
                manifest = get_project_manifest(repo_root, project_id)
                if manifest is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown project_id: {project_id}"})
                    return
                sample_text = str(body.get("sample_text") or body.get("text") or "").strip()
                if not sample_text:
                    self._bad_request("sample_text is required")
                    return
                try:
                    request_id = self._parse_request_id(body.get("request_id"))
                except ValueError as exc:
                    self._bad_request(str(exc))
                    return

                replay = find_generation_job(repo_root, project_id, request_id)
                if replay:
                    replay_status = str(replay.get("status") or "").strip().lower()
                    replay_payload = replay.get("response_payload")
                    if replay_status == "succeeded" and isinstance(replay_payload, dict):
                        payload = {**replay_payload, "idempotent_replay": True, "generation_job": replay}
                        self._send_json(HTTPStatus.OK, payload)
                        return
                    if replay_status in ACTIVE_JOB_STATUSES:
                        self._send_generation_conflict(
                            project_id=project_id,
                            request_id=request_id,
                            current_job=replay,
                        )
                        return

                generation_lock = project_generation_lock(project_id)
                if not generation_lock.acquire(blocking=False):
                    self._send_generation_conflict(project_id=project_id, request_id=request_id)
                    return
                try:
                    replay = find_generation_job(repo_root, project_id, request_id)
                    if replay:
                        replay_status = str(replay.get("status") or "").strip().lower()
                        replay_payload = replay.get("response_payload")
                        if replay_status == "succeeded" and isinstance(replay_payload, dict):
                            payload = {**replay_payload, "idempotent_replay": True, "generation_job": replay}
                            self._send_json(HTTPStatus.OK, payload)
                            return
                        if replay_status in ACTIVE_JOB_STATUSES:
                            self._send_generation_conflict(
                                project_id=project_id,
                                request_id=request_id,
                                current_job=replay,
                            )
                            return
                    try:
                        prepare_generation_job(
                            repo_root,
                            project_id,
                            request_id=request_id,
                            mode="real_api" if is_real_api else "dry_run",
                            sample_text=sample_text,
                        )
                    except GenerationInProgressError as exc:
                        self._send_generation_conflict(
                            project_id=project_id,
                            request_id=request_id,
                            current_job=exc.job,
                        )
                        return
                    mark_generation_running(repo_root, project_id, request_id)

                    if is_real_api:
                        try:
                            segments, gen_meta = generate_segments_real_api(
                                sample_text=sample_text,
                                language_direction=manifest.language_direction,
                                repo_root=repo_root,
                            )
                        except ValueError as exc:
                            mark_generation_failed(
                                repo_root,
                                project_id,
                                request_id,
                                error_code="invalid_request",
                                error_message=str(exc),
                            )
                            self._bad_request(str(exc))
                            return
                        except CostGuardError as exc:
                            report = exc.report or {}
                            reason = str(report.get("reason") or exc)
                            mark_generation_failed(
                                repo_root,
                                project_id,
                                request_id,
                                error_code="cost_guard_conflict",
                                error_message=reason,
                            )
                            self._cost_guard_error(exc)
                            return
                        except Exception as exc:  # noqa: BLE001
                            public = map_provider_error(exc)
                            mark_generation_failed(
                                repo_root,
                                project_id,
                                request_id,
                                error_code=public.code,
                                error_message=public.message,
                            )
                            self._send_json(
                                HTTPStatus(public.http_status),
                                {
                                    "error": public.code,
                                    "error_code": public.code,
                                    "message": public.message,
                                    "hint": public.hint,
                                    "request_id": request_id,
                                    "project_id": project_id,
                                    "generation_job": get_project_generation_job(repo_root, project_id),
                                },
                            )
                            return
                    else:
                        segments = generate_segments_from_sample(
                            sample_text=sample_text,
                            language_direction=manifest.language_direction,
                        )
                        gen_meta = None

                    try:
                        updated = update_project_segments(
                            repo_root,
                            project_id,
                            segments,
                            status="review_pending",
                        )
                    except ManifestWriteInProgressError as exc:
                        mark_generation_failed(
                            repo_root,
                            project_id,
                            request_id,
                            error_code="manifest_write_in_progress",
                            error_message=str(exc),
                        )
                        self._manifest_busy(exc)
                        return
                    payload: dict[str, Any] = {
                        "project_id": project_id,
                        "request_id": request_id,
                        "segments_created": len(segments),
                        "generation": "real_api" if is_real_api else "dry_run",
                        "project": updated.to_summary(),
                        "review_url": f"/review.html?project={project_id}",
                    }
                    if is_real_api:
                        payload["generation_meta"] = gen_meta
                    mark_generation_succeeded(
                        repo_root,
                        project_id,
                        request_id,
                        response_payload=payload,
                    )
                    payload["generation_job"] = get_project_generation_job(repo_root, project_id)
                    self._send_json(HTTPStatus.OK, payload)
                    return
                except Exception as exc:  # noqa: BLE001
                    mark_generation_failed(
                        repo_root,
                        project_id,
                        request_id,
                        error_code="generation_failed",
                        error_message=str(exc),
                    )
                    raise
                finally:
                    generation_lock.release()

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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nserve_frontend: stopped")
    finally:
        server.shutdown()
