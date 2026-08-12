# scripts

轻量脚本目录。已有脚本作为历史实现保留；后续实现轮可以在 dry-run 和测试保护下逐步增加扫描、解析、检查、导出等工具。

| 脚本 | 用途 |
|------|------|
| `agent.py` | 连续推进状态、轮次、任务队列和硬阻塞管理 |
| `run_real_api_smoke.py` | 统一真实 API 小规模测试入口；默认 dry-run / missing_api_key，不读取 `.env` |
| `run_browser_inspection.py` | 统一浏览器检查入口；检测并调用现有 Playwright 命令 |
| `agent_gate.py` | 完整确定性门控（exit 0/1/2）；仅可在一次性隔离副本运行，输出不得写回真实仓库 |
| `run_tooling_checks.sh` | 真实工作树/干净 checkout 可运行的控制面目标检查；已建 baseline 时保证前后校验（中间失败也执行后校验），manifest 缺失时只接受完全空状态或无 diff/无未跟踪与忽略项的 tracked workspace 骨架；部分/脏状态 fail closed，且不调用完整 gate、同步探针、inventory 生成器或 baseline create/rebaseline |
| `check_protocol_standard.py` | 协议与 project.yaml 合规检查（exit 0/1/2）；会写合规报告，仅在明确拥有该维护的一次性隔离副本运行且不回写 |
| `scan_repo_inventory.py` | 写入型 inventory 维护；生成 `governance/repo_inventory.generated.json`，只在当前 scoped task 明确拥有刷新时运行，不是普通验证 |
| `vector_db_inspect.py` | 向量索引 metadata 只读检查（JSON mock MVP；exit 0/1/2） |
| `serve_frontend.py` | 本地静态工作台（默认 http://127.0.0.1:5174） |
| `export_consistency_final_volume.py` | 一致性清理后的最终导出；默认仅保留单一 `full_volume_cn.md` |
| `check_final_translation_singleton.py` | 检查本地最终译文是否只有一份 canonical 文件 |
| `finalize_consistency_run.py` | 幂等收尾报告；可清理旧 round logs，并追加而非覆盖 audit log |
| `check_mcp_config.js` | 检查 `.cursor/mcp.json` 是否包含 5 个必需 MCP、JSON 格式、filesystem 授权与密钥泄露 |
| `check_mcp_config.py` | 同上（Python 版，历史保留） |

## Legacy launchers

以下旧生产入口默认禁用，除非人工设置对应 `ALLOW_*` 环境变量做历史复现：

- `production_pipeline.sh`
- `production_watchdog.sh`
- `start_production_detached.sh`
- `pilot_batch_chain.sh`
- `translation_autopilot_loop.py`
- `run_translation_recovery_round.py`
- `lock_baseline.py`

当前生产推进入口是 `local_scheduler_tick.py` / `local_scheduler_launchd.sh`，必须遵守 pause、lock、orphan、cost guard。
Workbench manifest 导出只写入 `workspace/workbench_exports/`；唯一正式译文由 `export_consistency_final_volume.py` 写入 `output_cn/translated/full_volume_cn.md`。
