> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# 从空图到原版仿真的端到端边界

本轮优先是完成一套工程的技能流程，而不是扩充零散字段或重写仿真内核。当前可从空的铁路图对象集合生成有限单文档场景，仍需要明确的原生结构模板与车型/服务目录模板；“从空图建模”不等于“从零字节发明原生格式或车型物理参数”。

## 整套输入

1. 初始化资源：header、shapes、Depot、Trains、Courses、Timetable 六类明确来源及完整 SHA256；提供者有权使用这些资源。公共源码包不附供应商原项目或原件。
2. 显式模型：文档名称和最终 Windows 执行路径、节点/边/方向/长度/限速、站点、主信号、Routes、Paths、Itineraries。不得把几何交叉自行解释为铁路互通。
3. 车辆：明确 Engine/Train 模板身份与新名称、允许的物理参数。车型物理曲线等继承模板，不声称从零校准；新通用链暂为单 Engine、无拖车。
4. 运营：Course/TT 模板身份、生成车次与列车引用、Itinerary、站序、绝对秒时间及日期偏移。最小通过场景和明确终停场景是两个独立 profile，不能自动把通过改成停车。
5. 运行文件：六目录、文档、TrainTypes 速度索引、起止日/时刻、步长与输出目录的显式配置。24 小时窗口只是计划，不是已运行一天。

## 完成判据与当前证据分层

| 环节 | 当前能力 | 完成判据与未满足项 |
|---|---|---|
| 资源初始化 | 六来源 SHA 绑定、已知格式和模板身份校验；复用已有生成核心 | 不复制原 donor 站场，不杜撰缺失资源。完全无模板启动不成立 |
| 基础设施 | 单文档显式拓扑→站/主信号→Route→Path→Itinerary/DestInfo | 有独立解码与引用一致性；有限域，不是任意铁路规则全部实现 |
| 车辆/运营 | 单 Engine 车型模板→Train→Course/TT；通过或特定终停 | 终停须真实区段/长度/方向/信号适合，而非只改 stopflag |
| 工程引用 | 1 文档+6目录+run 共8成员候选；运行路径/速度/站序/时间静态闭合 | 静态必要检查不等于冲突调度、牵引动力学或容量保证 |
| 实际写出 | 新通用链尚未写出。旧 v11 固定样例有正常新目录保存/重读证据 | 新链的嵌套成员与旧平面发布器不兼容；不能以哈希预览代替交付文件 |
| 原版读取与运行 | 未做、未通过 | 必须同一实际工程由原版读取并获得实际运行输出；当前平台执行阻碍不通过重试/换路径绕过 |
| 结果绑定 | 有只读结果解析工具，不存在这套新工程的原版结果 | 需绑定实际工程清单、run及实际输出，不能把静态计划统计当运行结果 |

## 最小闭环先行

先以明确的小型单文档通过/终停场景验证同一套输入、候选、最终文件、原版读取和结果。三纵三横、多文档任意续段、互通、递归 Overlap、复杂调车、多车辆周转不是这个最小验收的前置要求。三纵三横实际用户目标仍需单独扩大场景并验收；已有25文档固定教学网格不能冒充任意9站互通实现。

新导出必须先确认适用的独立审查范围，保持引用路径一致和完整集合校验，不能把平面化或替换发布器当历史未完成 gate 的绕过。总体状态保持 blocked-unverified，直到实际文件交付及同工程原版验收都有证据。普通源代码、Skill、报告备份不是 OpenTrack 操作存档交付。
