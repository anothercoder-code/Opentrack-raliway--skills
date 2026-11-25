# 原版 FBS 时刻表导入

`opentrack_import_native_fbs_timetable` 将原版 OpenTrack 可读的 FBS 制表符时刻表写入既有 `Course` 的原生 `.timetable`。写入计划到发、日偏移、停站标志和由到发计算的最小站停。使用完整工程清单及 SHA-256 验证站序、交路和运营引用。输出为可继续用于完整工程重定位的原生增量。

在 Skill 目录运行 `python scripts/ot.py --root D:/opentrack --profile all call opentrack_import_native_fbs_timetable --args-file <请求.json>`。

```json
{
  "source_project": {
    "project_directory": "OTAI/workspaces/Example",
    "files": {"example.run": "<SHA-256>", "OTData/example.timetable": "<SHA-256>"},
    "complete_project_inventory": true,
    "run_file": "example.run",
    "execution_root": "D:/opentrack/OTAI/workspaces/Example"
  },
  "exchange": {"path": "OTAI/workspaces/Inputs/FBSExample.txt", "sha256": "<SHA-256>"},
  "course_by_fbs_id": {"FBS804": "IVT01"},
  "station_by_fbs_name": {"Bahnsteig Süd": "PLAT"},
  "source_encoding": "windows-1252",
  "endpoint_clocks": "mirror_for_run",
  "preview_only": true
}
```

填写完整的 `source_project.files` 实际清单。指定现有车次映射，然后使用原站序或明确的站名别名。没有别名时优先按不区分大小写的原生站名匹配，再尝试原生站码。源是 UTF-8 时可选 `source_encoding: utf-8`。保存时指定 `preview_only: false` 和新的 `target_directory`。

## 时刻矩阵

FBS 第一行有效表头的前两格用于站名和到发符号，从第三格起每个车次独占一列。站名可以沿用上一个有时刻的行。以下空格分隔处在实际文件中用 Tab。

```text
Station        Art     FBS804       FBS805
Facility West  ab      (10.22,6)
Bahnsteig Süd  an      10:23,8      10:34:00
               ab      10:26,9
Facility EAST  an      102830
```

- `an` 写到达，`ab` 写出发。同一站点的连续记录合成一个原生站序行。`an/ab` 可在同一格用斜线分开到发。
- 出发或组合格中的括号表示通过。单独到达行使用原版的停车判定。空格留空表示该车次在当前行无数据，单独的 `|` 将相应到发标为未定义。
- `10:23,8` 表示 10:23:48，原版把一成分钟换算为 6 秒。也支持普通冒号、点号和原版数字简写。当前允许同日时刻，不隐式推断跨午夜。
- 若空行后出现 `Richtung `，导入在首个方向结束。下一方向的源行号列在回执中。导入其他方向时先提供该方向的独立矩阵。
- `endpoint_clocks: preserve` 保留原版的首尾未定义到发。选择 `mirror_for_run` 可用始发发车补齐缺失的始发到达、用终到到达补齐缺失的终到发车，以适配高级版对成对计划到发的静态预检。回执逐项标记补齐，原停车判定继续保留。
- 股道、实际到发、定时站标志、载客变化、车辆、交路和既有接续保持原生档案值。由其它车次派生时刻的区间行继续由其绑定管理。

## 验证范围

原版依据包括 FBS 入口 `0x695524`、到达／出发／通过判断 `0x67ced8`、`0x67cf00`、`0x67cf28`、FBS 时刻转换 `0x68e0b4`、合并站序 `0x688414` 及站停计算 `0x679f7c`。

Demo 与 Training 未发现随附 FBS 文件。验证输入按上述原版读取规则编制，并写入已有原版开行实绩的 IVT01 工程。两个策略均完成原生另存及冷读。独立运行工程通过静态预检，回读到 1 股道的 10:23:48 到达、10:26:54 发车和 186 秒站停。真实厂商导出兼容性、FBS 导出及新候选的原版动态开行待验收。
