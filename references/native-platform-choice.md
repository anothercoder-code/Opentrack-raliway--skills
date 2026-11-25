# 核验原版选择首选或备用站台

`opentrack_verify_native_platform_choice` 将原版实际到发、沿程位移、进路预留和物理占用
对应到冻结工程中的一个站台。它核对同一 Course 的已保存交路顺序及运行时实际使用的选项，
可同时比较另一趟车在首选站台的物理占用与预留时间。

1. 在 [既有线网运行计划](current-operating-plan-edit.md) 为车次声明首选和备用交路。
2. 为每个选项的停车边各建一个 [原生占用监视组](native-occupation-groups.md)。
   一个组对应一个完整的 Safety Element，且该资源只出现在一条待验交路中。
3. 启用 `Output Route Occ.` 和常规车次结果。原版任务结束后保留冻结输入、输出文件和进程回执。
4. 按保存的优先级提交 `choices`，明确预期实际使用的交路。默认核验终到站台，
   用 `platform_station` 指定需要核验的中途站。若还要验收首选站台状态，
   提供另一趟车的终到要求和要检查的时间关系。

```json
{
  "output_directory": "OTAI/workspaces/PlatformTrial/runs/0/project/output",
  "evidence_directory": "OTAI/workspaces/PlatformTrial/runs/0/evidence",
  "course": {"course_id": "M12TEST", "terminal_station": "Ring Station R2"},
  "platform_station": "Ring Station R2",
  "choices": [
    {"itinerary": "COMPOSITION_LOCAL_F2_R2", "resource": {"document": "R2", "group": "PLATFORM_D1"}},
    {"itinerary": "PLATFORM_CHOICE_D2", "resource": {"document": "R2", "group": "PLATFORM_D2"}}
  ],
  "expected_selected_itinerary": "PLATFORM_CHOICE_D2",
  "primary_availability": {
    "course": {"course_id": "M12BLOCK", "terminal_station": "Ring Station R3"},
    "mode": "occupied_at_alternative_reservation"
  }
}
```

`occupied_at_alternative_reservation` 检查备选站台取得预留时，另一趟车当时正在首选站台
物理占用。`released_before_primary_reservation` 检查待验车始发时首选站台正被另一趟车
占用，随后在上一趟车解除预留后取得首选站台。`unoccupied_at_primary_reservation`
检查待验车取得首选站台预留时，指定的对照车在该资源上没有预留。

可从 `generation` 或 `all` 工具集调用。结果列出已保存的交路优先次序、实际站台、
各选项的方向端和停车轨段，并保留原版文件 SHA-256。适用范围是从同一方向端出发、
每条交路只经过一次所选车站且站台资源互异的有界交路。

R2 对照中，首选 D1 空闲时，原版选中 D1。两车同时运行、前车全组锁闭两条进路共用的咽喉时，
原版在 D1 释放后才为后车预留首选进路。备用 D2 仍保存在 Course，并且两条交路也可汇合到同一个
原生终点。在该全组释放对照中，D2 的站台监视组无物理占用。调配验收须观察整条备用进路的可用状态，
包括公共咽喉和释放边界。

在同一通过交路对照中，为首选进路设置分段释放后，原版在 09:08:00 为后车预留备用 D2
（R2 方向端 120）。此时前车仍物理占用 D1，直至约 09:24:29。后车于 09:10:45 到达 R2，
随后驶满 34,036 米到达共同终点 R3，两趟车均完成仿真。原版区段占用和进路轨迹记录
将备用站台选择与中途实际停车对应起来。

同一车次可用 `availability_checks` 核验多条候选交路。每项指定 `itinerary`、独立见证车次 `course`
和 `mode`。`occupied_at_selected_reservation` 要求实际站台取得预留时，见证车在指定候选站台
处于物理占用期间。`unreserved_at_selected_reservation` 检查该见证车当时未预留该候选站台。
将 `require_all_higher_priorities_occupied` 设为 `true`，可要求所有优先级高于实际选择的候选都有
已核验的占用证据。

`throat_authority` 可同时核对多组共用咽喉。每组提供 `resource`、`preceding_courses` 和
`following_courses`，将待验车放在前后两列之间。该监视组必须位于每条候选交路上，且每个指定车次
只有一组完整的原版通过记录。接口按请求顺序核对每对车次先释放再预留，返回原版事件秒数和间隔。

R2 三站台对照中，D1 和 D2 均被其他列车物理占用时，后车于 09:14:00 预留第三优先的 D3
（R2/132、停车轨段 337）。将 D2 见证车移到 09:45:00 发车后，后车仍在 09:14:00 取得预留，
改走第二优先的 D2。共用咽喉的三个 Safety Element 均先释放再由下一趟车预留。
两案三趟车均按原版轨迹完成 34,036 米到共同终点 R3。

把同一后车的计划始发提前至 09:09:00 后，原版记录它在 F2 的入口信号停车，速度及位移保持为零约
69.53 秒。前车在 33009.51 秒释放从始发点起算的 3,136 米接近进路，后车于 33009.53 秒预留同段，
随后取得已释放的共用咽喉和 D3 站台。原版到发报表记载始发晚点 69 秒，仍完成 R3 终到。
