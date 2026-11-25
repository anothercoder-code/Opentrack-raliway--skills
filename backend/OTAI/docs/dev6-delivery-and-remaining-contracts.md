> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# dev6 既有Signal11保存参数

新增精确inspect与update-preview两个接口：读取/修改原始signed-int32 dispatch字段，以及四个有原setter/coder证据的独立布尔位。采用uint32掩码后恢复signed表示，保留全部未选位；新解码及反向全图验证证明仅指定保存字段变化。

只适用完整Document4、已知本地主信号族Signal11、普通互反End/Element和已知indication身份，保持类型/show/release/warning范围并要求performance/coasting数组为空。旧类型编辑guard完全未变：若旧工具因dispatch/辅助位拒绝，不可为了调用它偷偷重置这些配置。

raw dispatch不是已经认证的业务枚举。四bool保存正确也不证明列车保护、站停或调度行为安全。本轮没有原版运行、信号动态内核或导出；Source SHA/index/Signal-End ID/name均须精确。

## 数组只读补证

确认performance/coasting按TrainCategory数组名查索引，不是run速度TrainType顺序。原使用点把performance除以100；coasting整数仅正值启用，实际速度取独立字段。虽然一般NSNumber真实样本可读，仍未找到OTDelayPerformance或非空Signal数组golden，不能确认其class版本/分组，不创建、不增长、不猜写。详见docs/dev6-signal-arrays-evidence.md。

89项受影响回归、独审17项、最终真实双通道2项均有独立日志，测试组有重叠不累计唯一数量；全表176项仍不是全部完成。当前能力表按read/generate/modify/export分别记录，新接口export继续关闭。

## 旧入口可用性纠正

list_catalog/get_engine_diagram当前缺依赖，generate_operations明确隔离；已有源码/旧测试不算当前成功。176四维表逐单元格附不可用入口并保留独立current-only域的真实有界证据；原status/current_evidence标明历史记录。未恢复旧decoder/写入。见docs/dev7-legacy-interface-dependency-audit.md。
