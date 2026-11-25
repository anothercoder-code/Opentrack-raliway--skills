# 高级版原生写入

先确认适用的[原版软件授权](software-authorization.md)，再用 Python 3.13 查看当前接口。

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all tools
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all call opentrack_preview_signal_saved_parameters --args-file D:/RailWork/request.json
```

写入使用同一接口和参数结构，将 `preview_only` 显式改为 `false`，并给出 schema 中的
`target_path` 或 `target_directory`。原名带 `preview_` 的兼容入口默认继续预览。
Windows 需用固定本地 NTFS，目标文件或目录必须全新。对带 `.run` 的完整工程，
执行根和原生文件绑定必须与发布位置吻合。对局部增量，应按成员清单检查实际文件和
依赖关系，再决定如何应用到工程。

## 写入入口

下列名称省略公共前缀 `opentrack_`。参数、对象版本和发布范围以实时 schema 和各领域合同为准。

| 对象 | 入口和输出 |
|---|---|
| 单份信号或进路保护档案 | `preview_signal_saved_parameters`、`preview_signal_type_configuration`、`preview_signal_protection` 支持另存 `.opentrack`。信号类型检查动作保留只读。 |
| 车辆和运营目录 | `preview_consist_workflow` 另存混合编组，`preview_shunting_connections` 另存接续时刻表，`preview_rename_train_references` 成组另存列车目录和受影响的车次目录。 |
| 故障和事件集 | `preview_disturbance_scenario`、`preview_infrastructure_incidents`、`preview_incident_sets` 可另存受支持的车次原生文件。场景采样和原版运行需要另外验证。 |
| 工程和显式拓扑 | `preview_relocated_project`、`preview_multistation_line_project`、`preview_three_station_branch_project`、`generate_multi_document_topology`、`preview_full_multidocument_grid`、`preview_finite_explicit_topology` 可发布相应工程或拓扑档案集。 |
| 运营计划和调车拆分 | `preview_multistation_operating_plan`、`preview_multistation_timetable`、`preview_spatial_shunting` 可发布各自验证通过的工程候选。 |
| 径路、交路和单文档工程 | `create_multi_document_paths_itineraries` 可发布重绑定后的派生工程，`preview_finite_explicit_itinerary` 可成组另存图档和交路目录。`preview_infrastructure_chain`、`preview_operating_chain`、`preview_final_stop_chain`、`preview_initialize_project` 开放其有界写入流程。 |
| Windows 成组发布 | `batch_current_catalogs`、`generate_current_course`、`generate_current_network_archives`、`generate_current_operating_archives`、`create_current_itinerary` 复用 Windows 发布器。带运行配置的通用运营生成要求实际发布目标与执行根一致。 |

调车的旧 `preview_current_shunting` 继续用于检查。写入用
`edit_current_shunting`、`edit_current_shunting_structure` 或[按对象选择专用入口](native-movement-editing.md)。
从已有结果读数、审查仿真计划和动态原版运行分别有自己的验收范围。

## RailML 2.2 时刻表

`opentrack_import_railml_timetable` 接受 SHA-256 绑定的 `railml`、`courses` 和原生
`timetable` 文件。通过 `course_by_train_id` 明确给出 XML 列车 ID 与既有原生 Course 的对应。
默认使用 OCP 的 `abbrevation`、`code` 或 `name` 与原生站码匹配，特殊站码可显式提供
`station_by_ocp_id`。单段列车仍可直接映射。多段列车在 `<train>` 下按运行顺序列出
`<trainPartSequence sequence="…">`，编号为递增的正整数，每段引用一个 `trainPart`。
相邻段须在同一原生站码衔接。衔接处合并成一行，到点和发点分别取已定义的值，双方都提供时
必须一致。两侧有一侧停站即按停站核对。合并后的站序、停站属性及行号须与原生时刻表匹配。
每条源行须有一个所选时刻块，保存回执的 `assembly` 列出各车次引用的分段及衔接行。

`time_scope` 可用 `scheduled`、`published` 或 `calculated`。前两者写计划时刻，后者写已保存的
实际时刻字段。支持日偏移和整秒时刻，保留原有 Course、停站结构和编组。该时刻写入覆盖依次
运行的分段。同一时段并行的 `trainPart`、运营日历和逐线路 `sectionTT` 超出本工具写入范围。

对 `scheduled` 可显式指定 `connections: "match"` 核对原生接续，或用 `"merge"` 在新副本中
新增、更新交换文件声明的接续。默认 `"reject"` 要求先选用明确策略。接续双方的 RailML 列车 ID
都须出现在 `course_by_train_id`，目标 Course 在目标站须有唯一的原生时刻表行。
可引用原站或用 `ocpRef` 指定另一站。附带的 `trainPartRef` 须属于目标列车及包含目标站。
支持最小与最大等待、`none`、`join`、`split` 和 `meet`。等待用整秒的 `PT…` 时长，
须落在 24 小时内。合并时保存原有位置位、时间基准和调度距离，保留交换文件未声明的接续和等待。
新增接续使用原版的默认位置、时间基准和调度距离。商业转乘、外部目标和附加说明需要单独处理。
回执给出逐行匹配、创建和更新数。

原版接续回调用 `0x6a563c` 初始化所有者和站标，`0x6a5a44` 解析引用、等待和动作，
`0x6a6c1c` 将接续写入本行，`0x6a7d54` 校正目标 Course ID。读取等待时长见
`0x68fdec`，默认值见 `0x71145c`。已用此前原版曾运行的 Reading 四车交路依次完成
导出 6 条接续、匹配 6 条和在无接续对照副本中写入 6 条，冷读核对站、车、等待和动作位。
本批执行了离线操作，原版导入及仿真验收留在最终阶段。
[当前原生 RailML 2.2 导出](railml-timetable-export.md)
[官方 RailML 2.2 接续字段](https://www.railml.org/files/download/schemas/2013/railML-2.2/documentation_xs3p/timetableTypes.xsd.html)

## 保存与原版验收

确认 `saved=true`、写后回读以及成员 SHA，预览哈希仅描述内存中的候选。对已有工程的
运行记录增量，可用 `opentrack_prepare_reviewed_movement_application` 核对 `.run`、
发布清单、每份待替换文件的前态哈希，再在全新恢复目录保存 `before/`、`after/` 和
`application-plan.json`。按[原路径修改与重载流程](station-document-layout.md#修改现有工程)
处理正式工程的实际替换。
旧通用几何写入仍隔离在 `LEGACY_GEOMETRY_DISABLED`，改用已验证的专用写入入口或原版操作。
原版 GUI Save、真正重载、仿真执行和新增场景的运营行为应分别验收。
