# Round 47：API Dry-run and Cost Guard Hardening

## Agent 身份

你是 API Integration Agent，负责强化 dry-run provider、cost guard 与 controlled run 停止条件。

## 当前轮次

Round 47

## 本轮类型

`api_integration`

## 背景

真实批量翻译前必须有 fake → dry-run → controlled run 链路。`governance/model_policy.yaml` 已定义 cost guard 默认值，需代码与测试落地。

## 必读文件

- `docs/api_provider_strategy.md`
- `governance/model_policy.yaml`
- `governance/agent_policy.yaml`
- `docs/batch_translation_workflow.md`
- `.env.example`

## 允许修改

provider adapter、dry-run 模式、cost guard 模块、tests、config 示例、相关文档。

## 禁止修改

不提交 `.env`；无用户授权不进行真实 paid API 调用；不修改真实译文输出。

## 工具要求

Python 3、pytest、fake provider mock。

## MCP / Playwright 要求

N/A

## 通用协议要求

REAL_API_TESTS_ENABLED=false、MAX_TEST_COST_USD=0 为默认；keys 仅来自环境变量。

## 具体任务

1. 实现或强化 fake provider（固定响应、无 network）。
2. 实现 dry-run provider（记录 request 不发 network 或 mock endpoint）。
3. 实现 cost guard：token 估算、budget ceiling、超限 abort。
4. 添加 controlled run 模式开关与 checkpoint。
5. 编写 pytest 覆盖 guard 触发与 abort。
6. 更新 `.env.example` 占位（不含真实 key）。
7. 文档化 Round 50 受控试跑前置条件。
8. 更新 round_state。

## 验收标准

1. fake provider 测试全 pass。
2. dry-run 不产生真实 network 调用（mock 验证）。
3. 超 budget 时 run 停止并写 log。
4. `.env.example` 含 cost 相关变量说明。
5. 无 API key 出现在代码或 commit。
6. agent_gate 无 BLOCKED。
7. 真实 API 测试仅在显式 env 开启时可运行（默认关闭）。

## 安全检查

never log full API key；suspected secrets path-only report。

## Git 提交建议

`feat: harden api dry-run and cost guard`

## 最终报告格式

providers_implemented、guard_rules、test_results、env_vars_documented、ready_for_round_50。
