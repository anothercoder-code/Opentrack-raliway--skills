# 一站一文档的完整运营工程

当前配套版本为 `0.33.1-zeroaccept1`，使用 `opentrack_initialize_station_documents_project`。
同一接口先预览，再向显式全新目录发布；支持 Windows x64、固定本地 NTFS。
本候选补齐新Engine/Category名称的ASCII前置校验，保持既有图形对齐契约；
旧 `width/height` 输入需显式迁移，详见
[对齐字段](graphic-alignment.md)。历史 winmulti1 的三文档样例曾通过加载和联程，
后续发现双击属性面板崩溃；该结果不是当前工具编辑交互验收。当前原版 Inspector 修复
及离线验证范围见[安全扩展](inspector-safety.md)。

先读[受限英文三站单车流程](zero-start-three-station.md)：当前新ZF工程完成十成员
CLI/MCP生成、发布和独立回读；首次stock原版3.2km跨两文档边界并末站停车，产出
46文件，实际Delay Scenario为1。GUI三文件加载和原版Save已观察，独立检查仅
root的frame/view/visible矩形变动，23模型及Route/Path/Itinerary语义不变。
随后Save/reload及三个真实站对象Inspector双击更新通过。完整Preferences导入后
须执行原生Open→Cancel，再Ctrl+5确认ZF_TRIP/3200/Paths1of1/Routes2；未刷新时
GUI2的43输出有1条Origin warning，保留失败。刷新后的GUI3冻结43输出、零WARNING/
ERROR，十个保存输入及旧72原文件哈希不变，未改Train。08:12 GUI终态由原始CUA
和独立视觉复核确认，磁盘没有End事件且普通进程仍存活，不伪造PNG或使用exit码
替代GUI证据。限定三站流程通过；不能宣称全部工具GUI通验。2–12站是数据层范围。

## 本线性初始化入口的适用范围

以下站数、单车、向前、末站停和车型限制只约束 `opentrack_initialize_station_documents_project`。
它们不是完整Skill的全部设计范围；不匹配的工程按[复杂设计流程](complex-design-workflow.md)
选择其他已实现接口或原版工作流，不修改本入口校验来硬塞需求。

- 2–12 个有序车站组成简单线性链，每个 `.opentrack` 文档恰有一个 StationModel。
- 相邻文档使用成对连接器和原生 Route continuation；主 Path/Itinerary 贯穿全部站。
- 六个目录在工程级共用，只有一个同日向前 Course、一个单动力单元 Train。
- 起点发车，中间站通过，末站停车、零停留。车辆长度须大于 0 且不超过实际 500 米站区。
- 不支持分支、环线、中间停站、反向运行、折返、车底周转、多车运能或已标定动力学。

用户的“一站一文件”针对拓扑文档，不是把公共 Station/Train/Timetable 目录按站复制。
空拓扑生成仍需要授权格式模板和明确接受的车辆物理继承。
原版界面输入和新生成工程的站名、标签、对象名、文件名、执行路径均使用英文和
可打印 ASCII；中文只用于外部说明与报告。当前入口也对新Engine/Category输出名
使用既有ASCII校验，原模板lookup身份保持opaque精确匹配；不能把中文先写入
原版再期待编码转换自动修复。

## 最外层请求

| 字段 | 契约 |
|---|---|
| `sources` | 精确六项：`header`、`shapes`、`depot_template`、`trains_template`、`courses_template`、`timetable_template`；每项 `{path,sha256}`，对应实际原生字节。详见[初始化资源](project-initialization.md)。 |
| `spec` | 下表全部字段，未知字段拒绝。 |
| `preview_only` | 真正 JSON 布尔值，默认 `true`。保存须显式 `false`。 |
| `target_directory` | 保存必填，数据根内 `OTProjects/` 或 `OTAI/workspaces/` 下的全新相对目录。提供此字段时，即使预览也核对最终路径绑定。 |

使用 UTF-8 请求文件及 `--args-file`。不在 shell 中拼接大型 JSON。

## `spec` 的精确字段

| 字段 | 内容 |
|---|---|
| `schema` | 固定 `station-documents-final-stop/1`。 |
| `execution_root` | 最终工程的规范 Windows 绝对路径，正斜线、无结尾斜线，须等于实际发布目标。 |
| `document_paths` | `{站码:绝对路径}`，精确覆盖 `stations`；每项必须为 `execution_root/OTDocuments/站码.opentrack`。 |
| `run_filename` | 简单 `.run` 文件名，不含目录。 |
| `output_directory` | 工程内规范相对输出目录，与所有输入成员分离，通常 `output`。 |
| `stations` | 有序 2–12 项 `{id,name}`。`id` 同时是文档名和站码，ASCII 字母开头、后接字母数字或下划线、最多 24 字符，大小写无冲突；站名为明确的可打印 ASCII。 |
| `half_link_length_m` | 整数 1–100000 米；相邻站参考顶点间距离为 `2*(half_link_length_m+500)`。 |
| `vehicles` | 既有车辆生成契约：精确 Engine/Train/Category 模板身份、新名称、单项 `train_names`、显式模板物理继承许可和 Train 参数。详见[运营生成](wave11-operating-generation.md)。 |
| `course_template_id` | 既有当前格式 Course 的精确模板 ID；新 Course 不复用该 ID。 |
| `timetable_template_key` | 既有无 Connection 的精确 Timetable 模板键。 |
| `train_types` | 单项有序速度类型列表，与 `speed_type` 相同，对应原生 Edge 速度类型索引 0。 |
| `speed_type` | Course 使用的明确速度类型名称。 |
| `plan` | 仅一项 `{course_id,train,itinerary,visits}`；Train 与 `vehicles.train_names` 对应，Itinerary 等于 `itinerary_name`。 |
| `simulation` | 精确 `{start_day,start_time,stop_day,stop_time,step}`；日期偏移均为 0，明确起止时刻和步长。 |
| `path_name` | 新主 Path 名。 |
| `itinerary_name` | 新主 Itinerary 名。 |

`visits` 精确按 `stations` 顺序，每站一项：
`{station_sign,absolute_seconds,stop}`。时间为严格递增的同日整数秒；只有最后一项
`stop=true`，前面均为 `false`。时刻间隔还必须满足实际方向 Edge/Engine 限速的
必要时间下界；静态下界不代表列车动力学可达或时刻表运能已验证。

## 保存结构与回执

输出为 N 个 `OTDocuments/站码.opentrack`、六个 `OTData/chain.*` 目录文件及一个
`.run`，共 **N+7** 个成员，另有空输出目录。三站为十成员。`.run` 逐项绑定全部
文档和共同目录；不能把多个单文档八成员工程拼在一起冒充联通工程。

`candidate_receipt.saved=false` 只描述内存构造，包含真实源 SHA、成员清单、站序、
500 米到达站区、跨文档引用和静态验证。预览不会创建目标。
只有保存成功时顶层 `saved=true`、`project_files_delivered=true`，并另返 `publication`
和 `persisted_content_validation`，证明实际磁盘成员回读及完整引用检查。
`native_application_executed` 和 `native_runtime_verified` 始终不由此工具设为 true。

保存使用 Windows 句柄支持的整目录原子不替换提交，既有目标保留。源在构造前后与
提交周围重查。若错误携带 `commit_completed=true`，保留并检查已提交的完整目标。
若 `PUBLICATION_COMMIT_OUTCOME_UNCERTAIN` 携带 `commit_completed=null`，保留可能的
目标和 staging，核对实际身份后再决定重试。文件缓冲刷新不认证断电目录项持久性。

## 历史 REL 三站示例的重建方式

REL_A / REL_B / REL_C 各自成文档，共用原示例的车辆、Course、计划时刻和目录语义。
`half_link_length_m=500` 保持站参考点里程 0 / 2 / 4 km，因此主联程仍是 **4 km**。

这是按原生连接器和站区契约重新生成的分站模型，不是把旧存档字节切成三块。
每站局部线路为“半区间 / 左 500m 站区 / 参考点 / 右 500m 站区 / 半区间”，
三站文档各绘制 2 km，共 6 km；原单图绘制 5 km。首末站外围附加线路和各站 500m
普通到达区是明确的布局变化，主联程以外也有线路。末站参考点后保留 1 km。
这些新几何与跨文档运行必须由原版重新验收，不继承单文档样例的运行结论。

## Windows 现有多文档工程检查

`MultiDocumentTools` 的实际完整目录清单现使用本机句柄枚举，随后逐文件 SHA 绑定和
安全读档。目录重解析、硬链接、设备、路径碰撞及枚举期间变化会拒绝。显式清单最多
2000 文件、深度 16、总量 256 MiB；单文件读取上限仍为 20 MiB。
完整清单包括已有输出文件，不能运行后仍提交运行前只有十成员的旧清单。

真实 Windows CLI 已验证多文档 inspect、跨文档 Path 派生预览和三站空运营线性链
预览。旧预览接口仍不保存；新运营工程发布入口是本页工具。

## 历史 winmulti1 三文档原版运行记录

2026-10-29 使用全新原版 English OpenTrack 1.7 进程，从 Preferences Import
本次 `release.run` 后确认并自动打开 REL_A、REL_B、REL_C 三个文档。
打开 Itineraries（Ctrl+5）刷新并确认 REL_TRIP，再打开 Simulation（Ctrl+9）Start。
原版 Messages 全程 NORMAL，无 WARNING；事件中记录的所属文档随列车依次变化，
独立证明本次列车经过两处文件边界，而不是只打开了三个文件。

| 观察项 | 本次实际结果 |
|---|---|
| 发车 | REL_A，06:01:00，所属文档 REL_A |
| 中间通过 | REL_B，06:02:50，所属文档 REL_B |
| 末站到达 | REL_C，06:04:34，所属文档 REL_C |
| 物理停车 | 原版 `.vt` 最后两条速度均为 0；CourseStatistics 为 4km、1 次站停、0 次进路制动、0 次信号停车 |
| Course 结束 | 06:07:00 |
| 仿真结束 | GUI Current Time 06:12:00，Messages 显示 End of Simulation |
| 协议绑定 | `OT_Protocol.20261029-2035.txt` 列出本工程三个文档及六个正确目录 |

该历史版本合并回归 **139 项：136 通过、3 跳过、0 失败、0 错误**。一项因 OS 无文件
symlink 创建权限跳过；另外两项缺固定 25 文档网格所需的八个原始私有 fixture，
没有用其他 donor 冒充固定哈希源。此三站通过不认证该网格、多车全天运行、
全部 176 项功能或任意车辆物理标定。

验收机主报告：`D:/opentrack/integrations/winmulti1-20261029/发布与多文档全流程验收报告.md`。
可复核证据：同目录 `evidence/native-summary.json`、`evidence/unit-summary.json`、
`evidence/persistence-summary.json` 和 `evidence/station-documents-original-contracts.json`。
原函数契约证据记录目标 EXE/函数哈希与反编译来源；它和原版运行证据属于不同层次，
不可互相替代。交付包不包含私有 donor 或商业程序。
