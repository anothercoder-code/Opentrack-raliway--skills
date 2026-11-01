# 统一项目初始化：同一输入连接完整存档生成流程

使用 `opentrack_preview_initialize_project` 预览，使用 `opentrack_initialize_project` 预览或保存。MCP 和 Skill 调用同一配套后端。

本页用于用户要求的**新建工程**。对已有工程的延长、紧凑布局、补信号或站场修正，
默认修改当前 execution_root 内的原文件；先按[现有站图与工程布局](station-document-layout.md)
处理，不要为每次修改新建一个正式工程目录。本初始化发布器仍只接受全新目标，
不能将其视为覆盖接口；使用它准备候选时，候选工作区不等于另交付一个工程。

本用户优先采用[一站一文档](station-document-layout.md)。本页两种 profile 都是
单文档范围，适用于明确接受该范围的技术验收或适配项目；“单文档”不等于已支持
完整的单站运营 profile，终停 profile 仍要求至少两个车站和两次访问。多站工程先按该布局规划，
再检查多文档能力，不能为使用本发布器而默认把多个站塞进同一文档。

多站线性终停工程使用当前 `0.33.1-zeroaccept1` 保留的
[`opentrack_initialize_station_documents_project`](station-documents-project.md)，
可在 Windows 安全发布 N+7 成员。本页单文档工具和 profile 保持独立，不扩展成多文档。

预览工具只返回内存候选，`saved=false`，不创建目录。`0.31.0-winrelease1` 新增独立工程发布接口：Windows x64 本地 NTFS 上可以保存完整八成员工程和空输出目录。仅在发布回执的 `commit_completed`、实际重读和引用校验成功后报告已交付；两种工具均不运行 OpenTrack，不走旧 Project/draft 发布管道。

## 用户需要提供什么

### 1. 本模板式初始化入口的六个资源

以下六项是本页 `preview_initialize_project` / `initialize_project` 的合同，
不是每种空白工程或设计都必须外部提供的资源。基于打包审计形状的空白建图另见
[geometry editing](geometry-editing.md)，按实际需求选择；不要改写本入口的真实校验。

`sources`精确包含：`header`、`shapes`、`depot_template`、`trains_template`、`courses_template`、`timetable_template`。每项为 `{path,sha256}`，路径位于授权数据目录内，SHA须对应实际字节。模板用于已知存档格式、类型和明确选中的车辆/服务记录，不把已有铁路图当新模型直接复制。

“从零建模”是从空拓扑重新建立用户声明的对象，**不等于不需要任何格式/物理参数模板**。车辆物理值继承需用户明确接受，不宣称已经标定。

### 2. 明确选择一种有限业务范围

- `single_document_pass`：单文档点站通过模型，arrival=departure、无停站停留。
- `single_document_final_stop`：单文档明确站区，向前方向末站停车、零停留；不是中间停站、折返、车底周转或任意调车。

两者都要求显式拓扑、信号、进路、路线和行程，不能自动把图形交叉点当作互通，也不自动设计缺失站场。

先把用户要求的站型、股道、正线、两端咽喉、站台、站外段及信号放入完整方案，
再选择能表达该方案的生成入口。此处的有限 profile 不会自动补全任意真实站场；
不能先交付几条平行线并把它当作已经满足站场要求，也不能为适配工具而悄悄减少正线。

新建图形的 placement 必须显式给出 `x,y,angle,alignment_x,alignment_y`；Signal
定义也采用 `alignment_x/alignment_y`。通用生成组合为 `0/0`、`1/0`、`2/0`、
`0/3`、`0/4`，是已审原生子集，不是完整枚举声明。新 Station 保留 `0/0`；新 Signal
必须取实际 owner End 的方向，水平为 `1/0` 或 `2/0`，垂直为 `0/4` 或 `0/3`。
Signal schema 拒绝 `0/0`，共同工厂还校验输入与该 End 完全一致，不猜测或自动替换。
旧档检查、配置和原生克隆保留其源字段，不把这条新生成规则当作自动归一化操作。
旧 `width/height` placement 字段会明确拒绝；请核对实际 End 后重新预览，不能只把
像素尺寸改名为枚举。方向字节校验不等于原版显示、三显示或运行安全验收。
真实页面/画布尺寸不受影响。详见[对齐契约](graphic-alignment.md)。

### 3. `project` 的八组输入

| 输入 | 要给出的信息 |
|---|---|
| `infrastructure` | document_name/path，network顶点/边/速度，stations，signals，routes，paths，itineraries；不在此处重复header/shapes。边端点使用`from_end/to_end={vertex,side}`。|
| `vehicles` | 精确engine/train/category模板名，新名称，train_names，明确继承参数许可与已有typed列车物理参数。|
| `course_template_id` | 既有Course记录的精确模板ID。|
| `timetable_template_key` | 既有时刻表模板键，通常CourseID#index；不猜测。|
| `train_types` | 有序速度类型映射。|
| `speed_type` | 本次服务使用的明确速度类型。|
| `plan` | 每条Course的train、itinerary与按站顺序的absolute_seconds；末站停车profile还需每次visit的stop布尔值。|
| `run_configuration` | execution_root、windows路径方式、run_filename、output_directory、起止日/时刻、step。|

预览工具最外层为 `{sources, profile, project, preview_only:true}`。新发布工具增加 `target_directory`（数据根内的相对路径）和布尔 `preview_only`；保存必须显式设为 `false` 并指定全新目标。`run_configuration.execution_root` 必须等于实际绝对目标，`infrastructure.document_path` 必须指向目标内同名文档。字段、profile/站型、模板身份或 SHA 不匹配均拒绝。

## 数据流程与输出解释

格式资源检查 → 空图初始化 → 显式基础设施/信号/进路 → Station/Path/Itinerary引用 → Engine/Train/Course/Timetable → 六目录和.run绑定 → 候选存档独立重读与静态检查。

正常返回8个候选成员摘要：1基础设施文档、6数据目录文件、1.run，另有完整receipt（模板身份/资源角色/初始化和静态验证信息，具体以返回字段为准）。

- `outputs` 的 SHA 和 bytes 先证明内存候选；新发布工具另有 `publication` 及 `persisted_content_validation` 证明磁盘保存与重读，不证明原版运行。
- 预览工具 `receipt.saved=false`。新发布工具保留 `candidate_receipt.saved=false` 描述生成阶段，顶层及独立发布回执 `saved=true` 描述完成的落盘阶段。
- 遇到不支持的中间停车/反向停车/循环或缺模板，给出具体输入/范围差距，不换成任意旧接口绕过。
- 保存失败且 `commit_completed=true` 表示目标已提交，但后验失败；保留目标并核对实际字节，不覆盖重试或声称已回滚。提交前失败只清理本事务持有的临时对象。
- 动态信号、列车运动和运行闭环属于原版 OpenTrack，使用已保存的同一工程另行实际验收。

历史 staticfix1 未启动或操控 OpenTrack。历史 winmulti1 联程事件仍属历史运行
事实，但后续车站双击触发 Inspector 崩溃，不能据此认定当前 GUI 编辑安全。
[独立 Inspector guard](inspector-safety.md) 的安装、编译和严格 PE 检查不证明
原版已加载；`runtime_verified=false`。未来显式启动仅支持自身新 child 与自身
线程的 `WH_GETMESSAGE`，不能附加旧进程。

请求符合该有限范围时，可参考[英文三站单车验收案例](zero-start-three-station.md)；
其他新工程先按[需求组织设计](complex-design-workflow.md)，不默认缩减成三站单车。ZF新例的
原版运行与GUI保存事实属于该具体项目，不是本页两个单文档profile或全部工具的
GUI通验。该三站新目录Inspector更新、Save/reload及刷新后的GUI3已独立分项通过；
该ZF实测流程在导入后曾需要Open→Cancel、Ctrl+5刷新；其他项目先核对真实列表，
发现相应陈旧状态才按原版界面刷新，不把该动作序列当作所有导入后的固定仪式。未刷新
GUI2的Origin warning失败保留，不通过修改Train数据掩盖。
