# OpenTrack 原生供电区与测量仪

`opentrack_inspect_power_and_measurement` 读取明确绑定 SHA-256 的
`.opentrack` 工作表。返回供电区 ID、供电制式、显示设置、关联 Edge ID，以及测量仪 ID、
方向 End、显示选项、可见性和显示框。原版 Demo 的 v3 工作表可读取。

`opentrack_edit_power_and_measurement` 作用于 v4 工作表，可预览并保存新的原生
`.opentrack` 文件。创建时传入本机原版 `OTProjects/Demo/OTDocuments/topoOst.opentrack`
作为 `stock_donor`，其 SHA-256 为
`55f03e67a8b9c028bae2662b0a69f595de80e62b98f96e7fb97aab4de93b408a`。
输入工作表和模板保持原样。工具回读查验 Edge 和供电区的同一对象引用，
以及方向 End 和测量仪的双向指向。

使用 `scripts/ot.py --profile all call opentrack_edit_power_and_measurement`，
传入以下结构的 JSON。目标路径必须是授权项目目录下的新文件。

```json
{
  "source": {"path": "OTAI/workspaces/Line/OTDocuments/RDG.opentrack", "sha256": "<worksheet sha256>"},
  "stock_donor": {"path": "OTProjects/Demo/OTDocuments/topoOst.opentrack", "sha256": "<stock sha256>"},
  "operations": [
    {"action": "create_supply", "name": "RDG District 25kV", "power_system_code": 4,
     "position": [190, 62], "edge_ids": [20, 21, 22, 23]},
    {"action": "create_instrument", "end_id": 9, "name": "P9 Departure Monitor",
     "frame": [235, 125, 90, 42],
     "display": ["name", "course", "speed", "clock", "headway", "train_count", "signal_stops"]}
  ],
  "preview_only": true
}
```

需要写盘时指定 `target_path` 并设 `preview_only=false`。现有供电区可用
`update_supply` 调整制式、名称和展示，`set_edge_supply` 用 ID 指配供电区，
传入 `supply_id=null` 解除绑定。默认保护既有的 Edge 供电关联，明确使用
`replace=true` 才可重配。支持原版供电菜单的代码 0–14 和 101–200。代码 0 为显式无供电，1 为通用电气，
4 为 AC 25 kV 50 Hz，101–200 对应 Maglev 1–100。解除绑定与显式无供电的原版运行含义不同。
无供电区返回代码 0，未绑定轨段用默认代码 1。
为该区运行的车辆目录要具有相应供电制式的牵引曲线。

## 磁悬浮推进段和推进组

同一个编辑入口支持 `create_propulsion_segment`、`update_propulsion_segment`、
`set_edge_propulsion_segment`、`create_propulsion_group` 和 `update_propulsion_group`。
推进段类型 1000、1001 和 1002 分别对应原版类型 1、类型 2 和重叠段。创建时提供
`name`、`power_system_code`、`position` 及 `edge_ids`。可用 `allow_multiple_trains`
设置是否容许多列车。一个轨段可同时关联常规供电区和一个推进段，分别保存到两个原版字段。
`set_edge_propulsion_segment` 提供 `segment_id` 与 `edge_ids`。用 `segment_id: null`
解除关联，需要覆盖既有推进段时传入 `replace: true`。

创建推进组时提供 `name`、`position`、按所需保存顺序排列的 `segment_ids` 和
`max_active_segments`。可先保存推进段并用回执取得 ID。更新推进组时传入目标 ID 和需要修改的字段。
`segment_ids: []` 解除该组全部成员，设上限为 0 时，原版对非空组拒绝新增激活。
推进段成员必须是同一工作表内的原生推进段，一个推进段可以参加多个组。
`delete_power_model` 按 ID 删除供电区、推进段或推进组。删除时按原版函数清除对应的
轨段引用和推进组成员。如果还有已核对范围之外的引用，工具会拒绝保存并报告。

原版工作表写入采用 `OTEdgeModel.encodeWithCoder:`（0x4bd5e0）的两个独立轨段对象槽和
`OTPowerSupplyModel.encodeWithCoder:`（0x571d80）的限额及成员数组。
原版供电菜单用 `OTInspector.awakeFromNib`（0x4eff9c）追加 Maglev 项。
原版分组及限额见 `OTController.groupPropulsionSegmentGroup:`（0x42d640）和
`OTPowerSupplyModel.tooManyMovingCoursesInSingleGroupIfTrainWouldEnter:`（0x57146c）。
Reading 工作表的冷回读确认了三个推进段的轨段绑定、两个推进组的成员和限额。
推进参数为构造的教学数据。多列磁悬浮开行时的限额行为需要原版实跑。

在 `update_instrument` 中按 ID 修改方向、大小、显示项、可见性、框及观测 Edge。
观察信号停车时须用实际主信号方向 End。观察道岔动作时，将测量仪放在具有两条道岔腿的
End 的另一半。原版在动作时通过这个成对 End 向测量仪传递计数。

`relocate_instrument` 将已保存的测量仪迁到同一工作表中另一个未装仪器的成对方向 End。
用 `id`、`from_end_id` 和 `to_end_id` 核对身份，现有仪器迁移无需模板。保存保留名称、
方向、显示设置、尺寸和仪器 ID，显示框随两处图面坐标的差值平移。已启用停车或道岔计数时，
新点位须具备对应的主信号或道岔，避免迁移后计数悄然失效。

原版仪器的区域轨段独立于列车通过测点，区域可包含同图档中并不邻接测点的 Edge。
省略 `expected_edge_ids` 与 `edge_ids` 时保留区域。要改配，提供当前图档中保存顺序的旧区域 ID 和
经审核的替代轨段 ID；清空时提供 `edge_ids: []`。迁移与区域改配在同一次原生保存中完成。

```json
{"action":"relocate_instrument","id":31,"from_end_id":4,"to_end_id":12,
 "expected_edge_ids":[20,21],"edge_ids":[22,23]}
```

该请求以 Reading 冻结工程另存并回读，清除旧 End 的仪器引用、建立新 End 的双向关联。
仪器 31 的显示框横向移动 200 个图面单位，其他图元和运营定义经归一化序列化逐字节对照。
这份迁移版的原版仪器输出仍需实跑确认。

批量创建使用 `{"action":"create_instruments_at_locations","location":"main_signal"}` 或
`location:"switch"`。可用 `selected_end_ids` 指定当前工作表的方向 End，省略时扫描整份图档。
主信号涵盖原版类型代号 1、2、24、25、26。批量位置限定普通成对 End，道岔依据相对端是否有两条相互引用的本地轨段判定。
工具保留已有仪器，按原版 1.7.6 的批量规则在至少两处合资格位置时创建。单处可用
`create_instrument`。批量生成使用有方向 End 编号的可读名称，并根据目标提供停车或换位计数。

把新工作表纳入所选 `.run` 的工程后，在运行文件启用 `Output Instruments` 和
`Power/Dist. & Energy/Dist.`。用原版实际输出查验 `OT_<供电区名>.Pt` 的时间/功率，
以及 `OT_<仪器标记>.ins` 的车次、速度、方向、停车持续时间和道岔统计。
`opentrack_read_native_evaluation_file` 对这两类文件及仪器 `.sig` 支持 SHA 绑定分页。
`opentrack_evaluate_native_run` 的 `include_supplementary=true` 也可返回供电区和仪器摘要。

Reading 复测的两个主信号测量仪各记录一次 RDG09，分别给出方向代码 1 和 2，
相应信号停车统计为 0。同次仿真写出供电区的 316 个功率样本，峰值
12,324.529 kW。该值对应教学牵引曲线与仿真设置。原版同时写出 RDG:24
的两个信号记录。后续批量案例原版读取两个信号和两个道岔测量仪。列车正常停站后，
RDG:12 在 10:25:00.91 记录到一次换位，随后以 75 km/h 经过对应位置。
