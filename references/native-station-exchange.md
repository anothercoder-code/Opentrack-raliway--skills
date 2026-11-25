# 原版车站目录交换

`opentrack_edit_native_station_catalog` 可按已保存的站码原生修改站名、类型、公司和部门编号、
站内编号、X/Y、海拔、计时站和经纬度。请求用 `stations` 绑定原生目录和 SHA-256，
用 `edits` 提交带 `sign` 的记录，每条的 `changes` 仅填写待改字段。经纬度接受独立的带符号
十进制字符串，`"0"` 保存零度，空字符串清除对应字段。工具保留站码，可选用
`project_run` 核对同一工程的绑定。设置 `preview_only: false` 后写到新的 `.stations`
路径，回读本批变更和未选记录。

可以直接编辑旧 Station0、Station1 或 Station2 目录。工具把新副本的旧记录统一写成 Station3，
沿用原版解码器的默认值。Station0 补空类型，Station0 和 Station1 默认设为计时站，
Station2 的已保存计时值按原版规则解释为大于零。三个旧版本都以空字符串补齐经纬度。
`migrated_target_versions` 列出按来源版本升级的记录数量。目录的原有站码、已保存字段和对象引用保留，
只有请求列出的站点字段会改变。

要从另一个原生站库只迁移所选条目，使用 `opentrack_import_native_station_catalog_archive`。
以 `stations` 和 `donor_stations` 分别绑定目标目录和供体文件的 SHA-256，在 `station_signs` 中
列出精确站码。新条目保存已有多语言站名和站码对象的引用关系。`existing` 默认 `reject`，
`preserve` 跳过重名站，`replace` 将供体元数据写入已有站点对象并保留其目标站码引用。
可以先预览，再设置 `preview_only: false`、`target_path` 写成新的 `.stations`。
原版 Demo 有 2,877 条 Station0，Training 的 12 条记录为 Station3。Station1 和 Station2 的
写入覆盖以原版 Station 解码器字段测试确认。

`opentrack_import_native_station_catalog` 接收原版制表符文本、OpenTrack 的
`<stations>` XML 和 RailML 2.2 站点目录，将记录新增或更新到一份新 `.stations`。先读取源目录和交换文件的
SHA-256。工程有 `.run` 时可同时给出 `project_run`，核对实际 `StationFile` 绑定。

```json
{
  "stations": {"path": "<源 .stations>", "sha256": "<源 SHA-256>"},
  "exchange_file": {"path": "<交换文件 .txt 或 .xml>", "sha256": "<输入 SHA-256>"},
  "format": "opentrack_text",
  "existing": "update",
  "preview_only": false,
  "target_path": "<新 .stations>"
}
```

按精确站码匹配。可用 `station_signs` 选择本次导入交换文件中的具体站，留空导入全表。
`reject` 默认拒绝已有站码，`preserve` 跳过已有站码，`update` 更新交换文件实际提供的字段。
`replace` 沿用对应原版导入的同站处理方式。文本保留计时站标志，两个 XML 格式替换已有站时
将未提供字段恢复为原版默认值，并设为计时站。新站按原版初始化为计时站。导入以
Station3 保存，保留站码和未选站。旧文本和专有 XML 的新增名称采用可打印 ASCII。
交换文件中的重复站码会报错。

`opentrack_export_native_station_catalog` 接收 `stations` 和 `format`，可以用
`station_signs` 选择具体站码。设置 `preview_only: false`、`target_directory`
和可选 `basename`，可保存文本、KML、RailML 2.2 XML，或同时保存原版 `<stations>` XML 和同名 DTD。回执逐文件列出
SHA-256、字节数及原版格式未包含的字段。读取示例覆盖 Training 格式 v3 和 Demo Schweiz 格式 v0。

| 格式 | 原版交换字段 |
|---|---|
| `opentrack_text` | 原版 11 或 12 列，顺序为公司号、部门号、站内编号、保留列、X、Y、经度、纬度、海拔、站码、站名、可选站类型。保留列被忽略，两项经纬度都非零才读取。每行适配原版 1024 字节缓冲区。 |
| `opentrack_xml` | 使用站码、站名、公司号、部门号、X、Y 和海拔。原版导入回调跳过类型、股道数和经纬度。解析范围限于输入 XML，DTD 声明按原版文件名格式核对。 |
| `railml_2_2` | 读写一个 `infrastructure/operationControlPoints` 站库段。导出站码、站名和可用的经纬度对，导入另外识别 `tsi/@country`。 |
| `google_earth` | 原版 Google Earth KML 2.0，使用保存的经纬度。有效经纬度以经度、纬度顺序输出。 |
| `google_earth_ch` | 原版 Google Earth CH KML 2.0，用原版多项式将瑞士 LV03（CH1903）的 X、Y 换算为经纬度。只处理 X、Y 都为正的站点。确认目录的 X、Y 确实来自该坐标系。 |

两个 KML 入口按站名输出有坐标的站点，输出高度采用原版的相对地面零米。回执列出导出的
站码、跳过的站码和原版数值转换的告警。KML 是站点图层，原生目录或车站布局的修改继续使用
原生车站和图档写入入口。原版 KML 导出见 `0x53cbf8`、`0x53cff4`，坐标转换见
`0x52d98c`、`0x52d914`。

## 独立 RailML 2.2 站点目录

调用现有导入或导出工具并设置 `format: "railml_2_2"`。输入后缀可用 `.xml` 或
`.railml`，输出为 `<basename>.xml`。原版按 `code`、原版拼写 `abbrevation`、
`name` 的优先级读取站码，站名优先用 `description`，未提供时用 `name`。
`geoCoord/@coord` 按经纬度的原版顺序写成“纬度 经度”，两个数用一个空格分隔，零度
回读按原版规范化为 `0.000000`。`tsi/@country` 按原版整数前缀写入公司号，
没有数字前缀时为零。两个工具支持 ASCII、Latin-1 和原版明确转义的两种弯双引号。

独立导出沿用原版命名布局，基础设施 ID 使用本次 `basename`，同一请求的预览与另存结果
可按 SHA-256 对比。保存的站内编号、公司、部门、投影 X/Y、海拔、站类型和计时标志
超出此导出格式的字段范围。只有一项或格式无法回读的经纬度对会跳过，并列在
`coordinate_pairs_omitted` 中。图档中的站台、股道、信号和路网拓扑由基础设施交换处理。
独立站库的原版自带拼写以原版程序为目标，当前验证覆盖 XML 本地解析和原生档案冷读，
原版软件的对话框导入、XSD 校验和运行实测安排在最后验收。

原版独立导出入口为 `0x43024c`、`0x53d4ec`、`0x53ddf4`，
共用头部 `0x546d14` 和 OCP 写入 `0x546e40`。导入依次经过 `0x4302f4`、
`0x669990`，由 `0x669c58`、`0x669d0c`、`0x66a094` 处理。
离线验收使用原始 Demo 的 2,877 条记录，完整导出并比对站码和站名。另将三个多语言站
写入 Training 副本并回读，原有 12 条记录逐字段保持。Reading 的单站回导同时核对
已有 `.run` 的车站目录绑定，并用示意经纬度验证零度转换。

`.stations` 的车站目录和图档中的站台几何分别保存。使用新目录前核对项目内的站码引用，
再通过[原版仿真任务](native-simulation-jobs.md)验收受影响站点的停站和出发行为。

实现依据为英文原版手册 143 页和同一原版构建的函数 `0x53bde8` 文本导出、`0x6675bc` 文本导入、
`0x53c70c` XML 导出、`0x66a21c` 与 `0x66a5d0` XML 导入，以及 `0x663d78`、`0x663fe4`、
`0x66461c`、`0x664724`、`0x664904` 的 Station 初始化、复制和存档行为。原版 RailML 路网交换是 `OTRailML` 的独立流程。
