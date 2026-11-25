# 进路、径路、交路和调车原生编辑

编辑入口默认预览。确认修改对象和前后值后，提交同一请求，将 `preview_only` 设为 `false`，并指定尚未存在的输出路径。输入使用相对于实际数据根的路径和当前 SHA-256。工具会回读保存结果，遇到同名目标或过期输入会停止。

| 对象 | 入口 | 可编辑内容 |
|---|---|---|
| 进路 Route | `opentrack_edit_current_route` | 说明、预留与释放时间和距离、接近参数 |
| 批量进路 Route | `opentrack_edit_current_route_approach_batch` | 在同一原生工作表批量设置接近区长度和速度，按说明或信号显示数量查看选中的进路 |
| 信号和进路显示 | `opentrack_append_all_route_signal_aspects` | 按起点信号顺序批量追加显示，可写指定速度显示。见[信号操作](signal-operating-fields.md)。 |
| 进路 Route | `opentrack_fetch_discovered_routes` | 将审定的主信号间候选保存为一条本地进路或带一处原生续接的跨文档进路，可指定释放分组 |
| 进路 Route | `opentrack_edit_current_route_protection` | 占用区段进入条件、移动闭塞下的分区预留标记、释放分组、慢行区段和信号显示。信号显示使用同一起点信号机已有的代码 |
| 进路 Route | `opentrack_replace_current_route_movement` | 在同一文档内改走另一条轨道链，保留两个方向端点，明确新释放分组，并复核引用此进路的径路和交路 |
| 跨文档进路 | `opentrack_replace_current_cross_document_route_movement` | 同时修改主段和续接段及释放分组，可明确指定跨档慢行区，两份 `.opentrack` 成对另存。保留外侧方向端点，核对连接器、径路、交路及 `.dest` 索引 |
| 进路 Route | `opentrack_edit_current_route_lifecycle` | 改名时同步主段、续接段及引用径路。可删除无引用进路，也可调整起讫主信号、续接文档及各段释放分组 |
| 径路 Path | `opentrack_edit_current_path` | 说明、连续进路序列。可替换被交路引用的径路，并按已验证的原生续接关系跨文档串接 |
| 径路 Path | `opentrack_edit_current_path_lifecycle` | 从有序进路新建跨文档径路。改名同步交路及 `.dest`，删除或迁移时可显式替换受影响交路的径路序列 |
| 交路 Itinerary | `opentrack_edit_current_itinerary` | 新建多径路交路，或编辑说明、径路序列和安全余量表。兼容已验证的本地调车及保护区段布局，新建或换径路时同步写入 `.dest` |
| 交路 Itinerary | `opentrack_edit_current_itinerary_lifecycle` | 改名、复制、删除、换径路和重建 `.dest`。改名同步运行计划 `.courses`，删除可为已有运行计划指定等效交路 |
| 交路 Itinerary | `opentrack_import_native_itinerary_archive` | 按条从供体工程的 `.dest` 和图档导入交路，绑定目标原生径路，发布归属工作表与 `.dest` |
| 调车 Shunting | `opentrack_edit_current_shunting` | 既有本地调车的限速、预留时间和释放时间 |
| 调车 Shunting | `opentrack_edit_current_shunting_structure` | 本地调车新建、删除、改线，以及进路保护区段（Overlap）绑定和解绑 |
| 调车 Shunting | `opentrack_rename_current_shunting` | 同步修改调车本体、自动径路、交路索引及绑定该调车对象的进路保护区段名称 |
| 调车 Shunting | `opentrack_replace_current_linked_shunting_movement` | 修改已被交路或保护区段引用的本地调车走行链，保留方向端点并核对依赖 |
| 跨文档调车作业 | `opentrack_edit_segmented_shunting_itinerary` | 用本地调车径路和普通跨文档径路拼接交路。可同时创建本地调车段和更新 `.dest` |
| 多段保护区段 | `opentrack_compose_current_route_overlap` | 把连续的本地调车段合并成一条原生 Overlap，保留各源调车记录 |

先发现当前工具的参数结构。`opentrack_list_current_route_objects` 可列出文档内进路、径路和交路的确切对象名称。调车使用 `opentrack_preview_current_shunting` 的 `inspect_inventory`，取既有自动径路的名称、`array_id` 和 `start_id`。编辑进路或径路时也按名称及两个 ID 定位。

跨文档进路的 `slow_speed_zone_ends` 以两个 `{document,end_id}` 指定沿行车方向的慢行区间。
省略时保留现有端点，传空列表可清除。区间横跨连接器时，主段保存实际起点和本图最后方向端，
续段保存实际终点。回执列出两份本地存档的端点。各图档都可分别写有序释放组。

批量接近区入口使用 `source` 引用当前 `.opentrack`，在 `routes` 中提供各进路的 `name`、
`array_id`、`start_id`（最多 256 条）。修改时传入
`"changes":{"approach_length_m":400,"approach_speed_kmh":18}`。也可以单独设置其中一项，另一项
保留各进路原有值。仅检查时省略 `changes`，使用 `sort_by:"description"` 按保存说明排序，或用
`sort_by:"number_of_signal_aspects"` 按显示数量降序并以进路名称作并列顺序。排序作用于报告。
保存用 `preview_only:false` 与新的 `target_path`。工具回读每条进路并核对未选字段及现有引用。
原版接近区对实际制动的作用还取决于信号和运行情景。保存值可按原版时速轨迹验证。
固定闭塞对照中批量设置三条进路为 400 m、18 km/h。两列车在各自选定的 300 m 接近区段
均以 18 km/h 走行，每个区段有 300 个原版样本，最后各完成 12 km 到达 J23。

`opentrack_discover_network_routes` 以实际 `.run`、图档和 `.dest` 为输入，按起始主信号
分页搜索到下一主信号的走行链，并列出同一走行链上已有的原生进路名称。查看
`next_start_offset` 以及每个起点的 `exhausted`，区分已完成搜索和达到搜索上限的情况。
搜索结果可用于选择需要写入的走行链。算法根据已保存的方向顶点、连接器和轨段行走。

将已审定的结果项原样填入 `opentrack_fetch_discovered_routes` 的 `routes[].candidate`，
为每条进路给出唯一 `name`，并重新绑定项目现行的 `.run`、全图档、`.dest` 和
`.run` 中已配置的 `.courses`。写入会复核轨段序列、米数、主信号和续接关系，
按归属方向端的 `highestGivenRspID + 1` 分配原生标识。同一走行已保存时，
只有显式设置 `allow_duplicate_movement=true` 才会保存为另一条进路。可选值
`native_default`、`global`、`each_end` 和 `explicit` 用于选择释放分组。
`explicit` 提供按走行顺序排列、包含首尾的 `release_end_sequence`。
跨文档发布成对保存主段和续接段，工程原有径路和交路继续使用原绑定。
若要让车次使用新进路，再从径路编辑入口修改绑定，并运行原版核验。

进路改线、径路或交路换序列、调车结构修改时，提交同一工程的 `.run`、其中列出的原生文档和对应 `.dest`。进路和径路的变化会重新校验相关交路的方向端点和站点顺序。有距离相关安全余量的交路须保留原走行链。交路的文档和 `.dest` 一起另存在源工程外的同一个新目录，`bundle-manifest.json` 记录各自对应的原文件。

原版 1.7.6 的单条进路最多包含一处跨图档续接。原版搜索写入检查跨档连接器计数小于 2，接收段的续接序号为 -1。原版 Demo 的 topoWest 和 topoOst 各有四条接收段符合这一结构。超过一处文档边界的径路须在中间的主信号处分成多条进路再串接。改变已有引用的进路起点，需要先调整依赖径路。删除或迁移时会检查对应的 `.courses` 是否包含仍绑定该进路或径路的限速事件。交路已绑定运行计划时，保持起讫方向端点和停站顺序，改变走行链时按需提供新的安全余量。未绑定运行计划的交路可调整起讫点、站点顺序和归属文档。

跨文档调车作业通过交路串接，各调车段保留各自的速度参数，跨界段按普通进路运行。OpenTrack 的保护区段解析只取一层，合并时须为整条保护区段给出速度、预留时间和释放时间。

本地调车结构新建、分段交路的新建调车段可用 `rsp_id_policy: original_first_save` 按原版首次创建推进方向端的编号计数。
原版为编辑器副本取第一个编号，为写入工作表的自动 Path 取第二个编号。首次存档的调车体及其径路内部引用仍为 `[-1,-1]`。
这个选项用于现行工作表格式。Demo `topoOst` 和 `topoWest` 的工作表版本可用于只读核对。
冷读与预检证据与本仓库分开存档

### 保留在用交路的单边界调车重绑

`opentrack_rebind_single_boundary_shunting_project` 接收工程完整哈希清单、既有交路名和全部受影响车次
`expected_bound_courses`。在 `boundary` 填写 `source_connector` 和 `receiving_connector`，
格式均为 `[图档名, 连接器模型 ID]`，次序与走行方向一致。

按顺序列出 `paths`。已有普通径路用 `path`，已有调车径路用 `shunting`。已有普通跨档进路尚无
可单独使用的径路时，用 `create_crossing_path` 提供原进路的 `document`、`name`、`array_id`、
`start_id` 及新径路 `path_name`。用 `create_shunting` 提供本地图档、有向端序列及调车速度、
预留和释放秒数。各段须以相同的有向端相接，整个走行须完全保留原交路的有向端序列。
保存后，原 Course 和 Timetable 文件逐字节保持一致，`.run` 及 `.dest` 路径迁至新工程目录。

原版 Demo 的 topoWest 与 topoOst 中，可读的九个调车体均在父类中保存续接索引 `-1`。
原版进路的续接装配函数 `0x5a575c` 属于 `OTRoute`，图档打开时只对原生进路列表装配续段。
`OTDest.updateIfNeeded` `0x4754f4` 可按顺序还原普通径路和本地调车径路。运行速度求值
`0x47d890` 会应用当前调车体的速度。在用原生工程 XPLAT02 的回读例中，West 连接器 9
指向 East 连接器 0，East 有向端 4→8→12 另存为 25 km/h 本地调车段。站序、轨道链和
时刻表保持，候选通过静态预检。跨档与调车的组合运行待原版验证。

### 在多处图档边界之间插入本地调车

`opentrack_rebind_multi_boundary_shunting_project` 用有序 `boundaries` 列表声明沿行车方向经过的
全部连接器对。每一项使用相同的 `source_connector`、`receiving_connector` 格式。入口核对每对连接器
是否相互连接，并用原交路的有向端和物理边逐项复核完整走行。至少有一段本地调车须位于两处边界
之间。通过 `create_ordinary_path` 可一次把一组既有普通进路保存成独立的径路，传入新径路 `name`
和按走行顺序排列的 `routes`，每个进路给出 `document`、`name`、`array_id` 和 `start_id`。
现有普通径路和本地调车径路可按同样顺序直接引用。

R1→R2→R3 的独立车次 M16MAIN01 已在旧工程原版走行。新候选从 R1 连接器 101 跨至 R2 连接器 0，
经 R2 的 900 m 本地调车段，再从 R2 连接器 101 跨至 R3 连接器 0。原有 60 km 走行和车次、
时刻表均保留，车次和时刻表档案逐字节一致。两处边界顺序与原有一致。已完成原生另存、
独立冷读及静态预检。
新候选的调车速度和两跨界运行待原版验证。

## 按条导入原生交路

`opentrack_import_native_itinerary_archive` 用 `source_project` 绑定目标工程，用 `donor_project`
绑定供体工程。每项 `itineraries` 填写源 `source_name` 和目标新名字 `target_name`。
原生 `.dest` 是索引，必须同时读出供体图档中的交路对象。工具把对象归属到目标第一个径路所在工作表，
同时重建 `.dest` 中的目标工作表路径与有序径路索引。

- 已有径路的文档、名称、`array_id`、`start_id` 完全匹配时，可省略 `target_paths`。
  要换用目标工程的其他径路，逐项给出有序的确切引用，接口按方向端连接核对。
  站码不同可用 `station_mapping`，映射后的站序须能在目标交路按原顺序展开。
- 保留供体交路说明和安全余量。当两边逐段米数不同且供体有距离型余量时，
  在 `safety_margins` 明确给出新位置和余量，或给空数组清除。
- 输出是协调的工作表与 `.dest` 增量。将两者一起用于独立的目标工程副本，
  再绑定所需原生 Course 并运行。目标已有实际结果时，静态准备可能要求先在副本清空；
  交路增量不修改时刻表。
