# 原版 Protim/PIF 首版时刻表导入

`opentrack_import_native_protim_pif_timetable` 按原版 OpenTrack 1.7 的 Protim 首版读取器解析制表符 PIF。将连续走行段还原为既有原生 Course 的计划到发、日偏移、停车和站停。保存流程核对完整工程 SHA-256、已排车次、站序、交路及运营引用，并发布新的 `.timetable` 增量。

```json
{
  "source_project": {
    "project_directory": "OTAI/workspaces/Example",
    "files": {"example.run": "<SHA-256>", "OTData/example.timetable": "<SHA-256>"},
    "complete_project_inventory": true,
    "run_file": "example.run",
    "execution_root": "D:/opentrack/OTAI/workspaces/Example"
  },
  "exchange": {"path": "OTAI/workspaces/Inputs/ProtimExample.pif", "sha256": "<SHA-256>"},
  "course_by_pif_id": {"PIF804": "IVT01"},
  "station_by_pif_sign": {"ALT-PLAT": "PLAT"},
  "source_encoding": "windows-1252",
  "thd_week_pattern": "Y******",
  "endpoint_clocks": "mirror_for_run",
  "mirror_passage_arrivals_for_run": true,
  "preview_only": true
}
```

`source_project.files` 需要完整文件清单。站码默认与本地原生站码一致，变体按需提供 `station_by_pif_sign`。使用 `python scripts/ot.py --root D:/opentrack --profile all call opentrack_import_native_protim_pif_timetable --args-file <请求.json>`。指定新 `target_directory`、设置 `preview_only: false` 后另存，并可将增量纳入原生工程重定位。

## 记录布局

列号包含记录标记本身，从 1 起。

| 记录 | 首版读取字段 |
| --- | --- |
| `PIF` | 文件首行标记，后接制表符和头字段。 |
| `THD` | 第 4 列为源车次号，同时封闭前一个车次。 |
| `TMV` | 第 4、5 列为起讫站码，第 7、8 列为发到时刻，第 9 列参与停站判定。 |
| `TSP` | 第 4 列为原版读取器最近一次记录的停站站码。 |
| `PIT` | 封闭最后一个车次。 |

- 一个车次的走行段必须按源站码首尾连续。始发写发车，终到写到达；原版终到标为停车。
- 在中间站，最近的 `TSP` 站码与当前 `TMV` 起点相同，且 `TMV` 第 9 列是 `0` 时，写入上一走行段的到达及本段出发。否则按原版通过语义仅写本段出发。
- 支持 `HH:MM` 和 `HH:MM:SS`，两位小时显式超过 23 表示跨日。原版恰好 `24:00:00` 的日偏移分支有歧义，该时刻要求通过原生日期编辑另行设置。
- `endpoint_clocks: preserve` 保留首尾单边到发。选择 `mirror_for_run` 可补齐首尾的对侧时刻；选择 `mirror_passage_arrivals_for_run: true` 可用通过站的发车时刻补齐缺失到达。两个选项用于满足高级版运行预检对成对计划到发的要求，回执标出补齐项，停站判定沿用源记录。
- 识别原版过滤器携带的 `TRF`、`TDT`、`REF`、`TLD`、`LOC`、`PLT`、`NWK`、`TLK`、`NTE` 并统计。运营日历、列车和线路库、站台属性、接续继续沿用已有原生工程。区间派生的计划时刻由原绑定管理。

## 按 THD 七位周模式选择

`thd_week_pattern` 可选。省略时沿用首版固定列导入，同号 THD 收到重复错误。启用后，
对 THD 按制表符切分并略过空项，同时核对第 4 个非空字段与原版固定的第 4 列车次号相同。
模式读自第 8 个非空字段的前七个源字节。筛选要求这七位明确存在。源中大小写的 Y 和 N
分别视为 Y、N，其余位为通配。查询接受 Y、N、`*` 和 `?`，不足七位补 `*`，超出七位时取
前七位。只有源和查询在同一位置分别为明确的 Y 与 N 时，该版本才被排除。

对同号 THD，按 `course_by_pif_id` 绑定的每个源车次须恰有一个版本匹配。零个或多个匹配
会退出另存。每个版本只采用自身的移动和 TSP 停站记录。`thd_week_filter` 回执列出查询的
七位模式、匹配和排除数、所选 THD 源行及其模式。该模式仅用于导入筛选，原版函数证据覆盖
七个位置的比较。星期名称与位序的对应、具体年月日和节假日例外规则仍需供应方格式资料。

原版 `0x697a6c` 读取 THD 非空字段，`0x6a8a6c` 提供三种预设，
`0x6a8b5c` 执行位置比较，`0x6aa480` 以已选择车次名写入正式时刻表。
本工具用显式唯一匹配避免临时表内同号行的歧义。原版始终时刻条件和专用过滤文本再导出分别属于其他入口。

## 验证范围

原版依据为 Protim 首版入口 `0x6983d8`、原生站码写入 `0x689380`、扩展时刻 `0x68ed24`／`0x68effc`、站停时间 `0x679f7c` 和 PIF 筛选输出 `0x6a95f0`。

Demo／Training 未发现随附 PIF。验证输入按上述原版读取规则编制，使用已有原版开行实绩的 IVT01 工程。
分别完成原版单边时刻策略与运行补齐策略的 CLI 另存和冷读。THD 筛选用两个同号版本另存并
独立冷读。第 1 股道分别为 10:23:44 到、10:26:54 发、站停 190 秒，以及 10:25:55 到、
10:28:46 发、站停 171 秒。零匹配和多匹配的请求均核对了无输出。厂商原始 PIF 兼容性、
其他 Protim 变体和新候选的原版动态开行待验收。
