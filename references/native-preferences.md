# 原版 OpenTrack Preferences 配置文件

`opentrack_inspect_native_preferences` 读取 SHA-256 绑定的原版 Preferences 导出文件或 `.run`。
可核查模拟参数、目录路径、当前图档和有序的 `Document Set`。原版导出中空白的日偏移表示第 0 日。
全局文档组中可能还有其他工程的文档，读取结果会列出它们。

`opentrack_edit_native_preferences` 可用现有配置文件制作可带入原版的 `.txt` 或 `.run`。
使用 `changes` 写入原版参数，以 `copy_settings` 从另一配置文件择项复制参数。提供
`document_sets` 时按顺序替换新文件中的文档组，成员来自基准配置已经声明且经 SHA-256 核对的图档。
提供空数组会输出一份不带文档组记录的文件。原版导入含文档组的文件时会向当前用户追加这些组。

使用 `scripts/ot.py --profile generation call opentrack_edit_native_preferences`，以 UTF-8 JSON 传入以下格式。

```json
{
  "source": {"path": "OTAI/workspaces/Line/chain.run", "sha256": "<base sha256>"},
  "copy_settings": {
    "source": {"path": "OTAI/workspaces/AnotherLine/native-export.txt", "sha256": "<export sha256>"},
    "fields": ["Step"]
  },
  "changes": {"Label Size": "XL", "Delay Format": "M:SS", "Show Train Delay": "1"},
  "document_sets": [
    {"name": "Reading Platform View", "documents": [
      {"path": "OTAI/workspaces/Line/OTDocuments/RDG.opentrack", "sha256": "<worksheet sha256>"}
    ]}
  ],
  "preview_only": true
}
```

保存时以 `preview_only=false` 指定新 `target_path`。新文件继续使用基准配置的路径。
要把文件及工程一起交付，先重定位对应工程并核查目录和图档引用，再以新工程的 `.run` 为基准制作配置。

## 用原版导入和复核

1. 打开 `Info → Preferences → Import`，选择已准备的文件。检查目录、Simulation 参数和相关图档。
2. 在 `Document → Document Sets` 中查看或打开导入的文档组。
3. 回到 `Info → Preferences → Export`，在新位置填写文件基础名。Windows 原版保存面板使用 `.txt` 扩展名。
4. 读取原版再次导出的文件，对照所选参数、组名和成员的规范路径。在原版下，已存在的重复组名会取得唯一名称。

原版导入会把文档组写入当前 Windows 用户的 NeXT UserDefaults。需要隔离验收时，使用独立且已获
原版授权的 Windows 用户配置。需要在现有会话做可回退核对时，先用原版 Export 保存基线，
用唯一名称导入测试组，测试后在 `Document → Document Sets → Delete Set` 删除这些组。
需要恢复基线参数时，可先从基线导出制作 `document_sets: []` 的恢复副本，再用原版 Import 应用。

原版 1.7 导入和导出分别使用 `OTPreferencesController importPressed:` 与 `exportPressed:`。
文档组解析见 `OTController readPreferencesFromExportedPreferencesFile:`，文件导出由
`appendDocumentsSetsToFile:` 追加文档组记录。原版脚本运行只使用运行文件的图档声明和仿真参数。

Reading 验收件从原生配置生成两个有序文档组，并写入 0.5 秒步长。原版独立脚本仿真的协议
记录了 0.5 秒，列车实际停站 120 秒并跑完 4,225 m。图形界面中的文档组导入和重导出
仍需在授权的独立用户配置下验收。
