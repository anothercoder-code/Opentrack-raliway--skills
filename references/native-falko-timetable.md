# 原版 Falko 时刻表导入

`opentrack_import_native_falko_timetable` 把 Falko 计划到发、日偏移、停站和最小站停时间写入已绑定车次的原生 `.timetable`。通过完整、SHA-256 绑定的工程清单核对现有车次、站序、交路和接续。新输出使用现有的运营增量发布流程。

在 Skill 目录执行 `python scripts/ot.py --root D:/opentrack --profile all call opentrack_import_native_falko_timetable --args-file <请求.json>`。

```json
{
  "source_project": {
    "project_directory": "OTAI/workspaces/Example",
    "files": {"example.run": "<SHA-256>", "OTData/example.timetable": "<SHA-256>"},
    "complete_project_inventory": true,
    "run_file": "example.run",
    "execution_root": "D:/opentrack/OTAI/workspaces/Example"
  },
  "exchange": {"path": "OTAI/workspaces/Inputs/Plan.falko", "sha256": "<SHA-256>"},
  "course_by_falko_id": {"EXT804": "IVT01"},
  "station_by_falko_type": {"Falko-Platform": "PLAT"},
  "connections": "require_matching",
  "endpoint_clocks": "preserve",
  "preview_only": true
}
```

`source_project.files` 填写原版工程的完整实际文件清单。确认原生预检后，使用 `preview_only: false` 和新 `target_directory` 保存。结果含站序、时刻和连接的回执，以及替换清单。沿用原生项目重定位和预检流程，将增量纳入独立运行工程。

## 文件字段

原版 1.7 Falko 入口 `0x694720` 按 ASCII 空格分列，跳过三列行，读取十二列数据行。列号从 1 起。第 1 列是车次号，第 5 列是车站类型标识，第 10 和 11 列是到达和出发的累计秒。第 12 列为接续车次标识，首字符为 `-` 或 `#` 时该行无接续更新。其余列未参与原版时刻表写入。

```text
Falko Course Timetable
EXT804 0 0 0 West 0 0 0 0 -1 37350 -
EXT804 0 0 0 Falko-Platform 0 0 0 0 37430 37610 #none
EXT804 0 0 0 East 0 0 0 0 37700 -1 -
```

- 每个源车次各行连续排列。负累计秒表示未定义，跨午夜按累计秒和 `86400` 计算日偏移。保存域为转成原版 float32 后的整数秒，覆盖第 0–366 日。到发相同为通过，有正站停或仅有到达为停车。单边时刻对应最小站停 0 秒。
- `endpoint_clocks: preserve` 沿用原版 Falko 的未定义到发。高级版运行预检要求成对到发，可明确使用 `mirror_for_run`，由源发车补齐缺失的始发到达，由源到达补齐缺失的终到发车。回执列出补齐项。停站标志和源接续分类按原始到发判断。
- 使用 `station_by_falko_type` 指定别名。未指定时按原版流程优先做忽略大小写的 StationType 匹配，再尝试车站代码。重复类型要求明确绑定。
- 按已有车次的一整组连续索引更新。轮次派生时刻由其区间设置管理。图档、股道、编组、实际到发、载客变化和未选字段沿用原档。
- 有接续标识时，默认用 `require_matching` 核对同站 Connection6，要求目标恰好有一次到访。确需添加普通同站接续时明确设置 `add_transfer`。原版在非首站仅有到达时为该关系标记 `split`。该类记录可核对既有定义，分编新建和互补编组关系需通过原生运营入口配置。

## 验证范围

读取规则来自本机 OpenTrack 1.7 的 Falko 入口 `0x694720`、StationType 匹配 `0x666614`、累计秒转换 `0x68f324`、写入转发 `0x689a74` 及 Connection 默认布局 `0x710ae4`。

用按上述读取规则编制的 Falko 输入，在已有原版实跑证据的 IVT01 工程完成 CLI 另存和原生冷读。回读到 1 股道中途 180 秒站停，以及 10:22:30 始发和 10:28:20 终到的计划时刻。以 `mirror_for_run` 保存的独立工程通过静态运行预检。Demo 和 Training 未发现随附 Falko 文件。厂商导出件兼容性、分秒时刻、按原版 GUI 新建未绑定车次及新增接续的动态开行另待验收。
