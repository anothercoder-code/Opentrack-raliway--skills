> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# Signal performance/coasting：dev6只读补证

未修改生产、未创建合成数组并冒充golden、未运行原版。仅扫描已授权01/04及恢复v11中的fixtures/resources并阅读原01静态函数；不下载02。

## 新增可确定的语义

- 原01 `OTSimCourse.handlePassedSignalsOfEndArray:head:handlePowerSignals:` **0x63c2d0** 取得当前TrainCategory的categoryName，交给TrainController `indexOfTrainCategoryWithName:` **0x6cbc30**。后者转发TrainList **0x6d83f8**，顺序扫描`trainCategoryArray`并按名称相等返回位置。**performance和coasting索引对应当前Train目录中Category的数组顺序，不是run TrainType速度表索引**；独立读取应绑定明确Train目录、拒绝重复类别名及超长/缺项，不能凭类别名字臆造位置。
- 同一运行消费者读取performance与delay，再将performance **除100**传给`setAccPerformanceFactor:`。这使“百分数尺度、100为因子1”有使用点支持；不是仅凭默认100猜测。读取有效域仍由getter限定0<value<=200，否则回退100，回退值不能混作原始存档值。
- coasting getter **0x5d2628**仅把正整数返回，否则0；消费者仅以`>0`决定走类别coasting启用路径，实际上下速度来自另两个`coastingUpperSpeed_kmh/coastingLowerSpeed_kmh` getter。因此数组数值**不是km/h或米**。可描述为原始整数和当前消费者正值启用判定；不能声称所有正值是正式枚举、也不能删失非正原值变成bool。
- `informAboutTrainCategoryDownAtIndex:` **0x5d290c**对performance/coasting数组执行与Category下移相配的移位，进一步支持顺序依赖；不能只改TrainCategory顺序而认为信号数组不受影响。

## OTDelayPerformance布局：仍不可认证

- `encodeWithCoder:` **0x713d40**以一个`encodeValuesOfObjCTypes`调用，传入delay_s、performance，类型串地址为**DAT_0083ea78**。`initWithCoder:` **0x713ce8**读取class版本但没有显示条件分支，再按相同地址解码两个值。
- `encodeWithModelArchiver:` **0x713da0**明确分别`encodeFloat`两个字段。结合getter/setter可确定逻辑float字段和先delay后performance。
- **不能把这些证据等同于已确认经典归档class version和精确ff组。**现有可用string-literals注释未解析DAT_0083ea78；没有真实OTDelayPerformance实例，且未找到initialize/setVersion证据。缺initialize文件不是version0的证明。本轮不构造其class，也不实现既有项写入。

## 已授权实例扫描结果

考虑562个文件，按完整字节SHA去重为246个，55个候选成功按归档解码。4个包含名称的JSON/ZIP元数据候选不是归档，列为跳过，不能说解析失败证明不支持。

找到1204个**一般NSNumber**对象，链均为NSNumber0→NSValue0→NSObject0；观察编码组为`*`加`s`（1128）、`i`（52）、`f`（24），第一组保存ObjC类型串。这证明当前通用Foundation存在多种数值表示，不能认定`numberWithInt`一定写成`i`（小整数可能有紧凑类型）。它们在Engine、diagram等已授权fixture中，不是Signal coasting专属golden。

**OTDelayPerformance实例0；非空Signal performance/coasting数组0。**故“class版本仍未知”与“一般NSNumber读布局有真实样本”须分别报告。扫描并不排除其他未提供工程中存在实例，不能写成原版没有此功能。

## 本轮可以做到与具体剩余证据

可以只读报告Signal数组nil/长度、绑定TrainCategory名称顺序，以及已有通用NSNumber原始class/编码/值（只承认实际观察的完整形状）；若未来遇到未知类/版本，显示未知，不补默认记录。当前没有非空Signal数组样例，不能宣称完成其端到端读取验收。

要启用有限已有项修改，仍需：
1. 至少一个原版保存的非空performance Signal11归档，确证OTDelayPerformance完整class链/版本与ff分组；或明确授权静态数据证据解析类型串及class版本，不能猜。
2. 至少一个非空coasting Signal11归档，确认同一槽内NSNumber的编码形态及类别映射与实际Train目录；一般Engine NSNumber不能充当该golden。
3. 独立原存档→读取→单索引修改→freshdecode→逆向全图恢复测试，保留数组长度/其他项/End引用；数组增长及类别重排另立契约，不能套setter上界自动增长。

小型统计与函数SHA见 `artifacts/rebuild-dev6/signal-arrays-instance-scan.json`、`signal-arrays-static-evidence.json`；不包含供应商原件。以上是研究证据，不是生产功能或原版运行通过。
