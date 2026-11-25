# 验证原版进路释放、区段并行占用和通行权交接

`opentrack_verify_native_interlocking` 核对同次原版仿真的实绩。使用 `generation` 或 `all`
工具集，传入原版输出目录及其配对的 `evidence` 目录。两者都是配置根目录内的相对路径。

## 准备原版输出

1. 对每个要验证的 Safety Element，用 [原版占用监视组](native-occupation-groups.md) 选中一个监视组。
   组中包含该 Safety Element 在对应工作表中的全部 Edge。各工作表的组名在同次运行中唯一。
2. 在 `.run` 中启用 `Output Route Occ.`、`Output Timetable (Text)`、
   `Output Distance/Time`、`Output Speed/Time`、`Output Messages (Text)`、
   `Output Course & Station Statistics` 和 `Output Simulation Protocol`。
3. 使用 [原版仿真任务](native-simulation-jobs.md) 执行并保留冻结输入、进程回执及输出。
   为每个参与车次声明终到站，可同时填写始发站和运行距离。接口使用原版事件、速度、
   位移、统计和协议报告独立核对车次完成，再查找该车次唯一启用的保存 Itinerary。

## 提交验收目标

- `ordered_releases` 按行车方向列出同一车次先后经过的多个资源。检查保存 Itinerary
  上的区段顺序、原版占用进入顺序、逐段解除时刻和可选的最短解除间隔。
- `concurrent_traversals` 要求两车次在不同 Safety Element 上的物理占用持续重叠。
  `monitored_spans` 核对选定区段并列出整条保存 Itinerary 上共享的 Safety Element。
  `disjoint_itineraries` 还要求这两条保存 Itinerary 的 Safety Element 集合完全无交集。
- `consecutive_authorities` 选择一个共享区段及前后两次通行权。检查两车次在整个
  监视组的预留记录中相邻，检查该组异车次预留是否有时间交叠，并返回交接间隔。

```json
{
  "output_directory": "OTAI/workspaces/GridRun/runs/0/project/output",
  "evidence_directory": "OTAI/workspaces/GridRun/runs/0/evidence",
  "course_outcomes": [
    {"course_id": "H2E1", "origin_station": "Junction J21", "terminal_station": "Junction J23", "distance_m": 12000},
    {"course_id": "H2W1", "origin_station": "Junction J23", "terminal_station": "Junction J21", "distance_m": 12000}
  ],
  "ordered_releases": [
    {"course_id": "H2E1", "resources": [
      {"document": "J22", "group": "J22_Safety7"},
      {"document": "J22", "group": "J22_Safety19"},
      {"document": "J22", "group": "J22_Safety23"}
    ]}
  ],
  "concurrent_traversals": [
    {
      "first": {"course_id": "H2E1", "resource": {"document": "J22", "group": "J22_Safety7"}},
      "second": {"course_id": "H2W1", "resource": {"document": "J22", "group": "J22_Safety146"}},
      "scope": "monitored_spans",
      "minimum_overlap_s": 5
    }
  ],
  "consecutive_authorities": [
    {"resource": {"document": "J22", "group": "J22_Safety23"}, "leading_course": "H2E1", "following_course": "H2W1"}
  ]
}
```

保存 JSON 后，可在 Skill 目录运行以下命令。

```powershell
python scripts/ot.py --root D:/RailWork --profile generation call opentrack_verify_native_interlocking --args-file D:/RailWork/interlocking.json
```

结果保留原版 `.occ` 的预留、物理占用和解除时刻。监视组 `SR`、`ER` 须在同一车次
原版 `.step1`、`.step2` 的相同时间找到覆盖该区段的距离变化，时间允许 0.01 秒记录误差。
`.st1` 的同刻原始采样还须核对列车前端进入已保存区段，及结束占用时前端已通过区段末端。
位置默认容差 5 米，通过 `movement_boundary_tolerance_m` 设置。结果分别保留监视组全部
Edge、该车次实际绑定的 Edge、沿程轴距离和源文件 SHA-256。证据范围是所声明的车次、
资源和原版仿真时段。

## 原版验收样例

三乘三站场场景 0 中，H2E1 按 J22 的 Safety7、Safety19、Safety23 顺序解除预留，
两个相邻释放间隔为 89.65 秒、17.93 秒。H2E1 和 H2W1 在 J22 的两段不同接近区段上
同时占用 16.70 秒，后续共享 Safety23。H2E1 和 H1E1 两条各含 24 个 Safety Element
的保存 Itinerary 无交集，选定的 J22、J12 区段实测同时占用 21.79 秒。
共享 Safety23 上 H2E1 至 H2W1 的预留交接间隔为 13.56 秒，整个监测记录检出
0 次异车次预留交叠。

## 对照验证直连 Edge 排斥

`opentrack_compare_native_edge_exclusion` 比较关闭随机晚点的两次封存原版仿真。控制组的源
Edge 尚无排斥目标，目标 Edge 尚无排斥来源。试验组只增加所选的同工作表有向排斥链接。
工具以控制组原生工程重放这次写入，与试验组的冻结工作表比对，并核对相对化后的 `.run`、
目的径路库、其他工作表和非工作表输入。若序列化字节有差异，则比对原生对象图。

指定源、目标 Edge 各自的占用组，以及分别走行这两个 Edge 的两列车。两列车各需要一条
保存 Itinerary、明确始终点和总走行距离。工具以 `.occ`、`.step1`、`.step2` 和 `.st1`
验证两组中的实际区段走行。试验组还须有源车在目标区段仅预留的记录，原版 `SO` 与 `EO`
均为 `-1`，且 `SR`、`ER` 与源车实际区段预留相同。报告分别提供物理占用重叠、目标车
目标区段预留时刻差和两次通行权交接间隔。若 `.vt` 和 `.st1` 有进入选定区段前的停驶，
且停止结束时刻与目标通行权开始吻合，报告同时给出停驶时长、位置和控制组同位置停驶。

```json
{
  "control": {"output_directory": "OTAI/workspaces/GridControl/runs/0/project/output", "evidence_directory": "OTAI/workspaces/GridControl/runs/0/evidence"},
  "exclusion": {"output_directory": "OTAI/workspaces/GridLinked/runs/0/project/output", "evidence_directory": "OTAI/workspaces/GridLinked/runs/0/evidence"},
  "document": "J22",
  "source_edge_id": 289,
  "target_edge_id": 322,
  "source_group": "J22_Safety7",
  "target_group": "J22_Safety146",
  "source_course": {"course_id": "H2E1", "origin_station": "Junction J21", "terminal_station": "Junction J23", "distance_m": 12000},
  "target_course": {"course_id": "H2W1", "origin_station": "Junction J23", "terminal_station": "Junction J21", "distance_m": 12000}
}
```

```powershell
python scripts/ot.py --root D:/RailWork --profile generation call opentrack_compare_native_edge_exclusion --args-file D:/RailWork/edge-exclusion.json
```

三乘三站场原版对照中，两份协议各列出同样的 33 个车次，H2E1 和 H2W1 在两组均完成
12,000 米运行。重放 J22 的 `289 → 322` 后，工作表归档字节与试验组完全一致。控制组
两个区段的物理占用重叠为 16.70 秒，试验组为 0。试验组 H2E1 在目标区段取得一段
140.07 秒的仅预留保护。H2W1 在释放后 0.01 秒接权，目标区段预留比控制组晚 106.98 秒。
H2W1 在距始发 2,900 米处实际停驶 48.01 秒，终到晚 84 秒。报告范围为此次有向链接及
所选的两列车与监视区段。

## 对照验证限速占用接车和联挂

`opentrack_compare_native_occupied_entry` 比较同一工程在原版的许可与拒绝两次运行。
两案的冻结图档、股道、进路、车辆、时刻表、接续和仿真设置一致，入口信号只切换占用接车许可位。
供车进入已经停有受车的站台，按冻结进路的占用接车限速走行。工具核对两车的 Connection6、
冻结同向停车端和停车边、进路起点的原版信号位置、信号开始预留的阶梯、速度与位移同步样本，
以及联挂点的两前端间距与受车存档长度。许可案还须有两个同刻联挂消息、受车随后实际移动、
两车均通过完程核验。拒绝案仍要求原版进程正常结束、输出完整签封，供车应在信号处无下游预留，
两车原版均报告未完成交路。

```json
{
  "permitted": {"output_directory": "OTAI/workspaces/Allow/runs/0/project/output", "evidence_directory": "OTAI/workspaces/Allow/runs/0/evidence"},
  "denied": {"output_directory": "OTAI/workspaces/Deny/runs/0/project/output", "evidence_directory": "OTAI/workspaces/Deny/runs/0/evidence"},
  "receiver": {"course_id": "FEEDJOIN01", "origin_station": "Feeder Origin D", "terminal_station": "Terminal C", "distance_m": 7000},
  "donor": {"course_id": "FEEDJOIN02", "origin_station": "Feeder Origin D", "terminal_station": "Coupling Platform B", "distance_m": 4591},
  "station_sign": "RDG"
}
```

```powershell
python scripts/ot.py --root D:/RailWork --profile generation call opentrack_compare_native_occupied_entry --args-file D:/RailWork/occupied-entry.json
```

Reading 封存对照中，`MWAY` 工作表的 14 号主信号许可后，供车于 38,084.75 仿真秒获得
`R:MWAY-RDG` 通行权。由 `.vt` 与 `.st1` 同时刻取得的 964 条 20 km/h 样本覆盖始发后
3,501.1–4,570.9 米。原版在 10:38:25 成对记录联挂，两车前端差 208.9 米，受车存档长度为
209 米。撤销该信号许可后，供车在该信号的 3,500 米位置，从 10:35:12.05 停至原版运行
结束 11:00。此工具范围是限速式占用接车和一次原生联挂，等候时长式占用接车的原版动态仍待验收。

## 写入定时停车接车

`opentrack_edit_native_join_entry_mode` 按图档、进路名称、数组编号和起点编号选取实际
进站 Route。完整工程清单须按 SHA-256 绑定，原版进站信号须已允许占用接车。申请者须
提供该信号编号和原进路的 `flags`、`speed_kmh`、`wait_s`。跨图档时同时提供接收
片段的原值。两份片段在同次原生另存内调整，各自保留移动闭塞离散控制位。

- `setting: {"mode": "stop_and_wait", "wait_s": 45}` 写许可、使用速度与使用等待三位，
  进站速度为零，等待为正整秒。对应本机进路检查器允许设置 Stop Time 的原生条件。
- `setting: {"mode": "restricted_speed", "speed_kmh": 20}` 写许可及使用速度两位，
  并清除定时停车选项。速度至少 1 km/h。

默认返回预览并验证静态可开行。设置 `preview_only: false` 并指定新的 `target_directory`
可发布独立完整工程。车次、车辆、时刻表和接续保持原字节。Reading 的两份进路片段已完成
冷回读，配置为 `[7, 0, 45]`。等待的动态验收比较实际停稳到恢复走行的时长、联挂及完程。
