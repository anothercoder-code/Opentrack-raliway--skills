# 搜索并保存出站信号之间的径路

`opentrack_find_and_save_exit_paths` 对应 OpenTrack 1.7 的 R17.33「Search all Paths (Exit Signal to Exit Signal)」及 Treno 命名变体。它从所选图档的出站信号出发，沿原生存档中的进路逐条搜索。遇到下一架出站信号就结束这一径路。中间的进站信号和闭塞信号可继续连接已有进路。跨图档进路按存档中的续接和实际终端合并。

## 输入与结果

| 字段 | 用法 |
| --- | --- |
| `project_run`、`documents`、`dest_catalog`、`courses` | 提供运行文件、它绑定的全套图档、交路目录与车次目录的 `path` 和 `sha256`。图档字典的键是原生文件名去掉扩展名。 |
| `document`、`start_end_ids` | 指定出发图档。提供端点 ID 时仅检查对应出站信号。空数组搜索所选图档全部出站信号。 |
| `naming` | `standard` 按原版 `P:<起端>-<终端>` 规则结合站码、顶点名称和信号名称。`treno` 按原版变体省去附加信号名称。 |
| `duplicate_policy` | `reuse` 在名称及完整进路序列均匹配时复用既有径路。`append` 按原版习惯生成新的径路，重名依序加 `.1`、`.2`。 |
| `preview_only`、`target_directory` | 默认预览并返回径路、分段进路身份和距离。保存时设为 `false` 并提供项目外的全新目录。仅发布有变动的出发图档和回执。 |

工具保留既有径路、进路和交路身份，使用各始端的原生计数器分配新径路编号。保存前核对外部引用、限速事件及所有来源哈希。重载新文件时重新展开完整进路序列。没有新径路时返回结果，不创建输出目录。需要开行列车时，可在既有交路中明确选用新径路，再由原版仿真验收。

搜索依赖已保存的进路。需要新增进路时可先使用 `opentrack_discover_network_routes` 和 `opentrack_fetch_network_routes`。当前路径写入要求不重复经过同一个方向端点，回执列出因此跳过的分支数。达到候选或搜索步数上限时整批退出，缩小所选端点范围后可重试。Treno 选项保存原版命名，单独的 Treno 文件交付仍应按所需交换格式办理。原版资料依据包括 1.7 Release Notes 第 33 项和本机 1.7.6 的 `OTPathList.searchPathToExitSignal::`、`OTSignalModel.isExitSignal`、`OTPath.defaultName:`。
