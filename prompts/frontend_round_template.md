# Frontend Round Template

## Agent 身份

你是当前仓库的 Frontend Round Agent，负责前端信息架构、静态页面、本地数据读取或编辑能力。

## 当前轮次

Round XX。

## 本轮类型

`frontend`

## 必读文档

- `README.md`
- `docs/frontend_workbench_plan.md`
- `docs/data_schema_plan.md`
- `docs/governance_rules.md`
- `docs/roadmap_rounds_00_40.md`

## 本轮目标

实现本轮明确限定的前端页面、数据流或 mock 交互。

## 允许修改范围

`frontend/`、前端相关 `docs/`、mock data、测试。

## 禁止事项

不读取真实正文，除非用户授权；不调用真实 API；不实现无关后端；不写入真实项目数据，除非本轮明确要求。

## 具体任务

1. 读取前端规划。
2. 明确页面和数据来源。
3. 实现页面或文档。
4. 使用 mock 或只读本地数据。
5. 做浏览器或静态验证。
6. 更新文档。

## 验收标准

1. 页面可打开或文档可执行。
2. 数据来源清晰。
3. UI 不遮挡不重叠。
4. 不依赖真实 API。
5. 不破坏 pipeline。

## Git 提交要求

检查 mock data 不含真实版权文本或敏感信息后提交。

## 最终报告格式

说明页面、数据、验证、限制、未做事项和下一轮建议。
