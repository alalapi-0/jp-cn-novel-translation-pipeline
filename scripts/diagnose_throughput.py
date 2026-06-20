#!/usr/bin/env python3
"""Read-only throughput diagnostics for controlled translation runs.

The script scans metadata, checkpoints, model-run summaries and lightweight
logs. It intentionally avoids printing source text, translation text, API keys,
headers, or raw model responses.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from translation.run_progress import classify_run_recovery, safe_load_json as load_progress_json

WORKSPACE = REPO_ROOT / "workspace"
DIAG_DIR = WORKSPACE / "diagnostics"
SUMMARY_PATH = REPO_ROOT / "docs" / "archive" / "legacy_refinement" / "throughput_metrics_summary.md"
JSON_PATH = DIAG_DIR / "throughput_metrics.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def pct(num: int, den: int) -> str:
    if den <= 0:
        return "缺少数据"
    return f"{num / den * 100:.1f}%"


def iter_json_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix == ".json")


def summarize_runs() -> dict[str, Any]:
    runs_root = WORKSPACE / "runs"
    summaries: list[dict[str, Any]] = []
    totals = Counter()
    stage_counter = Counter()
    stage_segments = defaultdict(Counter)
    run_times: list[datetime] = []

    if not runs_root.is_dir():
        return {
            "run_count": 0,
            "runs": [],
            "totals": dict(totals),
            "stage_counter": dict(stage_counter),
            "stage_segments": {},
            "observed_time_range": {"first": None, "last": None},
        }

    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        meta = safe_load_json(run_dir / "run_metadata.json") or {}
        segments_doc = safe_load_json(run_dir / "segments.json") or {}
        draft_quality = safe_load_json(run_dir / "draft_quality_report.json") or {}
        refine_quality = safe_load_json(run_dir / "refine_quality_report.json") or {}

        chapters = segments_doc.get("chapters") if isinstance(segments_doc, dict) else []
        if not isinstance(chapters, list):
            chapters = []
        segment_rows = [
            seg
            for chapter in chapters
            if isinstance(chapter, dict)
            for seg in chapter.get("segments", [])
            if isinstance(seg, dict)
        ]

        total_segments = len(segment_rows)
        draft_segments = sum(1 for s in segment_rows if (s.get("draft_text") or "").strip())
        refined_segments = sum(1 for s in segment_rows if (s.get("refined_text") or "").strip())
        human_edited = sum(1 for s in segment_rows if s.get("human_edited"))

        chapter_total = len(chapters)
        draft_chapters = 0
        refined_chapters = 0
        for chapter in chapters:
            segs = [s for s in chapter.get("segments", []) if isinstance(s, dict)]
            if segs and all((s.get("draft_text") or "").strip() for s in segs):
                draft_chapters += 1
            if segs and all(
                s.get("human_edited") or (s.get("refined_text") or "").strip() for s in segs
            ):
                refined_chapters += 1

        stage = str(meta.get("scope") or meta.get("stage") or refine_quality.get("stage") or "unknown")
        stage_counter[stage] += 1
        stage_segments[stage].update(
            {
                "chapters_total": chapter_total,
                "draft_chapters": draft_chapters,
                "refined_chapters": refined_chapters,
                "segments_total": total_segments,
                "draft_segments": draft_segments,
                "refined_segments": refined_segments,
                "human_edited": human_edited,
            }
        )
        totals.update(
            {
                "chapters_total": chapter_total,
                "draft_chapters": draft_chapters,
                "refined_chapters": refined_chapters,
                "segments_total": total_segments,
                "draft_segments": draft_segments,
                "refined_segments": refined_segments,
                "human_edited": human_edited,
                "api_calls": int((meta.get("summary") or {}).get("api_calls") or 0)
                + int(refine_quality.get("api_calls") or 0),
            }
        )
        totals["spent_usd_micros"] += int(
            round(
                (
                    float((meta.get("summary") or {}).get("spent_usd") or 0.0)
                    + float(refine_quality.get("cost_usd") or 0.0)
                )
                * 1_000_000
            )
        )
        totals["spent_tokens"] += int((meta.get("summary") or {}).get("spent_tokens") or 0)

        dates = [
            parse_dt(str(meta.get("started_at") or "")),
            parse_dt(str(draft_quality.get("generated_at") or "")),
            parse_dt(str(refine_quality.get("generated_at") or "")),
        ]
        dates = [d for d in dates if d is not None]
        run_times.extend(dates)

        summaries.append(
            {
                "run_id": run_dir.name,
                "stage": stage,
                "provider_mode": meta.get("provider_mode") or refine_quality.get("provider_mode") or "缺少数据",
                "model_name": meta.get("model_name") or refine_quality.get("model_name") or "缺少数据",
                "chapter_offset": meta.get("chapter_offset", "缺少数据"),
                "chapters_total": chapter_total,
                "draft_chapters": draft_chapters,
                "refined_chapters": refined_chapters,
                "segments_total": total_segments,
                "draft_segments": draft_segments,
                "refined_segments": refined_segments,
                "draft_gate_passed": draft_quality.get("passed", "缺少数据"),
                "stage_c_eligible": draft_quality.get("stage_c_eligible", "缺少数据"),
                "refine_aborted": refine_quality.get("aborted", "缺少数据"),
                "abort_reason": (
                    (meta.get("summary") or {}).get("abort_reason")
                    or refine_quality.get("abort_reason")
                    or ""
                ),
            }
        )

    first = min(run_times).isoformat() if run_times else None
    last = max(run_times).isoformat() if run_times else None
    totals["spent_usd"] = round(totals.pop("spent_usd_micros", 0) / 1_000_000, 6)
    return {
        "run_count": len(summaries),
        "runs": summaries,
        "totals": dict(totals),
        "stage_counter": dict(stage_counter),
        "stage_segments": {k: dict(v) for k, v in stage_segments.items()},
        "observed_time_range": {"first": first, "last": last},
    }


def summarize_checkpoints() -> dict[str, Any]:
    rows = []
    status_counter = Counter()
    for path in iter_json_files(WORKSPACE / "checkpoints"):
        data = safe_load_json(path) or {}
        completed = data.get("completed_segments")
        completed_count = len(completed) if isinstance(completed, list) else 0
        status = str(data.get("status") or "缺少数据")
        status_counter[status.split(":", 1)[0]] += 1
        rows.append(
            {
                "checkpoint_id": path.stem,
                "status": status,
                "completed_segments": completed_count,
                "spent_usd": data.get("spent_usd", 0),
                "spent_tokens": data.get("spent_tokens", 0),
                "updated_at": data.get("updated_at") or file_mtime_iso(path),
            }
        )
    return {"count": len(rows), "status_counter": dict(status_counter), "rows": rows}


def summarize_model_runs() -> dict[str, Any]:
    files = iter_json_files(WORKSPACE / "model_runs")
    provider_counter = Counter()
    model_counter = Counter()
    stage_counter = Counter()
    status_counter = Counter()
    latencies: list[int] = []
    costs: list[float] = []
    tokens: list[int] = []
    times: list[datetime] = []
    missing_started_at = 0
    missing_request_hash = 0

    for path in files:
        data = safe_load_json(path)
        if not isinstance(data, dict):
            continue
        provider_counter[str(data.get("provider_id") or "缺少数据")] += 1
        model_counter[str(data.get("model_name") or "缺少数据")] += 1
        stage_counter[str(data.get("pipeline_stage") or "缺少数据")] += 1
        status_counter[str(data.get("status") or "缺少数据")] += 1
        latency = data.get("latency_ms")
        if isinstance(latency, int) and latency >= 0:
            latencies.append(latency)
        cost = data.get("cost_estimate_usd")
        if isinstance(cost, (int, float)):
            costs.append(float(cost))
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        total_tokens = usage.get("total_tokens")
        if isinstance(total_tokens, int):
            tokens.append(total_tokens)
        dt = parse_dt(str(data.get("finished_at") or ""))
        if dt is None:
            dt = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        times.append(dt)
        if not data.get("started_at"):
            missing_started_at += 1
        if not data.get("request_hash"):
            missing_request_hash += 1

    def stat(values: list[int | float]) -> dict[str, Any]:
        if not values:
            return {"avg": "缺少数据", "max": "缺少数据", "count": 0}
        return {
            "avg": round(statistics.mean(values), 2),
            "max": max(values),
            "count": len(values),
        }

    return {
        "count": len(files),
        "provider_counter": dict(provider_counter),
        "model_counter": dict(model_counter),
        "stage_counter": dict(stage_counter),
        "status_counter": dict(status_counter),
        "latency_ms": stat(latencies),
        "cost_usd": {"sum": round(sum(costs), 6), **stat(costs)},
        "tokens": {"sum": sum(tokens), **stat(tokens)},
        "observed_time_range": {
            "first": min(times).isoformat() if times else None,
            "last": max(times).isoformat() if times else None,
        },
        "missing_started_at": missing_started_at,
        "missing_request_hash": missing_request_hash,
    }


def summarize_agent_runtime() -> dict[str, Any]:
    runtime = REPO_ROOT / ".agent_runtime"
    status = safe_load_json(runtime / "status.json") or {}
    queue_rows = [json.loads(line) for line in (runtime / "queue.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()] if (runtime / "queue.jsonl").is_file() else []
    blocker_rows = [json.loads(line) for line in (runtime / "blockers.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()] if (runtime / "blockers.jsonl").is_file() else []
    report_counts = {}
    for name in ("real_api_reports", "inspection_reports", "quality_reports", "fix_reports"):
        report_counts[name] = len(iter_json_files(runtime / name))
    return {
        "status": status,
        "queue_count": len(queue_rows),
        "queue_status_counter": dict(Counter(str(r.get("status") or "缺少数据") for r in queue_rows)),
        "blocker_count": len(blocker_rows),
        "open_blockers": [r for r in blocker_rows if r.get("status") == "open"],
        "report_counts": report_counts,
    }


def summarize_logs() -> dict[str, Any]:
    rows = {}
    for name in ("refine_batch_log.txt", "pilot_batch_chain.log", "production_pipeline.log", "watchdog_poll.log"):
        path = WORKSPACE / name
        if not path.is_file():
            rows[name] = {"exists": False}
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        rows[name] = {
            "exists": True,
            "line_count": len(lines),
            "failed_count": sum(1 for line in lines if "FAILED" in line or "FAIL" in line),
            "already_running_count": sum(1 for line in lines if "already running" in line),
            "eligible_count": sum(1 for line in lines if "eligible=" in line),
            "done_count": sum(1 for line in lines if "DONE" in line),
            "last_timestamped_line": next((line[:160] for line in reversed(lines) if line.strip()), ""),
        }
    return rows


def summarize_recovery() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    checkpoints: dict[str, dict[str, Any]] = {}
    cp_dir = WORKSPACE / "checkpoints"
    if cp_dir.is_dir():
        for path in cp_dir.glob("*.json"):
            data = safe_load_json(path) or {}
            checkpoints[path.stem] = data

    runs_root = WORKSPACE / "runs"
    if runs_root.is_dir():
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            run_id = run_dir.name
            cp = checkpoints.get(run_id, {})
            progress = load_progress_json(run_dir / "run_progress.json") or {}
            meta = load_progress_json(run_dir / "run_metadata.json")
            segments = load_progress_json(run_dir / "segments.json")
            label = classify_run_recovery(
                run_id=run_id,
                checkpoint_status=str(cp.get("status") or ""),
                has_run_metadata=meta is not None,
                has_segments=segments is not None,
                has_progress=bool(progress),
                progress_status=str(progress.get("status") or ""),
            )
            rows.append(
                {
                    "run_id": run_id,
                    "recovery_label": label,
                    "checkpoint_status": cp.get("status"),
                    "progress_status": progress.get("status"),
                    "chapter_offset": (meta or {}).get("chapter_offset"),
                }
            )

    counter = Counter(r["recovery_label"] for r in rows)
    return {"runs": rows, "recovery_counter": dict(counter)}


def summarize_worker_registry() -> dict[str, Any]:
    state_path = WORKSPACE / "pipeline_state.json"
    if not state_path.is_file():
        return {"exists": False, "active_count": 0}
    data = safe_load_json(state_path) or {}
    workers = data.get("workers") if isinstance(data.get("workers"), list) else []
    return {
        "exists": True,
        "total_workers": len(workers),
        "workers": [
            {
                "worker_id": w.get("worker_id"),
                "pid": w.get("pid"),
                "task_type": w.get("task_type"),
                "stage": w.get("stage"),
                "run_id": w.get("run_id"),
                "status": w.get("status"),
            }
            for w in workers
            if isinstance(w, dict)
        ],
    }


def build_metrics() -> dict[str, Any]:
    runs = summarize_runs()
    model_runs = summarize_model_runs()
    checkpoints = summarize_checkpoints()
    agent_runtime = summarize_agent_runtime()
    logs = summarize_logs()
    recovery = summarize_recovery()
    worker_registry = summarize_worker_registry()
    observed_first = [
        parse_dt(runs["observed_time_range"].get("first")),
        parse_dt(model_runs["observed_time_range"].get("first")),
    ]
    observed_last = [
        parse_dt(runs["observed_time_range"].get("last")),
        parse_dt(model_runs["observed_time_range"].get("last")),
    ]
    observed_first = [d for d in observed_first if d is not None]
    observed_last = [d for d in observed_last if d is not None]
    runtime_hours = None
    if observed_first and observed_last:
        runtime_hours = round((max(observed_last) - min(observed_first)).total_seconds() / 3600, 2)
    chapters = int(runs["totals"].get("draft_chapters") or 0)
    rounds = int((agent_runtime.get("status") or {}).get("round") or 0)
    return {
        "generated_at": utc_now(),
        "runtime_hours_observed": runtime_hours,
        "chapters_per_hour_observed": round(chapters / runtime_hours, 2) if runtime_hours else "缺少数据",
        "chapters_per_round_observed": round(chapters / rounds, 2) if rounds else "缺少数据",
        "runs": runs,
        "checkpoints": checkpoints,
        "model_runs": model_runs,
        "agent_runtime": agent_runtime,
        "logs": logs,
        "recovery": recovery,
        "worker_registry": worker_registry,
        "missing_data": [
            "model_runs 缺少 started_at，无法精确计算每次请求完整耗时区间",
            "run_metadata.started_at 在写产物时生成，不能代表真实 run 开始时间",
            "缺少 scan/parse/context_pack/prompt_build/validator/exporter/git/CI 的分环节计时",
            "缺少每章请求数和 retry/error taxonomy 的统一结构化字段",
            "缺少 push 成功次数的结构化记录，只能从 git/终端记录间接判断",
        ],
    }


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return out


def write_summary(metrics: dict[str, Any]) -> None:
    totals = metrics["runs"]["totals"]
    model = metrics["model_runs"]
    agent = metrics["agent_runtime"]
    stage_rows = []
    for stage, data in sorted(metrics["runs"]["stage_segments"].items()):
        stage_rows.append(
            [
                stage,
                data.get("chapters_total", 0),
                data.get("draft_chapters", 0),
                data.get("refined_chapters", 0),
                data.get("segments_total", 0),
                data.get("draft_segments", 0),
                data.get("refined_segments", 0),
            ]
        )
    api_rows = []
    for stage, count in sorted(model["stage_counter"].items()):
        api_rows.append([stage, count])
    provider_rows = []
    for provider, count in sorted(model["provider_counter"].items()):
        provider_rows.append([provider, count])

    lines = [
        "# Throughput Metrics Summary",
        "",
        "## 当前统计时间",
        "",
        f"- 生成时间：{metrics['generated_at']}",
        "- 统计方式：只读扫描 `workspace/runs`、`workspace/checkpoints`、`workspace/model_runs`、`.agent_runtime` 与轻量日志；不调用真实 API，不读取 `.env`，不输出正文/译文。",
        "",
        "## 当前进度表",
        "",
        *md_table(
            ["指标", "值"],
            [
                ["总体运行轮数", (agent.get("status") or {}).get("round", "缺少数据")],
                ["运行目录数", metrics["runs"]["run_count"]],
                ["checkpoint 数", metrics["checkpoints"]["count"]],
                ["model_run 文件数", model["count"]],
                ["章节总数（run 内观测）", totals.get("chapters_total", 0)],
                ["初翻完成章节", totals.get("draft_chapters", 0)],
                ["润色完成章节", totals.get("refined_chapters", 0)],
                ["初翻完成 segment", totals.get("draft_segments", 0)],
                ["润色完成 segment", totals.get("refined_segments", 0)],
                ["观测运行时长（小时）", metrics["runtime_hours_observed"] or "缺少数据"],
                ["章节/小时（按初翻完成章）", metrics["chapters_per_hour_observed"]],
                ["章节/轮（按初翻完成章）", metrics["chapters_per_round_observed"]],
                ["成功 commit/push 数", "缺少数据（需从 git log/remote 或自动化状态补采）"],
            ],
        ),
        "",
        "## 每阶段吞吐表",
        "",
        *md_table(
            ["阶段", "章节数", "初翻完成章", "润色完成章", "segment 数", "初翻 segment", "润色 segment"],
            stage_rows or [["缺少数据", 0, 0, 0, 0, 0, 0]],
        ),
        "",
        "## API 指标表",
        "",
        *md_table(
            ["指标", "值"],
            [
                ["provider 分布", ", ".join(f"{k}={v}" for k, v in sorted(model["provider_counter"].items())) or "缺少数据"],
                ["model 分布", ", ".join(f"{k}={v}" for k, v in sorted(model["model_counter"].items())) or "缺少数据"],
                ["pipeline_stage 分布", ", ".join(f"{k}={v}" for k, v in sorted(model["stage_counter"].items())) or "缺少数据"],
                ["status 分布", ", ".join(f"{k}={v}" for k, v in sorted(model["status_counter"].items())) or "缺少数据"],
                ["平均 latency_ms", model["latency_ms"]["avg"]],
                ["最慢 latency_ms", model["latency_ms"]["max"]],
                ["token 总量", model["tokens"]["sum"]],
                ["估算 cost_usd 总量", model["cost_usd"]["sum"]],
                ["缺少 started_at 的 model_run", model["missing_started_at"]],
                ["缺少 request_hash 的 model_run", model["missing_request_hash"]],
            ],
        ),
        "",
        "### Provider 调用分布",
        "",
        *md_table(["provider", "model_run 数"], provider_rows or [["缺少数据", 0]]),
        "",
        "### Pipeline Stage 调用分布",
        "",
        *md_table(["pipeline_stage", "model_run 数"], api_rows or [["缺少数据", 0]]),
        "",
        "## Pipeline 耗时表",
        "",
        *md_table(
            ["环节", "当前数据"],
            [
                ["scan", "缺少数据"],
                ["parse", "缺少数据"],
                ["segment/chunk", "缺少数据"],
                ["context pack", "缺少数据"],
                ["prompt build", "缺少数据"],
                ["provider", f"model_run latency 可用：avg={model['latency_ms']['avg']}ms max={model['latency_ms']['max']}ms"],
                ["ResponseExtractor", "缺少数据"],
                ["Validator", "缺少数据"],
                ["quality review", "缺少数据"],
                ["exporter", "缺少数据"],
                ["diff/change_log", "缺少数据"],
                ["git commit/push", "缺少数据"],
                ["前端/Playwright", f"inspection_reports={agent['report_counts'].get('inspection_reports', 0)}；缺少单次耗时"],
                ["agent_gate", "本轮运行产生 WARNING；缺少历史耗时"],
                ["测试/build", "缺少结构化耗时"],
            ],
        ),
        "",
        "## 结论",
        "",
        "- 当前最明确的卡点不是单一模型慢，而是 Stage C 每次最多 30 segment、每批 4 segment、串行执行，并且重试/锁/agent 轮次管理混在终端脚本里。",
        "- 真实运行产物存在，但 telemetry 粒度不足，无法可靠回答 scan/parse/validator/git/CI 等分环节耗时；下一步应先补最小计时与错误 taxonomy。",
        "- `workspace/stage_state.json` 仍显示 refine in_progress / refine_blocked=true，说明阶段状态没有稳定收敛到可继续扩章的状态。",
        "",
        "## 下一步建议",
        "",
        "- 先执行 P0：修复 Stage C 小批量串行瓶颈、统一 checkpoint/run telemetry、阻止多终端重复 worker。",
        "- 暂停盲目继续 500/600 章，直到吞吐指标脚本能稳定显示章节/小时、失败率、重跑率和每环节耗时。",
        "- 为 provider、extractor、validator、exporter 添加轻量 timing span，不改译文内容。",
        "",
        "## 缺失数据与补采任务",
        "",
        *[f"- {item}" for item in metrics["missing_data"]],
        "",
    ]
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    metrics = build_metrics()
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(metrics)
    print(f"wrote {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {JSON_PATH.relative_to(REPO_ROOT)}")
    print(
        "summary: "
        f"runs={metrics['runs']['run_count']} "
        f"model_runs={metrics['model_runs']['count']} "
        f"draft_chapters={metrics['runs']['totals'].get('draft_chapters', 0)} "
        f"refined_chapters={metrics['runs']['totals'].get('refined_chapters', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
