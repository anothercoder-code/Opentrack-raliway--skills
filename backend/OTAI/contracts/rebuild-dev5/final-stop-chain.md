# 单文档显式终点停站：独立静态配置域

工具 `opentrack_preview_final_stop_chain`，不改变dev4默认通过计划。输出仍是一个文档、六目录、一个run共8个内存成员；只配置最终停站，不运行OpenTrack，不模拟制动，不导出存档。

## 输入与阶段

外层沿用六个SHA-bound donor、单Engine无trailer显式物理模板选择、Windows run配置、有序速度类型。`infrastructure`使用独立domain，stations改为明确AreaStation（reference_end、ordinary_ends、stop entry/exit/area_edge/length/exit_signal_name/direction）。不得根据名称或几何猜区段。每Course有2..100有序、不重复站次，`absolute_seconds`为day0起绝对秒，`stop`为严格布尔，只有最终一行true。最多100个独立Course，不生成Connections或周转。

阶段：全新拓扑→明确主信号→简单Route→`terminal_areas.bind_areas`→Path/Itinerary→车辆→独立final_stop_services用低层Course/TT构造→run和全体重读。未调用pass-only服务后改flags，未放宽旧A-B-A-B-A或六线路circulation校验。

## 停车区段的具体存档表示

普通入口双端保持type1，两半关联与终点reference双端同一StationModel；终点两半type2，仅type2产生站次。实际Edge连接entry.related到exit，长度须精确等于显式声明。entry及exit的四个half-end各有一条关联Edge，无分支；出口有匹配名称/type1-main4的方向信号，entry/reverse无停站信号。终点后轨道必须显式提供，工具不自动补。实际Engine长度向上取整不得超过区段，posInTrain=1不是数量。

每个停站计划须实际经过声明entry→exit；只有最后记录flags3，其余flags2，到发相等、零dwell、实际时间占位且actual day offsets0。支持明确跨日绝对秒和run时间窗。未知dwell/中途stop/反向/重复站次/多Engine/trailer/连接/周转不在本域。

终点静态stop配置**不是**确认列车在指定坐标实际停下，也不证明冲突安全、能力或一日仿真。适用于独立样例；实际三纵三横区段、方向、信号和时刻须用户明确设计。

## 普通验证

`test_dev5_final_stop.py`：9项通过，6.305秒。独立A→S→B→T图，行程A→S→B；A参考点与B参考点仅两站次，S是B普通站区入口，不增加站次。验证8成员、最终stop、跨日、type1/type2共享StationModel；短区段、无后续轨道、方向错、出口信号名错、非final-only拒绝；typed新增dwell字段拒绝、源donor不变。

服务层独立单测、真实MCP/Skill及独审结果另见对应报告，不能由此9项代称通过。部分generate/read覆盖M3.7.2/M7.1.2/M6.2.3/G05/G06；existing-project modify/export和真实停止观察未实现。
