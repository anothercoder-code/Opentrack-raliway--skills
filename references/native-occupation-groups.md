# OpenTrack 原生区段占用监视组

`opentrack_inspect_occupation_groups` 读取 SHA-256 绑定的 `.opentrack` 工作表，返回监视组、
已选状态、成员 Edge ID、显示标签 ID 和未能在原工作表中找到的 Edge ID。
支持读取原版 Demo 现存的 v3 工作表与当前 v4 工作表。

`opentrack_edit_occupation_groups` 在当前 v4 工作表创建新的本地监视组，或按已有组的准确名称
更新成员和已选状态。一个组可含一条或多条本工作表的 Edge。更新时只提交要变更的字段。
创建的新组默认选中。已有的图面显示标签随工作表保留。

通过 `--profile generation` 或 `--profile all` 调用，输入如下。

```json
{
  "source": {"path": "OTAI/workspaces/Line/OTDocuments/RDG.opentrack", "sha256": "<worksheet sha256>"},
  "operations": [
    {"action": "create", "name": "RDG_P9_ApproachAndPlatform", "edge_ids": [20, 21]},
    {"action": "update", "name": "RDG_Previous", "selected": false}
  ],
  "preview_only": true
}
```

把 `preview_only` 改为 `false` 并指定不存在的 `target_path` 才会写盘。工作表名、运营目录和
`.run` 中的图档绑定需要一致。组名使用字母、数字、下划线或短横线，开头使用字母或数字。
原版按组名生成文件，给参与同一次运行的各工作表选互不重复的组名。

在原版运行文件启用 `Output Route Occ.`，完成该原版仿真，再查看
`OT_Occ_<组名>.occ`。使用 `opentrack_read_native_evaluation_file` 分页查看 SHA-256 绑定的
原版输出。`SR`、`ER` 是预留开始和解除，`SO`、`EO` 是物理占用开始和结束。
多 Edge 监视组记录的是组层级的事件。需要各 Edge 的单独时刻时，分别建组。
验收时检查所需组对应的新输出、实际车次记录、明确的开始和结束时间及文件哈希。
原版也可生成 `OT_OccStatistics.txt`，其中含占用次数、小时统计、预留比例和所设时段的统计。
用 `opentrack_read_native_evaluation_file` 读取该文件可获得逐组统计、原始单位和时段，
也可在 `opentrack_evaluate_native_run` 设置 `include_supplementary=true` 后查看
`supplementary.occupation_statistics`。工具读取原版写入的统计量，时段未设时保留原始
`HH:MM - HH:MM` 或 `00:00 - 00:00`，并返回空的时长。跨日时段保留原始日偏移及换算秒数。

Reading P9 的原版复测中，RDG09 在进站与站台组合组 `[20, 21]` 占用 203.68 秒，
在出站组 `[22]` 占用 52.79 秒。两组的预留及解除时刻与该车次的原版进路记录一致。
停用组 `[23]` 未生成占用文件或统计行。车次停站 120 秒、走行 4.225 千米，
与未建组的原版基线结果一致。

## 在原版选择时段和查看柱形图

1. 在原版使用 `Info → Preferences → Import` 导入已重定位的 `.run`，选择打开其中列出的图档。
2. 在 `Simulation` 窗口顶部切换到 `Output`，确认 `Route Occ.` 打勾，核对所需监视组的 `Use` 状态。
3. 在阈值行下的 `Time Slot` 填日偏移和小时分钟，首日留空日偏移。Reading 对照可填 `10:22` 至
   `10:26`，按 Tab 提交。切回 `Simulation` 并点 `Start`。
4. 在新生成的 `OT_OccStatistics.txt` 核对 `Occ. Time Slot: 10:22 - 10:26`，并查看两组的时段预留比例。
   在 `Plot Inspector` 选择 `Occ. Stat.` 查看原版柱形图。在占用表下选择
   `Show Occ. Perc. in Time Slot`，按 `H / M / L` 阈值设置图面配色。

格式依据为原版 Demo `OTProjects/Demo/OTDocuments/topoOst.opentrack` 中的 `STATY_01`、
`STATY_02`、`STATY_03`，原版 Training `Training1.opentrack` 中的 `ST_C_01`、`ST_C_02`，
以及已完成仿真的 Cross6 `FoldedBase204` 对照输出。
工作表第 12 组为 `OTOccInfoList`，条目为 `OTOccInfo` v2，保存名称、
所属工作表、Edge ID 数组、已选标记和图面标签 ID。当前接口覆盖建组、成员和选中状态，
汇总时段和阈值来自原版输出窗口设置。
