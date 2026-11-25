# IVT 轨道文本导入

`opentrack_import_native_ivt_infrastructure` 将原版 IVT ASCII 制表符轨道表导入为普通、可编辑的 `.opentrack`。
按里程位置的先后顺序生成一条连续线路。输入为原 IVT `.txt`、`.tsv` 或 `.ivt`、当前图档页眉、对象形状库，
以及含站点标记时所用的原生 `.stations`。输入分别绑定 SHA-256。输出目录可包含原样复制的车站目录。

```json
{
  "source": {"path": "OTAI/workspaces/example/IVTPlatformLine.txt", "sha256": "<SHA-256>"},
  "header_document": {"path": "OTAI/workspaces/example/Header.opentrack", "sha256": "<SHA-256>"},
  "shapes": {"path": "OTAI/workspaces/example/NativeShapes.archive", "sha256": "<SHA-256>"},
  "stations_catalog": {"path": "OTAI/workspaces/example/Stations.stations", "sha256": "<SHA-256>"},
  "signal_sight_m": 500,
  "platform_areas": [{"station_sign": "PLAT", "direction": "ascending", "entry_position_m": "350"}],
  "preview_only": true
}
```

预览回执列出原行号、位置、配对端、原生轨段编号和实际保存的速度及设施。保存时提供新的
`target_directory` 并设置 `preview_only: false`。可选 `worksheet_name` 设置图档名。

| IVT 列 | 数据和写入口径 |
|---|---|
| 1 | 位置，米。严格递增，相邻差为整米。 |
| 2–3 | 递增方向、递减方向的端点名。各自写入原生配对端。 |
| 4–5 | 两个方向的公里标，单位 km。空值保留原生未设定标志。 |
| 6–9 | 递增方向四类限速，使用轨段起点行。 |
| 10–13 | 递减方向四类限速，使用轨段终点行。 |
| 14–15 | 起点行的坡度 ‰ 和曲线半径 m。空值采用原版初值 0。 |
| 16 | 起点行的隧道类型或隧道系数。 |
| 17–18 | 递增、递减方向的信号类型，绑定实际对应 End。 |
| 19 | 站码或原生车站目录中的站名。 |

四类限速写入原生索引 `0` 到 `3`。用于仿真时，`.run` 中的 `TrainType` 顺序与文件的四类依次对应。
首行的递减方向限速和末行的递增方向限速、坡度、半径、隧道属于边界输入。它们没有对应轨段，回执会列出。
用空行或 `//` 行写注释。尾部设施字段允许省略。数字接受点或逗号作为小数符。当前每条线路支持 2–1,000 行，
1022 字节以内的行内容，最多 100 个方向信号。分支和跨工作表连接需要额外拓扑数据。

隧道支持空值／`No Tunnel`、`Tunnel single, smooth`、`Tunnel double, smooth`、`Tunnel single, rough`、
`Tunnel double, rough`。数值可取原生可精确表达的 0.5 到 6.0（步长 0.1），或 7 到 50 的整数。
信号支持 `Main Signal`、`Main/Distant Signal`、`Distant Signal`、`Shunting Signal` 及已映射的二、三、四显示
类型。主信号可带 `home`、`block` 或 `exit`，缺省为 `block`。文件列里是信号类型，生成的信号 ID 使用
`IVT_<导入行序号>_A/D`。默认视距为 500 m，可随请求指定。虚拟信号、车载信号、停车标及其他特殊类型
须通过各自写入入口处理。信号显示与联锁需根据运行场景验证。

第 19 列按现有目录精确查找单一站码。默认写入图档上的点式站点，可在多行重复标记同一个站点。
站台停车范围可用 `platform_areas` 明确指定，起点必须是该方向相邻的轨段边界，参考端须有主出站信号，
并有足够的两端拓扑边界。停车区域信息由调用方补充。原版 GUI 为已导入车站生成的蓝底文字标签和折行排版
属于单独的图面样式。图档可继续使用已注册的进路、路径、交路及时刻表工具编排服务。

## 原版验收

教学文件生成 350、300、150、300、200 m 五个轨段、四类独立双向限速，以及原生站点和方向信号。
服务 IVT01 使用两个补充的 300 m 停车区，原版于 10:22:05 在 650 m 处停稳，停车 120.0 秒，继续开行，
并于 10:24:58 抵达 1,100 m 的 Facility East。原版 `.gradient` 验证前段 +2.5‰、650–800 m 段 −2.5‰，
`.radius` 验证 800 m 和 1,200 m，`.tunnel` 验证 350–800 m 为连续隧道范围，`.kmpos` 验证两向公里标。
运行途中三个实际主信号及站点的位置为 0、650、1,100 m。四类限速和反向远方信号由原生存档回读确认。

在原版 GUI 中对照导入时，打开一张空白工作表，加载对应车站目录，进入 `Functions → Exchange Infrastructure Data →
Import Infrastructure Data → IVT`，选取原始 ASCII 文件，在预览中选中全部有效行并执行 Create。带 IVT 的原版
手册为 E1.6 §9.8，打印页 143。映射依据包括原版 1.7 程序的 `0x430b14`、`0x54a1cc`、`0x549bf8`、
`0x4a7d84`、`0x4a924c` 与隧道函数 `0x4956d8`。

## Siemens 连续线路

`opentrack_import_native_siemens_infrastructure` 使用相同的 `source`、`header_document`、
`shapes`、`stations_catalog` 和新 `target_directory`。必填 `default_directional_limits_kmh`，
用四组 `[递增方向, 递减方向]` 填写目标原版车种序及建轨默认速度。Siemens 文件的速度 1
写入第一类的两个方向。其他类别保留已明确绑定的工程默认值。

ASCII 输入的八列依次为累计米数、速度 1、坡度 ‰、半径 m、隧道代码、站名、时刻、备注。
速度、坡度与半径按原版继承空字段，代码 2 写原生隧道类型 3。站名须与已绑定原生站库完全
相符。原版的 `Start Station` 和 `End Station` 提示会跳过。时刻与备注随存档回执保留，
车次时刻表使用独立的运营写入入口。当前支持位置递增、相邻差为正整米的一条连续线路。

按本机反编译列格式构造的验证文本搭配已有 Facility 站库和原生图档形状。
保存后的里程、分方向车种速度、曲线、坡度、隧道及站点以冷回读核对。

## SBB ZLR 连续线路

`opentrack_import_native_sbb_zlr_infrastructure` 使用同一套工程模板和四类双向默认限速。
在单图档连续线路可写双向限速、方向端公里标、坡度、半径、隧道类型和按原站库匹配的点站。
累计公里差按本机原版的单精度规则取整至米。第十列有 H 或 V 时，通过
`signal_template.worksheet` 绑定真实图档和 SHA-256，再用 `signal_template.signal_id` 选择原生信号设置。
相同累计位置、相同显式公里标的连续互补 H/V 行可写为一个组合信号，其他已审定距离仍严格递增。
已用按原版解析函数构造的文本和 Demo 原生文件验证。冷读与预检证据与本仓库分开存档

## Bentley Rail Track 平纵断面

`opentrack_convert_bentley_railtrack_to_ivt` 读取 SHA-256 绑定的 Bentley 报告。
`orientation` 选择 `horizontal` 或 `vertical`，分别恢复平面的直线及圆曲线，或纵断面的线性坡段。
输出沿用本机转换器的原版 IVT 表头、列序和字段精度。将保存的 IVT 连同工作表和对象样板交给
`opentrack_import_native_ivt_infrastructure`，可另存为可编辑的原生工作表。
两条链路使用按本机转换函数构造的报告和原版 Demo 图档完成冷读。厂商样本仍待核实。
冷读与预检证据与本仓库分开存档
