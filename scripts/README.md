# scripts

轻量脚本目录。已有脚本作为历史实现保留；后续实现轮可以在 dry-run 和测试保护下逐步增加扫描、解析、检查、导出等工具。

| 脚本 | 用途 |
|------|------|
| `check_mcp_config.js` | 检查 `.cursor/mcp.json` 是否包含 5 个必需 MCP、JSON 格式、filesystem 授权与密钥泄露 |
| `check_mcp_config.py` | 同上（Python 版，历史保留） |
