# Signal11 保存参数：raw dispatch 与独立布尔位

新增只读inspect与内存update preview，不修改旧Signal类型配置工具的guard。它们不保存/导出文件，不运行原版、GUI或仿真内核。

## Typed接口

- `opentrack_inspect_signal_saved_parameters`：`source={path,sha256}`、`target={model_index,signal_id,end_id,signal_name}`。
- `opentrack_preview_signal_saved_parameters`：同上，加非空`changes`和`preview_only=true`。
- `raw_dispatch_code`：严格有符号int32。**原版业务枚举未证实，接受存储值不表示该值具有有效运营含义。**
- 四个`StrictBool`：`balise_release_at_balise_position`、`acceleration_forbidden`、`keep_closed_for_station_stop`、`balise_control_all_braking_actions`。
- 不允许未声明字段、显式null、整数充当bool、bool充当dispatch。inspect/update输出旧/新raw_flags、raw_dispatch_code、各bool值、未认证业务语义提醒和源/输出摘要。

## 原01证据与槽

Signal11 coder `0x5d3fd0`：group12为dispatch的`i`；group9 slot2为flags的`i`。

| 字段 | getter | setter | 保存位 |
|---|---|---|---|
| dispatch |0x5cf660|0x5cf64c|group12 int32|
| baliseReleaseAtBalisePosition |0x5cf5d0|0x5cf5c0|0x20|
| accelerationForbidden |0x5cf624|0x5cf614|0x40|
| keepClosedForStationStop |0x5cf640|0x5cf630|0x100|
| baliseControlAllBrakingActions |0x5cf608|0x5cf5f8|0x200|

这些setter只赋原字段；coder把非零bool组合为各位。实现先转换uint32掩码，仅改明确请求位，再转回signed int32。其他位包括未知高位保持原值。不会猜测未知位含义，也不会以保存配置证明信号安全或列车运行效果。

## 身份与有限适用域

精确Document4继承与21组编码、Signal11/End7/Element0/SigInd0布局；SHA+graphicArray下标+Signal ID/End ID/name绑定。Signal、End、related End、SafetyElement均要求唯一模型身份；Signal↔End互指、related reciprocal、element成员和既有指示对象必须一致。未知Signal观察者、foreign indication、重复依赖ID拒绝。

保留main-family、location1/2、show2、release0、已知warning和delay范围、空performance/coasting数组的既有有限配置要求。仅dispatch与选定flags的旧默认值限制在此独立域放开；类型/类别/数组不变。旧`local_core.target`仍拒绝原不支持的dispatch/flags配置，测试明确检查没有暗中放松旧入口。

无关文档其他对象与外部连接元数据保留，但不声称整项目引用已验证。该本地工具不修复原存档、不迁移旧Document3，也不认证全软件参数覆盖。

## 验证

以`artifacts/rebuild-dev6/signal-parameters-tests.txt`及`signal-parameters-verification.json`为准。真实授权BJTU1 donor选择Signal261/End67/graphicArray135；每位双向、组合、int32边界、负flags高位保持、no-op原字节、逆向整档原字节、未知layout/误绑定/alias拒绝、typed输入严格性及wrapper不改源文件。所有输出fresh decode后反向只还原目标两槽，必须恢复整个图fingerprint。

范围映射：M3.6、R17.18、M7.2的保存配置子集。read/modify为本域证实；generate未新增；export关闭。不是整个需求结项，尤其M7.2运行时行为由OpenTrack负责。
