# Bundled backend: current scope and historical records

Current product scope is defined by [the enclosing Skill](../../SKILL.md),
[edition boundaries](../../references/editions.md) and discovered schemas.
Full exposes the maintained implemented tool set; its convenience generators and tested examples do not define all permitted railway designs.
Both editions require [full original-software authorization](../../references/software-authorization.md).

The text below is a **retained historical maintenance log**. Its words "current",
"candidate", "not installed", "only static", "not yet accepted" and test counts
refer to the named dated snapshot, not the latest maintained distribution.
In particular, an old three-station or fixed-25-document result is not the
capability boundary of every project; separate later cases have their own evidence.
Consult [current acceptance scope](../../references/acceptance-levels.md) before reporting status.
Old Station+Signal `(0,0)` generation assumptions are historical and superseded:
new Signals must match their actual owner End; Station `(0,0)` remains separate.
Do not infer a current permission restriction from a copied old task record.
Current user authorization, full-software entitlement, real input contracts and
applicable platform approval decisions still govern the actual operation.

---

# OpenTrack saved-data interface：现有版本维护状态

## 2026-10-30 inplace1：直接维护现有 Skill

在原有 source、工作区 payload、安装版及用户下载目录内同步维护，不再建立正式工程
或另一个 Skill 副本来代替修改。配套协议版本保持 `0.33.1-zeroaccept1`，本次维护由
manifest 的 `maintenance_revision=inplace1` 标识。

已合入新 Signal 必须匹配实际 owner End 的代码、公开 schema 和生成后验证；
现有 source 定向回归49/49通过，无跳过、失败或错误。早前独立候选的172项组合测试
为169通过、3跳过，与49项存在重叠，不相加成覆盖数字。

Skill 默认已有工程同路径修改，保留一站一文件及无关参数；候选与正式工程分离，
但不能停在候选回执就声称已修改当前工程。真实站场须有连接的咽喉、道岔、站外段、
信号与进路，图形尺寸和物理米分开核对。缓存刷新、写盘、重载和仿真分别举证；
焦点误投后停止试探并给用户单步恢复指引。当前八股道新站场仍只完成离线数据，
原版保存、重载、合流运行及闭塞故障恢复未验收。维护 Skill 不改变这项状态。

## 历史：2026-10-30 blockalign1 新 Signal 方向修复候选

独立的 `blockalign1-20261030/OTAI` 源副本修正新生成 Signal 的方向约束；版本暂保留
`0.33.1-zeroaccept1`，未安装或制作发行包，不改旧源、安装版或当前三站工程。
Station 仍可采用 `0/0`；新 Signal 必须匹配实际 owner End，水平为 `1/0` 或 `2/0`，
垂直为 `0/4` 或 `0/3`。Signal schema 拒绝 `0/0`，共同工厂还拒绝与该 End 不一致
的方向。既有档案检查、配置和原生保真克隆保留源值，不静默归一化旧 Signal。
以下 zeroaccept1/staticfix1 测试与原版事实均是历史记录，不是该源副本的新回归结果。
方向字节与引用的静态检查不能证明灯图可见、三显示、追踪、故障安全或 Inspector 安全。

## 历史 zeroaccept1 三站单车候选与原版记录

当前候选使用Python3.13.x，generation/all仍为102/121工具；未安装或制作最终发行包。
只增加新Engine/Category输出名的现有cf.name ASCII前置校验，原模板lookup身份行为
不变，不增加API或原生桥。其他生成逻辑沿用staticfix1。

当前候选静态组合166项：163通过、3跳过、0失败/错误。主进程165项，原始严格
process-global handle计数测试单独子进程1项；没有改断言或生产来掩盖资源泄漏。
三跳过为OS文件symlink权限不足和两个固定网格私有fixture缺失。此前受限沙箱的
Access denied cohort及共享进程handle计数181!=180 cohort均保留，最终组合另存。
AST265个文件、93份Markdown的127个本地链接、版本配对和102/121发现检查通过。

该历史案例见[英文三站流程](../../references/zero-start-three-station.md)：
线性三站、一站一文件、共用六目录、单动力单元单Course、起点发车中间通过末站停。
2–12站只是数据层输入范围，当前实机对象为ZF_A/Alpha、ZF_B/Bravo、ZF_C/Charlie。
所有新名称/路径使用可打印English/ASCII；proxy模板physics继承不代表重新标定。

当前证据分层：新声明十成员经CLI/MCP生成、发布、独立字节比对和引用检查；首次
stock原版ZF1001跨两个文件边界完成3.2km联程并末站物理停车，共46输出，实际Delay
Scenario为1。GUI三文件全部加载并原版Save；独立检查仅root frameRect/viewRect/
visibleRect变化，各文档23模型及Route/Path/Itinerary展开语义不变。

随后已在完整导入六目录后完成三文档Save/reload、Alpha/Bravo/Charlie三站真正
双击Inspector更新，未加载guard。GUI2的43输出含1条Origin warning，保留该失败。
Preferences Import之后执行原生Open→Cancel触发updateWhenInvisible:1，再Ctrl+5
确认ZF_TRIP/Length3200/Paths1of1/Routes2后Start；GUI3冻结43新输出、0 WARNING/
ERROR，同样3.2km/末速度0/Course08:07，十个本轮保存输入及72原始文件哈希不变。
未改Train或加入bridge以清警告。

原始CUA终态显示Current Time/End08:12、7条绿色消息，并获独立视觉复核；原生磁盘
文件没有End事件，普通GUI进程仍存活，不用exit码推断窗口完成，也未伪造PNG。
此限定英文字段、三站单车线性流程通过；不能据此宣布所有工具GUI通过、全2–12站
实机通过、完整176项等价或独立Inspector guard已运行验收。
原版运行会写回实际时刻和目录状态，应保留前后快照做语义复核，不得清除结果来强过
fresh initializer的未运行输入断言。

# 历史 0.33.0-staticfix1 静态修复与回归

当前配对 Python **3.13.x**，generation profile **102** 个工具、all profile **121** 个工具。
这些计数是发现清单，不是原176项功能的完成比例；完整原功能等价仍未完成。

保留工具 `opentrack_initialize_station_documents_project` 支持从六个真实 SHA 绑定模板
生成 2–12 站简单线性链，每站一个 `.opentrack` 文档，共用六个运行目录和一个 `.run`，
合计 N+7 成员。范围为同日单动力单元、一个向前车次、只在末站停车；不支持分支、
循环、中间停站、反向运行、折返或车底周转。原单文档初始化工具独立保留。

Windows x64、固定本地 NTFS 已支持原生句柄完整目录枚举，解锁既有多文档 inspect、
跨文档 Path/Itinerary 派生和 A/B/线性站链预览；旧预览仍不保存。新发布器实际保存
N+7 成员，以整目录原子无覆盖提交，并独立读取全部字节、引用与路径绑定。
源变化、已有目标、错误目标路径和损坏候选会拒绝；提交后失败保留已提交目标。
状态不明的提交不得当作回滚清理。文件缓冲已刷新，目录项断电持久性未认证。

当前三站示例按 REL_A、REL_B、REL_C 重建成三个单站文档，站参考点里程仍为
0/2/4km，主联程4km。各站两侧500m站区和外围线路是明确的新布局，不能称为
旧档案的逐字节切分或全部几何不变。原例和旧发布包保留。

该历史轮次只执行静态、离线数据及部署检查，未启动或操控 OpenTrack。生成入口统一
使用 `alignment_x/alignment_y`，支持已审通用组合 `0/0`、`1/0`、`2/0`、`0/3`、
`0/4`，拒绝混合非零组合及旧 `width/height` placement 字段。当时把 Station 与
Signal 一并设为 `0/0` 的生成假设已由上面的 blockalign1 源副本更正：新 Signal
必须匹配实际 End，而 Station 可以保留 `0/0`。原档通用读取和原生克隆保留原值，
真实画布尺寸不受影响。

该 staticfix1 历史组合静态回归 **162项运行：159通过、3跳过、0失败、0错误**；一项需要系统
文件 symlink 权限，两项缺固定网格原始私有 fixture。公共对齐入口专项13/13、
共用契约7/7。跳过项不算通过，这些检查不包含原版进程执行。

独立英文 Inspector guard 针对旧 `selectedGraphicModel` 生命周期问题；与对齐数据
修复分别验证。`--check` 只作严格 PE 文件检查；未来显式 `--launch` 仅创建自身新
child，并以 `WH_GETMESSAGE` 绑定该 child 的自身线程，不附加旧 PID。
编译、离线测试和安装不等于原版加载成功，`runtime_verified=false`。
见 [对齐字段](../../references/graphic-alignment.md) 与
[Inspector安全边界](../../references/inspector-safety.md)。

## 历史 winmulti1 运行观察与后续崩溃

该历史版本合并回归 **139项运行：136通过、3跳过、0失败、0错误**。一项因 OS 无文件 symlink
创建权限跳过；两项缺固定25文档网格所需八个原始私有 fixture，未用其他 donor替代，
该网格仍未认证。核心、Windows目录枚举、发布事务和既有多文档CLI流程均有专项证据。

历史 winmulti1 三文档原版联程曾完成：全新原版进程导入 `release.run` 后自动加载
REL_A/B/C，Ctrl+5刷新REL_TRIP，Ctrl+9启动。原版事件分别记录 REL_A 06:01发车、
REL_B 06:02:50通过、REL_C 06:04:34到达，证实经过两处文件边界；末两条速度为零，
统计4km/1次站停/0次进路制动/0次信号停车，Course结束06:07，GUI仿真结束06:12。
Messages全程NORMAL、无WARNING；`OT_Protocol.20261029-2035.txt`记录本工程三文档
和六目录。随后用户双击车站图标发生原版 Inspector 崩溃。既有仿真事件保留为历史
运行事实，不能作为 GUI 编辑安全、修复后数据或当前 guard 的原版验收。

详见 Skill 的 `references/station-documents-project.md`，以及验收机
`D:/opentrack/integrations/winmulti1-20261029/evidence/native-summary.json`、
`evidence/station-documents-original-contracts.json` 和
`D:/opentrack/integrations/winmulti1-20261029/发布与多文档全流程验收报告.md`。

## 历史 winrelease1 单文档有限范围发布

该历史版本配对 Python **3.13.x**，generation profile **101** 个工具、all profile **120** 个工具。计数是接口清单，不是176项原功能的完成比例；完整原功能等价仍未完成。

本版支持 Windows x64、固定本地 NTFS 上的真实安全读档、新目标单文件保存和完整八成员新工程发布。新工具 `opentrack_initialize_project` 从空拓扑构建显式单文档线路，依赖六份 SHA 绑定的格式/车辆/服务资源；支持通过或末站正向停车的受限 profile。实际发布嵌套 `OTDocuments/`、`OTData/`、`.run` 与空输出目录，原子无覆盖提交后重新打开、核验身份、逐字节重读和跨文件引用。其他预览接口不因此自动获得保存能力；旧 Linux 增量 catalog bundle 发布器在 Windows 仍不支持。

最终组合测试 **86项运行，85通过、1项因系统符号链接创建权限跳过，无失败**。真实 junction、硬链接、源变化、提交竞争、故障与清理分支经过本机测试；跳过项不等同于验证通过。逐文件缓冲已 FlushFileBuffers；目录项断电持久性未认证。

本机原版 OpenTrack 1.7 已完成有限场景的空图生成→安全保存→加载→仿真闭环：`Release_FromZero_20261029` / `ReleaseLine`，`REL1001` 于06:01从REL_A发车、06:02:50通过REL_B、06:04:34到达REL_C并实际停车；原版统计为1次站停，Course结束06:07，GUI仿真窗口结束06:12。须在加载后打开 **Itineraries（Ctrl+5）** 使本地 Itinerary 列表刷新，再启动仿真；复验后的原版消息日志没有 WARNING。此前未刷新时原版使用外部信息重建临时 Itinerary 并发出 Origin 警告，其触发链已单独追溯。

这是同一版本、同一工程在本机的受限实跑验收，不认证任意站场、跨文档调车、中间停站、折返、车辆周转、物理参数标定或176项全部等价。Skill/MCP 数据工具自身不会启动原版；原生验收通过电脑操作另行完成。测试及原版运行证据见本次发布报告和 `D:/opentrack/integrations/winrelease1-20261029/evidence/`。

## 历史 static5 静态交付记录

以下 static/dev 条目保留各自当时的范围与限制，不覆盖上面的当前验收结果。

static5交付时仅支持Python3.13.x；历史3.12证据不作为该历史版本运行验收。桥接与server都提前拒绝其他版本。

此版基于冻结 dev8，补强统一初始化候选的成员/目录碰撞、专用run验证与八成员回执契约，纠正文档版本及保存边界。只进行静态和内存数据检查；未测试新增保存、未执行原版。

初始化仍为六模板支持的空图生成，MCP/Skill返回预览，不交付OpenTrack操作档案。总体原版端到端仍blocked-unverified；176项不是全部完成。

本次用户交付目标为组织代码/Skill/说明，不将源包交付当仿真工程交付。详见docs/static-delivery-review.md、docs/dev8-export-applicability-review.md及总包中文清单。

## static2 bridge repair

No hard-coded D:/opentrack backend. Explicit OTAI_ROOT or exact paired package locations only; static version and runtime tool-discovery checks before forwarding. Independent Skill ships a paired backend source snapshot. The user's successful 0.30 native sample is not evidence of 0.31 native acceptance. Output persistence and runtime gates are unchanged.

## static3 compatibility

Bridge UTF-8, Python/dependency/configuration checks and structured host-filesystem diagnostics added. Standard Windows lacks required secure reading primitives; archive read/preview and write are not certified or enabled by a fallback. Only cloud tests and mocked capability differences are in scope. Native execution, licensing, completed-status semantics and original model inputs are unchanged.
