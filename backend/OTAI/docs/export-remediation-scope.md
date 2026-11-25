> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# 新工程导出整改：现有实现、可开发范围与启用边界

## 本次只读结论

static5 的 `current_archive/bundle_tools.py` 仍为原平面发布器，SHA256：`dd174b1294016d5cde798ab1d35f702e39832fd99042bd8908bbb6c24490e334`。本次未运行发布器、未写出工程、未运行原版。

在当前源码包递归检索，未发现恢复的嵌套 publisher、wave13 最终门槛实现或具体否决参数。另对当前共享目录有限深度的相关文件名检索也未找到该实现；这不是对所有历史备份内容的穷尽证明。当前只有旧审查摘要，不能还原被拒操作范围或宣称其通过。

**不是所有导出开发被禁止。** 合同设计、纯内存候选验证、只读代码审查可以继续；但不能借新路径、平面化或另写发布器重试范围未知的旧否决。用户要求修复不自动证明旧平台否决已解除。

## 已存在，不应重写或重复报功

- 新统一链已经生成七份档案与一份文本 run 的实际 bytes，并验证角色、引用、运行配置、哈希、长度及回执层级。
- 同一输入路径在多资源角色中必须具有一致 preimage，之后再次核对源字节。
- 平面发布器已有目录 FD/no-follow、fresh target/no-replace、成员落盘重读、源前后核对、目录身份和提交后错误语义。
- 支持 per-member validator；文本 run 必须用专用校验器，不能作为 typedstream 解码。
- 新工具 schema 仍固定 preview_only=true、没有 target；预览输出是摘要，不是已交付存档。

## 确切缺失实现/合同

1. 新候选为 `OTDocuments/<name>.opentrack`、`OTData/infrastructure.<六角色>`、`<name>.run`。旧发布器明确拒绝含分隔符的成员；其 empty_directories 只代表平面空目录，不能承载这些嵌套数据。
2. 没有获独立审查的“嵌套成员→逐级目录 FD→成员”事务实现及递归清理所有权合同。旧平面 cleanup 不能直接假设适用于嵌套树。
3. 没有新链保存接口的 target、预览/提交条件、提交后可查询的收据与重读接线。包装器不能仅更改 saved 布尔值。
4. 必须区分七档案 run-binding manifest 与全部八成员交付 manifest；额外 bundle-manifest.json 是包装元数据，不应被计为第九份业务档案。
5. 存档中的 Windows execution_root 与云端物理交付根是两个概念。应保留明确部署映射，不自动把 Windows 引用改成云路径。任何路径重定位必须重新验证 DestInfo/run，而非仅改文件名。
6. 提交前失败与提交后检查失败必须分别报告。后者应标 commit_completed=true，保留目标，禁止自动覆盖重试；不能将“检查失败”说成“未写出”。
7. Linux renameat2 与目标文件系统原子 no-replace 支持、目录持久化、最终路径重读需在具体允许环境验证。Windows只读候选不能承担发布器，Windows保存仍是独立合同。

## 可立即继续、无需运行发布器的工作

- 固化输入/输出 envelope：六角色源路径+SHA、完整不可变 preimage、准确八成员 bytes、候选校验报告、明确 execution_root/output_directory。
- 对正常候选做纯内存 role/manifest/run/DestInfo 契约检查；对未知元数据拒绝，不涉及真实路径替换或历史安全测试。
- 为未来嵌套写出绘制事务状态与所有权表：目录创建顺序、父 FD、成员所属目录、预提交失败清理、原子提交点、提交后失败收据。此为设计/审查，**不能据此偷偷接线启用**。
- 恢复原拒绝动作的精确记录，或取得平台对具体新审查范围的明确结论。用户意愿和平台执行许可应分开记录。

## 供审的普通云端 fresh-directory 验证方案（本次不执行）

### A. 旧平面发布器的独立控制实验

目的仅验证已存在平面保存路径在选定 Linux 文件系统上的普通工作条件，不证明新嵌套工程可导出。

- 环境：云端 Python3.13；独占新验证根，例如 `/workspace/shared/opentrack-export-validation/<批准的唯一ID>/`。
- 数据位置：该根下 `OTProjects/sources/` 放经授权的用户自有/自制合法档案副本，记录各 SHA、长度、用途；不得包含供应商二进制或未经授权原件。
- 目标：该根下预先存在的 `OTProjects/exports/` 中一个明确尚不存在的 `flat-control-<ID>`。目标不是任何源的父目录，不覆盖任何既有用户文件。
- 输入：最少一份正常合法、<=20MiB 的已有 typedstream 成员；如验证 run，须完整六目录/文档绑定且提供独立文本 validator，不以任意文本充当合法存档。
- 一次正常保存，随后全成员字节/SHA重读、manifest角色核对、源字节不变、目标清单与提交收据一致。不得运行旧攻击/竞态/替换测试；目标已存在时不覆盖。
- 所需明确范围：根确认此准确动作不属于历史被拒操作，或取得相应平台允许结论；用户确认具体授权源与云临时根。若原有用户指令已涵盖自制样例和独占云临时目录，无需重复泛问“允不允许开发”，但应记录具体依据。

### B. 新八成员嵌套工程的保存验收

A 的通过不能代替 B。只有旧否决边界可排除或适用的新审查明确允许后，才能提交一个经过独立审查的嵌套实现/接线方案；不得用“另外一种发布器”绕开旧问题。

最小验收同样使用独占云根及明确不存在的目标，实际保留 `OTDocuments/`、`OTData/`、run和声明的空输出目录；提交前与最终位置都对全部八业务成员重读并验证七档案引用/run与全部交付manifest。只验证正常合法输入，不执行被拒历史安全测试，也不运行OpenTrack。结果只能称“云端存档写出/重读通过”，不能称Windows原版加载或一日仿真通过。

## 当前停止点与需要的最小决定

当前可以完成上述纯数据和事务合同开发；**新链写出尚不能启用**。缺失不是一句泛泛“没有权限”，而是：原wave13否决操作范围未恢复、当前嵌套实现未恢复/未审，以及具体新云目录/输入与适用验收范围尚未确定。根应先确认允许评审的具体方案；如果无法排除与原拒绝范围重叠，应停在设计/纯内存验证，报告精确缺口，不尝试替换路径。
