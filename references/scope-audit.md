# 范围审计

## 当前 AI 工具箱边界

OpenTrack 是铁路仿真求解器。本 Skill 负责发现、选择、组合和验证工具，并把
候选文件与原生运行证据分层记录。实时 profile 快照是 `ai` 21、`generation`
219、`all` 249 个工具。语义能力目录当前有 11 项，受控发布白名单有 15 个
粗粒度 reviewed writer。`ai` 只公开紧凑入口并隐藏低层 writer，发布桥每次只
执行一个计划动作和一个 writer。机器可读状态见
[AI toolbox status](coverage/ai-toolbox-status.json)。

## 任务族状态

`supported` 表示一个入口可以完成限定任务。`composed` 表示注册工具按依赖
顺序可以完成。`partial` 表示仅有明确子集。`unreachable` 表示当前没有安全
工具路径。`requires_native_app` 表示剩余证据必须由原版软件产生，未观察的项
保持 `not_run`。工具数量不是功能完成率。具体路径与限制见
[advanced original-function gaps](advanced-original-function-gaps.md)。

## 历史快照和非当前证据

`coverage/requirements.json` 和 `coverage/完整复刻验收表.md` 保留 176 项历史
来源清单、限定函数证据和不同阶段测试记录。它们用于查找遗漏，不作为当前
发行完成分母。`scope-audit-summary.json` 是 2026-10-31 的历史范围检查，
其中的 profile 数和 basic/full 分布不能当作当前注册清单。

## 封存与不可达能力

八个旧几何、editor、draft 和 demo 入口继续由
`LEGACY_GEOMETRY_DISABLED` 封存。任意复合道岔、交分、菱形交叉、梯形咽喉、
通用站台能力模型、完整信号族、死锁证明和一般车底周转尚未由通用工具链
覆盖。未知身份、断开站台和非连续边返回结构化限制，不能根据图形邻近推断
连接。

## 最终原生验收边界

打开原版 OpenTrack、加载候选、GUI Save、真实卸载重载、Inspector、信号与
灯色、零速停车、计划发车、下游到达和当前工程实际开行统一留在最终原生验收。
历史 Reading P9 只证明其记录版本、输入和案例，不提升当前工程或当前轮状态。
本轮没有打开原版软件，也没有把规划、预览、存档生成或历史结果升级为原生
验收。
