> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev3 单文档基础设施闭环

新增 `opentrack_preview_infrastructure_chain`：一次纯内存调用生成拓扑→主信号→Route→点站→Path→Itinerary与对应DestInfo。它复用已有存档核心，不引入另一仿真内核、不通过中间落盘绕过导出门。

请求须明确权威文档路径、有向端点序列、信号属性和Path/Itinerary顺序。点站两半共享同一StationModel，最终Station目录及DestInfo路径/ID/ExtInfo保持闭合。分支只走用户选择的边，不自动寻路。非默认Route描述/释放/预留及信号显示、尺寸、视距、延时亦经独审读取验证。

输出为三个候选成员的摘要，不是文件交付：基础设施文档、Station目录、DestInfo目录。`saved=false`、`operating_ready=false`。没有车辆、Course、时刻表或.run；不支持Connector、多文档、循环Route/Path/Itinerary，未知字段明确拒绝。

本轮独立普通验证、链与分支真实MCP/默认Skill回归和受影响模块回归见artifacts/rebuild-dev3。41项针对性回归包含此前有限拓扑、有限行程、注册/元数据及新闭环；不是重新运行全部旧90项，旧90项结果保留为dev2历史证据。四个关键复用核心哈希未变，原v11发布器未改。

剩余工作仍包括：一般运营数据接入该新基础设施、跨文档主段/续段参数化、其他目录重命名和参数域、新导出独立审查、原版加载/一日场景实测。不能由这个单文档预览成功推断全部176功能完成。
