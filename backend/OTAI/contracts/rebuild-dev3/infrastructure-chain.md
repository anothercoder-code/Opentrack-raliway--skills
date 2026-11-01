# 单文档基础设施编排闭环

工具：`opentrack_preview_infrastructure_chain`。本轮新增的是纯内存编排接口，不是新存档格式、动态内核或原版GUI替代。

## 明确输入

- SHA绑定的Document4 header及shape donor；新的文档名、权威`.opentrack`路径；路径basename必须等于文档名。
- 有限双顶点/边图（继承现有profile、每半端最多两边、detector禁用，最多400双顶点/800边）。几何交叉不自动连接。
- 明确主信号位置、方向、名称、sight/delay/display参数；现有固定raw main-signal profile，不代表全部信号制式。
- 有序简单Route端点列表及description/release_groups/reserve_previous；显式Path所选Route名字、有序Itinerary所选Path名字。
- 可选point-station（sign/name/vertex/side/placement/timing-point），不是平台或停车范围。
- 不接受多文档或Connector参数。未知字段不忽略；不支持自动寻路和循环／重复Route、Path、Itinerary。

## 阶段与存档契约

1. `topology.generate_network`：全新图对象，原donor仅提供header/type shape，原文件不变。
2. `native_signal_routes.build_main_signal`：新model ID=max+1，Signal↔End双向引用；随后`build_route`验证明确有向End序列、两端main信号、无内部main信号、RSP highwater及局部引用。
3. `station_binding.bind_stations`：两半End都绑定同StationModel/type2，同时生成Station目录；原函数回滚验证所有既有Signal/Route保持。
4. 初始化空`OTDestInfoList`，调用`multi_document.operations.create_path/create_itinerary`建立精确引用。原有方法保存首对象和完整Info顺序，并独立回滚/新解码。生成路径采用明确权威document_path，不把临时目录当原生路径。
5. 最终`Project`完整重读；DestInfo精确核对；Station目录sign集合和StationModel一致、点站两半绑定仍然成立。

核心返回三个成员bytes：文档、Station目录、DestInfo目录；wrapper仅返回hash/size和结构收据，`saved=false`。无写出或后续文件句柄，不因内存生成成功宣称文件已交付。不会自动补Train/Depot/Course/Timetable或.run，始终`operating_ready=false`。

## 本轮普通验证

9项测试通过：真实donor单文档链、显式分支选择、内部main信号拒绝、反向不连通拒绝、Path不连续拒绝、重复Route端点拒绝、权威basename不匹配拒绝、Connector字段拒绝、typed wrapper源保持且拒绝保存/多文档额外字段。链例新解码验证Itinerary确为A→B→C、DestInfo正确且B点站两半共享StationModel；分支例额外Route存在但未被选择的D分支不进入Trip。

这些是纯存档与接口测试，不是原版载入、停车、联锁或一日仿真验收。M3.6/M4.1/M4.3/M4.4/G03/G04/A06/A07为有界生成/读取部分证据，不标整项完成；修改已有工程、导出及通用互通未实现。
