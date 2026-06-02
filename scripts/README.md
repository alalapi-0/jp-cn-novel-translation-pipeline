# scripts

轻量脚本目录。已有脚本作为历史实现保留；后续实现轮可以在 dry-run 和测试保护下逐步增加扫描、解析、检查、导出等工具。

| 脚本 | 用途 |
|------|------|
| `agent_gate.py` | 确定性 Agent 门控（exit 0/1/2）；支持 `--json`、`--strict` |
| `check_protocol_standard.py` | 协议与 project.yaml 合规检查（exit 0/1/2）；支持 `--json` |
| `serve_frontend.py` | 本地静态工作台（默认 http://127.0.0.1:5174） |
| `check_mcp_config.js` | 检查 `.cursor/mcp.json` 是否包含 5 个必需 MCP、JSON 格式、filesystem 授权与密钥泄露 |
| `check_mcp_config.py` | 同上（Python 版，历史保留） |
