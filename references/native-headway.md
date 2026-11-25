# 用原版仿真比较发车间隔

`opentrack_compare_native_headway_runs` 比较两列车在不同计划发车间隔下的实绩。它读取已完成的原版任务，
从原版时刻表输出取到发和通过时刻，返回满足延误门槛的最小已测间隔。使用前确认
[原版授权](software-authorization.md)。

1. 选定一条有向交路和两趟依次发车的列车，冻结相同的进出站端点、里程、车辆、闭塞方式和运行设置。
   仿真场景使用 `Delay Scenario=0`。
2. 用 `opentrack_batch_current_catalogs` 的 `shift_timetable_rows` 等量平移后车全程计划。
   将各时刻表放入对应的原生工程副本，使用 [原版运行任务](native-simulation-jobs.md) 依次运行和保存证据。
3. 在 `leading_course` 和 `following_course` 分别给出 `course_id`、`origin_station`、
   `terminal_station` 和 `distance_m`。在 `runs` 列出 2 至 32 组不同间隔的
   `output_directory` 和 `evidence_directory`，路径相对于数据根目录。
   `maximum_delay_s` 默认 5 秒，按两趟车各自所有有计划时刻的原版观测事件核对。

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile generation call opentrack_compare_native_headway_runs --args-file D:/RailWork/headway.json
```

工具比对原版程序指纹、封存输入、运行设置和所用输出散列。除工程搬移所产生的声明路径变化外，
唯一允许变化的是可用现有原生写入器重现的后车计划平移。两趟车均须原版完整走行并终到。
每组返回计划及实测发车间隔、两车最大晚点及对应事件。所有候选均未满足门槛时，最小通过值为 `null`。
间隔和晚点按原版时刻表实绩的秒级记录计算。

候选对比结果覆盖已提供的离散间隔和延误门槛。需要逐一核验更小的整秒间隔时，可提交下述扫描。
厂商 Headway Calculator 还支持对不同列车路径与闭塞制式计算最小间隔和临界区段。[厂商说明](https://www.opentrack.ch/opentrack/opentrack_e/opentrack_e.html)
闭塞资源与预留释放实绩可查[原版联锁校核](native-interlocking.md)。

## 小数时刻与移动闭塞取证

`opentrack_measure_native_headway_trace` 读取一至十二次已经完成并封存的原版任务。填写
`leading_course`、`following_course`、`runs`，以及从共同有向交路起点量起的
`checkpoints_m`。每次运行须包含这两趟车、一个共同交路和同一里程参考，须有原版
`.st1`、`.vt`、`.step1`、`.step2` 和运行协议。可在 `monitored_resources` 另填
`document` 和 `group`，检查已有原生 `.occ` 文件的共用区段。

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all call opentrack_measure_native_headway_trace --args-file D:/RailWork/headway-trace.json
```

- 每个里程点给出冻结图档中的 Safety Element、前后车真实通过时刻及间隔上下界。
  结果用轨迹的相邻原版观测点约束，通过时刻按 0.01 秒、里程按 0.1 米计入打印舍入。
  采样越稀疏，时刻上下界就越宽。
- 单独报告原版 `.tt` 整秒发点、首次出现正速度的样本、冻结配置步长和协议显示步长。
  为每趟车给出原版预留、释放曲线的样本形态。对同一里程，也可核对前车释放曲线与后车预留
  曲线到达该点的区间。曲线未覆盖该点时，对应字段为空。
- 对明确选择的监测组，将原版占用进入时刻与同一冻结区段的实际走行互证。
  报告前车释放预留至后车接收预留的时差及舍入范围。多个运行各自给出证据。
  这些结果可以分析实测亚秒交接，计划时刻仍按存档整秒保存。

在同一条 12 km 交路的既有原版数据中，固定闭塞产生同一打印时刻的预留阶梯跳变，移动闭塞及
CBTC 在单个保存区段内部也观察到连续的预留进展。移动闭塞案 J22 监测组由前车在
32955.53 秒释放，后车在 32955.59 秒接收，原版差值为 0.06 秒，配置步长为 0.2 秒。
该算例验证的是观测到的交接和走行时间范围。

## 车站及终端实测吞吐

`opentrack_measure_native_station_throughput` 用已完成的封存原版任务核对车网投入运行后的站点实绩。
提供 `output_directory`、`evidence_directory`、原版实际使用的全部 `course_outcomes` 和所需
`station_signs`。每趟车填写编号、始发站全名、终到站全名和预期里程，与原版完程评估沿用同一格式。
终到通过的车次可声明 `terminal_event: "Pass"`。

工具把每个原版 `.tt` 中的车站全名定位到冻结 `.stations` 的站码，逐站把到达、出发、通过
计数与原版 `OT_StationStatistics.txt` 对照。所有使用的车次及原版统计文件都须具有运行任务封存的散列。
可填写 `windows`，每项包含从第 0 日起算的 `start_s` 与 `stop_s`。窗口包含起点并排除终点。
省略时按原版配置时间窗统计。用 `peak_window_s` 指定滚动窗口长度，返回各类最大计数及其最早窗口，
同时给出头尾事件用于复核。

普通到发、通过、始发、终到和不同车次数分别列出。一趟车同一站的到达、出发与通过可能都是原版的
独立记录。终端完程按车次最后一次已验证的到达或通过计数。同一实体车辆更换车次时，依旧按原版
车次输出计数。每小时折算值适用于该观察窗。

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all call opentrack_measure_native_station_throughput --args-file D:/RailWork/station-throughput.json
```

## 全部整秒候选和起点限制

在 `opentrack_simulation_control` 的批处理启动请求加入 `headway_sweep`。
填写 `leading_course_id`、`following_course_id`、`minimum_s`（默认 1）和 `maximum_s`。
`expectations.courses` 按前车、后车顺序分别填写两车的始发站、终到站和里程。
工程只使用这一对有直接发车时刻、无需接续的列车，并使用零号延误场景。
每个正整数建立一份冻结原生工程，后车的全程计划按同一个偏移变化。

可以把长扫描拆成相邻的独立任务。各任务使用同一份原生输入，组合时每个整数只出现一次。
使用外部 OTD 规则的扫描任务也可以合并，所有任务须绑定同一规则包并使用对应的原版启动参数。 [原版 OTD 规则绑定](dispatching-rules-otd.md)
全部运行成功后，把任务目录交给 `opentrack_evaluate_native_headway_sweep`，
用 `maximum_delay_s` 指定两车允许的最大晚点。若从 1 秒起每个较小值都已运行且未通过，
可确认这一对车和本次门槛下的最小正整秒计划发车间隔。

当相邻失败值的最差事件是始发晚点时，工具对照原版信号停车消息、后车零速轨迹、
两车的预留与释放阶梯以及冻结图档，报告实测受限的起点信号和释放区段。
可用 `monitored_resources` 指定该区段的占用组，进一步核对 `.occ` 中异车次的通行权交接。
原版小数时刻用于区段交接，整秒晚点仍取原版时刻表计时。

## 不同径路共用的固定闭塞区段

在 `headway_sweep` 中设 `comparison_mode: "shared_fixed_block"`。两车各自使用一条有向
交路，可以有不同的始发、终到和走行距离。按前车、后车顺序声明各自的完程条件。两条
交路必须不同，使用固定闭塞，并在封存图档实际共用至少一个 Safety Element。
仍然只平移后车时刻表，原版逐秒候选、车辆、图档及运行配置的核对保持一致。
省略模式时沿用同交路扫描。

为需要取证的共用区段保存原生占用监测组。评估会发现具有原版占用输出的共用组，也可在
`monitored_resources` 中明确指定 `document` 和 `group`。报告首先列出冻结图档中实际共用的 Safety Element
及两套独立径路里程。若最小通过值旁边有一组失败值，再比较同一组原版 `.occ`、两车各自的
`.step1`、`.step2` 和 `.st1`。两车的发点需要按计划执行，失败案由下游事件超过晚点门槛。
报告检查前车释放和后车接收是否相差至多一步，将通过案按后车实际发点对齐，再核对失败案
的后车是否较晚进入同一个闭塞区段。证据不足的组单独返回原因，整秒最小通过值仍由原版运行决定。
