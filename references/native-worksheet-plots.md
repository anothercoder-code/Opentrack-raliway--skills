# 原生工作表 Plot 编辑

`opentrack_inspect_saved_plot_settings` 可按 `.opentrack` 的路径及 SHA-256 查看原生 Plot 编号、
轴范围、图例和各线系列。`opentrack_edit_saved_plot_settings` 在相同的源绑定下，以 `plot_id`
选择图形，并可同时修改 `axes` 和 `series`。预览确认后，以 `preview_only: false` 和新的
`target_path` 保存原生工作表。该工作表继续保存可编辑的 `OTPlotModel` 和线系列数据。

```json
{
  "source": {"path": "<源 .opentrack>", "sha256": "<源 SHA-256>"},
  "plot_id": 0,
  "axes": {
    "x_title": "Distance (km)",
    "x_range": {"minimum": 0, "maximum": 6},
    "x_grid": true
  },
  "series": [{"index": 0, "expected_name": "OT_100.vs", "changes": {"line_width": 3.5}}],
  "preview_only": true
}
```

- 每个轴支持标题、可见范围、主网格、车站网格和细网格。范围使用该轴原有的单位，时间轴填
  总秒数。修改范围后按原版 `calculateDeltaXandDeltaY` 重算刻度间隔。PlotModel4 还支持显示或
  隐藏各轴的图例。PlotModel3 的解码器固定显示两轴图例。
- 线系列通过从零开始的原生序号和原名双重绑定。可写名称及正笔宽。具备相应能力位且已绑定
  原版车次的 OTPlot1 可写 `overwrite_data` 和 `plot_online`。打开在线刷新会同步启用覆盖，
  关闭覆盖会同时停用在线刷新。保存时保留现有点列、颜色、线型和车次。真实仿真中的曲线更新
  需由 OpenTrack 运行并验收。柱形及占用数据可保留，也可对经核实的离线柱形使用以下写入入口。
- 实际案例覆盖 Training 的速度图和含轨道的工作表，以及 Demo 的旧时距图和较新柱状图。
  对应原版依据为 `OTPlotModel` 的 `0x569084`、`0x569494`、检查器 `0x562b64`、刻度逻辑
  `0x563270`，以及 `OTPlot` 线系列的 `0x56025c`、`0x56041c`。

## 离线柱图和轴标记

用 `opentrack_create_saved_plot` 的 `bar_series` 新建离线分类柱图，类别从 1 开始，分箱及数值由调用方提供。
用 `opentrack_edit_saved_plot_settings` 的 `bars.series` 替换原生静态柱形系列，传空数组即可清空。
检查时给 `include_bar_points: true` 可回读原生柱高、分类位置及可用的车次、站码和时间字段。
当前写入支持经核实的 `OTBarPlot` v0、`OTPlot` v1 与 `OTBarPoint` v1 档案，仿真在线更新的柱形保持原有绑定。

新建或修改已有 Plot 时，可独立指定 `axis_marker_groups` 的 X、Y 分组，包含 `text`、`signal` 与 `station`
标记。单独修改标记时保留原有轴范围与线系列。Demo 的留存分类柱值和 Training 的信号、车站标记已通过回读。
冷读与预检证据与本仓库分开存档

## 插入和删除线系列

`opentrack_edit_saved_plot_series` 使用同一份 `source` 和 `plot_id` 绑定。`operations` 中的
`delete_series` 用当前零基 `index` 和 `expected_name` 指定删除的线系列。
`insert_existing_series` 以 `index` 指定插入位置，允许放到末尾，`donor` 指定原始 `plot_id`、
`index` 和 `expected_name`，并可用 `name` 给复制件另取名称。

插入位置按本次操作的执行顺序解释，供体位置始终基于本次操作前的源存档。同一工作表复制时
省略 `donor.worksheet`，跨工作表导入时用它绑定供体路径与 SHA-256。供体和目标的原生轴类型
及标题须相同。跨工作表可转移历史线系列，正在联机绘制或覆盖更新的系列在原工作表内复制。
复制件拥有独立的原生 OTPlot 及点列，保留颜色、线型、边界、车次绑定及保存的运行选项。

`viewport` 默认保留视口。没有设置 `viewport` 且首次向零范围的空白 Plot 导入外部点列时，会自动拟合。
明确选择 `fit_line_data` 时，用剩余线系列
的保存边界重新拟合，时间轴对齐到 600 秒边界，数值轴对齐到原版自动刻度。自动拟合要求
两个轴都有非退化范围。对应原版函数为删除 `0x56239c`，数据边界 `0x561d0c`、`0x561fc8`，
自动拟合 `0x56356c`、`0x5635c8`。柱形、占用和轴标记对象仍由各自的原生图层管理。

## 原始点列与新 Plot

在线系列入口的 `operations` 中使用 `insert_external_series` 可从一个数值点列文件创建一个或多个
可编辑原生线系列。每行第 1 列是 X，第 2 至第 6 列各是一条可选 Y 系列，列间使用空格或制表符。
按原文件顺序保存，包括重复的 X 值，同一文件的多个 Y 系列会依次插入。

```json
{
  "action": "insert_external_series",
  "index": 2,
  "source": {"path": "OTAI/workspaces/Case/output/OT_RDG09.vs", "sha256": "<point file SHA-256>"},
  "name": "RDG09 speed"
}
```

支持原版 `OT_Plot`、`OT_TimeXPlot`、`OT_TimeYPlot` 头及普通纯数值文本。原版时间轴保留总秒数，
`OT_tunnel` 结果使用原生隧道纵轴。
插入已有 Plot 时，时间轴类型和已知轴标题须相符。缺少相容图形时，可用
`opentrack_create_saved_plot` 指定 `source`、`frame` 和 `point_files`。
传入一个全新的工作表路径可保存包含新 Plot 的独立原生工作表副本。

```json
{
  "source": {"path": "<source .opentrack>", "sha256": "<worksheet SHA-256>"},
  "frame": {"x": 45, "y": 100, "width": 380, "height": 200},
  "point_files": [
    {"source": {"path": "OTAI/workspaces/Case/output/OT_RDG09.vt", "sha256": "<point file SHA-256>"}}
  ],
  "preview_only": true
}
```

- `frame` 为原生工作表坐标中的左下角及宽高，单位为点。可省略 `point_files` 创建空白 Plot。
- 新 Plot 随数据拟合视口，时间轴沿用原版的 600 秒边界。可明确提供 `x_range`、`y_range` 或轴标题。
  相容的多文件可以在创建时同时导入。
- `OTPlot1` 可随点列保存原版已知描述符的线系列类型、车次和可用运行选项，打开后的 OD、PO 状态默认关闭。
  老图档中的 `OTPlot0` 继续保存原始点列与外观，回执用 `saved_course_and_options: null` 标明该格式缺少这些字段。
  原版程序内自动更新和联机刷新仍需运行验收。柱图、占用图和信号轴图例使用各自的原版类型。
- Training 速度图与 Reading 新速度／时间图分别用封存原版输出逐点对照。Plot 创建使用原版
  0x560e98、0x569494 与同类 Demo／Training 存档字段，文本导入参考原版 0x565340 和手册 8.7.1。

## 用原版占用记录创建工作表图

`opentrack_create_saved_plot` 可从一个或多个 `OT_Occ_*.occ` 创建独立时间轴占用图。
使用 `occupation_files` 给出 `source.path`、`source.sha256` 和可选的
`show_reservations`。每份文件对应一行占用系列，默认显示预留。不同来源的图其资源名须相异。

回读保留占用开始、离开以及预留、释放四类记录的顺序与车次，时钟以原版单精度存储，
原版缺时刻 `-1` 会跳过。图档保留独立可编辑的 OTOccupationPlot2 和 OTOccupationPoint0，
报告显示导入点数和跳过数量。原版绘制和运行中的更新仍待集中验收。

## 仿真实时延误柱形

`opentrack_create_saved_plot` 可用 `runtime_delay_bar: true` 新建原版 36 型实际延误柱形。
`opentrack_edit_saved_plot_settings` 可在空白数值图中添加该绑定，或在仅含同类系列的图中启停刷新。
仿真提供活动车次、延误和 X 轴分组。暂停保存当前柱值和标签，重新启用后由原版运行更新。
已核对 Demo 独立图档的启用、暂停、恢复和存档回读。窗口刷新留到原版验收。
冷读与预检证据与本仓库分开存档
