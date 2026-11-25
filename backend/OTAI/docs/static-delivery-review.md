> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# 静态交付文档与接口审查

本报告区分源码/Skill 交付、内存候选生成、真实工程保存及原版运行。审查范围为当前文档和纯数据接口；未执行发布器或原版程序。

## 已存在且正确的边界

- README、INSTALL-REBUILD、REBUILD_STATUS、SKILL 正文及 `references/project-initialization.md` 已明确：新统一入口仅返回八成员内存候选的摘要，不产生可下载的 OpenTrack 工程。
- `InitializeProject` 只允许 `preview_only=true`，没有保存目标；严格输入拒绝未声明字段。旧 baseline 的保存目标字段不能移植到这个接口。
- “从空图”必须有六类明确 SHA 绑定的格式/车辆/服务模板，不是零模板、零字节建模。车辆物理参数继承要明确接受，不宣称独立标定。
- 单文档通过或有限末站停车范围已写明；不是中间停留、折返、车底周转、任意多站互通或实际一日仿真。
- 原版加载/运行未验证，与具体存档函数的静态输入输出验证分开。原版拥有动态仿真内核。
- 安装说明明确纯源码包不附原版应用及用户原始项目，原始测试模板不是安装发现工具的前提。

## 已修正并复核的交付表述

1. README、包版本和 SKILL 已统一为 `0.31.0-static1`。该标记不代表稳定发布或原版验收通过。
2. SKILL YAML description 已明确：仅显式支持保存的 baseline 工具可保存，新统一初始化保持 preview-only。
3. SKILL 通用步骤 4 已限定支持保存的 baseline 工具，不能套用到新项目预览接口。

## 未解决、不得由文案改成“完成”

- 新八成员链的实际存档导出未启用。其目录布局、运行文件校验、完整成员清单、输入快照与提交错误处理仍需适用的独立导出审查；旧平面发布器不能原样接受。
- 没有同一新工程的原版读取、运行与结果证据。不能把当前源码包、预览 SHA 或静态测试日志说成运行完成。
- 176 项功能仍需逐项范围与操作类别证据；工具数量、单一样例、源码哈希均不是全部复刻证明。

## 已修正并静态复核的纯数据接口

未发现阻断当前有限预览交付的 P1 问题。此结论仅为代码静态复核，不是实际工程、发布器或原版验收。

- 核心 `validate_candidate` 新增精确八成员角色集合、非空 bytes、大小写/文件目录冲突及输出目录冲突检查。保留 OTDocuments/OTData 嵌套结构，没有平面化绕过旧发布器。
- 七份档案与第八份文本 run 分开处理。run 经独立记录解析、请求配置重建比较、档案引用绑定和七档案 manifest 验证；最终交付候选 manifest 另含全部八成员，避免两个层级混用。
- 包装器重新计算实际八成员哈希/长度，对比顶层 manifest、chain 哈希及 next-write manifest；校验角色、数量、六来源哈希/长度、profile、运行路径及依赖回执一致。
- 顶层及 chain 必须明确 saved/native_application_executed/native_runtime_ready 为 false。next-write 保持未启用；返回 envelope 也明确未执行、未就绪。
- 六角色模板校验、同路径不同 preimage 拒绝、最终源文件重读、明确物理继承及 no-write 路径原已存在，本轮保留，不能重复宣称首次实现。
- 包装器合成回执检查不独立证明档案语义；该责任仍由核心及既有构造器承担。SHA 校验是完整性证据，不是资源来源认证、物理校准或原版兼容认证。

冻结文件 SHA256：

| 文件 | SHA256 |
|---|---|
| project_initialization_workflow.py | `a74bd3c44b994af50a57c776b7580635bd6f5e568ce16126c42c3e017ea80217` |
| project_initialization_tools.py | `cb45d1e92fd0d31c746c6d49dd79b5b44c29b3e6100385943489f11a276312c2` |

本次独立审查未运行测试。现有实现测试记录分别报告核心 16 项纯数据检查通过、包装器 6 项纯合成回执检查通过；不合并为“22 项原版验收”，也不将改动前传输日志作为本次重新执行证据。实际生成工程的全量传输重跑、导出及原版加载/运行不在此次静态审查结论内。
