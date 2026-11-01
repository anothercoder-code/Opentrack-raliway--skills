# 跨文档 Shunting 与递归 Overlap：原生契约复核

日期：2026-10-29。仅静态读取已授权的原01函数与原04存档，不执行原版，不创建新发布或修改 dev0。证据索引与04扫描结果位于 artifacts/rebuild-dev1。反编译代码是原二进制的推断表示，动态调用参数需结合实际存档解释，不能当作原作者源码。

## 结论

1. **原生局部 Shunting/Overlap：已证支持。** 自动 OTPath 包装 OTShunting；同一 Shunting 可作为 Overlap，没有独立 Overlap 类。04中发现5个真正由本地 End.ShuntingList 持有的 Shunting，均只引用本地模型。原生 Overlap 可选择 Route 终点文档内其他 End 的 Shunting，不局限于恰好从 Route 终点开始。
2. **跨文档单一 Shunting：当前未形成可实现的原生持久化契约。** 原生 Shunting 选择浏览器明确在文档边界停止展开，因此“该界面支持随意跨文档延长 Shunting”被代码证据否定。SecurityArray 父类虽有跨文档索引字段，却不能证明 Shunting 具备 Route 的续段保存和重建协议。不得把继承字段存在等同于跨文档 Shunting 支持，也不能据此断言原版所有其他路径绝对不支持。
3. **递归 Overlap：已检查运行构造路径不递归展开。** 父类允许持久化 overlapName/startID，因而 Shunting 也能承载这些字段，但原生 `getOverlap` 只查找一层；`Dest.fillElementLists` 取选中 Overlap 的边和释放时间，`addSlipsToList` 只遍历该对象自身的边，不调用下一层 getOverlap。不能用给 Shunting 再写 Overlap 字段来声称“嵌套防护区已经生效”。不实现未经证实的递归行为。

## 具体代码证据

- `OTRouteInspector.ot_browser:createRowsForColumn:inMatrix:` **0x5b5030**：在 shuntingBrowser 分支中，候选 End 的 document 与其 actualRelated.document 不同则设置为 leaf；起始行也执行该判断。这是明确的界面可达性限制，不是根据方法名猜测。
- `OTSecurityArray.checkConnectionToOtherDoc` **0x5be554**：检测 related 是连接器且目标文档名不同，并写 `indexOfFirstEndInOtherDoc = i + 1`。这是通用父类字段；在本次函数文本扫描中，调用者是 Route 搜索路径。尚无 Shunting 构造器设置该索引及构建配对续段的完整证据。
- `OTRoute.encodeWithCoder:` **0x5a7538**：编码前 removeObjectsOfContinuation，编码后 appendObjectsOfContinuation。对应实现 **0x5a5874 / 0x5a575c** 是 Route 专属；Shunting encoder **0x5c90cc** 只调用父类encoder并附加 speed，没有同样的strip/reappend行为。
- `OTSecurityArray.encodeWithCoder:` **0x5c2c3c**：持久化当前 SecurityArray6 的组5跨文档索引、组7 overlap名称、组9 startEndID；没有 Overlap 文档名字段。对象类布局继承这些槽，不代表所有子类业务语义均启用。
- `getOverlap` **0x5c20b4** 与 `getOverlapWithName:andOverlapArrayStartEndID:` **0x5c213c**：startID<0时从最后End的ShuntingList按名称查找；非负时在最后End所属文档中查找该ID的End，然后查其ShuntingList。没有进一步 `getOverlap` 递归调用。
- `OTRouteInspector.overlapChangePressed:` **0x5af994** 收集 Route 最后End文档中的全部 Overlap；`overlapOKPressed:` **0x5afa44** 可从此完整列表选择，并将所选 Shunting.firstEnd.ID 写入临时startID。`numberOfRowsInTableView:` **0x5b5ff8** 显示终点列表或全列表两种视图。这证明显式同文档非终点起点是原生可选域。
- `OTDest.fillElementLists` **0x476138** 在每个 simRoute 上调用一层 getOverlap，将其 addSlipsToList 并取 releaseTime。`OTSecurityArray.addSlipsToList:` **0x5c2204** 只将自身 edgeAtIndex 添加到集合。所检查路径不传播 Overlap 的 Overlap。

## 原04实例扫描

扫描46个 `.opentrack` 文件、33个唯一SHA，全部可由通用只读typedstream解析器解码；旧Document3/SecurityArray5也仅解析不迁移。实际主文档模型数组的本地 ShuntingList 中共有5个 Shunting，topoOst中4个、topoWest中1个。均 `indexOfFirstEndInOtherDoc=-1`、全部几何节点在该文档模型数组中、overlap名称为空。所有扫描Route均无非空Overlap名称，因此没有原04中的Overlap绑定或递归实例可用作黄金样例。

完整对象遍历共遇到9个Shunting对象；其中4个并非主文档本地ShuntingList直接持有，部分节点在主模型数组之外。**这些嵌套对象不能作为跨文档Shunting支持的证据。** 扫描报告分别保存全图与本地归属统计，避免把嵌套残留/引用对象当作有效跨文档运行路线。

另一个已证输入覆盖差异：自动Path包装的Shunting body IDs并不总是[-1,-1]。原04中本地记录还出现[3,597]和[5,597]，后一条实际本地起点为540。当前dev0使用[-1,-1]初始化的有限模板是一个数据子域，其检查器会拒绝上述原档变体。必须表述为“本工具未覆盖”，不能表述为“原档坏了”或“原版没有该能力”。详见扫描记录中的body_id_pair及info_refs。

## 对接口的建议

- 保持跨文档Shunting创建关闭，原因写为：缺少续段构造、跨文档归属、保存/重载解析的可靠契约及有效原档样例。不要照搬Route的配对续段结构。
- 保持递归Overlap创建关闭，原因写为：已查原生准备路径只处理一层；仅可保存字段不能证明递归效果。此项不应作为必须复刻的原生功能。
- 可明确新增独立有限域 `same_document_explicit` Overlap绑定：仍以精确name/ID/start引用绑定同一终点文档的Shunting，允许非终点起点。必须显式选择该语义，不悄悄放宽现有终点域，也不推断该位置的运行防护合理性。当前没有实际绑定黄金样例，先补数据往返和原生查询等价的只读解析测试再考虑上线。
- 原档Shunting检查应分为“能读取/报告”和“允许修改”。只读报告可展示不同body ID形态；修改需要分别核实原生新建、复制、自动Path重建中的ID与OTArrayInfo更新顺序，不把不匹配历史字段自行修复。

本轮没有生成跨文档Shunting样例、没有执行动态内核或原版。证据不够完整的两个主题以精确缺口结束，避免新增看似可用、实际不被原版解释的数据。

## 已补只读检查接口

在独立 dev1 目录新增 `current_shunting_workflow/inventory.py`，并为现有工具增加 `inspect_inventory` action。只接受明确的 Document3/4、End6/7（含已知 StationEnd0/Conn1 子类）、Shunting0/SecurityArray5或6、Path0和ArrayInfo0布局。按实际本地 End.ShuntingList 枚举，排除非本地列表的嵌套对象。输出原始path/body ID、saved refs、overlap字段、节点归属与editable标记。未知布局拒绝。

原04五条本地记录全部可读且editable=false，原有core严格修改读入仍拒绝这些旧文档。生成域新记录可读且editable=true，此标记只表示满足现有preview修改域，不表示原版运行认可、保存授权或安全发布门已通过。没有迁移、规范化或修复原存档，也没有放宽create/bind/delete的校验。

## 收尾补充：显式同文档非终点选择

已新增 `bind_overlap` 的可选 `spec.selection_policy`：默认 `route_terminal` 保持终点起点约束；显式 `same_document_explicit` 允许当前 Document4 新建域内同文档的非终点起点。要求精确 name/array_id/start_id 引用、全部节点为当前文档模型中的同一对象，且起点和后续节点均不得重入 Route 终点之前的节点；仍不接受旧版变体、跨文档或递归 Overlap。此非重入约束是工具保守限定，不声称为原生完整范围。

正常例子由 `tests.test_rebuild_dev1_overlap_selection.example()` 从已有网格数据中选取不相交的局部有向链创建 Shunting，再以显式策略绑定。测试验证默认策略拒绝、显式策略保存后全新解码的 name/startID、按原生查询规则从指定 End.ShuntingList 按名称唯一解析、解除后逐字节恢复，以及 wrapper 不修改源文件。仅数据层验证；未验证这种位置实际运营防护效果，未改默认场景或原04。
