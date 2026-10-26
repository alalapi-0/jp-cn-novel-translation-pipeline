# 显式接受版本与安全导出

此协议适用于 P2.R03.T01 的工程候选。真实作品、正式稿和 UI 接受仍需后续验收；本轮仅使用隔离合成输入，无模型调用。`accepted` 表示已有代理或 PSH 的当前候选接受，始终保留 `human_approved_final=false`，不签发人类批准，不解除语义自动接受禁用。

在源导入时独立冻结现有 project manifest 的 `source_inventory`。带完整 source binding 的输入使用 `workbench-source-inventory/2`，每项记录段 ID、源段 SHA、章节 ID、完整源文档版本和 binding SHA。旧 v1 可读且可辅助预览，不能正式导出。`source_documents` 显式列出本项目预期全部章节的 `chapter_id/path/source_revision`；路径限定到方向对应 input_jp/input_cn。缺章、空章、重复章组、额外/重复/乱序段、不同源版本或未知映射均拒绝；没有固定章数，也不扫描目录推定作品边界。范围完整性以独立冻结的导入清单为准，不证明导入清单之外的全书覆盖。

本项目 manifest 增加 `accepted_revision`，没有另一套数据库。由调用者显式指定每段 `target_field`；`build_accepted_revision` 只捕获既有当前非人类接受记录，逐段绑定源版本、目标字节、依赖身份、审查记录哈希。它不会创建或升级接受。draft 与 refined 无隐式优先级，选 refined 需要针对该文本的独立当前接受。更改任何已选文本、源、上下文/模型等已有依赖、审查或清单使旧 revision 失效。暂存期间即使内存选择与审查一起换成另一个有效版本，也必须与本次开始时的 accepted revision 比较并拒绝，不能提交先前快照。未选字段的编辑不改变权威版本。

正式 CLI 要求 `--selection-manifest workspace/manifests/<project>.json --selection-sha256 <exact SHA256>`。清单必须已含上述独立冻结范围、显式选择和当前审查。CLI 读取现有 review state，不发现 run 文件、不按 mtime 选择、不跳过缺失章节。旧 discover_canonical_files 调用直接拒绝。CN_TO_JP 共用同一接口并写 output_jp；这不证明逆向翻译质量。

导出前验证完整范围、既有接受和源文件实际字节，再从同一冻结字节用当前 parser 重建章节/段/binding 覆盖。完整 volume 和 manifest 先写入 `.revisions/<bundle SHA>/`，逐文件和目录 fsync，内容验证后才替换唯一 `.current` 符号链接。现有 volume/manifest 路径均通过该指针访问；manifest 绑定 accepted revision、源清单和 volume SHA。消费者需要一致读取时，必须通过 `read_current` 固定一个快照，不能将跨切换前后分别打开的别名视作一个事务。Workbench 状态只称快照完整性，不把磁盘完整性称作当前审查/人类接受。

旧常规文件先逐字节保存到旧快照，再转换别名；转换中失败仍可读取旧内容，首次转换可能新增指向旧快照的指针。无正式内容预清理、删除或全局替换。多余旧正式输出（含旧双语正式副本）、外来符号链接、部分旧文件、源/审查/清单在暂存时变化均拒绝并保留；在提交前再次检查。`.gitkeep` 占位文件保留且不计正式副本。现有 singleton 检查器在两个方向均验证新快照。过程崩溃在提交点前保留旧指针；提交点后消费者只能观察完整新快照；替换已发生但 fsync 观察报错时，按实际可验证指针核对结果，不盲目重试。此处验证普通进程退出/IO 异常，未模拟存储设备断电。

发布使用现有本机 checkpoint_lock，序列化本模块导出写者；提交前复核源、选择清单、审查和别名。它不是对不遵守协议的任意外部文件写者的文件系统 CAS。不可变快照保留恢复版本；快照 SHA 不包含其自身，manifest 亦不循环自哈希。暂存目录正常退出删除，进程崩溃留下的非当前完整快照不自动采用。未知或正在使用的文件不作为清理对象。

Workbench 的现有 manifest 导出继续是辅助候选预览，允许 approved 子集或显式 draft，`is_canonical=false`。译文、双语和辅助 manifest 使用同一 bundle 和项目专属指针；不会将辅助预览替代正式稿。实际 UI 导入→接受→唯一导出入口归 P2.R03.T02，领域接受服务和收益门归 P2.R04。

验证入口：隔离 `scripts/isolated_checks.py --entry pytest -- tests/test_canonical_export.py ... -q` 与 `npm run check:tooling -- --surface codex`。测试覆盖两个非固定章号、双方向、完整范围、显式 draft/refined、过期依赖/接受、同尺寸同 mtime 源变化、暂存后变化、IO/指针/提交前回调异常、旧文件迁移、普通进程退出、外来链接和辅助双文件失败。只在隔离副本运行，不触及真实正式稿。
