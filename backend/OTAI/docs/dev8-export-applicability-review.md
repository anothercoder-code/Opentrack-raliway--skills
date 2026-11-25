> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev8：既有平面发布器对新八成员候选的适用性审查

## 结论

**不能把 dev4/dev5 的八成员映射原样交给原 v11 `publish_bundle`。** 关键不在于成员有八个，而在于新候选使用 `OTDocuments/...`、`OTData/...` 嵌套成员名；旧发布器明确只接受平面文件名。其 `empty_directories` 也只是平面、保持为空的目录，不是把文件放进这些目录的能力。

这不是“所有文件写出都被禁止”。既有 `opentrack_generate_current_operating_archives` 有独立的平面生成＋正常新目录保存调用链；此前保存/重读证据只属于那个已测试的数据和发布范围，不能自动证明新嵌套候选可以交付。本轮**仅静态阅读**，没有运行发布器、没有新写入实现或原版执行，也没有重试历史安全测试。

## 本轮核对的代码

冻结 dev6 源码：

- `current_archive/bundle_tools.py` SHA256 `dd174b1294016d5cde798ab1d35f702e39832fd99042bd8908bbb6c24490e334`，与留存 v11 发布器一致。
- `current_archive/operating_generation_tools.py` SHA256 `7f0262952060d500688f0875d95c5c3b21f3a16311310dcac2b51b4db19724c8`。
- dev4 `operating_chain_workflow.py` SHA256 `966a4790fd84c5eaeaa4d54c81542275109be64e1143a7117db9c3b955870d3c`。
- dev5 `final_stop_workflow.py` SHA256 `74bb2520897017d859b7d343c21deedc039ea54b0e36982ab7c69f1a8ac7b5dc`。

哈希用于标识本次阅读版本，不是功能或安全通过证明。

## 逐项契约差异

| 条件 | 旧 v11 发布器／既有调用链 | dev4/dev5 新候选 | 判断 |
|---|---|---|---|
| 文件布局 | `publish_bundle`拒绝名字内 `/`、反斜杠、空名及保留manifest名；全部文件放在一个新目录 | 一个`OTDocuments/<name>.opentrack`、六个`OTData/infrastructure.*`、根目录`.run` | **直接不兼容**，调用会在写入前拒绝嵌套名 |
| 空目录 | 只允许平面目录名，并检查它们确实保持为空 | 输出目录声明通常为`output`；OTData/OTDocuments必须含文件 | `output`可能符合；两个数据目录不能冒充空目录 |
| `.run`验证 | 默认每成员按typedstream档案读取；既有OperatingGeneration专门给`.run`注册`verify_manifest`回调 | `.run`是文本，receipt绑定其余七成员 | 必须提供正确run专用validator，不能默认解码，也不能空函数跳过 |
| 跨文件引用 | 原平面调用链在生成时就使用平面document/catalog路径 | DestInfo和run保存明确Windows执行根下的嵌套路径 | **不能仅取basename压平文件名**；否则文件位置与引用分离 |
| Manifest | 调用者构造`manifest.files`、sources及result；发布器写出manifest和成员，但不自动从业务意义证明整个manifest | 新wrapper仅返回hash清单；run receipt覆盖七档案而非完整八成员交付manifest | 需要有清晰的完整八成员manifest和run receipt层级，逐字节对应，不能把两个对象混用 |
| 来源快照 | `inputs`须是每个实际路径对应唯一不可变preimage；既有OperatingGeneration拒绝同路径不同preimage | 新wrapper各角色按SHA读取，`inputs[path]=blob`最后值覆盖同路径较早值 | 暴露保存前应显式拒绝重复路径的矛盾preimage，不能只依赖最后一次路径记录 |
| 文件大小 | 每成员20MiB，读取也为20MiB | 新wrapper另有合计256MiB上限，候选输出未统一以发布器20MiB界限定义 | 必须保留更窄的既有成员上限并明确失败，不隐式扩大 |
| 保存请求 | 既有schema有preview/显式fresh target；publisher读取`result.preview_only` | 新schema `preview_only: Literal[True]`，无保存目标，返回`saved=false` | 不是已接好“切换开关”；新增接口语义需要独立review |
| 目录事务 | Linux `renameat2` no-replace；已有父目录；dirfd/no-follow；只清理自身记录的staging对象 | 尚无新候选到此事务的可用适配 | 不得降级普通rename/overwrite，不能另建写入路径绕过限制 |
| 保存后状态 | 原发布器区分未提交失败与`BUNDLE_COMMITTED_POSTCHECK_FAILED`，后者明确禁止当作可覆盖重试 | preview无这些交付状态 | 适配必须保留提交/回读/耐久性状态，不把异常统一报“没有写入” |
| 原生执行根 | 保存目录为云服务器受限相对路径；`.run`中的Windows执行根只是声明 | 两个新域同样只做静态声明 | 保存成功也不证明Windows根存在、原版可访问或仿真已运行 |

`ArchiveTools.path/parent_fd`还限定目标在授权数据根下`OTProjects`或`OTAI/workspaces`，不接受绝对路径、上跳或跟随符号链接。目标须不存在，不得包住或等于输入。现有父目录可用性、Linux文件系统支持和大小边界都不能由用户请求“完成”推断为自动满足。

## 直接暴露写出还缺什么

1. **确定要交付的准确布局**：保留现嵌套八成员，还是另行设计平面候选。当前旧发布器只支持后者的平面事务，但**现有新候选不是平面候选**。
2. 对保持嵌套布局的实现，需要独立核对目录层级、成员及目录冲突、来源快照、实际stage对象所有权、no-replace提交、部分失败清理、提交后失败回执。旧flat审查不能代替这些证明。
3. 若考虑平面布局，必须先做纯数据层的准确DestInfo/run路径和manifest重建审查；这属于新的语义适配，不是“改几个名字就复用”。**不得用它作为重试历史被拒操作的替代路径。** 本轮没有实现这种适配。
4. `.run`专用验证必须绑定本次实际七个档案；完整八成员外加发布manifest的交付receipt须准确区分。维持Course/Train/Engine/Station/Itinerary、绝对时间和速度索引检查。
5. 在适用操作范围明确后，才可做专门的正常新目录保存→独立读取→全部引用重读回归，并记录源字节不变和真实文件路径。只读源码审查、内存重读或hash清单不等于这项通过。

## 历史限制与精确阻碍

- 已知历史wave13最后独立嵌套发布/事务安全审查被中止，但具体被拒调用、参数与范围未恢复。**不能把它说成已通过；也不能从摘要推断所有正常平面保存都被禁。** 当前明确指令不允许重跑该测试、运行发布器或新增替代写入，本轮严格遵守。
- 原版IPC/启动验证另有明确阻碍，本审查不重试。它与“能否静态保存正确文件”是两项不同状态，不能把IPC阻碍用来掩盖尚未完成的导出适配。
- 对新嵌套八成员，当前确切缺口是**适用的导出契约/独立review及获准范围内的实际保存回读**，不是仿真内核，也不是缺少用户希望完成工作的表达。

## 最小合法下一步

先保留可复现的内存候选和完整内容验证；记录八成员布局、权威原生路径、sources/preimages、run专用validator和预期交付receipt。由主任务恢复或明确历史拒绝的操作边界，选择一个不构成同一被拒操作重试的、适用的独立审查范围。范围确定后，仅对具体允许的正常fresh-directory保存执行回归；未明确前不运行发布器、不复制新发布器绕路。

既有v11平面生成保存能力可作为单独范围评估是否满足某个明确用户场景，但不得替换用户的新终停模型、偷偷重新生成固定样例或把它的保存成功挂到dev4/dev5候选上。本审查不作这种替换，也不执行任何保存。
