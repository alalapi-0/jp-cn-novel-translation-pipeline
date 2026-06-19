# scripts

轻量脚本目录。已有脚本作为历史实现保留；后续实现轮可以在 dry-run 和测试保护下逐步增加扫描、解析、检查、导出等工具。

| 脚本 | 用途 |
|------|------|
| `agent.py` | 连续推进状态、轮次、任务队列和硬阻塞管理 |
| `run_real_api_smoke.py` | 统一真实 API 小规模测试入口；默认 dry-run / missing_api_key，不读取 `.env` |
| `run_browser_inspection.py` | 统一浏览器检查入口；检测并调用现有 Playwright 命令 |
| `agent_gate.py` | 确定性 Agent 门控（exit 0/1/2）；支持 `--json`、`--strict` |
| `check_protocol_standard.py` | 协议与 project.yaml 合规检查（exit 0/1/2）；支持 `--json` |
| `scan_repo_inventory.py` | 仓库 inventory 与工具链环境审计；生成 `governance/repo_inventory.generated.json` |
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
