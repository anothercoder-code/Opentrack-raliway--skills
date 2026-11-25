> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev8：统一初始化与交付边界

新增 `opentrack_preview_initialize_project`，将六个资源角色、模板身份、完整单文档输入和两种业务 profile 接成同一入口。核心返回8个真实内存 bytes 成员，包含文档、六目录和run；工具只返回摘要/清单，不写出文件。资源manifest记录格式、SHA、所选身份；派生空图检查明确剔除旧图；继承车型物理有清单，不是重新标定。

核心10项、包装9项、冻结后独立5项及保留dev3–dev6回归67项通过；组间重叠，不累计成唯一用例数。独立组含两个profile各自真实MCP和默认Skill调用、完整回复一致、候选独立解码、引用/米制长度/绝对秒跨日/终停区段关系，以及缺模板、错角色、错误单位类型和未接受物理继承等输入拒绝。拒绝不改变源或项目spec。详见artifacts/rebuild-dev8报告。

read/generate 有限域得到新证据；本轮不增加modify覆盖；export仍未完成。176原功能定义未变，不把新统一入口算功能全覆盖。旧不可用入口状态保持。

## 最小未闭环项

1. 新候选含嵌套OTDocuments/OTData目录，不能直接使用旧flat-only发布器；flatten不能保证DestInfo/run路径正确。适用的独立导出审查与合法普通保存/重读尚缺，不以另写发布器绕过历史gate。
2. 新统一入口仍依赖六类用户授权模板资源。公共源包不含供应商原件；需实际可用的初始化资源才能复现真实候选生成，不能仅运行源码即宣称零模板建模。
3. 同一新工程没有原版读取、运行或结果，当前执行条件阻碍不通过重试/换运行环境绕过。总体blocked-unverified，不宣称一日仿真成功。

后续应先闭合此小场景实际文件和原版同工程验收，再扩大用户三纵三横方案。不是继续添加可选信号字段、递归Overlap或重写内核。
