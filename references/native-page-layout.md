# 原生工作表打印页面设置

`opentrack_inspect_saved_page_layout` 读取工作表的纸型、打印方向、四边页边距及横向和纵向分页。
`opentrack_edit_saved_page_layout` 将这些设置写入一个新原生 `.opentrack`，保留工作表画布、窗口和既有图元。普通的原版 OTDocument3 和 OTDocument4 文件均可用。

用 `scripts/ot.py --profile generation call opentrack_edit_saved_page_layout`，从标准输入传入 JSON。

```json
{
  "worksheet": {"path": "OTProjects/Demo/OTDocuments/Output4.opentrack", "sha256": "<source SHA-256>"},
  "orientation": "landscape",
  "horizontal_pagination": "fit",
  "vertical_pagination": "automatic",
  "margins_pt": {"left": 18, "right": 24, "bottom": 30, "top": 36},
  "preview_only": true
}
```

- `orientation` 可填 `portrait` 或 `landscape`。切换方向时同步交换存档中的纸张宽高。
- 两轴分页可分别设为 `automatic`、`fit` 或 `clip`。这些是原版 Document Setup 和 AppKit 的打印分页模式。
- 页边距的单位是点。要设置页边距时四边均应明确填写，留出正的可打印面积。
- 要换纸张时填写 `paper`，包含 `name`、`portrait_width_pt`、`portrait_height_pt`。宽高按未旋转的纵向提供。使用原版打印机可识别的纸型名，例如原档的 `A4`。自定义尺寸使用 `name: null`。指定名称时，原版恢复页面可能依据当前打印机的纸型表解释该名称。

其他字段沿用原档。设置 `preview_only: false` 并指定一个新的 `target_path` 即另存工作表，随后可独立回读。原版 1.7 保存时记录左、右、下、上页边距，方向和两轴分页，以及纸张宽高和名称。依据英文手册 9.5 节和原版工作表归档函数 0x4abe9c、0x4ab658。真正出页的分页效果和打印设备设置需在原版打印预览或输出中复核。
