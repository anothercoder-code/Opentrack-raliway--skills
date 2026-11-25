> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev2 数据能力交付

本轮不是仿真内核，也不是GUI重做。以原存档输入输出与引用闭包为目标；运行动态由OpenTrack负责。

## 三项实际新增能力

1. **声明式有限多文档拓扑**：用户显式给文档、双顶点、边、点站及成对连接器，不再只能用固定A/B或25文档样例。边界为工具域：1–16文档、总400双顶点/800边；几何相交不自动互通。返回预览，不生成进路/运营列车，不更改原三纵三横设计。
2. **既有调车参数修改**：支持已知Document3/4及SecurityArray5/6的速度、释放时间、预留时间三参数。原04五条记录已修改、重读、恢复验证；原IDs、ArrayInfo、几何不变。三条旧indication指向其他对象，原样保留并明确不认证，绝不擅自“修复”。
3. **列车改名与反向引用同步**：完整选定单run项目内，修改唯一Train16名称及所有匹配Course11引用。前后静态预检、独立重读、共享关系及源不变检查。未知同名文本、字典键、别名、额外未绑定文件保守拒绝；这不是所有对象的通用重命名。

每项都已核对相应原01函数及原存档契约，报告只保存证据名称/SHA，不打包供应商函数源码。生成/修改候选保留于内存并重读，工具仍返回saved=false，不冒称文件交付。

## 176项四维表

`replica/dev2-operation-coverage.md`和`replica/requirements.json`按读取/生成/修改/导出分别维护。源码候选映射为部分证据；未复核不等于不支持。实际有界操作的测试另外记录，不提升为整个原功能完成。查询支持`section=requirements, operation=read|generate|modify|export`；不会用旧整体status代替该操作状态。

## 仍然缺少

- 新预览工具导出尚未启用：需要对具体发布实现的成员映射、源不变、路径约束、已有目标处理、部分失败与正常保存重读做独立审查。历史中断不算通过，不替换实现绕过。
- 通用拓扑之后的通用进路/Path/列车与时刻表一体化装配，尚未自动覆盖任意声明图；已有专门运营生成域不等于该通用接口自带完整运营。
- 原档完整Shunting编辑（重名/变更路径/引用传播），跨文档单个Shunting、递归Overlap没有被此参数接口“顺便实现”。后两者不能假设原版支持。
- 其他目录名称的全项目反向引用更新与所有参数域仍需逐项证据；本轮只闭合Train→Course。
- Diagram、Document Set、Incident支持的是存档静态语义，非绘图/自动激活/事件实际触发证明。
- 原版加载及一日场景未执行；不因此开发第二个动态内核。

## 验证说明

以`artifacts/rebuild-dev2`最终日志为准，区分原档、合成、真实传输、保留回归。首次恢复缺少两组既有生成fixture导致测试setUp错误，已保留日志并从核SHA的v11包恢复输入后重跑；不把初次错误掩盖为通过。
