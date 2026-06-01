# 从单本翻译任务到中日文互译流水线的迁移说明

## 旧定位

单本日文轻小说中文翻译任务仓库。

## 新定位

中日文小说互译生产流水线仓库。

## 保留旧结构

- `input_jp/`
- `output_cn/`
- `notes/`
- `prompts/`
- `docs/`

## 新增方向

- `input_cn/`
- `output_jp/`
- `directions/jp_to_cn/`
- `directions/cn_to_jp/`
- `shared/`
- `workspace/`
- `data/`
- `frontend/`
- `src/`

## 兼容原则

1. 旧的日译中流程继续可用。
2. 新增中译日不应破坏旧流程。
3. 共享核心逐步抽象，不一次性大重构。
4. 旧 notes 文件未来可以迁移到 project-level data。
5. 旧 prompts 可以作为 `JP_TO_CN` 的早期模板。
6. 新 prompt 需要逐步分方向组织。
7. 真实原文和译文不因迁移自动移动或提交。
8. 现有脚本不在治理轮中改写。
