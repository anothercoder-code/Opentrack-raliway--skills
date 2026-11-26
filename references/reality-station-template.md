# 现实车站建模工作流

本页说明如何按现实资料复刻指定车站，并让列车经实际进路停站后继续开行。
先确认[原版完整版授权](software-authorization.md)。不要从网页截图、线路示意或图上
相邻关系推断站台股道、停车边界和实际咽喉。

先用[需求正规形式](requirement-normal-form.md)记录车站事实与来源，再用
[能力组合](capability-and-composition-model.md)选择已有实现，把实际拓扑、
设施、进路和运行计划排入[控制执行计划](workflow-plan-and-execution.md)。复杂道岔、
非连续站台面或不能证明的咽喉运动必须作为结构化 `unsupported` 缺口保留。

## 理解车站并选择实现组合

先从用户描述、运行图和正规资料中提炼车站功能，再选择所需对象和接口。不要因为
模板名称或已有生成器不同就拒绝任务，也不要为每个原版字段或函数另做一一对应的
求解器。优先组合通用的解析、拓扑、引用、语义写入和校验能力，同时检查每个真实
入口的输入边界和被封存代码。

| 请求范围 | 使用入口 | 能原生写什么 | 仍缺少什么 |
|---|---|---|---|
| 一个直线贯通站台、一个方向、一条股道、一个中途停站 Course | `opentrack_build_reference_platform_corridor` | 站台物理长度、股道名、站台标识、方向停车 Edge、停车区、站参考与出站主信号、可选矩形、Course/Timetable、`.run` | 多站台、真实咽喉、多股道并行、复杂联锁和 GUI 验收 |
| 多股道、岛式站台两面、多 Edge 站台、真实咽喉与有向进路 | 先按[复杂设计工作流](complex-design-workflow.md)组合原生网络、RailML 设施、连接、进路和运行计划 | 有明确原生对象的拓扑、End/Edge、站台映射、股道、断点、进路与计划 | 本资料模板不会自动生成这些对象，必须准备实际拓扑和受审核的设施映射 |

单走廊模板是
[reality-station.request.template.json](../assets/reference-platform/reality-station.request.template.json)。
多股道合同表是
[reality-station.multi-track.request.template.json](../assets/reference-platform/reality-station.multi-track.request.template.json)。
第二个文件标注了 `satisfies_single_corridor_builder: false`，不能传给单走廊生成器冒充成功。
可运行的岛式双面语义示例是
[reality-station.semantic.example.json](../assets/reference-platform/reality-station.semantic.example.json)，
用于 `opentrack_validate_reality_station_plan`。先复制并替换全部示例值，再校验实际站场；
示例通过只证明其静态语义闭合，既不写工程，也不证明原版加载、停车或开行。
不可支持的复合道岔反例是
[reality-station.unsupported.example.json](../assets/reference-platform/reality-station.unsupported.example.json)，
用于确认校验器返回 `UNSUPPORTED_COMPOUND_TURNOUT`，而不是从图形相邻关系猜测连接。
需要逐项填写现实站资料时，可从
[模板目录](../assets/reference-platform/templates/) 复制来源登记、原生 ID 映射、
有向拓扑、站台尺寸、咽喉进路、车辆服务和发布回执模板。模板只定义待填结构，
所有示例值都必须由当前工程和实际资料替换，之后仍须发现并遵守所选工具的实时
schema。
完整可校验版式还会保存每段 Edge 的起止 End、终到边界、信号、停车标、有向连接和
共用资源。已通过契约校验的合成示例在
[reality-station.semantic.example.json](../assets/reference-platform/reality-station.semantic.example.json)。
复制模板填写后先调用
`opentrack_validate_reality_station_plan`；该调用只做纯离线语义检查，不写档案。

## 现实资料清单

对每一字段保留来源、发布日期、查询日期、适用方向和单位。至少核对：

1. 站名、站码和版本化资料基准。不要把邻近区间或另一线路的同名站台混用。
2. 站台号、岛式/侧式、股道号或运营名称、行车方向、可停车边界，以及台面宽度和高度。
3. 站台由一个或多个原生 Edge 构成时的顺序、每段起止 End、累计长度和允许通过方向。
4. 停车标、出站信号、进站及中继信号、道岔、可走进路和共用咽喉资源。
5. 每段坡度和各 TrainType 限速。缺少值时必须标注假设，不能默认为实测。
6. 车辆长度、最高速度、加速、制动、阻力、编组和是否接受继承的代理物理模型。
7. 车次、停站到发时刻、前后站，以及该列车是否确实在该站台面停车。

`usable_length_m` 和项目资料中的 `platform_length_m` 需要分别记录。若证据只给站台
总长而没有可用停车范围，单走廊入口只能按明确标注的教学假设使用该总长；多站台和
复杂咽喉方案则必须补齐真实停车边界。

## 单走廊填写和发布

复制单走廊模板到 `OTProjects` 或 `OTAI/workspaces` 下的工作文件，执行：

1. 六份原生来源使用当前可读的实际文件，并填写实测 SHA-256。不要保留
   `REPLACE_WITH_64_LOWERCASE_HEX` 占位符。`header_document` 必须是 worksheet header，
   其余角色必须符合[生成输入](generation-inputs.md)。
2. `platform.length_m` 为整数米。设置 `drawing_side` 时才建议绘制站台矩形，填写
   `width_m` 时其值必须为正数。宽度和图形位置不改变物理停车长度。
3. `execution_root` 必须规范为 Windows 盘符绝对路径、英文正向斜杠，并与
   `target_directory` 在保存时指向同一个全新目录。
4. `plan` 中至少一条 Course 在目标站 `stop: true`，且 `arrival_s < departure_s`。
   计划时间从第零日零时起计，受 `simulation.start_s < stop_s <= window_days*86400`
   约束。边界时刻是模型值，引用车站时刻则来自时刻表或用户资料。
5. 先保持 `preview_only: true`。核对 `reference_platform_visits`、
   `topology.platform`、全部成员 SHA、列车长度不超过站台长度和生成的 `.run` 绑定。
6. 将目标改为全新目录和 `preview_only: false`。保存器会复查全部来源，原子
   no-replace 发布完整目录后独立读取；目标已存在时必须停止，不能覆盖。

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all call opentrack_build_reference_platform_corridor --args-file D:/RailWork/OTProjects/RealityStation/request.json
```

命令的 JSON 回执内 `result` 保存为可复核的 `build.json`。不要把命令行包装层回执
直接当成构建回执。单走廊结果只证明有界静态生成和已声明计划；它不证明真实咽喉、
多股道联锁、GUI Save 或实际运行。

## 岛式站台、多股道与咽喉

多股道合同应先形成实际原生图，再对已存在或已生成的对象填写映射：

- 岛式站台两面分别声明站台面、股道、方向和侧别。两面可以属于同一
  `OTStationModel`，但停车长度、出口信号和方向必须分别核对。
- 一个物理站台跨多个连续 Edge 时，记录有序 Edge/End 列表。RailML 站台跨度必须
  连续、同向且无内部岔路或额外信号，否则拒绝“完整站台”映射。
- 咽喉由真实 paired End、分支 Edge 和方向进路表达。图上交叉、平行线或站台矩形
  都不构成连通；不能把普通相邻 Edge 当成道岔。
- 为每个允许运动声明 Route/Path/Itinerary 和共用资源。静态集合检查只证明声明的
  资源关系和参考闭包，不证明原版调度、死锁自由或连续车体净空。
- 多方向接入、站外正线数、并联股道数量和岛式台面数按资料建立，不套用八股道案例。

可复用的实际案例是
[RailML 多 Edge 站台回归](../backend/OTAI/tests/test_railml_multiedge_platform.py)、
[岛式两面和道岔重建回归](../backend/OTAI/tests/test_railml_station_rebuild.py)和
[原生咽喉占用定位](../backend/OTAI/tests/test_native_throat_passage.py)。这些证明特定
有界数据和离线读回，不是任意现实站的自动建模能力。

## 最小数据结构

对现实站复刻至少保存以下映射，字段含义见多股道模板：

```text
source_register[]
site_identity
tracks[]
platform_faces[]
platform_spans[]
signals[]
stop_posts[]
directed_links[]
shared_resources[]
throats[]
routes[]
movements[]
assumptions[]
```

文件层面的实际映射则使用现有工具自己的精确 schema，例如 RailML 设施入口要求
`tracks[].edges[]`、`stations[]`、`platform_edge_id`、`exit_signal_id` 和可选
`stop_post_id`。合同表不是另一个可执行 schema，不能直接传入工具。

在 `ai` profile 中发现 `opentrack_validate_reality_station_plan` 后，可先用语义计划校验
资料、股道方向、岛式双场面、连续 Edge、停车标/出口信号、有向进出咽喉、共用资源、
列车与站台长度、跨日停站时续及下游站。结果为 `UNSUPPORTED_COMPOUND_TURNOUT`、
`UNSUPPORTED_NONCONTIGUOUS_PLATFORM` 等时必须显式保留；这也是“按模板作出可规划计划”
能力与“在任意现实站成功开行”能力之间的实际边界。

`opentrack_validate_reality_station_plan` 的成功只表示来源引用、有向运动、站台设施、
车辆长度和计划时间在离线层闭合。它返回 `ready_for_native_write: false`，并把原版
加载、GUI Save、真实停车、复开、下游到达和日志证据保持为 `not_run`。复杂道岔使用
`UNSUPPORTED_COMPOUND_TURNOUT`，站台 Edge 缺少精确共享 End 时使用
`UNSUPPORTED_NONCONTIGUOUS_PLATFORM`；不能因为图上相邻而自动补连接。

## 生成后的统一验收清单

离线阶段先完成下面可证明的检查，再启动原版软件：

- [ ] 请求和所有来源字节的 SHA 已冻结，占位符、`../` 和绝对来源路径已排查。
- [ ] preview 无保存；正式目标是新目录；第二次发布返回 `TARGET_EXISTS`。
- [ ] 所有成员文件、空输出目录和 `.run` 绑定均被独立冷读，源 SHA 未变。
- [ ] 站台 Edge 顺序、物理米数、股道名、方向、停车区和参考端正确。
- [ ] 停车标、出口信号、道岔车位、进路、Path、Itinerary 和 Course/Timetable 闭包正确。
- [ ] 至少一条通过 Course 在目标站台面停车，列车长度可容纳，出发时间晚于到达。
- [ ] 对多股道方案逐条验证每个允许运动，并记录共享资源与明确非连通关系。
- [ ] 资料缺失项、代理车辆物理和合成边界已写入假设，未冒充实测。

原版最终阶段再分别执行：

- [ ] 从实际工程加载，不用第二份工程替代。
- [ ] GUI 核对站名、站台面、股道、方向、信号、道岔和进路。
- [ ] GUI Save 后磁盘字节有变化，真正卸载全部受影响文档和目录缓存，再从原路径重载。
- [ ] 实际开行通过咽喉并到达目标站台，停车期间速度为零且位置稳定。
- [ ] 计划到发后再次开车并到达下游目标。
- [ ] 核对 `.tt`、`.vt`、`.st1`、`OT_Messages.txt`、车次统计和原生运行图。
- [ ] 原等级保留 WARNING，ERROR/FATAL 或非预期停车判失败。

前五项离线条件满足也只说明候选可复核。实际停站和 UI 结果必须由本工程自己的
原版运行和界面证据完成。
