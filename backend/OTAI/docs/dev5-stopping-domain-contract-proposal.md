> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev5 停站域：只读契约定位与最小下一步

## 结论

可以自主实现一个**独立、显式、单文档、单程、仅终点停站的存档预览域**，不改dev4通过计划默认行为，不自动改变三纵三横。已有`terminal_areas.bind_areas/read_document`证明停车范围不是一个新“停车区对象”：它是明确方向的普通End站区成员＋type2站参考点＋实际轨道Edge＋同一StationModel及出口信号的组合。不能只改TT stop位。

但现有公开terminal_area整体不能直接套用通用链：其服务核心硬性要求5次A-B-A-B-A出现且仅index4停，连接核心还硬性绑定H1..V3、TRAIN_01..06、S*_IN、420秒及同日。**不放宽这些旧guard**；另建有限服务适配层，复用已验证低层Course/TT构造及area reader，仍使用原存档格式。

## 原生字段与实际区段要求

- 站对象：Station目录sign/name与StationModel一致；raw profile 2/4/1。
- Reference End：成对双顶点两半都关联同一StationModel，`stationEndType=2`，作为一次真实站点出现。
- 普通站区入口 End：两半也关联该StationModel，但`stationEndType=1`，不增加时刻表站次。原01 `OTEndModel.isStationEndModel` 0x4c1898 明确type1返回false，其余返回true；本实现只承认已验证type2，不扩大到其他值。
- 显式`entry_end_id`、`exit_end_id`、`area_edge_id`、`length_m`、`exit_signal_name`、`direction=forward_only`。Edge必须实际连接entry的related半端与exit，方向与所选Route一致；声明长度须等于实际Edge长度。
- 已有area reader要求entry、related(entry)、exit、related(exit)四半端**每个恰有一条关联Edge**，即此停车范围内部无分支。不能用只有终点一半无后续轨道的point样例直接冒充符合条件；要显式提供参考点之后的轨道，否则拒绝，不自动加假轨道。
- exit上必须实际存在type1/main4、名称匹配的方向性ExitSignal；entry、其related、exit的reverse half不可带另一停站信号。反向半端绑定相同station并不授权反向停车。
- 单Engine、无trailer、posInTrain=1的现有域：从实际Engine存档读取车长，`ceil(length)<=area.length_m`；不把posInTrain当数量，不靠请求自报车长覆盖原档。

## Timetable与行程必须一起验证

- 时刻表字典key `course_id#index`、Course/Train/Itinerary精确引用、完整站出现顺序、index/maxIndex、Station sign。
- planned arrival/departure、各自day offset；实际arrival/departure仍HH:MM:SS占位，实际day offsets清零。
- stop/timing flags：通过2，明确停站3；最终记录从`course_factories.new_timetable`正常构造，不能写后凭flags宣称实现。
- 最小新域：origin不停止且arrival=departure，所有中间站通过，**只有最后一站stop=true，arrival=departure、dwell=0**。这是终点停站静态配置，不是出站后继续运营或中间停留。逐段计划不低于限速/最高速度必要下界，但不证明实际可运行。
- 最终行程上一节点必须是所声明普通entry，最后节点必须是exit；StationModel同一对象、对应Edge确实被行程使用。仅同站名不足以确认停站位置。

## 可复用模块与不能直接复用的原因

- topology/main-signal/Route生成核心：全新未绑定station文档先建信号及简单Route；之后`terminal_areas.bind_areas`（它拒绝已有station），然后已有Path/Itinerary生成。**不能直接给dev3已绑定pointstation的输出再bind_areas**。
- `terminal_areas.read_document`与`zero_terminal.area_operations.station_sequence`：可作实际area/方向/站次/速度trace校验，不要求更改现有原生布局。
- `vehicle_catalogs.generate_vehicle_catalogs`、`course_factories.new_course/new_timetable`、`run_bundle.build_run/verify_archive_bindings/verify_manifest`：复用生成/完整八成员绑定。新增有限服务编排须补全输入模板检查、area长度、独立回读；不能简单调用dev4 pass-only服务函数再改stop位。
- `zero_terminal.area_operations.generate_service_catalogs`：固定A-B-A-B-A五次出现和终点同End要求，不能直接用来生成A→B新域。
- `zero_terminal.circulation.bind_turnrounds`：固定六线路和五站次、完整chain partition；暂不接入，不把同终点停车等同于周转。
- `multistation_timetable.api.generate_from_spec`：已有arrival_s/departure_s/stop与实际type1→type2区段、车长检查，但它自行重造2..12站多文档chain+500m区段，并带保守顺序/折返规则；不是通用单文档byte适配器。可参考其低层TT构造和校验，不能以修改传入network来替换用户模型。

## 最小独立样例与验收

自主测试可使用明确标注的合成图：A参考点→S普通站区入口→B终点参考点→T轨道延续，行程只选A→S→B；S两半type1与B两半type2绑定B站，S→B实际Edge长度足够，A与B有正确方向主信号，B之后轨道只是显式拓扑、不是自动续发。两个站次，最终B停。此例不改变用户已有三纵三横。

1. 正例新解码：入口不产生第三站次，A/B两行TT，B flags3且实际时间空；引用、长度、方向、出口信号及六目录/run完整；输入不变，saved=false。
2. 普通拒绝：短于实际车长、错方向/错Edge、缺出口信号、area中分支、reference无后续轨道、只把stop=true而无area、区域与pointstation重叠，全部不生成可交付文件。
3. 跨日显式终点到达和run窗核对；中途stop或dwell、反向停车、多Engine/trailer、重复站次、turnround/连接请求明确拒绝。动态停车未实测，不能由此计“完成一日仿真”。

## 真正需要用户设计的信息

开发上述有限接口与独立样例无需再询问。把它应用到**用户实际三纵三横**之前，需要用户给出或确认具体停车的Station/方向、entry/exit与区段长度、对应出口信号、哪些车次终停及到达时刻；若原拓扑缺所需续接轨道，需要明确设计决定，不能自动插入。用户若要求中途停留后续发或折返，还须另选适用域，不能猜测终点停站代表这些行为。

本文件仅只读研究；没有实现新域、执行原版、修改基线或开启导出。
