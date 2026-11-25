# 原生工作表图片

`opentrack_embed_saved_worksheet_picture` 将外部 PNG、TIFF 或 EPS 保存到原生
`.opentrack` 工作表。用 `worksheet` 和 `image` 分别绑定图档、图片路径和 SHA-256。
已有 PNG 调用也可继续使用 `opentrack_embed_saved_worksheet_png` 的 `png` 参数。
添加图片时，`frame` 必须包含图面坐标 `x` 和 `y`。若省略 `width` 和 `height`，
使用图片的自然尺寸。若只填写一边，另一边按物理长宽比计算。

要替换已有图片，指定 `graphic_id`。省略 `frame` 时保留该图形现有的位置和显示宽高。
`preview_only: false` 和新的 `target_path` 将结果保存为 `.opentrack` 副本。
`opentrack_inspect_saved_worksheet_bitmap` 按图形编号读回载荷类型、原始尺寸及显示框。
位图报告像素和 TIFF 的 SHA-256，EPS 报告矢量字节 SHA-256 及边界框原点。

支持静态、非隔行、每通道 8 位的 PNG，包括灰度、索引、RGB 及带 alpha 的图片。
透明像素需要用 `background_rgb` 给出三项 0–255 的背景色，保存时按指定颜色合成。
图档存储原生 `OTLogoModel` 和其 `NSBitmapImageRep` 的未压缩 RGB TIFF 像素。
图片仍是可独立移动和替换的工作表图形。PNG 的文件元数据不进入该 RGB 表示。

TIFF 支持单图、正向、条带式的每通道 8 位灰度和 RGB。可读未压缩、LZW、Deflate、
PackBits 及适用的水平预测。透明区域支持非预乘 alpha，需指定 `background_rgb`。可直接保留
原版格式兼容的 TIFF，其他支持的 TIFF 归一为原版 RGB 表示。按各轴 DPI 计算自然尺寸，
缺省使用 72 dpi。磁贴、多图以及其他像素配置需要进一步支持。

EPS 写成原生 `NSEPSImageRep`，保留源矢量字节，并保存 DSC 外层 `BoundingBox` 的尺寸
和原点。支持在外层尾部声明边界框。Training 的 180 × 19 点 EPS 及 Demo 的 653 × 429 像素、
150 dpi TIFF 已通过公开接口另存并回读。后者自然尺寸为约 313.44 × 205.92 点。图片替换可以保留
既有显示框。原版窗口内的显示仍待集中验收。

原版 `OTController.paste:`（0x434d1c）为 TIFF 和 PostScript 创建同一种照片图元。
保存字段由 `OTLogoModel.encodeWithCoder:`（0x519934）和
`OTLogoModel.initWithCoder:`（0x519848）对照确认。AppKit 的 EPS 编码函数保存边界原点及源数据。
