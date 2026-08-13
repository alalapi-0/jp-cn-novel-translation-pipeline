# Git-safe cohort 远端最终化

本文件是本仓库每轮 Git 交付的执行权威。目标是让已审查、可进入 Git 的轮次成果及时到达 GitHub，而不是长期堆积在本地工作树。

## 完成语义

一次轮次只处理一个 `git_safe_cohort`。实现和验证完成后，必须生成绑定精确路径、文件状态、mode 与 SHA-256 的 JSON plan；按风险等级满足 DIRECT / REVIEWED / GOVERNED 所需审批；再由 `scripts/git_safe_cohort_finalizer.py` 执行：

1. 校验当前 HEAD、空 index、前一 HEAD 的远端 SHA、既有 `origin`、既有安全非默认分支和审批 envelope；
2. 只暂存 plan 中的精确路径；modified/deleted 判断、暂存和失败恢复均使用 raw blob/index plumbing，不运行 clean filter；
3. 复核 staged path set、字节、mode、secret 与 never-commit 边界；
4. 使用固定非私密身份 `Codex Git-safe Cohort Finalizer <codex-git-safe-cohort@users.noreply.github.com>` 创建一个 commit，并复核完整 commit metadata；不继承用户 Git identity、签名配置或 `GIT_AUTHOR_*` / `GIT_COMMITTER_*`；
5. 立即重新解析并核验 endpoint/default/lineage；literal URL 的 `ls-remote` 与 push 使用最小环境 allowlist，禁用所选仓库、global、system、config-env、proxy/TLS/transport-helper rewrite，HTTPS 只显式注入单一白名单 `osxkeychain` helper并禁用交互 prompt；随后在无 hooks 的隔离临时 Git 配置中，以已核验的 URL literal 和 exact commit SHA 普通 push 到 `origin/codex/light-novel-governance-closure-20260813`；依赖多 helper、URL-specific helper、ASKPASS 或自定义 Git transport 的环境会 fail closed。
6. 用 fresh `git ls-remote` 确认远端 SHA 等于本地 commit SHA。

只有第 6 步成立时 cohort 才是 `complete`，随后才可选择下一 cohort。`candidate_ready_for_delivery`、本地 commit、push 命令返回 0、缓存的 remote-tracking ref 都不等于完成。

## 固定权限边界

- Standing policy 只允许已存在的 `origin` 与已存在的 `codex/light-novel-governance-closure-20260813`；`main` 是默认分支，禁止直接 push。
- 改 remote、branch 或扩大外部效应需要用户新的明确授权和治理复审。
- 禁止 force-push、merge、默认分支更新、分支创建、PR、deploy、release、凭据修改和全量 staging。
- edit/build 请求和 Round Prompt 不能自行扩大 Git 权限；它们产生的候选仍须满足本策略、验证和审批门禁。
- 真实原文、完整真实译文、workspace runtime、artifacts、用户私密内容与 secrets 永不进入 Git。Git-safe 的代码、测试、schema、治理文档和脱敏 metadata/report 才可登记。

## Plan 格式

Plan 是临时、非仓库产物；不要把真实内容或凭据写入 plan。审批登记的 plan SHA-256 定义为该 JSON object 使用 UTF-8、sorted keys、无多余空白的 canonical serialization 摘要；所有执行命令必须以 `--expected-plan-sha256` 提供该登记值。最小结构如下：

```json
{
  "schema": "git_safe_cohort_v1",
  "cohort_id": "unique-cohort-id",
  "base_sha": "40-lowercase-hex",
  "remote": "origin",
  "remote_url_sha256": "64-lowercase-hex",
  "branch": "codex/light-novel-governance-closure-20260813",
  "default_branch": "main",
  "commit_message": "fix: one coherent delivery unit",
  "review_lane": "reviewed",
  "approvals": {
    "validation": "passed",
    "judge": "passed",
    "governor": "not_required",
    "content_safety": "passed",
    "approval_subject_sha256": "canonical SHA-256 of every plan field except approvals",
    "evidence": ["exact reproducible evidence identity"]
  },
  "delivery_authority": "standing_git_safe_cohort_policy_v1",
  "paths": [
    {
      "path": "src/example.py",
      "state": "modified",
      "mode": "0644",
      "sha256": "64-lowercase-hex",
      "classification": "code"
    }
  ]
}
```

`approval_subject_sha256` 绑定所有实际交付字段（除 approvals 本身），`content_safety=passed` 表示 exact candidate 已完成 never-commit/private-content 复核；执行时另以整个 plan 的 canonical SHA-256 防止审批 envelope 本身被改写。`governed` lane 要求 `judge=passed` 且 `governor=approved`；`direct` lane 的两项为 `not_required`。删除项使用 `mode=absent`、`sha256=null`。重命名必须显式登记旧路径删除和新路径新增。

## 命令

```bash
python3 scripts/git_safe_cohort_finalizer.py preflight /absolute/path/to/PLAN.json \
  --expected-plan-sha256 REGISTERED_PLAN_SHA256
python3 scripts/git_safe_cohort_finalizer.py finalize /absolute/path/to/PLAN.json \
  --expected-plan-sha256 REGISTERED_PLAN_SHA256
python3 scripts/git_safe_cohort_finalizer.py verify /absolute/path/to/PLAN.json \
  --expected-plan-sha256 REGISTERED_PLAN_SHA256
```

push 或远端核验失败时，本地 commit 保留，cohort 为 `incomplete`，ignored receipt 位于 `.agent_runtime/inspection_reports/git_delivery/`。不得原样盲重试。只有凭据、网络、远端状态或 transport 方法确有变化后，才可对同一 remote/branch 使用：

```bash
python3 scripts/git_safe_cohort_finalizer.py retry-push /absolute/path/to/PLAN.json \
  --expected-plan-sha256 REGISTERED_PLAN_SHA256 \
  --change-evidence /absolute/path/to/RETRY_CHANGE_EVIDENCE.json
```

Retry evidence 必须绑定同一 cohort 与 plan SHA，包含受控 condition、唯一 change ID、`recorded_at`、前一 receipt 的 exact `previous_attempt_updated_at`、不同的 before/after 非敏感状态指纹和一行摘要。`recorded_at` 必须晚于所绑定的前一 attempt；后续 attempt 的 before fingerprint 必须接续前一 attempt 的 after fingerprint。finalizer 会在任何外部 push 尝试**之前**把 evidence 原子记录为 consumed；已消费 evidence 不可复用。condition-specific 指纹与摘要由 Root/owner 的已登记真实诊断证据提供，finalizer 负责身份、时间、链路与不可重放门禁，不把任意自声明字符串提升为事实。改变 target 不属于 retry，必须取得新授权。下一 cohort 的 preflight 会重新要求当前 base SHA 已在远端，因而失败或未核验的交付会持续阻断推进。

若进程在 commit 后、receipt 完整写入前中断，本地 commit 必须保留。对同一登记 plan 重新执行 `verify` 可在远端已包含该 commit 时重建 complete receipt；远端尚未包含时，`retry-push` 会先逐路径复核该 commit，再要求一份未消费的 change evidence，绝不重新提交或扩大路径。

## 报告与状态

Tracked round report 只能在 commit 前记录 `candidate_ready_for_delivery`，且 `remote_sha_verified=false`、`next_recommended_round=""`。push 后的完成真值是 fresh remote SHA 核验与 ignored local receipt；不要为了写回同一个 commit 的 SHA 再制造自引用 commit。下一轮开始时必须 fresh verify 前一 HEAD，然后才可创建新的 cohort/report。
