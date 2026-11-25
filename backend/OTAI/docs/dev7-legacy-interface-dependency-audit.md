> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev7前置：三个旧接口的实际依赖审计

本轮只读审计dev6 clean源码环境；未开启旧写入、未导入/执行vendor代码、未改生产、未恢复旧发布器。仅两个只读Registry方法实际调用，第三个写入口只检查注册后的handler。证据：`artifacts/rebuild-dev6/dev7-legacy-interface-dependency-audit.json`。

## 结论与此前表述纠正

此前“加速延迟/曲线阻力等在stock_maintenance已有支持”应严格更正为：**代码和typed schema存在，但当前clean包的相应旧入口不可调用，不应记为已覆盖的可用功能。** 这不等于缺少仿真内核，也不是要求运行原版来解决。

| 入口 | 真实状态 | 依赖链／缺失 |
|---|---|---|
| `opentrack_list_catalog`，kind=trains | generation Registry列出；实际只读调用返回`NATIVE_DEPENDENCY_MISSING`，module=`typedstream_writer`，component=`.native_service` | Service lazy facade→native_service→archive.py；尚未进入项目文件读取就import失败。并非数据目录不存在导致。 |
| `opentrack_get_engine_diagram` | generation Registry列出；实际只读调用同样返回`NATIVE_DEPENDENCY_MISSING`，component=`.engine_points` | PointReader→archive.py→缺typedstream_writer；不能因工具可发现就声称Engine图完整读取可用。 |
| `opentrack_generate_operations`（含rolling_stock_operations/update_formations等） | Registry注册后handler已被`legacy_geometry_guard.reject`替换；**没有调用写入口** | 独立隔离码`LEGACY_GEOMETRY_DISABLED`；旧whole-project geometry写被隔离，其show_grid映射和未验证Document group18问题仍未解除。即便补decoder也不会解封。后方Generation→StockOperations→archive依赖还存在。 |

## 具体缺什么

`archive.py`定位CODE_ROOT/OTAI/vendor，优先OTUndo/tools，否则vendor/legacy，并可能追加vendor/python。此环境`find_spec`全部不存在：typedstream_writer、typedstream、opentrack_course_schema、opentrack_train_schema、opentrack_station_schema、hsr_capacity_graph。没有通过改sys.path或复制陌生解析器绕过。

v11完整ZIP只读清单确认：包含自有archive.py/generation.py/stock_maintenance.py消费者代码，**不含**上述typedstream_writer、三个schema或hsr_capacity_graph模块。ZIP有`verification/vendor/typedstream`（pytypedstream 0.1.0），元数据声明LGPL-3.0-or-later，附COPYING/COPYING.LESSER；它是只读测试oracle，不是缺失writer/schema/whole-project pipeline，不能当作补齐旧依赖的证据。当前独立codec另有MIT LICENSE。未执行vendor代码，也未把供应商原件纳入新产物。

## 安全且最小的下一步

1. **目录读取优先复用当前独立入口**：`opentrack_inspect_current_archive`对明确catalog文件已有轻依赖读取及分页；若用户需要run上下文，可增加只读完整库存→精确catalog绑定适配器，而不是恢复整个旧native_service。旧list_catalog的高级语义（曲线展开、分类/行程使用关系等）须逐项列差异，不能直接宣布完全替代。
2. **Engine图读取可优先移植纯数据投影**：用现独立`current_archive.writer`及已审Engine2/OTDDiagram布局，源SHA+engine name+diagram index绑定，只做paged stored point/scale读，不自动排序、推导功率、创建图、写出文件或调用旧PointOperations。先核实颜色/供电列表/损耗字段的完整布局，不能把已有曲线编辑器当成全部图属性读取。
3. **Train/Engine参数只迁移有证据的缺口**：复用已验证current_archive scalar/stock字段架构，将旧models中有原01getter/setter+coder支持的少量字段逐项移植成新的preview-only字段域，并fresh decode/逆向全图验证。优先Train加速延迟/最小保持速度/曲线阻力等尚不在当前allowlist的字段；flag组合需保留其他位、业务枚举未知则raw明确标注。不搬运旧draft/publish流程、不解除legacy_geometry_guard，不把整个stock_maintenance复制过来即算安全。

未做依赖安装、写入解封、原版运行或导出。具体3个入口状态只适用于当前恢复的clean包和当前环境；并不推断过去包含额外依赖的环境从未运行过它们。

## 精确可移植的三个Train参数（非重复allowlist）

已搜索current_archive全部.py，未见以下三个字段名/对应snake_case；它们不在train_fields十项、stock_operations六项、scalar_tools typed字段、vehicle_catalogs三个显式物理参数中。旧rolling_stock/TRAIN_SCALARS和models确有它们，但经上述隔离入口不可用。

| 建议字段 | getter / setter | Train16保存槽 | 原setter可证明的有限数行为 |
|---|---|---|---|
| acceleration_delay_s | accelerationDelay_s `0x6c14a4` / setAccelerationDelay_s: `0x6c14b0` | group9 slot0，f，s | 负数归0；非负数保留 |
| acceleration_delay_at_stop_s | accelerationDelayAtStop_s `0x6c14dc` / setAccelerationDelayAtStop_s: `0x6c14e8` | group22 slot0，f，s | 负数归0；非负数保留 |
| minimum_time_to_hold_speed_s | minTimeToHoldSpeed_s `0x6c1514` / setMinTimeToHoldSpeed_s: `0x6c1520` | group20 slot0，f，s | 有限输入夹至[0,60] |

`OTTrain.encodeWithCoder:` `0x6c2dbc`明确依此顺序编码三字段。三个getter直接返回成员。setter没有名称/ID引用修改，不要求重算编组、制动曲线或恢复旧Project流程。API可明确只接受有限binary32、拒绝bool/NaN/Inf，再复现上述clamp。NaN/Inf的原生FPU分支不作为此API承诺。

特别注意第三项：**旧models允许到1,000,000且旧scalar赋值路径并不自动复现60秒clamp，不能原样复制当作原生setter等价。** 是否启用该规则另由Train group15的useMinTimeToHoldSpeed位决定；首轮三个字段迁移应保持该位原值，返回“值已配置、启用标志未改”，不擅自启用。这是存档配置而非运行时速度规则实现。

最小回归：原Train16唯一身份/拥有关系；每字段负/零/正数与保持时间60上下界；binary32舍入、strict类型；fresh decode逐值比对；逆向只还原这三个槽必须恢复整图；源档不改。新增工具仅preview，原隔离入口与发布器保持关闭。
