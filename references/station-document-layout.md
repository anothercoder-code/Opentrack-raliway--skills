# 一站一文档与既有工程修改

**案例与合同边界：**本文涉及的站数、股道数、网格或走廊是现成辅助入口和验收案例的范围，不是所有复杂设计的固定规定。其他设计先按[需求组织设计](complex-design-workflow.md)，再选择符合实际合同的实现路径。

铁路工程默认采用 **一个 `.opentrack` 拓扑文档放一个车站**；用户明确接受的教学或
技术验收样例可以例外。车站文档应容纳本站站线、咽喉、站台、局部进路和信号，
采用稳定站名或站码。区间归属须明确，必要时可以另设区间文档。

相邻文档通过明确的边界和成对连接器相连，不能由屏幕上的端点接触推断连通。
Engine、Train、Course、Station、DestInfo、Timetable 等目录及 `.run` 在工程级共用；
“一站一文件”不要求按站复制公共目录或车辆。跨文档身份采用文档名与本地对象 ID
共同核对，连同连接器两端、Path/Itinerary 连续性、站序和运行绑定一起校验。

## 修改现有工程

默认沿用原 `execution_root`、同一组正式文件路径及已核实的文档身份；不要每改一轮
就创建一个新的正式工程、改名搬家或重新导入运行配置。修改流程只维护一个明确的
待替换 patch 候选，正式工程在替换前仍是原文件。

1. 读取当前实际文件，记录每个受影响成员的路径、身份及 `before_sha256`，列出字段
   差异和依赖闭包。保留可校验的原字节备份、哈希和原路径映射，形成明确的恢复凭据。
2. 参数调整只修改命中的字段，不为满足旧工具的狭窄条件重置无关限速、方向、车辆、
   物理参数或信号配置。必须重建拓扑时，候选只覆盖受影响的图及其依赖的 catalog/run；
   保留无关数据，并验证所有引用。未改对象的 UID/ID 在兼容性可证明时保留；结构改变
   需要新身份时显式分配并重绑，不能承诺强行保留已不兼容的旧 ID。
3. 对候选做实际字节重读、字段差异、图和跨文件引用检查。替换前重新核对原身份及
   `before_sha256`；源已变化就停止，用新读取结果重新形成候选，不能套用旧 patch。
4. 先关闭持有受影响对象的 Inspector，再让 OpenTrack **真正卸载所有受影响的旧文档**，
   并处理完相关 dirty 状态。若闭包包含共享 catalog 的内容变更，还须卸载相应目录
   控制器的缓存；只关闭图形文档不够。无法证明已独立卸载目录缓存时，应在替换前正常
   结束受控的原版会话，处理明确的修改提示，再写文件并重新启动。不能先改目录文件、
   后让旧进程退出，因为退出可能将旧内存目录写回。隐藏窗口或再次 Open 一个已打开
   文件不算卸载；同一路径绑定正确也不证明 catalog 内容已重读。具体操作见
   [用户指导流程](user-guided-operation.md)与[Inspector 生命周期](inspector-safety.md)。
5. 通过已有授权、具备上述前置检查与恢复凭据的有限替换流程提交这个闭包，记录逐项
   结果；失败时先确定实际已替换范围，再按恢复凭据恢复并重读核对。提交状态不明时
   保留目标与候选，先核实身份，不能盲目重试或回滚。不得声称多个文件的逐项替换
   天然是一个原子事务。随后从同一路径真正重载，复核活动绑定和语义；改过的共享
   catalog 还要核对实际行程、列车、车次、站序等内容，不能只看路径文字。

新建发布器的 fresh-only/no-replace 契约保持不变：
`opentrack_initialize_station_documents_project` 与 `opentrack_initialize_project`
不会因此变成 overwrite 接口。它们可以按自身契约生成新候选，但不能冒充现有工程的
覆盖工具；没有受支持的有限替换实施路径时，应明确说明尚待完成的替换步骤。
这里的“同一文件”指既有正式成员及其可验证身份；原子替换可能产生新的磁盘 File ID，
不能把相同路径误报为物理文件身份从未改变。

## 站场必须有真实拓扑

- 对要求真实咽喉与多股道接发车的站场，按站型提供实际相连的站外段、进出站咽喉、
  道岔分支、方向、按需设置的站台及相应进出站信号，并给出可追踪的运行路径。不能只用平行线和
  站台矩形代替要求的咽喉，也不能由这些图形证明线路可达；简单停靠点另按其需求处理。
- 原生道岔由 paired End 及实际 Edge 分支连接表达，不新造 `Switch` 存档类。分支
  所在 End 半边决定允许的运动；逐条验证来向、正线/侧线和出向，不以图上交叉代替连接。
- 每段分别给出图上起终坐标/绘图长度与物理长度（米），以及方向限速等必要参数。
  例如图上 100 单位、物理 500 m 是两个独立值，不按屏幕比例相互推导；主联程里程
  应由实际 Edge 长度复核。参见[显式网络生成](wave9-network-generation.md)。
- 站外主线数、站台数、各方向接入和可达关系受原需求约束。“4组复线”须保留原话并
  解释究竟指四对八线还是其他组织；不能静默改成两条主线。站内股道数并不自动决定
  站外正线数。只有明确选定时，才使用例如“8股道、4座岛式站台、2条正线”的方案；
  这只是一个具体布局示例，不是其他站场的默认模板，也不能冒称用户已接受未确认的参数。

Station 新建布局使用 `alignment_x=0, alignment_y=0`。新 Signal 必须绑定实际 owner
End 并使用该 End 的方向对：水平 `(1,0)` 或 `(2,0)`，垂直 `(0,3)` 或 `(0,4)`；
不把 Station 的 `(0,0)` 套给 Signal，不从名称或示意图自动猜向。既有原生对象的
对齐值按修改契约保留，不能为了新建 profile 静默归一化。位置字段中的 `width/height`
不是对齐值，不能自动迁移；详见[图形对齐](graphic-alignment.md)。

Main 信号必须按真实方向将运动切成相邻主信号之间的 Routes，不能跨越中间主信号
构造一个 Route；Path/Itinerary 再连续组合这些 Routes。Safety 应按实际共用轨道、
道岔及冲突运动绑定资源；既要验证共享通行路径可达，也要验证方向冲突受到互斥。
共享区段不能继续使用“所有通行路径资源必须 disjoint”的旧判据：资源交集本身不是
错误，漏锁真实冲突也不是通过。静态资源检查不能替代原版调度和冲突验收。

## 当前入口与独立验收

### 三站八股道站场 CLI

本 Skill 的 [scripts/yard.py](../scripts/yard.py) 提供独立的有界站场入口，不依赖
旧工程、历史候选、E-yard 回执或本机用户目录。它从六份实际原生资源生成空白图中的
三个单站文档：每站 8 股道、4 座岛式站台图形、12 组真实 paired-End 道岔、16 架
方向信号及 15 个英文 Label；站外有 2 条正线（一条 D、一条 U）。每方向的四条
站线共用咽喉和区间，8 条行程各长 10 km，9 个车次包含间隔 15 s 的 D1 追踪车。
岛式矩形是图形，不表示已建立旅客站台容量模型。

使用配套 Python 3.13.x 和当前 backend `0.33.1-zeroaccept1`。准备 UTF-8 JSON 请求，
顶层精确包含：

| 字段 | 值 |
|---|---|
| `schema` | `three-station-yard-request/1` |
| `sources` | `header`、`shapes`、`depot_template`、`trains_template`、`courses_template`、`timetable_template` 六项，每项为实际 `{path,sha256}`。路径相对 `--root`，须在其 `OTProjects` 或 `OTAI/workspaces` 下；SHA 为实测小写 64 位十六进制。 |
| `recipe` | 精确 `{stations,execution_root,block_profile}`。`stations` 按联程顺序给出三个 `{id,name}`；ID 为唯一英文标识，name 为英文可打印文本；`execution_root` 为实际执行目录的规范 Windows 正斜杠绝对路径；`block_profile` 固定为 `eight_platform_two_mains_5km`。 |
| `accept_proxy_physics` | 必须显式为 JSON `true`，接受该有界方案的继承代理物理模型及未标定范围。 |

资源不随 Skill 分发。当前有界车型选择固定为 `CR400AF_8_PROXY_350` Engine/Train、
`Category 1`、`G1046` Course 和 `G1046#0` 无连接时刻表模板；Header 还须满足实际
type25 区间信号、灰色调色板及已审查 OTLabelModel1 golden。Header 的已验证 SHA 为
`8323d7f1486c1754c5a1d320ba10e27fe2bfa57cf394cb3753f30742a67d4de6`。
这些是格式/车型继承资源，旧轨道会从派生空壳中移除。缺少匹配资源时先用资源检查
定位实际文件，不用占位 SHA 或擅自换车型来通过验证。

接口形式如下；`reviewed-yard.json` 必须先由 agent 用实测资源和目标值准备完成：

```text
python -X utf8 -B scripts/yard.py preview --root <authorized-data-root> --request <reviewed-yard.json>
python -X utf8 -B scripts/yard.py stage --root <authorized-data-root> --request <reviewed-yard.json> --target OTAI/workspaces/<fresh-stage>
python -X utf8 -B scripts/yard.py publish --root <authorized-data-root> --request <reviewed-yard.json> --target OTProjects/<fresh-project>
```

`preview` 只输出候选与引用验证回执，不写工程。`stage` 只向新的工作区目录写出 17
成员，返回 `staged=true,published=false`；其实际暂存路径不要求等于运行绑定，不能
因此直接声称工程已发布。`publish` 要求 `recipe.execution_root` 等于实际新目标，
复用既有 Windows x64 固定本地 NTFS 的 handle-backed 完整工程发布器：来源重查、
原子 no-replace、17 成员及空输出目录完整枚举、写后 SHA 和依赖闭包重读。既有目标
会被拒绝，没有 overwrite 参数。现有工程修改仍使用本页前述原位 patch 流程。

17 成员为三个 `.opentrack`、正常/故障各六个目录和 `eighttracks.run`/`failure.run`。
两场景共用三个站图，输出分别为 `output` 和 `output-failure`；固定运行窗口为
09:00–09:20、Step 0.2 s、Delay Scenario 0，Break Time 默认 00:00:00，便于无人值守
原版脚本运行。故障场景选中首站实际共享 D 向 B2 信号的 09:00–09:06 通行封锁；
该事件不直接写灯色，也不撤销已授予的进路。

### 校验同一工程的实际原版输出

[scripts/yard_audit.py](../scripts/yard_audit.py) 是此 profile 配套的结果校验器，支持
上述任意三个合规英文站名。先保留 `yard.py` 的完整 JSON 回执；在 PowerShell 中
可将其 stdout 通过 `Set-Content -Encoding UTF8` 写到当前工作区的明确 `.json` 路径，
避免默认重定向写成其他编码或工具输出被截断。校验器不启动原版、不修改正式工程。

在首次打开原版或运行前，选定输出目录须为空，执行 `capture`。它读取实际17成员，
按回执 SHA 核对生成前态，重新解析存档并重建轨道/道岔/共享区间资源，将输入与回执
快照写入同一工作区证据目录。`--project` 和 `--evidence` 都是相对 `--root` 的路径，
证据必须位于 `OTAI/workspaces` 且在正式工程之外。

```text
python -X utf8 -B scripts/yard_audit.py capture --root <data-root> --project OTProjects/<project> --evidence OTAI/workspaces/<acceptance> --label normal1 --scenario normal --receipt <full-yard-receipt.json>
python -X utf8 -B scripts/yard_audit.py verify --root <data-root> --project OTProjects/<project> --evidence OTAI/workspaces/<acceptance> --label normal1 --scenario normal
```

两条命令之间执行当前工程的原版加载、保存、真正重载及实际仿真；文件读取回执不
代替这些界面动作。`verify` 使用已经保存的回执和输入快照，检查新产生的9车、27站序
事件、各10km行程、实际终到零速、原生告警、128项共有区间预约/释放与故障停车恢复。
输出必须指向同一工程，实际 Delay/黏着/性能/速度类型/事件选择须符合这份 profile。
所有 WARNING 保留原严重等级，未知告警或 ERROR/FATAL 失败；不是要求排队场景零告警。

原版 Save 引起的限定窗口/文本适配及不可变值共享差异须重新逐字段核验；车辆、
信号或其他业务字段改变会被拒绝。退出时选中场景的实际时刻表写回，只允许实际
到发时间及实际日偏移四字段，并逐项对照本次原版 TT/VT 输出。另一个场景的时刻表
若在本次捕获后变化则拒绝。若有明确的临时断点及恢复操作，显式添加
`--allow-break-control-changes`；仅归因 Break Time 一项，其他运行字节仍受保护。

故障场景另用 `--scenario failure` 和独立 `--label failure1`，保持正常输出原样。
若此时工程已经被原版保存或写回，`--reference` 指向第一次 capture 保留的
`OTAI/workspaces/<acceptance>/normal1-reference`，沿用同一份生成回执；不必再生成
一个正式工程。已有输出需先保留，再以新标签捕获下一次实际运行的空输出前态。

原版头部时间默认按 `--producer-offset +08:00` 解释，应与实际生产环境一致。
producer 跨度默认不超过60s；人工暂停的真实会话可显式调整
`--max-header-span-s`（最大600s），并记录本次理由，不覆盖先前失败结果。
解析器会在结束时重查输入、输出、快照、基线及回执原始字节，拒绝检查中途的漂移。

此校验不观察屏幕，也不单凭文件证明实际运行了哪个 EXE。动态灯色、GUI结束状态、
原版保存/重载操作仍需当前原版观察和启动证据。车身净距结果依赖明确的坐标/采样
误差包络；0.5m单步位置纠偏不等于全局连续误差界。终到后未导出的最终咽喉释放
不能由终到或零速度推造。

生成、暂存和完整发布都属于保存数据能力，不会启动 OpenTrack。原版 Save/重载、
各车次跨文件运行、共有区间占用/释放、故障停车恢复及动态红黄绿显示须对这份新工程
分别验收；不能继承当前本机或历史 ZF 工程的仿真结果。

[一站一文档发布入口](station-documents-project.md)的受限 profile 是 2–12 站简单
线性链、N 个单站文档、六个共用目录和一个 `.run`，只支持一个向前末站停车车次。
它是技术基线，不代表上述真实咽喉站场、任意分支或多车冲突已经实现和验收。
既有 inventory、Path/Itinerary 派生、A↔B、线性链及有限拓扑预览仍各有自己的 schema
和保存边界，不能把预览回执称为已交付工程。单文档八成员入口也不能用于拼接联通的
多站工程，或为迁就发布器把全部车站静默合并回一个文档。

每个新工程或实质性修改都分别记录以下验收，历史样例结果不自动继承：

按当前任务与用户授权记录各项状态；未要求或未执行的原版步骤标为待验，不因维护
Skill、检查文件或报告状态而自行扩大到桌面操作。用户停止 GUI 后须保持停止，直到
明确恢复操作。

- **数据与替换：** 实际落盘成员、哈希、未改字段及恢复凭据，连接器、跨文档引用和
  catalog/run 活动绑定一致。
- **原生布局可见：** 每站单独打开，图形、咽喉分支、站台和信号朝向与设计相符，
  Inspector 显示当前真实选中对象。
- **原生保存与重载：** 对确实 dirty 的目标 Save 后读回，再真正卸载并从原路径加载。
  对 clean 文档按 Save、仅聚焦已打开窗口或查看时间戳都不能替代这些检查。
- **运动与冲突追踪：** 逐方向追踪实际路径、站外接入、跨文档边界、到站停车，检查
  共用资源依释放顺序的同向通行与对向/交叉互斥，再核对 Course 与全程结束。

实际原版步骤及证据分类见[用户指导流程](user-guided-operation.md)；限定三站历史
结果见[英文三站起步](zero-start-three-station.md)。加载、可见、保存、重载、轨迹和
调度是不同验收项，不能用候选生成成功或某一项通过代替其余结果。
