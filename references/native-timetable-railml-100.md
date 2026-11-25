# 原版 RailML 1.00 时刻表交换

OpenTrack 1.7 的旧版时刻表 XML 在 `<railml>` 下使用 `<timetable version="1.00">`，每趟车直接包含
`<train trainID="…" type="planned">` 和 `<entry posID="…">`。运行结果另用 `type="calculated"`
记录。同一文件可包含同一车次的两种记录。RailML 2.2 使用不同的车段和车站引用结构。

## 从原生目录导出

`opentrack_export_native_railml_100_timetable` 直接读取 SHA-256 绑定的当前 `.courses` 和 `.timetable`。
预览列出导出的行数、实际时间处理方式和字段遗漏。写出新文件时提供 `target_path`，其扩展名为
`.railml` 或 `.xml`。原版车次 ID、站码、计划行、日偏移、停站标志、站台编号、最小停站时间、
平均出发延迟、编组标识及可表达的接续字段按 1.00 格式输出。

```json
{
  "timetable": {"path": "OTAI/workspaces/example/line.timetable", "sha256": "<SHA-256>"},
  "courses": {"path": "OTAI/workspaces/example/line.courses", "sha256": "<SHA-256>"},
  "course_ids": ["IVT01"],
  "railml": {"planned": true, "published": true},
  "target_path": "OTAI/workspaces/example/Exported.railml",
  "preview_only": false
}
```

`railml.published` 从原生已保存的计划时间生成 `publishedArrival` 和 `publishedDeparture`。
如需导出已保存的实际时间，设置 `railml.calculated: true` 和 `saved_actual: as_valid`。
原生时刻表不持久化实际时间的运行有效标记，因此回执记录这一选择。可使用 `only_active`、站码筛选和
`existing_stations_only`。筛选已有站点时提供 `stations_catalog`。

如需原版 OTT 时刻表，给导出请求增加 `variant: "ott"`。计算记录的 `railml.metadata_date` 使用
`YYYY-MM-DD`，省略时取 OpenTrack 1.7.6 中的默认值 `2007-01-01`。支持已保存的计划和计算时刻，
计算记录仍需明确 `saved_actual: as_valid`。跨午夜日偏移保留独立 XML 属性。
Minimal 和 Reading 的两份导出按冻结原版样例核对，另按原版手动输出函数写齐 XML 闭合标签。
冷读与预检证据与本仓库分开存档

## 导入并写回已有车次

通过 `opentrack_import_railml_timetable` 选择 `format: railml_1_00`，按源 `trainID` 指向已有原生
Course。源 `posID` 默认就是原生站码。别名由 `station_by_pos_id` 显式给出。

```json
{
  "format": "railml_1_00",
  "railml": {"path": "OTAI/workspaces/example/Edited.railml", "sha256": "<SHA-256>"},
  "timetable": {"path": "OTAI/workspaces/example/line.timetable", "sha256": "<SHA-256>"},
  "courses": {"path": "OTAI/workspaces/example/line.courses", "sha256": "<SHA-256>"},
  "course_by_train_id": {"IVT01": "IVT01"},
  "time_scope": "scheduled",
  "legacy_entry_fields": "update",
  "target_path": "OTAI/workspaces/example/Edited.timetable",
  "preview_only": false
}
```

`scheduled` 更新计划时刻，`published` 只采用显式发布时刻，`calculated` 写入已保存的实际时刻。
计划和发布记录需要完整依序匹配已有站点。实际记录可唯一匹配现有站序的子序列。跨日采用显式日偏移。
计划时刻按回写后的完整车次重新核对先后和最小停站时间。`legacy_entry_fields: update` 可随计划时刻写入
源文件明确给出的停站、股道编号、最小停站时间和平均出发延迟。默认 `match` 要求这些字段与现有保存值相符。
已保存的编组、接续关系和等间隔车次定义继续使用原生对象。源文件给出编组或接续时核对可表达的标识、时长和动作。
新建 Course、重新绑定交路、编组变换、时刻表行增删与接续重编排使用对应的原生写入入口。

默认读取完整 XML。部分原版运行目录的 `OT_Timetable.xml` 以完整 `</train>` 结束，缺少最后两层闭合标签。
对这种具有原版页眉和记录标记的文件，可显式设置 `legacy_recover_footer: true`，解析时补齐两个闭合标签。
源文件字节保留，短缺的时刻表行仍需通过站序和索引检查。RailML 2.2 继续使用原有解析和车段合并合同。

## 验收

已将原版运行生成的 1.00 时刻表回导到原生目录。计划记录的原生输出与输入逐字节相同，计算记录写入实际
到发字段。另一验收将 IVT01 从原生目录导出为 1.00，调整起点发车为 10:23:00、中途发车为 10:27:00、
最小停站时间为 150 秒，再把回导目录交给原版 OpenTrack。IVT01 在 650 米处 10:24:05 到、10:27:00 发，
日志停站 175 秒，零速轨迹为 174.86 秒，10:27:52 抵达 1,100 米处的 Facility East。

原版映射依据包括导入入口 `0x69f578`、1.00 导入解析 `0x6a27f4`/`0x6a2d48`/`0x6a4340`、
独立导出入口 `0x545230`、页眉和尾部 `0x545298`/`0x54532c`、计划和计算导出 `0x545374`/`0x546250`。
