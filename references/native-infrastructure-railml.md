# RailML 2.2 基础设施交换

`opentrack_convert_native_railml_infrastructure` 使用已授权 OpenTrack 安装中的
`OpenTrack.app/Resources/railML4OT.jar`，在 RailML 2.2 基础设施 XML 和原版 GModel
`.plist` 或 `.opentrackgmodel` 图档之间转换。后端需要本地 Java，可用
`OPENTRACK_JAVA_HOME` 配置其安装目录。
当前适配已审核的原版 `railML4OT.jar` 2.0.16.20150225。
原版 GUI 的 Java 定位由原版安装决定，Skill 的 Java 定位由后端环境配置决定。

```json
{
  "source": {"path": "<RailML XML>", "sha256": "<源 SHA-256>"},
  "direction": "railml_to_gmodel",
  "preview_only": false,
  "target_path": "<新图档 .opentrackgmodel>"
}
```

用 `gmodel_to_railml` 可反向转换，目标为 `.xml` 或 `.railml`。转换在独立目录运行。
保存回执核对原版桥接程序的完成标记、输出格式、原件 SHA-256 和新文件回读。回执提供
轨道或轨段数量、总长、连接统计、原生图档端点范围及桥接器警告。原版轨道与轨段的切分口径可以不同，
应结合布局和连接逐项验收。RailML 导出的原版元数据含当前时间。

## 写成普通可编辑图档

`opentrack_materialize_native_gmodel_worksheet` 将原版桥接输出的基础轨道和道岔拓扑写成
普通 `.opentrack`。源 GModel、当前版图档页眉和对象形状库分别以 SHA-256 绑定。图档页眉
提供工作表范围和打印设置，使用已有授权工程的数据范本。所选页眉的工作表范围需覆盖源轨端坐标。

```json
{
  "gmodel": {"path": "<GModel .plist>", "sha256": "<SHA-256>"},
  "header_document": {"path": "<当前版 .opentrack 页眉源>", "sha256": "<SHA-256>"},
  "shapes": {"path": "<对象形状库>", "sha256": "<SHA-256>"},
  "fallback_speeds": [{"train_type": "0", "speed12_kmh": 80, "speed21_kmh": 80}],
  "preview_only": false,
  "target_path": "<新 .opentrack>"
}
```

已定义的双向速度保留，空速度字典使用输入的 `fallback_speeds`。示例的 80 km/h 是教学值，
对应的源轨段 ID 会列在回执中。普通开放终端使用成对顶点中未接轨的一半表示。回执对应原始与
新图档的 End、Edge 和安全元件 ID，并验收位置、长度、坡度、半径、第一和第二分支以及安全分组。
有活动信号、车站、进路、测量设备和跨图档连接的 GModel 超出当前拓扑导入合同。

新 `.opentrack` 可通过原版普通文件打开流程检查。安装了配套后端时可用 `scripts/ot.py call`
调用同一写入入口。走停站、进路、交路及时刻表流程时，使用回执给出的新原生 ID。

## 写入站台、停车位置和出站信号

1. 对包含设施的原始 RailML 使用 `opentrack_convert_native_railml_infrastructure`，设置
   `direction: railml_to_gmodel` 和 `geometry_only: true`。临时送入原版桥接器的 XML
   提取几何视图，回执列出移出的 OCP、断面、站台边、信号和停车标。原 RailML 仍用于设施映射。
2. 将 GModel 写成普通 `.opentrack`，在图档或回执查明每条源轨道所对应的原生 Edge、递增里程方向及起始 End。
3. 调用 `opentrack_apply_native_railml_facilities`，用相同完整 RailML、普通 `.opentrack` 的 SHA-256 及设施 ID
   预览映射。可把图档和 `FacilityCatalog.stations` 保存到新目录，或提供 `source_project` 直接另存完整工程。
4. 在导入后的完整工程中接续编制原生进路、路径、交路、车次和时刻表。

```json
{
  "railml": {"path": "OTAI/workspaces/example/FacilitySource.xml", "sha256": "<SHA-256>"},
  "worksheet": {"path": "OTAI/workspaces/example/FacilityWorksheet.opentrack", "sha256": "<SHA-256>"},
  "tracks": [{"track_id": "trPlatform", "edges": [{"edge_id": 25, "start_end_id": 5}]}],
  "signals": [{"signal_id": "sig1"}],
  "stations": [{"cross_section_id": "cross1", "direction": "up", "platform_edge_id": "platform1",
                "exit_signal_id": "sig1", "stop_post_id": "post1"}],
  "preview_only": true
}
```

`tracks` 按 RailML 递增里程列出每条选中轨道的完整物理 Edge 序列。单轨道可映射多段，连续段必须
通过配对的原生 End 接续，总长度与源轨道一致。选中的信号、断面和停车位置必须精确落在原生段端点。
信号按 `up` 或 `down` 写入一个方向端。主信号 `main` 和主远组合信号 `combined` 可选
`home`、`blocking` 或 `exit`，分别对应原生角色 2、3、4。远方信号 `distant` 和调车信号
`shunting` 分别使用原生类型 3、4，无需 `function`。`repeater` 按原版导入函数同样写成类型 3，
反向导出统一为 `distant`。可独立设置 `virtual`。物理主信号或组合出站信号可用作选定平台的停车信号。
视距使用源 `sight` 的整数米数，缺省时可为该信号提供 `fallback_sight_m`。信号名称采用
`name` 或 ID，站点采用 OCP 的 `name` 和 `code` 或各自的 ID。
这些原生文字使用工具现有的可打印 ASCII 格式。
如果源图档已为进路放置了匹配的信号，在对应的 `signals` 项加 `existing_model_id`。
工具核对实际方向端、信号型号及角色、虚拟标志、名称及视距，保留既有信号、ID、外观和进路引用。

站台从 `platformEdge.pos` 沿指定方向覆盖一段或多段完整、连续的无分岔 Edge。`up` 加长度，
`down` 减长度。末端须与同一 OCP 的断面、所选出站信号及可选的停车标一致。工具把入口和中间每对
原生 End 作为同一 StationModel 的普通成员，使用类型 1。末端保留唯一类型 2 参考对和明确的停车用出站信号。
回执按行车方向列出 `area_edge_ids` 和 `ordinary_end_ids`，以 `stopping_edge_id` 标出最后一段。
为兼容既有请求，`area_edge_id` 也指最后一段。只绑定断面的站点可作点位。连续运行中，列车进站并在
终点按站名报码的已验证做法是为终点也配置停站区域，并给相邻区域保留独立的站点边界。

新信号沿用零延迟及显示图标和符号配置，站库采用通用 timing 站点配置。
源侧别和高度随回执保留为元数据。多候选停车点、轨段内部停点、信号显示与联锁、
车站地理表达及普通图档的设施完整反向导出仍需单独处理。
回执分别报告写入和未选中的设施。

### 写进完整的未排班工程

在上述设施请求中增加 `source_project` 并指定新的 `target_directory`。`source_project`
提供工程目录、其实际绝对运行根、原 `.run` 文件名和所有成员的 SHA-256。

```json
{
  "source_project": {
    "project_directory": "<数据根内的源工程目录>",
    "execution_root": "<源工程的绝对运行根>",
    "run_file": "station.run",
    "complete_project_inventory": true,
    "files": {"<每个工程成员的相对路径>": "<SHA-256>"}
  },
  "target_directory": "<数据根内新的完整工程目录>",
  "preview_only": false
}
```

设施请求的 `worksheet` 必须是 `.run` 所引用的图档。可以保留已有进路、路径、交路和车辆。
源工程须无已保存的车次、时刻表行或事故。设施另存会在原 `.stations` 成员路径追加新站点，并保留
当前布局的既有站点记录。出现同名站号时停止发布。车次、时刻表、车辆和机车目录的字节逐一核对。
新工程包含重新绑定的 `.run` 和空输出目录，回执列出原生 StationModel 的站号及成员端。设施另存与
冷读是开行准备的一步，后续仍需按实际径路编制运营数据并使用原版验证。

### 同站多股道

同一站点的各股道必须在 RailML 里引用同一个 OCP。对每条股道分别提供 `cross_section_id`、
`platform_edge_id`、`exit_signal_id` 和方向。可选的停车标须单独绑定该股道的信号和站台。
各股道使用不同的原生轨道名称，例如 `1` 和 `2`，以及互不重叠的原生轨段和 End 对。
每条停站径路承载自己的类型 2 参考对及出站信号。它们共享一个 StationModel 和一条站点目录记录。

```json
{
  "stations": [
    {"cross_section_id": "C1", "platform_edge_id": "C1_platform",
     "exit_signal_id": "C1_OUT", "stop_post_id": "C1_stop", "direction": "up", "station_anchor": true},
    {"cross_section_id": "C2", "platform_edge_id": "C2_platform",
     "exit_signal_id": "C2_OUT", "stop_post_id": "C2_stop", "direction": "up"}
  ]
}
```

`station_anchor: true` 指定站点图标所放的参考端，同一个 OCP 最多选一处。未指定时使用该站
第一条绑定的参考端。反向导出要提交所有股道映射，并为同一原生站名使用相同的 `ocp_id`。
输出包含一条 OCP 和每股道各自的断面、站台、信号、停车标。回执的 `native_station_groups`
列出股道名称、原生参考端与图标位置。当前支持不同物理股道，单一股道的多候选停车点另行配置。

同站双股道样本从同一出发站经道岔进入共享的 `CENTRAL`。导出并经原版 Java 桥接回导后，工作表和
站点目录逐字节一致。原版开行 `CENTRAL_P1` 从 11:12:09 到 11:14:09 在 750 m 的 1 股道停站，
原版信号位置输出为 `C1_OUT`，随后到达 1,100 m 处的东端。 `CENTRAL_P2` 从 11:22:14 到
11:24:14 在 850 m 的 2 股道停站，输出为 `C2_OUT`，随后到达 1,200 m 处的另一东端。
两列均停稳 120.0 秒，原版车站位置输出均为 `CENTRAL`。本例为两条显式按股道开行的径路。
[RailML 2.2 基础设施类型规范](https://www.railml.org/files/download/schemas/2013/railML-2.2/documentation_xs3p/infrastructureTypes.xsd.html)

### 停站实跑验收

教学线路由五段 350、300、150、300、200 m 的轨道组成，三个信号及中间和终到两处 300 m 站台以
同一 RailML 的设施数据写入。原版 OpenTrack 中，RMLF01 于 10:21:00 从 Facility West 发车，
10:22:04 在 650 m 的 Facility Platform 停稳，10:24:04 继续开行，于 10:24:57 抵达 1,100 m 处的
Facility East。速度/距离输出确认站台原地停车 120.0 s 和终点停车。原版 `.statpos` 和 `.sigpos` 分别
确认 West、PLAT、East 与 WEST_OUT、PLAT_OUT、EAST_OUT，三对位置均为 0、650、1,100 m。

跨段样本将同一 300 m 站台写成 240 m 和 60 m 两段。导出、原版 Java 桥接回导后，
普通图档与站点目录逐字节一致。90 m 编组 RMLP01 在原版于 11:02:04 抵达 650 m 处的出站信号，
停稳 120.0 秒，11:04:04 继续开行，11:04:57 到达 1,100 m 处的终点。按编组长和采样停车点
计算，车尾在 560 m，比停车段起点 590 m 向后 30 m，停稳时车身跨两个原生站台轨段。
驻站采用原版手册 E1.6 第 3.7.2–3.7.3 节的分组语义。原版
`OTController.groupStation:`（`0x42ce10`）把所有选中 End 关联到唯一 StationModel，
`OTEndModel.isStationEndModel`（`0x4c1898`）区别普通类型 1 与站点参考端。

### 停车区跨原生图档连接器

`opentrack_apply_native_railml_cross_document_platform` 将连续的单方向 RailML 站台写入两张或更多
已有原生图档。用路径和 SHA-256 绑定 RailML、所有参与的 `.opentrack` 和一份 `.stations`。
`track.edges` 按源轨道里程递增方向列出完整轨道，每段包含 `document`（图档文件名去扩展名）、
`edge_id` 和 `start_end_id`。如站台跨边界，需要映射到已保存的双向配对连接器。
站台边界必须位于完整轨段端点，两侧均不能分岔。停车端的原生主出站信号要与源文件中的名称、
方向和已声明的视距相符。

```json
{
  "track": {"track_id": "cross_track", "edges": [
    {"document": "West", "edge_id": 12, "start_end_id": 1},
    {"document": "West", "edge_id": 13, "start_end_id": 5},
    {"document": "East", "edge_id": 20, "start_end_id": 1},
    {"document": "East", "edge_id": 21, "start_end_id": 5},
    {"document": "East", "edge_id": 22, "start_end_id": 9},
    {"document": "East", "edge_id": 23, "start_end_id": 13}
  ]},
  "station": {"cross_section_id": "P_X", "platform_edge_id": "P_AREA", "exit_signal_id": "P_SIGNAL",
              "stop_post_id": "P_STOP", "direction": "up"}
}
```

每张图档保存本地的同名 StationModel。两侧有轨道的普通 End 归入同一站点，连接器本身只保留原生
跨图档关系。停车所在图档是唯一类型 2 参考对所在处，两边共用一条站点目录记录。回执区分实际停车
Edge 和全部有序停车区 Edge。原生运营计划按入口到停车端核对跨图档同名成员及物理间距，同时保留停车段
索引用于精确进路和编组验证。本入口保存参与的图档和站点目录。进路、交路和列车按原生工具接入已有工程。

原版 `XPLAT02` 在两张图档的 240 m 和 60 m 轨段组成的站台上运行。90 m 编组于 12:42:04 在
650 m 处停稳，12:44:04 重新开行，12:44:57 到达 1,100 m 处的终点。连接器位于 590 m。
从车头停车位置和编组长计算，车尾在前一张图档的 560 m 点。通用运营计划已按全长 300 m
验证并保存这个 90 m 编组的跨图档停车路径。

跨两个或更多既有连接器的一个连续站台，回执按行车方向列出 `reciprocal_connector_pairs`。
在站台有效长度内，如因原生进路的续接范围需要设置区间信号，RailML 应在同一位置声明既有的
`type="main" function="blocking"`。工具核对其方向、名称、视距、两侧独立安全单元、同一股道名及
实际的随前段预留进路。停车端仍为唯一的 type 2 参考对。既有同名站点改组、分岔站区和多候选停车点另行处理。
原版 `OTSimCourse.calculateSimBrakeActionsForStations…`（`0x63f6f0`）沿走行 End
比较站名标识，原版连接器解档（`0x4102d8`）将其设为普通类型 1。

### 跨图档站台的无模板反向导出

`opentrack_export_native_railml_cross_document_platform` 读取已经关联好的原生工作表及站点目录。
用路径和 SHA-256 绑定源文件。沿用上面的 `track` 和 `station` 映射，在 `station` 补充原生
`station_sign` 和输出的 RailML `ocp_id`。工作表中的物理轨段须全部位于这一条无分岔轨道上，
各部分的原生轨道名和线路名须一致。供回导使用的 `cross_section_id`、`platform_edge_id`、
`exit_signal_id` 和可选 `stop_post_id` 由请求明确指定。

输出一个连续 RailML 轨道、一个 OCP、完整站台和停车信号。原生图档连接器在 XML 中表现为
内部轨段边界，回执记录两侧原生连接器 ID、附着端和里程。几何同时携带所选限速类别、坡度和曲线半径。
可使用下文的 `speed_profiles` 明确导出多个类别。预览通过后，设置 `preview_only: false` 和一个
新 `target_path`，保存 `.railml` 或 `.xml`。

导出前会在内存中去掉所选站台关联，再通过原生导入核对所有参与图档的成员和参考端。
回执提供 `worksheet_seed_sha256`、`worksheet_restored_sha256` 及 `worksheet_bytes_match`。
实际回导时，给 `opentrack_apply_native_railml_cross_document_platform` 提供具有同一连接器的
无该站台关联的原始图档，以及对应的轨段绑定。外部文件的原生站点图元 ID 分配顺序可以不同，
此时以停靠方向、参考端、普通成员和单一目录身份的读回为准。XML 的内部边界可在原版 Java 桥接器读成
连续几何。还原原工作表需要上述原生底图和映射。

验收样本的 RailML 轨道长 1,300 m。原版 Java 桥接器读回 350、240、60、150、300 和 200 m 六段轨道。
回导后的两张 `.opentrack` 和站点目录均与导出来源逐字节一致。OpenTrack 1.7 实跑中，
90 m 编组 XPLAT04 在 650 m 的 Connected Platform 停稳 120.0 秒，于 13:04:57 抵达 1,100 m 的
Connected East。列车停稳时尾部位于连接器另一侧，确认跨过两个原生工作表。

三图档 Canal 教学例的工作表和站库也实现逐字节回导。335 米站台跨过 690 米和 740 米处的连接器，
715 米处为站内区间主信号。已另存的 90 米编组计划在 765 米处停站 120 秒，按计划头位计算车尾在
675 米。实际走行与停车范围以原版输出验收。

### 从 RailML 新建多个原生工作表

`opentrack_rebuild_native_railml_corridor` 用一条连续无分岔的 RailML 2.2 轨道及明确的
切图里程建立新工程。用 SHA-256 绑定 `railml`、原生 `header_document` 和图元结构
`shapes`。轨道、信号、库内站点、互反连接器及通过进路按照 RailML 数据重新生成。
原生样本提供工作表头部及归档类结构。

```json
{
  "track_id": "canal_track",
  "worksheets": [
    {"document": "ApproachWest", "start_position_m": 0, "end_position_m": 690},
    {"document": "CanalMid", "start_position_m": 690, "end_position_m": 740},
    {"document": "TerminalEast", "start_position_m": 740, "end_position_m": 1540}
  ],
  "station": {"cross_section_id": "CANAL_REF", "platform_edge_id": "CANAL_AREA",
    "exit_signal_id": "CANAL_EXIT_XML", "stop_post_id": "CANAL_STOP_XML", "direction": "up"},
  "train_types": ["instructional"],
  "execution_root": "<新工程绝对路径>",
  "run_filename": "canal.run",
  "preview_only": true
}
```

分段须从轨道起点连续覆盖到终点，切图位置可在 XML 已有物理区间内部。工具组合双向限速、坡度、
曲线半径和各项边界，逐条回读生成的轨段。多个可适用车型需明确 `speed_profiles` 的映射。
`target_directory` 和 `preview_only: false` 会发布包含 `.run`、工作表及原生目录的新工程。
对导出 XML 省略的两端设施和其他车站，按实际线路补充站点、列车径路、车辆和时刻表。
Canal 的重建样例已完成补充和首班车计划保存，既有 Canal 案例覆盖同一待验的开行工况。

### 从 RailML 新建分岔站场

`opentrack_rebuild_native_railml_station` 从连通的 RailML 2.2 面向道岔及可选到发线回接生成普通工作表、
原生道岔、跨图档互反连接、所选信号和站台。请求绑定 `railml`、`header_document` 和 `shapes` 的 SHA-256，
并指定 `execution_root`、`train_types` 和目标工程。`worksheets` 的每项用 `document` 和有序 `tracks`
定义覆盖的区间；每个区间包含 `track_id`、`start_position_m` 和 `end_position_m`。同一轨道的区间须连续覆盖，
切图位置须避开道岔，分岔的物理连接必须在同一工作表中。

多股到发线可分别在同一主线的较低里程处分岔、较高里程处回接。分岔用 `orientation="outgoing"`
与所属到发线的 `trackBegin` 配对，回接用 `orientation="incoming"` 与 `trackEnd` 配对。
每对连接 ID 必须互指，道岔位置各自独立。原生道岔按走行方向分别写在两半方向端上，主线使用默认第一腿。

`stations` 的每项增加其所属 `track_id`，按设施映射给出 `cross_section_id`、`direction`、
`platform_edge_id`、`exit_signal_id` 和可选 `stop_post_id`。每个站台连同参考端须位于一张表内，
共享一个 OCP 的站台也须位于同一张表。工具回读有向边、道岔腿顺序和默认位置、
各图档连接以及每股道的停车参考端。需要单一连续站台横跨工作表时可使用上面的走廊重建入口。

另存后，在新工程中按需要建立进路和交路，再用原生运营编制入口配置车辆和时刻表。
双股道案例已从空运营目录另存四条跨图档进路及两班车。原生时刻表回读分别在 750 米和 850 米处
安排 120 秒停车，计划终到 1,100 米和 1,200 米。冷读与预检证据与本仓库分开存档

J22–J23 的 8 公里多到发线样例保存了两站的 W1、W2 双股道及两趟列车。两车各走一组股道，
均在 700 米和 6,700 米处安排 90 秒停车，再汇至同一终点。左右平台侧记录源 RailML，轨道和停车参考
逐项按旧图核对。四个未纳入本次设施写入的原有 25 型信号列在来源记录中。
冷读与预检证据与本仓库分开存档

## 从普通图档反向导出设施

`opentrack_export_native_railml_facilities` 从已保存的普通 `.opentrack` 和配套 `.stations` 回读站名、
站点配对端、连续站台边界与所选信号的名称、类型、角色、视距和虚拟标志，在 SHA-256 绑定的
RailML 2.2 模板中写入这些数据。
模板可取带设施的原始 RailML，或从原版 GModel 桥接器导出的同一几何。`tracks` 仍使用原生 Edge 和
里程递增方向的起始 End。工具验证已映射的连续轨段，以及能在两侧原生 End 落实的直接双向连接。

```json
{
  "template_railml": {"path": "OTAI/workspaces/example/FacilitySource.xml", "sha256": "<SHA-256>"},
  "worksheet": {"path": "OTAI/workspaces/example/FacilityWorksheet.opentrack", "sha256": "<SHA-256>"},
  "stations_catalog": {"path": "OTAI/workspaces/example/FacilityCatalog.stations", "sha256": "<SHA-256>"},
  "tracks": [{"track_id": "trPlatform", "edges": [{"edge_id": 25, "start_end_id": 5}]}],
  "signals": [{"signal_id": "sig1", "track_id": "trPlatform", "direction": "up", "end_id": 8}],
  "stations": [{"station_sign": "PLAT", "ocp_id": "oc1", "cross_section_id": "cross1",
    "track_id": "trPlatform", "direction": "up", "platform_edge_id": "platform1",
    "exit_signal_id": "sig1", "stop_post_id": "post1"}],
  "preview_only": true
}
```

每个工作表站点需要一条映射。既有 RailML ID 的记录在其原有轨道和结构上更新，可用同一条映射回读。
采用几何模板时，由请求给出新 ID。导出保留模板中已有的站台侧别、高度和未选中的数据内容。
同一轨道可映射 `up` 或 `down`，以实际原生方向端和完整站台段推导位置。跨段站台的每对普通成员
必须沿同一无分岔轨道连续。停车标以同一停车参考端、站台与信号关系写入。回执区分原生回导检查和逐字节相同。
原生回导检查要求站名、方向端、全部有序轨段、最后一段停车 Edge、信号名称和视距相同，
并核对所选原生车站目录条目。通过预览后，用 `preview_only: false` 和新 `target_path` 发布 `.railml` 或 `.xml`。

两座 300 m 站台的教学例经导出、原版 Java 几何桥接、普通图档物化和设施回导后，图档和站点目录的
SHA-256 与原件相同。原版再次开行 RMLF01，确认 650 m 处停稳 120.0 秒，继续行至 1,100 m 并于
10:24:57 抵达 Facility East。自定义信号设备、联锁状态和双方向共用站台仍需其他交换入口。

## 从普通图档直接生成 RailML

`opentrack_export_native_railml_geometry` 从当前版普通 `.opentrack` 提取轨道几何。
提供完整的物理轨段清单和每条轨道的 RailML ID。沿里程递增方向，逐段指定 Edge 的起始 End。
工具核对每段的长度、相邻 End 配对、轨道和线路名称，以及所有物理 Edge 的唯一覆盖。
工具从已保存的原生端点关系生成轨道连接。简单道岔要求直股连续、使用原生第一轨段，
侧股使用原生第二轨段并从道岔起始。此范围采用原生默认开向和零转换延时。

```json
{
  "documents": [{
    "path": "OTAI/workspaces/example/Track.opentrack",
    "sha256": "<SHA-256>",
    "tracks": [{"track_id": "main", "edges": [
      {"edge_id": 16, "start_end_id": 1},
      {"edge_id": 17, "start_end_id": 5}
    ]}, {"track_id": "branch", "edges": [{"edge_id": 18, "start_end_id": 5}]}]
  }],
  "speed_train_type": "0",
  "preview_only": true
}
```

整个连通网络的多个原生图档可以同时提交。跨图档连接从双向 `OTConnModel` 的文件和对象 ID 读取，
只有两侧能各自落到唯一轨道端点时才导出。对相连图档平移绘图坐标，使接口重合。
同一图档的多处接口必须允许同一坐标偏移。生成的交换文档使用合并后的轨道网络，保留连接关系。
原版桥接回导后可以写成一个连续图档。按原图档拆分、原生进路片段、路径、交路、车次以及图幅格式仍需单独交换。

在设施导出请求省略 `template_railml`，可用同一几何生成逻辑从单张工作表输出站点、连续整段停站范围、
主出站信号和可选停车标。请求须覆盖该图档所有 Edge，仍须显式选择设施 ID、站点目录和运行方向。
几何生成与设施均写入同一份 XML。工具在发布前核对所选站点及设施的原生回读。

生成的 XML 写入长度、绘图坐标、坡度、曲线半径和指定速度类别的双向限速。
限速写入原版桥接程序实际读取的 `infraAttributes/speeds/speed`，各限速变化点引用相应分组。
原版桥接及普通图档回导在 IVT 五轨段样本中保留了所选类别的 10 个限速值，以及
±2.5‰ 坡度和 800、1,200 m 半径，无需提供 `fallback_speeds`。
未选速度类别、特殊轨道类型、供电和检测设备等以回执里的未交换项目为准。自动构建复杂道岔、
保存联锁行为以及跨图档合并设施仍需其他流程。

独立样本回读了 750 m 的三轨段道岔。Reading 教学项目的 EA、RDG、WB 三张图档生成 5 条 RailML
轨道、2 对原生跨图档连接以及 2 对图档内轨道连接。原版桥接回导并写成普通图档后，13 个轨段合计
6,425 m，全部属于一个连通分量。设施和进路重建后，RMLX01 于 10:41:00 从 Twyford 一端发车，
在 3,125 m 处的 325 m Reading Platform 9 从 10:43:56 停至 10:46:00，
并于 10:48:37 抵达 Tilehurst 一端。原版按全程 5,825 m 报告，速度和距离采样确认站台原地停车
123.49 秒。单图档无模板的设施往返样本 RMLG01 也在原版开行，于 650 m 处停站 120.0 秒，
并在 1,100 m 处抵达 Facility East。两个原版任务的冻结输入均通过 SHA-256 核对。

### 一次交换多个双向限速类别

在无模板几何或设施导出中，用 `speed_profiles` 选择原生限速键和对应的 RailML ETCS 类别号。
每个键和类别号须分别唯一。轨段每个方向都保留各自限速。显式映射采用 RailML 2.2 的
`speedChange@etcsTrainCategory` 和 `vMax`。ETCS 类别号的有效范围是 0–15，按目标项目
所用类别给出映射。[RailML 2.2 XSD 类型文档](https://www.railml.org/files/download/schemas/2013/railML-2.2/documentation/railML.html)

```json
{
  "speed_profiles": [
    {"native_train_type": "0", "etcs_train_category": 3},
    {"native_train_type": "1", "etcs_train_category": 0}
  ]
}
```

通过原版桥接器生成 GModel 后，调用 `opentrack_materialize_native_gmodel_worksheet`，提供同一份
`speed_profiles` 和 `railml_speed_source: {"path": "...", "sha256": "..."}`。目标一致性检查使用
带 SHA-256 的实际 RailML 和 GModel。原版桥接器按首次出现的顺序把 ETCS 类别重编号，工具重跑原版桥接
以核对 GModel，再按映射恢复原生键，回读每条命名轨道的有序轨段和双向限速。限速数据须覆盖每个原生轨段
及方向，且每个边界的类别顺序一致。带 `profileRef`、带时段或制式约束的其他 RailML 速度记录需要单独转换。
原版的索引与 `.run` 中列车速度类型顺序相关，开行时按目的工程的原生速度类别设置列车。

IVT 五轨段样本回读了四个类别的 40 个双向限速值，同时保留 800、1,200 m 半径和 ±2.5‰ 坡度。
旧的单类别导出继续使用 `speed_train_type` 和原版桥接兼容结构。

另一例把原生速度键 `0、1、2、3` 映射到 ETCS `3、0、2、1`，再用源文件回导恢复原生键。
原版 OpenTrack 的四趟车均驶完 3,000 m。正向类别 0、反向类别 1、正向类别 2、反向类别 3 的速度采样
分别达到并维持 32、43、62、57 km/h，各自对应原生文件中保存的方向限速。

## 原版图档验收

1. 用原版 `Document → Open Special → Open Property List (plist)...` 打开 Skill 生成的
   `.opentrackgmodel`。原版文件选择器按此扩展名筛选。原版基础设施 RailML 导入也可生成 GModel。
2. 在图档中检查轨道的长度和连接。对于下文的教学例，检查两段相接轨道或一个三端点道岔。
3. 普通仿真工程可直接使用本页写入入口生成的 `.opentrack`。按项目需求配置站台、信号、进路、
   车辆和时刻表，再执行[原版仿真验收](native-simulation-jobs.md)。
4. 导出现有原版图档时，先在副本中使用原版 RailML 基础设施导出。原版会通过
   `saveAs_plist` 在图档旁保存同名 `.plist`。该文件可用于 `gmodel_to_railml`。

原版桥接程序已在两段相连教学轨道上完成双向转换，保持 750 m 总长及一个双向中间连接。
带道岔的第二例在同样的总长下生成 150、150、450 m 三段轨及一个三端点节点，回导仍为两条轨道、
一个道岔。该道岔写成普通图档并添加运营数据后，原版 OpenTrack 验收了两条径路和两趟列车。
TURNO01 从 Turnout West 于 10:21:00 发车，走行 600 m，于 10:22:01 抵达 Turnout Branch。
TURNO02 于 10:26:00 从同一站发车，走行 300 m，于 10:26:43 抵达 Turnout Main。
复杂道岔、信号显示、站台范围和运营引用需按目标工程逐项核对。源文件接收 RailML 2.2
的 2013 命名空间及有正长度的轨道。缺少有效可视位置的 RailML 可能产生重叠顶点。

原版函数 `0x596984` 和 `0x596644` 分别调用 `r2p` 及 `p2r`。`0x49db80` 和 `0x49dbe4`
将工作表写入 GModel 属性列表。[RailML 基础设施规范与示例](https://www.railml.org/en/subschemas/infrastructure)
