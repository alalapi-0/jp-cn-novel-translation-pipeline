# 旧译与旧框架基线 v1

读者：P2 修订对照和 P5 回归实施者、独立审查者。更新触发：基线输入、代码、Prompt、知识、provider/model、参数或上下文身份改变。状态及下一任务仍只来自 `governance/round_state.yaml` 的当前单元，本页不调度任务。

## 三个结果名称

- **B_old**：通过固定开发读取器返回的旧译字段。保留 record_id、容器/字段/源锚点和目标版本；旧 approved/locked 标签不构成真值。生成它的历史代码、Prompt、知识、模型与参数没有证据时全部记 unknown。
- **B_framework**：冻结旧框架在相同条件下重新执行的严格基线。本次不可用：历史 provider/model/参数及知识条件不能确认，也没有付费调用授权。绝不为重跑恢复 scheduler、读取凭据或启动不安全旧脚本。
- **B_framework_adapter**：本次实际完成的受控适配基线，单独命名并记录差异。它使用冻结提交 `6342df6138915d49fddc08cf7f3ec99c1f042be6` 中原来的 SYSTEM_PROMPT、`_prev_tail_summary`、`build_batch_messages` 纯函数，经过 AST 选择，仅执行这些已审查函数与常量；不导入旧 runner。选择函数文档默认 `compact_context=False`，不加载未完成血缘适配的 TM/知识/作品配置，通过当前 Agent 额度生成。该模式不是历史生产配置或完整旧 runner 的复现。

旧 runner 已发现的失败成功、预算、恢复及隐式资产读取风险保留在 P2.R01 的原始证据。受控适配只重用纯 Prompt，并采用已修复的 extractor/validator、登记读取器及预算，不复制旧调度、缓存、写入与批准流程。

## 版本与可比性

`translation-baseline-pair/1` 为每个配对保留完整原文章节版本、片段 span/哈希、旧译 record_id/目标哈希、适配结果原始响应哈希及解析/校验结果。源文 identity 必须与登记片段一致；预算必须用整个原文版本及完整文档范围，不能用短片段或另一个 run 名重置。

条件分为 source、code、prompt、knowledge、provider、model、parameters、context。每项包含 known/unknown、身份哈希和证据说明。unknown 的 identity 必须为 null；两个 unknown 不相等于已验证匹配。适配代码身份包含冻结 Prompt、适配/校验实现；明确省略知识是本次已知条件，不能据此推断历史也没有知识。

`compare_conditions` 逐项报告 match/different/unknown，并强制显式适配差异。即使声明的条件哈希都相同，本接口仍标 `strict_same_conditions=false`、`framework_effect_attribution=prohibited`：历史文本与适配执行不是新旧框架单因素实验。未来若要估计框架效果，必须另行固定新旧候选的实际模型/参数、输入、知识和评价条件，不能把这批偏好回执改名为框架提升率。

本模块只检查提供的记录与条件形状/一致性，不能自行认证外部模型来源；实际放行证据仍由固定 `DevelopmentReader` 与私有来源回执提供。历史模型/参数不可得不授权换用付费 provider，也不阻断其余优化任务。

## 运行与失败

本次放行仅为开发集，保留集目标/反馈继续封存。源文选择先看冻结 source-cue 分层与位置元数据，再读目标，不按旧译质量挑样本。排除上一批已经消耗内容操作的八个完整章节版本，避免以新的片段 ID 重置既有单元预算。

调用前由任务私有桥接进程持有既有 `ContentUnitBudget` 的整个源文版本 lease。生成及两个审阅各在进入原生 Agent 工具前持久预留，返回后才记录完成；同源全局 checkpoint 和固定 8 次操作、2 次修订、1,200 秒上限保持不变。重放同请求必须符合既有 transient/retry 规则。桥接的超时可以拒绝结果、保留计数，不能声称能够抢占原生模型或看到内部重试/Token。

桥接是本次工具调用的生命周期包装，沿用 `workspace/checkpoints/content_units` 的已有计数，不是第二个业务状态或调度器。任务不控制宿主服务。所有 helper 句柄在回执后收取，原始响应、失败、未知调用和已消耗计数保留。checkpoint 的 succeeded 只说明回调结束，不能证明翻译正确。

解析不完整、重复/缺失/额外 ID、空目标等失败保留原始响应哈希和错误，适配候选 text/target_revision 为空，绝不升级为成功。结构通过也只称 structurally_validated_candidate。比较记录固定 agent_proxy、not_granted、auto_acceptance_enabled=false、canonical_write=false。

## 本次范围及解释

私有包为 `workspace/tooling/optimization/P1.R03.T02/`。从固定困难线索分层中选出三个未用开发章，各取首个唯一定位且长 55–220 codepoint 的 draft_text 对应源段：两段叙述/道具说明和一段面向读者的作者提示；原始选择保留，不事后排除作者提示。原范围仍为 609 章、开发 480/留出 129。

一个未参与审阅的 Agent 只读取冻结 Prompt 请求并生成三个结果；两个非改写者只读取各自匿名盲包，A/B 顺序相反。源文必要的前文只供审阅，不能冒称旧生成过程也使用它。所有文本与上下文身份固定，逐项问题用 source-review/1 的引用/span 接口核对。

偏好、严重错误否决和文学表达分别保留原始意见；没有参考金标，不计算真实语义 precision/recall，也不把旧译自动当正确答案。同模型能力与两个顺序/历史的混杂限制仍适用。三段样本不证明整章/整书质量、跨作品效果或个人风格；不产生 canonical 选择、人审、正式导出或框架因果收益。
