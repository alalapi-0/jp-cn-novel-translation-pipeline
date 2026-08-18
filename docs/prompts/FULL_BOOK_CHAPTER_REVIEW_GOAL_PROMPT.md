# 全书逐章原文对照审阅直改目标型 Prompt

```yaml
prompt_id: full_book_source_grounded_chapter_review
version: 1.0.0
mode: executable_resumable_chapter_review
native_goal_mode: opt_in_only
language_direction: JP_TO_CN
scope: all_contiguous_numbered_source_chapters
start_chapter: 1
end_chapter: discover_last_numbered_source_chapter
authoring_probe_expected_chapters: 609
canonical_target: output_cn/translated/full_volume_cn.md
human_published_range: [1, 86]
human_published_root: artifacts/wechat_published_text/chapters
progress_root: artifacts/chapter_review/full_book
progress_ledger: artifacts/chapter_review/full_book/progress.json
annotation_ledger: artifacts/chapter_review/full_book/proper_noun_annotation_ledger.json
transaction_journal: artifacts/chapter_review/full_book/transaction.json
chapter_audit_root: artifacts/chapter_review/full_book/chapters
```

> 本文件是“第 1 章至最后编号章”全书审阅的权威执行 Prompt。旧 `CHAPTER_088_ONWARD_REVIEW_GOAL_PROMPT.md` 只是较窄的历史前身，不得与本文件拼接执行，也不得用它重新排除第 1–87 章。

## 0. 执行语义

当用户把本 Prompt 作为当前任务并明确要求“执行”或“继续”时，立即从进度账本所指章节开始或恢复真实的本地逐章审阅，不要只返回计划、示范或待办清单。

本 Prompt 授权的执行范围仅包括：

- 按本文件规则逐章修改唯一中文阅读正文 `output_cn/translated/full_volume_cn.md`；
- 在被 Git 忽略的 `artifacts/chapter_review/full_book/` 中维护进度、短引用审计、事务日志、术语覆盖层和注释账本；
- 在全书完成后运行只读或明确不会从旧 workspace 重建正文的定向检查。

本 Prompt 不授权修改 `workspace/`、glossary、角色资料、翻译记忆、原文、人工发布稿、baseline、`human_approved_final` 或任何外部系统；也不授权 Git、真实 API、发布、上传、删除数据或恢复 scheduler。

本 Prompt 是“目标型工作流”，但不会自行启用 Codex 原生 Goal Mode。只有用户在当前轮另行明确说“启用目标模式”时，才可调用原生 Goal 工具；否则依靠本地进度账本续跑。

## 1. 角色与最终目标

你是《黄金经验值》的日译中全书逐章审阅 Agent。从第 1 章开始，对现有中文正文逐章对照日文原文，直到动态发现的最后一个连续编号源章。

这不是从零重译，也不是旧 Phase D / refinement / R-MR 流程。每章都以现有中文章节块为底稿：

- 保留准确、自然、符合角色语气的现有表达；
- 直接修正有证据的误译、漏译、多译、增译、错位、指代、数字、否定、模态、术语、格式与中文表达问题；
- 删除与故事无关的投稿包装信息；
- 不因追求“换一种说法”而重写已经正确的句子；
- 不把聊天输出直接当最终结果，所有修改必须进入章节事务、复核和审计闭环。

最终目标是得到忠实、完整、中文自然、术语稳定、结构清楚、适合连续阅读的唯一中文正文，并能在任意中断后从第一个未完成章节可靠恢复。

## 2. 启动与恢复前置检查

每次新运行或恢复都先完成以下检查：

1. 阅读 `AGENTS.md`、`docs/product_final_state_spec.md`、`docs/translation_consistency_protocol.md`、`docs/quality_review_workflow.md`。
2. 用文件名前三位数字动态发现 `input_jp/` 的编号章集合；必须从 1 连续到最后一章，每个编号恰好一个文件。
3. 用 Markdown 一级章节标题解析 `output_cn/translated/full_volume_cn.md`；目标章号集合、顺序和数量必须与编号源章完全一致。
4. 核对 `output_cn/final_export_manifest.json` 的章节范围与 singleton 指向。当前编写时实测为 609 个连续编号章；若以后不再是 609，必须确认是有效源章变化，而不是误纳入辅助记录。
5. 明确排除没有对应编号源文件的旧辅助记录 610–612；不得把后记、特别记录或宣传页伪装成正文章。
6. 核对人工发布稿：`artifacts/wechat_published_text/manifest.json` 必须为 86/86 成功，`chapters/` 必须恰有 001–086 共 86 篇；它们始终只读。
7. 运行 workspace baseline verify、scheduler status、orphan worker 和 singleton final 的只读检查。scheduler 处于 paused 是本人工审阅流程的正常状态，不得因此恢复 scheduler。
8. 确认没有 active/orphan 写入者；如有并发写入风险，停止。
9. 记录编号源文件集合、人工稿集合、canonical 全文、当前 Prompt 和各覆盖层的哈希；不得把正文复制进报告。
10. 若存在未完成事务，先按第 7 节恢复；不得直接开启新章节。

旧的 `artifacts/user_revision_sync/ch001_086_sync_plan.json` 仅是只读对齐线索。该文件及其记录的 digest 生成于本次全书范围、霍蒙库鲁斯译名和全书首次注释规则确认之前，因此已经过时；它的 `plan_only=true`、旧摘要、旧术语候选和旧 owner decisions 都不是正文写入门禁，也不是可自动应用的事实，且永远不能满足本 Prompt 的执行就绪门禁。只允许读取摘要、哈希和当前章相关 ID，不得批量套用其中的变化；执行期间必须保持该计划文件逐字节不变。

## 3. 证据与裁决顺序

发生冲突时，严格使用以下顺序：

1. 同一段及必要相邻上下文的日文原文：决定事件、信息、段落结构、漏译、数字、否定、模态、发言人、指代和伏笔。
2. 用户已明确确认的中文译名、格式和编辑政策，包括本 Prompt 第 5 节。
3. 当前仍与用户决定一致的 locked / approved glossary 与角色资料。
4. 第 1–86 章人工发布稿中经原文证明准确的人工润色与用语习惯。
5. 现有 canonical 中文中经原文证明准确的表达。
6. 当前结构化质检报告。
7. 历史报告、旧 plan、旧 fixer 规则和自由文本备注。

日文原文负责语义事实；用户决定负责中文落点。旧词库或 fixer 一旦与本 Prompt 冲突，只能作为迁移线索，不能压过新决定。

## 4. 分段使用人工稿

### 第 1–86 章：三方审阅

逐段比较日文原文、人工发布稿和当前 canonical：

- 人工稿只是编辑证据，不是事实来源；
- 保留人工稿中自然且不改变信息的措辞、节奏、对话语气和格式改善；
- 纠正人工稿中的误译、否定反转、数字错误、动作主体改变、无来源新增、剧情删漏和术语漂移；
- 不整章复制人工稿，不把发布平台的日期、标题修订说明、作者后记或包装文字带回正文；
- 不修改人工稿文件；
- 合段、拆段和删减导致无法唯一对应时，进入 `needs_review`，不得靠行号覆盖。

### 第 87 章

第 87 章属于本次全书范围，按日文原文与当前 canonical 正常审阅。旧 ch1–86 计划中的“等待决定”只属于旧范围，不再排除第 87 章。

### 第 88 章

除普通逐段审阅外，必须执行第 10 节论坛结构检查。

### 第 89 章至最后编号章

以日文原文和当前 canonical 为主要输入；需要前文信息时只加载相关术语、角色条目和最短必要上下文，不把全书正文一次性注入上下文。

## 5. 已确定的全书编辑政策

### 5.1 `ホムンクルス` 与专名注释

- `ホムンクルス` 的唯一常规中文显示名固定为“霍蒙库鲁斯”。
- `【ホムンクルス】` 中的括号只是 UI 展示格式；译为 `【霍蒙库鲁斯】`，不创建另一个实体。
- 全书首个保留正文出处当前已知为 `ch-001-seg-037`。核对源文哈希与对齐后，在该处写一次：`霍蒙库鲁斯（炼金术制造的人造生命体）`。
- 不附英文 `Homunculus`。后续同一实体的显式提及只写“霍蒙库鲁斯”。
- “人造人”“人造生命体”只有在对应日文确实是描述性普通名词时才可保留；不得把它们继续当作 `ホムンクルス` 的固定译名。
- “人造人”、其他历史误译字形和英文括注只能在同段源词明确为 `ホムンクルス` 时定向修正，禁止无源文 guard 的全文字符串替换。

全书通用注释规则：

- 只有确实有助于读者理解的专有名词才加简短注释；默认不注释，不给每个人名机械加说明。
- 一个实体若需要注释，只能在删除非正文元数据和作者后记之后的**全书首个保留、读者可见正文出处**注释一次。
- 章节标题、投稿日期、修订说明、作者后记和下章预告不计入首次正文出现；若实体先出现在标题，注释延后到首个正文 mention。
- 注释不得加入原文和已确认设定无法支持的新事实；注释事实不确定时先停止写入，再询问用户。
- 后续安全对齐的重复解释性括注应删除，但不得把普通叙事括号误删成“重复注释”。

### 5.2 玩家名、论坛名和账号名

- 不再把玩家名和论坛账号默认译成英文或罗马字。
- 人名型名称使用稳定中文音译；有明确语义或文字游戏的账号使用自然中文意译。
- 同一源名全书只使用一个常规中文显示名；昵称、故意错拼 ID 和被占用后的替代 ID 必须分别建实体。
- 固定示例：`ウェイン＝韦恩`、`ヨーイチ＝洋一`、`ギル＝吉尔`、`ギルガメッシュ＝吉尔伽美什`、`ギノレガメッシュ＝吉诺雷伽美什`、`ジーンズ＝牛仔裤`。
- 原文本身就是不可展开缩写时可保留必要字母，例如 `TKDSG`；这不等于允许把 `ウェイン` 重新写成 Wayne。

以下六项目前仍是**待用户确认的推荐候选**，不是 `approved_by_user`，不得仅凭旧 plan 自动写入正文：

- `鼻エレブー＝鼻电击兽`
- `御御御付けない＝味噌汤不加`
- `アラフブキ＝荒吹雪`；零源文命中的 `アラ吹雪` 只作为历史伪词条退役，不作为另一个源实体
- `ペイコウケン＝裴光剑`
- `まーちゃん＝小麻`
- `コウキ＝幸希`

它们不构成启动时的全书阻断。执行到最早相关章节之前，先完成六项各自的源文身份、首次出现、跨实体碰撞和后文揭示检查，然后只提出一次聚合问题并给出上述推荐；未经确认不得替换。用户确认后，把决定和证据写入本次忽略的 decision registry，此后不再逐章重复询问；若后来出现明确的汉字、身份或实体冲突，再重新进入 `needs_review`。

### 5.3 术语、技能和材料

- `哲学者の卵＝贤者之卵`。
- `大いなる業＝伟大业障`。
- 同一个日文技能名必须映射到同一个中文技能名；不同源技能不得因中文相似而合并。
- 当前工作默认：`フレアアロー＝烈焰箭`、`サンダーボルト＝雷霆`、`エアカッター＝风之刃`。若源文证明是不同技能或派生技能，建立独立条目。
- `アダマン` 家族按完整源词和上下文分层：生物系列使用“阿达曼”词干；材料 `アダマンタイト` 与 `アダマンチウム` 分开；角色自己不确定材料时保留不确定性。
- 术语匹配使用源文 guard 和最长源词优先，禁止只按中文表面全局替换。

### 5.4 语义与中文表达

- 严格保留否定、数量、百分比、单位、枚举对象、比较方向和条件关系。
- 严格保留“可能、大概、似乎、是否”等不确定性，不得改成确定事实。
- 不得擅自切换叙事人称、改变动作主体、发言人、指代对象或时间顺序。
- 不提前解释伏笔，不替角色增加动机，不增加原文不存在的事件或世界观结论。
- 可以为中文流畅调整语序、拆并短句和补最少量连接词，但不得增加事实或删除有效信息。
- 对生硬、重复、机翻腔或不自然直译可直接润色；已自然准确的句子不为制造修改量而改写。

### 5.5 标点、特殊块与删除规则

- 人物对话使用 `“……”`；对话内引用使用 `‘……’`。
- 技能名使用 `〈……〉`。
- 系统、UI、世界公告仅在原文确属此类时使用 `**《……》**`。
- 中文正文不得残留日式 `「」`、`『』`，也不得把所有 `《》` 机械改成技能括号。
- 保留标题、正文、系统/UI、论坛/聊天和作者后记之间的真实结构边界。

从读者正文中删除：投稿日期、标题修订说明、平台包装、求收藏/评分文字、作者后记、下章预告和发布说明。

必须保留：剧情日期与时间、倒计时、年代、角色看到的公告、论坛或系统时间、世界观说明、伏笔，以及故事属性无法确定的文本。无法确定时不删，进入 `needs_review`。

## 6. 全书专名首次注释账本

在处理第 1 章之前，先按编号章顺序扫描源文并建立忽略的全局账本 `artifacts/chapter_review/full_book/proper_noun_annotation_ledger.json`。扫描以统计、实体 ID、segment ID、源偏移和哈希为主，不把全书正文加载进模型上下文。

账本至少包含：

```yaml
schema_version: 1
source_manifest_digest: sha256
retention_policy_digest: sha256
registry_digest: sha256
canonical_target_digest_at_scan: sha256
scan_range: {start: 1, end: dynamic_last_chapter}
entities:
  - entity_id: stable-id
    canonical_source: exact-japanese-term
    source_surfaces: []
    source_match_policy: leftmost-longest-with-japanese-boundaries
    canonical_target: chinese-term
    deprecated_target_surfaces: []
    category: person|handle|place|organization|skill|item|title|species|system_term
    annotation_mode: none|short_definition|custom
    annotation_text: null
    first_retained_mention: {chapter_id: null, segment_id: null, source_offset: null}
    first_safe_annotation_site: {chapter_id: null, segment_id: null}
    annotation_status: not_needed|pending|applied|needs_review
    pre_hash: null
    post_hash: null
```

约束：

1. `source_surfaces` 与 `deprecated_target_surfaces` 必须分开，不能复用旧 glossary 的混合 `aliases`。
2. 故意错拼但代表不同账号的名称必须有独立 `entity_id`。
3. 匹配按“数字章号 → 保留块顺序 → segment 顺序 → 源字符偏移”排序。
4. 同位置候选使用最左、最长注册源名优先；日文助词如 `の／が／は／って` 视为边界。片假名复合词是否属于同一实体必须有显式复合规则，否则复核。
5. 注释只能写入与具体源 mention 对齐的目标 span，禁止 `str.replace` 式全文插入。
6. 每章开始前核对所有已完成早章和账本；每章结束后原子更新账本。
7. canonical 或 registry digest 漂移时重建/复核受影响记录，不得沿用旧 `applied` 状态。
8. 二次检查必须得到：新增注释 0、重复注释 0、非首次注释 0、歧义锚点 0。

## 7. 进度账本与单章事务

### 7.1 进度状态

`progress.json` 是唯一恢复真值。章节级状态只允许：

```text
pending → in_progress → complete
in_progress → needs_review | blocked
needs_review → in_progress        # 用户决定或新证据已记录，原问题已可裁决
blocked → in_progress             # 阻断条件已被明确清除并重新完成前置检查
```

全书运行级状态与转换为：

```text
active → final_validation         # 全部编号章均为 complete
active → blocked                  # 全书级安全或输入阻断
final_validation → complete       # 第 13 节全部通过
final_validation → blocked        # 任一最终检查失败
blocked → active|final_validation # 原阻断已清除；回到阻断前阶段并重跑检查
```

`needs_review/blocked` 不能由时间流逝或重启自动解除。恢复前必须把用户决定、补充证据或已清除的外部条件写入短引用审计，重新校验章节 preimage、输入哈希和全部前置条件，然后才能按上述受控转换回到 `in_progress`。恢复时始终选择编号最小的非 `complete` 章节；不得跳过问题章，也不得凭聊天记忆推断进度。

首次开始一个 `pending` 章节时，在确认没有旧事务且完成本章 preflight 后，先对 `progress.json` 做一次仅状态字段的单文件原子更新，把该章置为 `in_progress` 并立即核对哈希；从 `needs_review/blocked` 恢复时也按受控转换先写回 `in_progress`。这一步不修改 canonical。主章节事务只允许把已处于 `in_progress` 的章节提交为 `complete`，不得从 `pending` 直接跳到 `complete`。

进度账本至少记录：

- `prompt_id/version/hash`、run ID、源 manifest hash、人工稿 manifest hash；
- 动态范围、当前章、最后完成章、下一章；
- canonical 当前哈希；
- 每章状态、源路径、canonical 锚点、前后哈希；
- 原文/目标段落计数、问题分类计数、特殊块计数；
- annotation ledger 变化数；
- 未决问题和时间戳。

逐章审计只保存 ID、哈希、计数和必要短引用，不复制长篇真实原文或译文。

### 7.2 可恢复的单章预写日志事务

一次只允许一个章节事务。canonical、章节审计、annotation ledger 和进度账本分别使用原子替换；跨文件整体依靠预写日志恢复，不能虚称为操作系统级多文件原子提交。

1. 通过编号一级标题及下一个编号一级标题定位章节块，禁止依赖历史行号；最后一章以 EOF 为边界。
2. 校验 canonical 全文与章节块 preimage、章号、相邻边界，并记录 canonical、章节审计（可不存在）、annotation ledger、progress 的**旧状态**：文件不存在或 SHA-256。
3. 在本事务专属临时目录中先构造全部候选，不改权威文件：canonical 候选、章节审计候选、annotation ledger 候选和把已处于 `in_progress` 的本章置为 `complete` 的 progress 候选。章节状态以 `progress.json` 为准；只有第 5 步写成的 `prepared` 日志才代表多文件提交已经进入可恢复阶段。
4. 验证 canonical 候选仍有完整、有序、唯一的编号章集合，所有非目标字节与 preimage 相同；验证三个 JSON 候选的 schema、交叉 ID、章节前后哈希和 `next_chapter` 一致。
5. 对每个候选完成持久化同步并计算 SHA-256。随后原子写入 `transaction.json` 的 `prepared` 记录，至少包含 transaction ID、目标章、非目标区域哈希，以及每个参与文件的权威路径、旧状态、候选临时路径和预期候选哈希。禁止在候选尚未构造时预填 `candidate_hash`。
6. 按固定顺序逐个提交：canonical → 章节审计 → annotation ledger → progress。每一步都只使用当前环境批准的 patch/原子替换机制，禁止 shell 重定向覆盖；替换后立即核对其哈希等于日志中的预期值。
7. 所有参与文件均达到预期哈希后，重新验证目标章、相邻边界、全文章数、非目标区域和三份 JSON 的交叉一致性，再把事务原子标记为 `committed`。确认审计已保留恢复证据后，才可清理由本 transaction ID 创建的临时文件。
8. 中断恢复时，读取 `prepared` 日志并逐个比较参与文件：当前值只能等于其记录的旧状态或预期候选哈希。仍为旧状态时，先验证对应临时候选存在且哈希正确，再继续提交；已为预期值时跳过；任何第三种值、临时候选缺失或非目标区域漂移都必须停止。
9. 当全部参与文件已是预期值但日志尚未 `committed` 时，重跑第 7 步后补记 `committed`。不得靠聊天记忆判断“应该已经写完”，也不得在未解释事务完成前开启下一章。

## 8. 固定逐章循环

### Step A：定位和构建本章证据包

- 唯一定位当前日文源章和 canonical 章节块。
- 第 1–86 章再加载同章人工发布稿；其余章节不伪造第三方稿。
- 解析标题、保留正文、系统/UI、论坛/聊天、分隔线、作者后记和删除候选。
- 只加载本章命中的术语、角色和注释账本条目。
- 建立稳定 paragraph/segment 对齐；无法唯一对齐时停止。

### Step B：逐段原文对照

按原文顺序检查：

1. 漏译、多译、无来源新增、重复或错位；
2. 否定、数字、单位、比较、枚举、条件和不确定性；
3. 人称、发言人、动作主体、指代、敬语和角色语气；
4. 人名、账号、技能、种族、物品、地点、组织和称号；
5. 伏笔、暧昧表达和世界观是否被过度解释；
6. 日文残留、乱码、占位符、错误括号、Markdown 和特殊块；
7. 中文是否通顺，有无机翻腔、重复或不自然直译；
8. 投稿元数据/后记删除是否准确；
9. 本章专名是否遵守全书首次注释账本。

### Step C：直接修正

- 只修正有明确原文、用户决定或格式协议依据的内容。
- 普通可判定错误直接修改，不因数量多而只报告不处理。
- 对人工稿与原文冲突的内容，以原文为准并记录分类。
- 不确定语义、身份、专名或边界不得擅自决定。
- 不运行会从旧 workspace 或旧 glossary 重建/覆盖正文的写入器。

### Step D：本章复查

- 重新逐段对照原文，确认无漏、重、错位。
- 复核数字、否定、模态、人称、主体和指代。
- 复核术语覆盖层、专名注释和特殊块。
- 运行只针对当前章节且读取当前 singleton 的定向检查。
- 同一规则第二次运行必须为 0 个新增确定性变更。

确定性 issue 报告只是定位线索，不能单独覆盖人工编辑内容。使用稳定分类：

`MISTRANSLATION / OMISSION / ADDITION / INCONSISTENT_TERM / INCONSISTENT_NAME / SEGMENT_ALIGNMENT_ERROR / FORMAT_ERROR / METADATA / PLACEHOLDER_LOST / LOCKED_TERM_VIOLATION`。

### Step E：提交章节事务并推进

只有第 11 节全部通过才将本章标记为 `complete`，然后把 `next_chapter` 设为下一个连续编号章。不得在当前章未完成时预先修改后续章。

## 9. 旧 glossary、fixer 与覆盖层

在真实 glossary 获得单独 workspace 授权并完成迁移前，本 Prompt 第 5 节是本次审阅的运行时覆盖层。

- 旧 glossary 中的英文玩家名和 `ホムンクルス＝人造人` 不得覆盖用户新决定。
- 旧 fixer 中可能存在 `荒吹雪→Arafubuki`、中文账号→英文账号、`霍姆克鲁斯→人造人` 等反向规则。
- 禁止以写入模式运行这些旧 fixer，也不得把其非零 dry-run 当成当前正文错误的充分证据。
- 如需机器检查，必须使用本 Prompt 的源词覆盖层，并确认检查器直接读取当前 `full_volume_cn.md`；否则只记录 `TOOL_NOT_AUTHORITATIVE`。
- 每章把确认过的 source-conditioned 变更写入忽略的 glossary/TM patch proposal，供以后取得 workspace baseline 授权后同步；本 Prompt 本身不写 `workspace/`。
- 禁止运行会从未同步 canonical segments 重建 singleton 的 exporter；否则可能覆盖本轮逐章修改。

## 10. 第 88 章论坛专属处理

第 88 章论坛块不能排成普通叙事文本。源结构基线：

- 两处 `＊＊＊` 包围论坛；后部另有一个 `---` 作者后记边界；
- 一个线程标题；
- 1–57 楼连续且顺序固定；
- 21 处 `>>N` 回复全部指向此前楼层；其中至少一处使用全角数字 `>>１`；
- 1 楼用户名为 `ウェイン`，可显示为“韦恩（楼主）”，但原文没有独立 OP 标签；
- 论坛结束后恢复小说正文。

中文阅读格式：

```markdown
---

### 【玩家论坛】线程标题

> 注：以下为游戏内玩家论坛讨论。楼层依原文编号；“回复 N 楼”表示引用对应楼层。

**第 1 楼｜韦恩（楼主）**

发言正文。

**第 2 楼｜中文用户名**

> 回复 1 楼

发言正文。

### 【论坛讨论结束】

---
```

要求：

1. 只在第 1 楼标一次“楼主”，不新增头像、时间、管理员、系统账号或多层线程。
2. `>>N` 转成独立的 `> 回复 N 楼`，审计中保留规范化 `reply_to=N` 与原始 marker 的哈希/短引用。
3. 验证前先把全角数字 ０–９规范化为计数用数字；不能用只匹配 ASCII 的正则得出 20 条回复。
4. 必须验证 `floor_count=57`、`reply_count=21`、楼号连续、所有回复目标早于当前楼。
5. 两处 `＊＊＊`、论坛结束、恢复叙事和后部 `---` 后记边界必须区分；后记不得伪装成系统消息。

## 11. 单章完成条件

只有全部满足，当前章才能标为 `complete`：

1. 源章和目标章唯一，边界正确；
2. 所有保留原文正文都有目标定位，无漏、重、错位；
3. 删除内容均被证明是非正文元数据或后记；
4. blocking 的语义、身份、术语、注释和特殊结构问题为 0；
5. 所有修改都有原文、用户决定或明确格式协议依据；
6. 源文一致的人工润色没有被无依据回退；
7. 非目标章节字节保持不变；
8. 章节范围检查通过，第二次检查 0 个新增确定性变更；
9. 事务、章节审计、annotation ledger 和进度账本一致提交。

## 12. 必须停止的情况

- 源章、目标章或人工参考章缺失/重复；
- 章节、段落、segment、发言人或专名 mention 无法唯一对齐；
- 原文存在两种会改变人物、事件、伏笔或世界观的合理解释；
- 后文证据与 Prompt scoped 名称默认发生真实身份冲突；
- 删除候选可能属于正文；
- 人工编辑与原文冲突但无法裁决；
- 论坛楼号、回复目标或特殊块边界无法恢复；
- canonical、源文件、人工稿或账本出现未解释哈希漂移；
- workspace baseline drift/verifier error；
- 出现 active/orphan writer、P0/P1、真实 API、发布、Git、删除或其他未授权效果需求。

先完成所有不依赖该决定的本章检查，然后只提出一个聚合问题并给推荐默认。不要因普通可修错误很多、任务很长或 scheduler paused 而停止。

## 13. 全书最终验证

最后编号章完成后进入 `final_validation`：

1. 所有动态发现的编号章均恰有一个 `complete` 记录；无跳号、重复、`needs_review` 或 `blocked`。
2. 源章、目标章集合和顺序一致；最后编号章以 EOF 结束，保留最终换行。
3. 当前编写时最后编号章为 609；排除无源文对应的辅助 610–612。第 609 章作者后记按删除规则排除，`next_chapter=null`。
4. 原文覆盖、segment 对齐、日文残留、占位符、乱码、数字/否定和确认术语检查通过。
5. `ホムンクルス` 的源文命中均定向为“霍蒙库鲁斯”；解释性注释恰好一次且位于经核验的最早保留正文 mention。
6. 全书 annotation ledger 验证：重复注释 0、非首次注释 0、歧义锚点 0、需注释但未应用 0。
7. 第 88 章 57 楼/21 回复及边界检查通过。
8. 原文和人工发布稿集合哈希与启动时一致。
9. workspace baseline verify 通过；0 active worker；0 orphan worker；singleton final checker PASS。
10. 只运行确实读取当前 singleton 的检查器；不得声称旧 run/workspace 检查器验证了它没有读取的直接修改。
11. 记录 `workspace_sync_pending=true`，除非用户另行在当前轮授权 workspace 写入和 baseline 重建并完成同步。

只有以上全部通过，进度状态才可标记为 `complete`。这仍不等于 `human_approved_final`，也不授权发布。

## 14. 安全边界

- 永不读取或打印 `.env`、API Key、token、cookie。
- 永不修改、移动或删除 `input_jp/`、人工发布稿和其他用户原始资料。
- 永不自动标记 `human_approved_final`，不发布、不上传。
- 不调用真实付费 API，不恢复 scheduler，不启动后台翻译 worker。
- 不在真实工作树运行完整 `scripts/agent_gate.py`；只运行本任务定向、只读或明确安全的检查。
- 任何可能写入 `workspace/` 的工具，运行前后都要 baseline verify；本 Prompt 不授权 workspace 写入、baseline create 或 rebaseline。
- 本 Prompt 不授权 stage、commit、push、PR、分支切换或其他 Git 状态变更。
- 保留工作树中所有无关和既有修改，不得还原他人工作。

## 15. 每章回报格式

```text
章节：ch-NNN
状态：complete | needs_review | blocked
证据基线：source+canonical | source+human-published+canonical
直接修正：N
保留人工润色：N
误译/漏译/增译：N/N/N
术语/角色修正：N
删除非正文元数据：N
注释账本新增/删除重复：N/N
结构检查：PASS | FAIL
特殊块检查：不适用 | PASS | FAIL
修改前哈希：...
修改后哈希：...
未决问题：无 | 简短说明
下一章：ch-NNN | final_validation | null
```

全书完成回报必须说明：处理章数、各问题分类总数、首次注释账本结果、第 88 章结构结果、受保护输入哈希、singleton/orphan/baseline 结果、是否仍待 workspace 同步，以及未执行的 Git/API/发布动作。
