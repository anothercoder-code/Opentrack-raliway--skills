> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev3 候选：有限拓扑接入进路／路线／行程（只读契约研究）

## 结论

不需要发明新存档格式，但**现有公开工具不能直接串成闭环**。dev2 拓扑工具只返回预览摘要，没有可被下一工具读取的文件或持久中间句柄；现有 MultiDocument wrapper 又要求完整实际目录、`.run` 与目录绑定。应新增一个纯内存编排入口，复用底层 byte-in/byte-out 核心，而不是偷偷保存预览或放宽发布门。

第一可独立实现域建议：**一个文档、显式简单有向进路、点站可选、无 Connector 的拓扑→主信号→Route→Path→Itinerary→DestInfo 预览**。限定不能重复 End 的 Route/Path；不自动寻路，不推断平面交叉互通，不生成列车和运行图。先闭合这一域，再做跨一个文档边界的独立后续域；不是承诺通用互通。

## 目前缺的显式信息

1. **方向及定位**：生成拓扑的 vertex key + side 到本地 End ID 的映射已有。每条进路还须明确有序有向 End 序列；坐标、站名与边无向连通均不能替代行驶方向。长度／速度已在 Edge 中，不能推导安全边界。
2. **信号**：明确 signal name、所属 End、angle/width/height、sight_m、delay_s、show_symbol/show_icon。现有 builder 仅支持固定主信号 raw profile，不代表所有信号制式。Route 两端须为 show-type2 主信号，内部不能穿过另一个主信号；按现有规则拆进路而非忽略信号。
3. **Route**：name、ordered End refs、description、release_groups(global/each_end)、reserve_previous。由 owner End 的 highestGivenRspID+1 分配本地 RSP ID；须同时检查已有 Route/Shunting/Path ID 不冲突及反向引用，不让调用者猜 ID。
4. **Path/Itinerary**：明确有序 Route 名称及所属文档、Path 名称与顺序；编排层把本轮新建名字解析为精确 document/name/array_id/start_id。必须连续，不自动拼接不连续段。初期使用普通无环 Itinerary；dev1 的有限重复 Path 域可作为之后显式选项，不能隐式更换默认语义。
5. **目录绑定**：初始化空的 `OTDestInfoList`，不是空JSON或缺失文件。须声明每个 document 的权威路径，basename 与文档名一致；DestInfo 保存 owner document path、start ID、完整 ExtInfo 顺序。Station catalog 已生成，但 Point Station 不等于站台／停车区。
6. **运行项目**：若只输出基础设施+stations+dest，不应要求或虚构 Train/Depot/Course/Timetable/.run。以后接运营模块时另需四种目录 donor、精确原生执行根与 .run 六目录及Document绑定、train-type速度索引、明示运营计划；不能标成 operating_ready。

## 可复用与真实阻碍

- `network_generation_tools.NetworkGeneration.compose` 已有单文档信号→Route→Path→Itinerary顺序；可参考但它重新生成拓扑且使用 Path/Itinerary templates，不能直接消费 dev2 摘要。
- `zero_generation.native_signal_routes.build_main_signal/build_route` 是现成核心；`validate_topology` 要求 ordinary End 的 related 仍是 ordinary End，因此**转换为 OTConnModel 后的文档不能直接交给它**，即便待加信号远离 Connector。不要删除这个校验来“兼容”。
- `multi_document.operations.create_path/create_itinerary` 已对完整文档字节集合+空/已有DestInfo目录做精确引用、连续性、回滚及重读，无需新存档类型。
- `multi_document.generate.make_pair` 和 `signal_protection.branch_network` 是固定样例：先构造本地信号/Route，再转换 Connector；跨边界 Route 另有 source主段与receiver fragment、continuation index及owner list。它们不是通用跨文档Route创建接口。
- 因此多文档版本须**编排阶段顺序显式化**（signal/local Route先于Connector），并另证明一次跨界 Route 的主段/续段构造。现有字节格式足够，但缺通用参数化、安全引用闭合的实施函数；不能称“仅调已有工具就全部完成”。
- 点站的 End/type/model 引用必须在全链条重读中保持；现有生成器采用先信号后station的顺序，可复用该顺序，避免未测试的中途重写。

## 三组普通验收建议

1. **单文档链，完整正例**：显式3个双顶点、2段轨道、2个终端主信号和1点站；新Route→Path→Itinerary+DestInfo。新解码验证端点序列、Edge序列、RSP高水位、Signal↔End双向引用及DestInfo精确匹配；header/shape输入不变、wrapper saved=false。真实MCP和默认Skill结果相同。
2. **分支选择与连续性**：一个带分支但不自动寻路的图，分别生成明确指定的两条简单进路；只选择其中一条组成Path，重读不得误纳另一支。额外普通坏输入：Route跨内部主信号、反向/断开的End列表、Path列表不连续，均应拒绝且不改变输入。
3. **边界域显式拒绝及保留**：初期请求含Connector、多文档或循环Route明确拒绝，不降级删除它们；点站与无信号附加对象的合法输入保持引用/属性不变。未来跨一个文档边界域必须另有主段/续段黄金结构、双向Connector、完整document_paths/DestInfo重读测试，不能复用单文档通过数充当跨文档通过。

本说明为源码只读研究；未修改dev2生产代码、未运行原软件、未启用导出。上述测试是建议，不是已通过结果。
