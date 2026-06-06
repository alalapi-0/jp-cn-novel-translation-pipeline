# MCP 文档索引

本仓库通过 `.cursor/mcp.json` 声明 Workspace MCP Servers，供 Cursor / Codex Agent 使用。

## 文档

| 文件 | 说明 |
|------|------|
| [WORKSPACE_MCP_SERVERS.md](./WORKSPACE_MCP_SERVERS.md) | 各 server 用途与配置摘要 |
| `docs/agent_skills/mcp_usage_skill.md` | Agent 技能：降级与安全 |
| `docs/mcp_playwright_setup_plan.md` | Playwright MCP 安装与验证 |
| `docs/mcp_verification_checklist.md` | 验收清单 |
| `docs/design/stitch/STITCH_MCP_SETUP.md` | Stitch 设计 MCP |

## 检查命令

```bash
npm run check:mcp      # 必需 server + 安全
npm run check:stitch   # Stitch 集成
```

## 配置位置

- 项目：`.cursor/mcp.json`（可提交，无密钥）
- 用户：`~/.cursor/mcp.json`（勿把 Key 提交到仓库）

修改 `mcp.json` 后通常需 **Reload Window**。
