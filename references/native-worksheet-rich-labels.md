# 原生工作表富文本标签

## 导入外部 RTF

`opentrack_import_saved_worksheet_rich_label` 从 SHA-256 绑定的 `rtf` 文件新建
独立标签，或替换现有独立标签内容。传入源图档 `worksheet`。新建填写
`frame: {x, y, width, height}`，替换填写 `graphic_id`，沿用原位置和框。
可同时提交下文的 `appearance`，用 `preview_only: false` 和新的 `target_path` 保存。

导入支持原生 RTF0，以及可使用 Windows-1252 表示的 RTF1 文本子集。该子集支持多段、
字体、字号、粗体、片段颜色、跨段共用对齐和作用域内的文字样式。RTF1 转成原版标签用的 RTF0。
嵌入对象和未复原格式控制需要另行处理。新标签在只有一种文字颜色时使用该颜色作为模型前景。
有多种片段颜色时可用 `appearance.text_rgb` 指定原版视图重新载入时应用的整体前景。

Training 存档已用此入口另存两段文本，核对了加粗片段、重音字符、两种字体、颜色和文本框。
原版 `OTLabelModel.pasteAt:::withData:`（0x516374）和
`init::withData:`（0x516638）建立独立标签，`encodeWithCoder:`（0x517120）
将其保存为 RTF 及图元外观。

## 检查和编辑已有标签

`opentrack_inspect_saved_worksheet_rich_label` 按图档路径、SHA-256 和图形编号读取 RTF0 字段，
列出文字片段、字体表、粗体、半点字号和片段前景色，并读取标签框锚点、段落对齐和背景开关。
`opentrack_edit_saved_worksheet_rich_label` 用原片段
序号和 `expected_text` 匹配内容。`replace_with` 的每个片段可以独立指定粗体、字号、`font` 和 `text_rgb`。
省略格式时沿用被替换片段的设置。字号的原生单位为半点，例如 `28` 表示 14 pt。
`paragraph_break_before: true` 在该片段前插入新段。多段标签的回读以从零开始的 `paragraph` 标出所属段落。
逐片段字体的 `family` 默认沿用原片段的字体类别。已有同类别、同名称的字体和相同 RGB 色值会复用对应表项。

```json
{
  "worksheet": {"path": "<源 .opentrack>", "sha256": "<源 SHA-256>"},
  "graphic_id": 53,
  "edits": [{
    "index": 0,
    "expected_text": "Output Example",
    "replace_with": [
      {"text": "Output "},
      {
        "text": "Platform 9",
        "paragraph_break_before": true,
        "bold": false,
        "size_half_points": 28,
        "font": {"face": "Times New Roman", "family": "roman"},
        "text_rgb": [30, 88, 160]
      }
    ]
  }],
  "preview_only": true
}
```

设置 `preview_only: false`、给出新 `target_path` 后保存 `.opentrack`。文字仍是
`OTLabelModel` 内的原生 RTF。新文字采用可打印 ASCII，普通反斜杠和花括号按 RTF 字面量转义。

## 外观

可单独提交 `appearance`，也可与 `edits` 同一次保存。每项只在显式提供时修改。

```json
{
  "worksheet": {"path": "<源 .opentrack>", "sha256": "<源 SHA-256>"},
  "graphic_id": 53,
  "appearance": {
    "resize_anchor": "right",
    "paragraph_alignment": "center",
    "font": {"face": "Arial", "family": "swiss"},
    "text_rgb": [30, 88, 160],
    "background_rgb": [242, 244, 246],
    "draws_background": true
  },
  "preview_only": true
}
```

- `resize_anchor` 是原版重新测量标签框时使用的水平锚点，可选 `left`、`center`、`right`。
  保存操作保留现有图形坐标和已存矩形。
- `paragraph_alignment` 写正文段落的 RTF 对齐控制，可选 `left`、`center`、`right`、`justified`。
- `font` 替换单字体标签的字体表。使用单个已声明的字体，`face` 填目标机器上的字体名称，省略
  `family` 时沿用现有类别。可显式选择 `swiss`、`roman`、`modern` 或 `nil`。字号和粗体继续应用于原片段。
- `text_rgb` 将整个标签的前景色同步写入原生 `NSColor` 和 RTF 颜色表，三个整数依次表示红、绿、蓝
  通道，范围 0–255。新前景色为不透明。
- `background_rgb` 写不透明填充色。`draws_background` 控制原版标签背景填充开关。
  背景或者框锚点单项保存会保留原始 RTF 字节。

支持实档中独立图形的原生 RTF0 标签和扁平字体表。可分次修改整段外观和逐片段字体或颜色。
附属和仿真标签由各自原生编辑器管理。
原版 `0x517120` 以 AppKit 的 `RTFFromRange:` 写入，`0x516e30` 以
`replaceCharactersInRange:withRTF:` 恢复。`0x516ce8` 设置原生模型的锚点、颜色和背景开关，
`0x518698` 应用锚点，`0x51854c` 对标签全部文字应用字体。
多段、混合字体和逐片段前景色已在 Demo 图档完成另存及独立内存解码。
原版打开标签视图时会以模型的前景色覆盖整个文本范围。逐片段颜色写入 RTF 存档，
原版可见前景色由 `appearance.text_rgb` 控制。目标字体由工作站提供。
标签框绘制和重新测量留待集中验收。

## 信号名称与临时标签

`opentrack_edit_saved_temporary_labels` 可将存档的信号名称批量写成原版独立临时标签，切换独立既有标签的临时属性，或清除全工作表的独立临时标签。
继续使用 SHA-256 绑定的 `worksheet` 和默认预览。核对回执后设置 `preview_only: false`，另存到新的 `target_path`。

| `operation.action` | 参数与结果 |
|---|---|
| `create_signal_name_labels` | `signal_ids` 选择实际 Signal 图形编号。省略时按图档顺序处理有名称的当前格式信号。匹配原版 6 pt 正文和信号图形框中心。普通及组合主信号的灯位、虚拟图标和附加符号尺寸已核对。画面隐藏图标也可处理。需要放置其他可见信号图标时，按回执确认工具边界。可选 `font_face` 默认为 Helvetica。 |
| `set_temporary_label` | 用 `graphic_id` 选择独立标签，填 `expected_temporary` 和新 `temporary`，仅写其原生类型位。 |
| `remove_temporary_labels` | 移除图档中所有独立临时标签。工具会报告移除的 ID，继续保留普通标签和运营数据。需要保留的一枚临时标签可先转为普通标签。 |

批量生成等同原版菜单命令追加一批标签，重复执行会增加一批。名称使用单行原生 RTF0。字体随工作站，
初始文字框预留显示空间，实际字体排版由原版渲染。实现依据 OpenTrack 1.7 发布说明第 37 项及
原版 0x4a550c、0x4a692c、0x516a1c 和 0x5d84a4。Reading 的两枚名称标签和 Demo 的临时属性已经过文件回读，
原版窗口渲染和存盘菜单行为待验。
