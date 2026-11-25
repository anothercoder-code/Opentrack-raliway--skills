> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# 下一轮存档参数缺口：只读审计（dev5）

审计范围：当前已注册工具、typed schema、实现源码，以及原01函数文本。没有修改生产代码、没有执行原版、没有新增导出。以下是候选缺口，不是已实现或已验收声明。优先级按证据完整度，不按参数数量。

## 1. Signal11 调度模式（优先，单一整数字段）

- **getter/setter**：`OTSignalModel.signalDispatchingType` `0x5cf660`；`setSignalDispatchingType:` `0x5cf64c`。setter直接赋值，不调用其他对象。
- **存档槽**：Signal11 `contents[12].value`，编码 `i`。`encodeWithCoder:` `0x5d3fd0`在 warningSpeed 后编码 signalDispatchingType；现 `route_factory.SIGNAL` 精确布局也给出 group12=i。
- **范围**：可证明原始有符号int32存储域；尚未核实所有枚举值对应运营含义，不能把任意int32说成有效调度配置。现生成器固定7，仅证明默认值，不证明其他枚举。
- **现覆盖不足**：`signal_type_workflow/local_core.target`要求dispatch=7；type配置只改group8/11。现SignalAttributes schema不含dispatch字段；没有可调用的指定dispatch编辑。
- **副作用**：setter未见对象引用变更；不模拟调度效果。必须保持End、SigInd、Route/Path、graphicArray身份不变，不放松已有类型转换校验。
- **可独立回归**：已有Signal11选择器（源SHA、graphicArray index、Signal/End ID/name）；修改单槽、fresh decode、反向全图还原、默认7往返。其他代码只能标raw而非枚举认证。映射M3.6、R17.18（部分read/modify，export仍关闭）。

## 2. Signal11 四个独立布尔存档位（优先，不是整包flags裸写）

| 字段 | getter | setter | group9 slot2 位 |
|---|---|---|---|
| baliseReleaseAtBalisePosition | 0x5cf5d0 | setBaliseReleaseAtBalisePosition: 0x5cf5c0 | 0x20 |
| accelerationForbidden | 0x5cf624 | setAccelerationForbidden: 0x5cf614 | 0x40 |
| keepClosedForStationStop | 0x5cf640 | setKeepClosedForStationStop: 0x5cf630 | 0x100 |
| baliseControlAllBrakingActions | 0x5cf608 | setBaliseControlAllBrakingActions: 0x5cf5f8 | 0x200 |

- 四setter均直接写char字段；Signal coder `0x5d3fd0`对非零布尔值逐位组合。typed API应只接受真正bool，保留所有其他位，不采用任意int32覆盖整flags。
- 现本地signal工具只接受固定辅助位组合，并且类型修改不编辑flags；SignalAttributes也没有这四字段。生成器默认flags不是独立修改能力。
- 不含外部名称/ID引用更新，但属于信号运行行为配置。只验证存档赋值，不宣称列车保护安全性、站停行为或运行效果。
- 可独立测试每位开/关及组合、其他位逐位保持、End/指示图引用不变、解码/逆向全图还原。枚举语义不涉及，单位不适用。映射M3.6、M7.2（仅配置层，不实现运行时行为）。

## 3. Signal11 按索引 performance / delay 项（证据有层级缺口，先既有项修改）

- **容器/槽**：`performanceArray` getter `0x5d2004`；Signal group14 `@`。Signal coder明确编码该数组。
- **getter/setter**：`performanceAtIndex:` `0x5d2010` / `setPerformance:atIndex:` `0x5d20fc`；`performanceDelayAtIndex:` `0x5d2258` / `setPerformanceDelay_s:atIndex:` `0x5d22a8`。
- **子记录**：`OTDelayPerformance`，getter delay_s `0x713cb0`、performance `0x713ccc`；setter `0x713cbc`、`0x713cd8`直接赋float；coder `0x713d40`按 delay_s、performance 顺序编码；init `0x713bfc`默认0/100。
- **范围与单位**：Signal-level性能getter/setter以0<performance<=200为有效域，否则getter回退100；delay单位s，子setter未夹范围。应API限制有限binary32并明确这是工具限制，不能猜物理有效上限。performance的百分数解释仍需UI/使用点进一步确认，当前只称原始性能值。
- **重要边界**：setter允许索引<=1000，而prepare `0x5d2330`的`arg1 - 1U < 999`仅创建长度1..999；不能直接宣传0..1000自动增长均安全。先限定已有非负索引，不增长、不迁移旧NSNumber格式；默认值回退不等于数组已经存在。
- **尚缺证据**：本次对原04可解析.opentrack遍历未找到OTDelayPerformance实例；编码函数证明字段顺序，但确切子类版本/`ff`分组与真实golden数组仍应在实现前从原01类型元数据或其他已授权原档核实。不能依据变量名直接捏造子记录布局。
- **现覆盖不足**：当前signal工具明确拒绝非空performance/coasting数组，没有数组字段schema。可先补只读库存和已有项schema验证，证据落齐后做索引修改+所有其他项/共享对象不变。不得把索引自动解释成TrainCategory ID；类别到索引映射另需核实。映射M3.6、R17.15（部分待证实，不结项）。

## 4. Signal11 按索引 coasting 原始整数项（结构证据有界，语义需核实）

- `coastingArray` getter `0x5d261c`，Signal group15 `@`；`coastingAtIndex:` `0x5d2628`；`setCoasting:atIndex:` `0x5d268c`。
- setter用NSNumber.numberWithInt构造对象并替换数组索引；getter仅返回正整数，缺项/非正数回退0。不能擅自把存储值归为bool，或把整数解释成距离/速度。
- prepare `0x5d2764`用整数0填充，长度条件与performance相同；同样不应按setter索引上界盲目生成数组。
- 现工具没有此修改入口且拒绝非空数组。优先实现既有项read/modify，需核实NSNumber当前编码形状及类别索引映射；不改变数组长度，不调用运行时coasting行为，不承诺自动节能优化。
- 回归：共享数组拒绝、单索引替换与其他项/引用保持、正值/0/负值存储和getter回退的区别、fresh decode与逆向全图恢复。映射R17.16、M3.6（部分），export不启用。

## 已有能力，不重复发明缺口

- Route release/announce distance、reserve/release time、reservation distance、approach length/speed、release groups、reserve_previous已在`signal_protection/core.py`暴露。不要再作为新参数域计算。
- Train10原始字段在`train_fields.py`；Engine resistFactor/adhesion和Category5在`engine_category_fields.py`；Train最大加速度/制动延迟/释放速度及Category相关6字段在`stock_operations.py`。既有参数不能重复计数。
- 加速延迟、最小保持速度及曲线阻力等在旧`rolling_stock.py`/`stock_maintenance.py`和typed models中已有代码。需要区分旧操作链复用与当前轻依赖入口接线，不能声称完全不存在。
- Engine cw/radio已有`opentrack_batch_current_catalogs`；adhesion_load/force_max/min已有`opentrack_edit_current_engine_physics`；曲线有专门工具。
- Signal名称、sight/release speed/delay已有旧SignalAttributes/geometry实现；当前创建接口也支持命名。名称编辑不是纯新增功能，最多是现存能力迁移到current-archive工具域，不能虚报。
- Timetable现有时间编辑、批量计划时移及正在推进的停站流程不重复提案。

以上四个候选都不需要实现仿真内核；只有前两项现有字段/编码证据足够直接开始有限接口。数组两项应先补真实布局/索引映射证据，不能因用户要求全覆盖而跳过。
