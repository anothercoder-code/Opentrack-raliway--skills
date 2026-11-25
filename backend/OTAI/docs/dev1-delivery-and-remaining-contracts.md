> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev1 数据接口交付边界

本轮只补数据建模、引用、预检和查询接口，不新增仿真内核。运行、动态闭环和信号变化由 OpenTrack 负责。

## 能力增量

1. 覆盖信息直接读取随包元数据，并校验当前源码/三份报告的SHA；无需旧 typedstream 解析依赖。89条历史保存函数记录与176条需求都保留原含义，不根据工具数量换算完成率。
2. `.run` 的 Incident 被解释为 CourseList 内的事件名称。预检、项目检查、迁移和相关事件工具一致，不尝试读取同名文件。
3. 已知 Diagram13 的自路径与 Station 引用、Document Set 的有序分组有静态检查。仅验证被明确选中的文件集合，不证明界面绘图、脚本自动激活分组或事件实际触发。
4. 新增独立有限 Itinerary 域，允许显式重复引用简单 Path。顺序与边界连续性、文档/name/ID仍精确验证；不改变普通 Route/Path 的原无环约束。
5. 原04已知 Shunting 布局可只读枚举；旧变体显示不可编辑。当前新建域可显式选择同文档非终点 Overlap，保守拒绝重入，不推断运营防护合理性。

## 未完成项及下一步所需证据

| 项目 | 具体缺口／下一步 |
| --- | --- |
| 新增预览工具的文件交付 | 候选内容已在内存生成并做数据重读，但wrapper未导出文件。需要对适用导出实现独立审查：成员到目标文件的映射、源文件不变、路径约束、已存在目标处理、部分失败处理与正常新目录保存重读。历史被中断流程不能算通过，也不替换发布器规避。 |
| 任意多文档互通网络生成 | 当前固定25文档示例并非通用互通生成器。有限重复行程不新增道岔/互通布局；需要明确用户拓扑设计及文档边界，不能擅改三纵三横基线。 |
| 跨文档单个Shunting | 已发现原生浏览器在文档边界停止，Route专属续段编码并不见于Shunting。尚缺Shunting原生创建→保存→重建的跨文档续段及ArrayInfo语义；不把父类字段存在当作支持。 |
| 递归Overlap | 已检查getOverlap和Dest消费仅展开一层，没有递归效果证据。不能因为父类可保存名称字段就实现或宣传递归防护。 |
| 原版旧Shunting修改 | 原档的body ID/start ID形态与新建域不同；可读不等于可安全改写。需要原生新建/复制/自动Path重建的ID更新契约。 |
| 任意重命名/更新 | 尚未覆盖全项目所有反向引用传播；精确生成/局部有界修改不等于通用rename/update。 |
| 原版载入和一日场景验收 | 尚未实际运行OpenTrack；数据测试不替代原版加载。该验证不要求开发第二个仿真内核。 |

这些限制不影响已验证的旧v11正常新目录导出流程；新预览接口仍明确返回未保存。功能表维护在replica，不将哈希相符、纯工具发现或单一样例通过标成原软件全部功能完成。
