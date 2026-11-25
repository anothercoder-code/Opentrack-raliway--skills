> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev5 显式终点停站存档域

新增 `opentrack_preview_final_stop_chain`，独立于通过计划，构造单文档单程最后一站停车的八成员内存候选。没有通过修改一个stop标志冒充完整停车模型。

实际检查入口两半type1与终点两半type2属于同一StationModel、实际单Edge方向/长度、出口信号、区域四半端无分支，以及从实际Engine读取并向上取整的车长能放入该区段。普通入口不增加时刻表站次；行程实际最后两节点必须正是所选入口→参考点。

服务通过原有Course/Timetable构造函数生成，不修改旧固定五站次guard。仅最终行记录为stop，前序通过；到发相等、dwell0、实际时间占位/实际day0。全部字典key、站序、索引、日偏移、车辆/行程及六目录/run引用重读核验。显式合成A→S→B→T例仅选择A→S→B行程，T为请求声明的拓扑，不是自动加轨或后续开行。

不支持中途停留续发、反向停车、折返/Connection/车底周转或多Engine/拖车。实际三纵三横应用须明确站、方向、entry/exit/长度、出口信号与终停车次计划，不擅替用户设计。终点存档配置正确不等于实际已停稳或完成仿真。

本轮受影响回归、独立服务/编排及真实双通道证据在artifacts/rebuild-dev5。八成员仅存在内存候选，saved=false；未开启新导出、未执行原版、未修改既有核心guard。
