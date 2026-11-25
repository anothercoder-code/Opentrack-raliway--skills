> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev4 单文档运营数据闭环

新增 `opentrack_preview_operating_chain`，复用dev3基础设施、既有车辆/服务/run核心，一次内存事务生成8成员：1个基础设施文档、Depot/Train/Station/DestInfo/Course/Timetable六目录和run。

## 已闭合的静态信息

- 明确模板与SHA的Engine/Train/Category关系，生成命名列车类型。
- Course引用准确Train与Itinerary；时刻表字典key、顺序、站点、时分秒及日偏移匹配显式计划。
- 有序TrainType名称对应速度索引，未选分支的边亦不能缺必要速度数据。
- DestInfo权威文档路径与run执行根完全一致，六目录角色及文档均绑定。
- 所有计划时刻在run窗内，通过既有最小行驶时间下界检查；跨午夜保留真实day offset，不只看时钟字符串。

只支持单Engine无拖车的模板继承、点站通过计划；到发相等、零停站时间。不自行补首尾点站、修复计划、不支持停车/折返/物理车底周转。三可设物理参数单位明确为m/s²、秒、km/h；其他模板物理信息继承并非重新标定。

当前只接受Windows原生执行根。生成的run所指目录不是本服务器或用户电脑上的已创建目录。输出目录与run文件名的大小写无关冲突，已由独立审查发现并在新编排层修复；没有修改旧发布器或放宽既有guard。

## 交付与验证边界

八成员只有内存候选及摘要，`saved=false`，无文件/输出目录被创建。24小时配置不等于执行一日仿真；时间下界忽略加速与冲突，不证明运行可行、容量或调度安全。预印模拟结果不存在，不产生任何虚构运行指标。

本轮验证日志与逐字段读取证据见artifacts/rebuild-dev4，初次独审问题及修复前测试保留。实际调用已区分成功数据请求与明确拒绝的坏配置，不将新工具注册数或单样例转为176项完成率。

剩余范围包括通用停车区/停车计划与车底接续、跨文档主段/续段参数化、其他原生参数/引用域，以及未启用的新导出。既有专门停站/多文档生成工具的有限能力不等于本通用编排支持这些范围。原版仍负责动态运行，不开发另一内核。
