# 发行能力、工具合同与历史记录

不要因为文件名含 `current`、字段名含 `current_source`，就把一份旧记录当成当前软件/项目
已经通过的证据。先读记录日期、版本、工程身份、受测输入和证据层次。

| 资料 | 正确用途 | 不能推导 |
|---|---|---|
| `EDITION.json` 与 `RELEASE-MANIFEST.json` | 本次发行身份、文件清单及授权要求 | 所有公开工具都已原版GUI通验 |
| [版本划分](editions.md)与实际发现的schema | 当前版本提供的能力类别、各接口合同 | 单个模板的范围就是原版或整个Skill的上限 |
| [basic-edition.md](basic-edition.md)、[basic-edition.json](basic-edition.json) | basic1的历史发行和当时三站案例 | basic2也开放旧八股道/高级入口，或其结果属于当前工程 |
| [release-validation-summary.json](release-validation-summary.json) | inplace1/basic1等当时的测试与原版观察 | 字段中current_source即当前full1全部功能已验收 |
| [coverage/current-function-coverage.json](coverage/current-function-coverage.json) | 记录日期对应的功能覆盖和状态轴 | 历史数量等于当前接口数；静态接口等于实际仿真能力 |
| [release-validation-20261031.json](release-validation-20261031.json) | 双版发行的汇总，含不同阶段结果及限定说明 | 汇总内的Full结果自动成为Basic能力，或旧原版成功替代本次运行 |
| [验收分层](acceptance-levels.md)中的具体案例 | 技术路线和已观察行为的参考 | 新站数、布局、车辆、故障和运行图已经通过 |

历史原始记录不为“统一口径”改数值或删除失败。新变化增加明确作用域的修订记录，
用本次证据更新本次结论；字段同名不表示它们属于同一工程、同一次运行或同一版本。

软件授权另按[完整软件授权前提](software-authorization.md)执行。旧程序保存检查通过、
历史GUI截图或成功仿真，都不证明当前用户、设备和用途持有合法完整版授权。
