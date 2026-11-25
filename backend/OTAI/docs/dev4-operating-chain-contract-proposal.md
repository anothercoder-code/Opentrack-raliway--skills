> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev4 候选：单文档基础设施→完整运营目录与run的一次预览

**只读研究，未实现。优先级建议高于通用跨文档Route续段**：可直接推进用户列车／引擎／Course／时刻表目标，而且现有核心已具备单文档数据契约，不必先研究新续段分配。

## 最小可独立实现域

一次纯内存请求：调用dev3 `compose_infrastructure`，再生成Depot、Train、Course、Timetable，并合并既有Stations、DestInfo，共六目录；最后生成`.run`，总共一个基础设施文件＋六目录＋一个run（8成员）。只做单文档、单引擎无拖车的类型定义、点站**通过计划**，非停车运营。显式方案优先，不自动排图或折返；所有成员留在内存，wrapper仍`saved=false`。

这里“完整六目录”只是静态文件集合闭合，不证明物理列车流转、能力、冲突解决、停车或原版运行成功。

## 可复用函数与必需显式参数

1. `infrastructure_chain_workflow.compose_infrastructure(header,shapes,expected_hashes,spec)`：沿用dev3完整参数，明确基础设施内的document_path必须等于`execution_root + / + OTDocuments/<name>.opentrack`，防止DestInfo与run分属两个原生根。
2. `zero_operations.vehicle_catalogs.generate_vehicle_catalogs(depot_blob,trains_blob,spec)`：额外SHA绑定两个目录donor；明确engine_template/train_template/category_template、engine_name/category_name、新train_names、`use_template_physics=True`、`inherit_conflict_definitions=True`及maximum_acceleration/braking_delay/braking_release_speed三个参数。现有模板必须恰为单Engine、无trailer，且模板Train绑定选中的Engine/Category。物理参数继承不是重新标定，不把多个类型名说成独立追踪车辆。
3. `zero_operations.speed_preferences.replace_train_types(b'', ordered_names)`：可根据明确有序TrainType名字生成仅供内存解析的偏好记录，无需读取含陈旧路径的run donor。`read_train_types/index_for_course`负责校验；Course指定speed_type必须在此列表里，沿途Edge速度字典使用其下标字符串且具有正向/反向值。顺序不能靠集合推断。
4. `zero_operations.operations.generate_service_catalogs(inputs,course_template_id,timetable_template_key,document_name,plan,speed_type)`：额外SHA绑定Course/Timetable两个donor，明确模板记录ID/key；其余六个输入是生成后的Train、Depot、Stations、Document、DestInfo及上步偏好bytes。显式plan为course_id、train、itinerary、按行程顺序的`{station_sign,absolute_seconds}`列表。
5. `zero_operations.run_bundle.build_run`：完整六角色catalog_paths、document_paths、execution_root/path_style、同一有序train_types、start/stop day+time、step、output_directory、run_filename。建议本轮固定规范成员位置，只让用户显式选择根、时间窗和安全输出名，避免另造任意路径布局域。随后`verify_archive_bindings`、`verify_manifest`及现有Project/预检对最终所有成员新解码。

## 不能直接无条件复用的地方

- dev3测试样例仅有中间B一个pointstation；服务生成的`station_sequence`明确要求**行程首尾均绑定station且至少两个站点出现**。新运营请求必须明确提供A/B/C或至少A/C点站，不能悄悄添加/移动站点来通过。
- 现有`generate_service_catalogs`是pass-only：到发时刻相等、dwell=0、stop_at_station=False；不接受arrival/departure/stop扩展字段。Category的stopAtEveryStation位会被拒绝。要停车需独立停车范围契约，不应泛化此函数或靠flags硬改。
- 每个计划站序必须与实际Itinerary station_sequence完全匹配；绝对时刻严格递增且不低于Edge限速／车辆最高速度计算的最小行驶时间（只是下界，不是实测运行时间）。不做排图可行性保证。
- 现有`multistation_timetable.api.generate_from_spec`不能直接接dev3bytes：它一开始就调用固定2..12站多文档chain生成器，并含专属500m停站区、turnround/连接逻辑。不能把它视为通用运营适配器。
- 现有`OperatingGeneration.compose_operating`也先重建旧NetworkGeneration拓扑，携带额外Path/Itinerary模板和发布参数；复用其中的纯函数编排而非直接调用整个公开wrapper。新入口不要接入其保存路径。
- `run_bundle.verify_archive_bindings`会要求实际使用的速度索引在所有Edge都存在，不仅选定行程上的边；分支图也须完整填写，不应过滤未选分支来绕过。
- 下游run基本profile不接受辅助diagram/document-set或Incident选择；初期不继承这些配置。生成run不要求创建输出目录，保持预览无写入。

## 三组最小验收

1. **A/B/C点站链正例**：一Engine+两Train定义、两Course、显式6条通过时刻表（仅示例数量），最终8成员。新解码核Engine↔Train↔Category、Course→Train/Itinerary、TT字典key/course/order/station/time、DestInfo→Document、run六角色及文档路径；MCP/默认Skill相同，全部donor不变。
2. **域不满足拒绝**：dev3仅B站的样例、未知列车/行程、站序错、速度type缺失、时间早于下界、run窗外、document_path根不一致、停止/停站额外字段；不产生可交付文件、不隐式补站或更改时间。
3. **分支及跨日**：明确选择其中一条分支的行程，未选分支Edge速度仍完整；计划跨午夜时验证day offsets和时刻，而非只比HH:MM:SS。区分24小时窗口与完成一日真实仿真，不证明周转或冲突安全。

这是下一可实施接口差距：新增纯内存编排入口＋请求schema＋全成员回读/传输回归。无需新存档格式；无需改三纵三横基线、原版内核或开启导出。
