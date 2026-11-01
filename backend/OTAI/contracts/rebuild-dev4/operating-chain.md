# 单文档通过计划：基础设施＋车辆＋服务目录＋run

`opentrack_preview_operating_chain` 以一次请求组合既有纯数据核心，生成内存中的 **8成员**：一个基础设施文档，DestInfo/Depot/Train/Course/Stations/Timetable六目录及一个`.run`。不是新存档格式或第二仿真内核。

## 参数与单位

- `infrastructure`：dev3完整单文档显式拓扑/主信号/Route/Path/Itinerary/点站请求及header、shape的路径SHA。
- 另4个目录donor Source：Depot、Train、Course、Timetable。每个在使用前核SHA，返回前核源字节未变；累计最多256MiB。
- `vehicles`：既有模板名字及新Engine/Category/Train名字，显式接受模板物理属性与冲突定义继承。限单Engine无trailer。三个Train参数单位：maximum_acceleration_mps2 **m/s²**、braking_delay_s **秒**、braking_release_speed_kmh **km/h**。不是物理重标定；Train名字是定义，不代表已追踪车辆。
- `train_types`：明确有序速度类型名，Course `speed_type`须精确映射（按既有大小写规则）。Edge字典key是该顺序下标字符串，所有Edge包括未选分支均需存在使用的索引和正双向速度。
- `plan`：Course ID、Train、Itinerary和完整有序visits；`absolute_seconds`为从day0 00:00:00起的非负绝对秒。必须严格递增，且不低于方向Edge限速／Engine最高速度推导的理想最小时间；此下界不计加速、闭塞、冲突或调度等待，不证明可行排图。
- 行程首尾必须已有显式pointstation，至少两个站点出现；计划站序须与实际Itinerary一致。不会自动补站或修改时刻。
- `run_configuration`仅**Windows**规范根；`document_path`必须恰为根＋`/OTDocuments/<name>.opentrack`。明确开始/结束day+HH:MM:SS、step、输出名及run文件名。`step`是现有run数字字符串，按原校验解析；不创建输出目录。

## 严格通过域

生成Timetable arrival=departure、dwell=0、stop_at_station=False。Category stopAtEveryStation会被旧核心拒绝。未知stop字段、停站计划、多Engine、trailer、自动寻路、跨文档及循环域未开放；不偷换用户基线或把旧guard删除。只需明确生成计划，不会宣称周转、能力、冲突安全或真实一日仿真。

## 复用与新检查

调用dev3 `compose_infrastructure`、`generate_vehicle_catalogs`、`replace_train_types(b'',...)`、`generate_service_catalogs`、`build_run`。新编排固定规范成员，验证恰为七个数据输入＋一个run；`verify_archive_bindings`与`verify_manifest`验证跨文件类型/路径/时窗，最终另作Project/DestInfo完整重读与每条Course、TT key/order/station/clock/day/passflag/dwell检查。继承物理模板和所有元数据并非重新验证物理参数。

Core返回成员bytes供内存消费者；MCP/Skill wrapper仅返回hash、size、阶段收据，始终`saved=false`且不启用发布器。

## 本轮普通测试与覆盖

12项通过（6.745秒）：正常8成员；跨日分支（验证day offsets）；首尾缺点站、未知Train、站序错、缺速度type、过快、run窗外、根不一致、未选分支缺速度索引拒绝；wrapper源保持，stop/posix/save参数拒绝。全部使用恢复的授权目录donor，仅静态字节处理，未执行原版。

部分generate/read证据：M2.1.1、M2.1.3、M5.1.1、M5.2、M6.1.2、M6.2.3、G02、G05、G06、A06。不标原需求整体完成；existing-project modify和export仍未提供。实际传输验证由独立测试另记录，不将单元测试称为传输通过。

独立审查发现并已修复：最终run文件名与OutputPath目录可能同名，新编排和typed配置均按casefold拒绝重叠（相等及祖先后代）；新增普通配置冲突测试覆盖大小写。不改变旧发布器或其审查状态。
