# 现实站台建模和原版停站验收

先确认[原版授权](software-authorization.md)。接到现实车站复刻任务，先确定站名、站台号、
股道、行车方向和用户要验证的车次。按参数记录来源、日期以及适用范围。优先使用业主
线路图、站台实长表、公开时刻表或用户实测资料。实长与可用停车长度含义不同时，
分别记录并使用已核实的停车范围。站台宽度、停车标、道岔、坡度、限速、信号、车型和
时刻缺证时，按教学假设说明，或询问会改变用户要求的参数。

从资料收集、入口选择到两档模板和最终验收，先读
[现实站台资料模板](reality-station-template.md)。单走廊 JSON 可以直接绑定和发布；
多股道/岛式/多 Edge/真实咽喉合同只用于整理资料及后续组合，必须保持
`satisfies_single_corridor_builder: false`，不能传给单走廊生成器。

单走廊模板是
[reality-station.request.template.json](../assets/reference-platform/reality-station.request.template.json)，
多股道资料合同是
[reality-station.multi-track.request.template.json](../assets/reference-platform/reality-station.multi-track.request.template.json)。
完整示例见
[Reading 9 号站台请求](../assets/reference-platform/reading-p9.request.example.json)。

## 生成原生走廊

`opentrack_build_reference_platform_corridor` 适用于一个**直线贯通站台及其进出站走行**
的有界工程。完整站场、多股道、咽喉道岔或曲线站台按
[复杂站场工作流](complex-design-workflow.md)组织已验证的原生能力，并补相应运行验收。

- 选择六份 SHA-256 绑定的原生 `header_document`、`shapes`、`depot_template`、
  `trains_template`、`courses_template`、`timetable_template`。使用接续折返时才需要
  `connection_template`。车辆物理继承及测试参数需明确声明。
- `spec.schema` 使用 `multi-station-timetable/1`。在 `spec.network.platform`
  中指定 `station_id`、`platform_id`、`track_name`、
  `direction`（`forward` 或 `reverse`）和以米为单位的 `length_m`。
  `station_id` 对应 `network.stations` 中的 ID。选填 `drawing_side`（`above` 或 `below`）
  和有资料支持的 `width_m`。绘图轴向和行车方向要在 `model_assumptions` 中说明。
- 在 `evidence` 中给出 `source` 与 `supports`，把模型假设放在 `model_assumptions`。
  本入口写入承载业务的方向停车区。它将真实米数写入原生 Edge，并验证普通 End、站参考 End、
  StationModel、股道和出站主信号的关系。可选 OTRectModel 用于图面，省略实宽时宽度为示意。
- 按 schema 填 `spec.plan`。至少有一个行程在该站台**中途停车**，且
  `arrival_s < departure_s`。选定站的停车必须走声明的方向和 Edge，
  列车需能放入该停车区。可用 `spec.simulation` 设定 `start_s`、`stop_s` 与 `step`，
  时刻用自第零日零时起计的秒数。
- 先预览，再给实际新目录、`preview_only=false`。保存包括图档、六类原生目录和 `.run`。
  保留构建请求和结果回执。按回执内的 `files` 校对实际磁盘成员。

[Reading 9 号站台示例请求](../assets/reference-platform/reading-p9.request.example.json)
默认只预览，包含 325 米停车区、10:23 到达及 10:25 发车的停站计划和资料来源。
示例里的六个模板路径和 SHA-256 对应本机验收资料。换到其他资料目录时，将它们绑定到
可用的同角色本地模板，并设置相对应的 `target_directory` 和 `network.execution_root`。

### 从空图档分步建站和排首班车

1. 用 `opentrack_initialize_empty_current_project` 新建原生工作表、六类目录和
   `.run`。填写原版速度类型、运行时窗及站点和信号位置输出。
2. 用 `opentrack_generate_current_network_archives` 绑定该空工程和原生结构模板。
   提供有向轨段、主信号、进路、径路和交路。使用完整工程输出跟踪各阶段的输入散列。
3. 用 `opentrack_apply_native_railml_facilities` 的 `source_project` 模式把核定
   站点和停车区同时写进工作表和站库。已有出站主信号用 `existing_model_id`
   核对方向、原生标识、名称和视距。
4. 用 `opentrack_import_native_rolling_stock_archives` 的
   `target_scope: pre_service_project` 导入所选编组和依赖车辆。
5. 用 `opentrack_generate_existing_network_operating_plan` 在空车次、空时刻表
   目录中写首班车。使用各自绑定 SHA-256 的原生 Course 和时刻表结构模板，
   按本工程的车站、交路和计划到发另存完整候选。

Reading P9 的分步另存工程复用样例所记录的 325 米站台和 10:23–10:25 计划停站。
两侧边界及 1,700 米、2,200 米接近段沿用教学模型参数，209 米编组为参考车辆。
该案的 4,225 米走行、原版停站与复开按最终验收清单检查。

## 原版运行和验收

`run_reference_platform.py` 使用已核对指纹的原版 OpenTrack 1.7、
准备好的工程回执和原生 `.run`。在能读取原版运行库和用户设置的正常 Windows
环境启动，并使用独立空输出目录。旧原版会写回部分目录，所以实跑用专用隔离工程。

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all call opentrack_build_reference_platform_corridor --args-file D:/RailWork/request.json
python -X utf8 -B scripts/run_reference_platform.py --root D:/RailWork --exe D:/RailWork/OpenTrack.app/OpenTrack.exe --request D:/RailWork/request.json --receipt D:/RailWork/build.json --evidence D:/RailWork/OTAI/workspaces/PlatformEvidence
```

构建命令的 JSON 回执需提取 `result` 保存为 `build.json`。
运行脚本保存原版输入快照、进程、消息、实际到发和验收结果。已取得原版输出时，
可用 `verify_reference_platform_run.py` 对同一批次证据复核。

验收要求对应车次的 `.tt` 出现目标站台实际到发，`.vt` 在停站区间有连续零速和发车后正速，
`.st1` 的停车位置参考值落在该方向 Edge 范围内，并到达下游终点。原版会用首末两个采样点
记录连续的零速和不变位置，验收按这两个端点覆盖的时间核对停站。
车次统计和消息分别核对运行距离与错误；保留 WARNING 原等级。GUI Save/重载、真实车辆动力学、
车尾实际坐标和整个车站的运营容量分别需要对应证据。
