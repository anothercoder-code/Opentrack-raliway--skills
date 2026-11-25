# 原版仿真任务和延误场景

`opentrack_simulation_control` 在 Windows 上用原版 OpenTrack 1.7 运行已保存的
工程。使用此前确认的[原版软件授权](software-authorization.md)。`job_directory` 是
资料根中的新目录，和原工程分开。工具从源 `.run` 读取六类目录、图档和可选运行图的
明确绑定。实际仿真使用逐场景重绑定后的副本。新建任务不改源工程、源输出和源实际时刻。

使用 `all` 或 `simulation-evidence` 工具配置，提交 UTF-8 JSON。

```json
{
  "action": "start",
  "project_directory": "OTAI/workspaces/ReadingP9Aligned_20261123",
  "run_file": "chain.run",
  "job_directory": "OTAI/workspaces/ReadingBatch",
  "scenarios": [0, 17],
  "expectations": {
    "courses": [
      {
        "course_id": "RDG09",
        "origin_station": "Twyford-side boundary",
        "terminal_station": "Tilehurst-side boundary",
        "distance_m": 4225,
        "required_stops": [
          {"station": "Reading Platform 9", "min_dwell_s": 120, "position_min_m": 1700, "position_max_m": 2025}
        ]
      }
    ]
  }
}
```

```powershell
python -X utf8 -B scripts/ot.py --root D:/opentrack --profile simulation-evidence call opentrack_simulation_control --args-file D:/opentrack/reading-job.json
```

用同一工具提交 `{"action":"status","job_directory":"OTAI/workspaces/ReadingBatch"}`。
查看任务及场景状态、实际运行进程结果和验收标记。用同样的目录和 `action:"stop"`
请求取消。后台进程只用它保留的句柄停止自己启动的原版进程。取消在轮询后生效。
若后台进程已经消失，`worker_lost` 保留最后记录状态，进程状态需要重新观察。

每个场景会创建 `runs/<场景号>/project` 和 `evidence`。任务保留源快照、
重绑定前后哈希、写回差异、原版日志和对应新输出。仿真副本会清空已保存的实际时刻，
并移除原版曾从其他图档存入 `.dest` 的无关索引。选定车次引用该索引时，任务会报告
缺少相关图档。任务关闭断点并打开逐车时刻、速度、距离、消息、占用、统计和仿真协议输出。
场景通过原版 `-scriptinit -runfile=...` 逐个执行，原有分布和故障选择被保留。
`completed` 表示原版进程完成，`native_simulation_verified` 还要求对应的逐车证据。
验收多轮后，`delay-summary.json` 按车次、计划站点事件和访问次序统计原版实际延误，
并列出通过及未通过验收的场景编号。
多场景的延误分位数、准点次数和区段占用汇总可用[原版随机批次统计](native-delay-batch.md)独立复核。

多个已准备的工程可用 `scripts/native_validation_queue.py --root <资料根> --queue <SHA-256 绑定清单>` 集中预检。
默认只在内存重演每案的原生输入。`--report` 可以保存工作目录、数据变化及预期输出。最终原版验收使用 `--execute`
和新的报告路径，沿原版运行任务逐案提交，每案保留独立输出和核验结果。

需要加载已导出的 OTD 进路排斥规则时，在同一 `start` 请求设置 `dispatching_rules`，填写规则清单
路径与 SHA-256。规则会按 `.run` 和工作表身份核对并复制到每个运行副本。 [原版 OTD 规则绑定](dispatching-rules-otd.md)

### 原版 Defined 延误

原版仿真窗口中的 **Defined** 选择保存为 `.run` 的 `Delay Scenario#-1#`。
`Mean Delay` 保存全局初始延误的默认秒数。逐车逐站的均值和命名分布名保存在
`TimetableFile` 绑定的原生 `.timetable`，常见路径为 `<工程>/OTData/<工程名>.timetable`。
Defined 使用同一份时刻表，无需单独的延误文件。

将以下 `defined_delay` 与原有 `source_project` 及保存参数一同提交给
`opentrack_edit_current_operating_plan`。工具把模式、全局值与逐站均值作为一批原生文件
更改另存，并回读各站次。`station_sign` 是要核对的原生站码。`index` 从零起算，
以保存时刻表的实际行定位，同一站重复访问可用各自索引填写。

```json
{
  "global_mean_delay_s": 15,
  "visits": [
    {"course_id": "RDG09", "index": 0, "station_sign": "EA", "delay_s": 60},
    {"course_id": "RDG09", "index": 1, "station_sign": "RDG", "delay_s": 35}
  ]
}
```

逐站均值按原版设置器的整秒口径写入。现有命名分布可用 `clear_distribution: true` 明确
移除后改成固定均值。只切换模式时可省略 `visits`，省略全局值时写入 0。也可用
`opentrack_edit_runfile_parameters` 单独写入 `Delay Scenario` 的文本值 `"-1"`，保留原时刻表。

原版从交路实际首站查找初始延误。车型启用专属初始延误时优先使用车型设置，其后才查
首站的命名分布或均值。无命名分布且首站均值为零时，原版查全局均值。中间站的均值用于站停延误，
加入计划发时或站停时长由原版车型设置决定。原版 Defined 能启用概率门控及命名分布，
因此固定均值的存档值只是输入，可用原版完程与时刻记录核对实际执行。

将候选 `.run` 和 `.timetable` 作为同一工程使用。`opentrack_preflight_simulation_prepare`
报告原版选择值、绑定时刻表、全局均值、非零均值行数及仍含命名分布的行数。
可以在正常运行请求选择 `"scenarios": [-1]`，也可以沿用 `.run` 中的 `-1`。
场景副本会保留 `.timetable` 中的逐站延误，并在未来运行时核验原版协议的 `Delay Scenario : -1`。
Reading P9 已完成 `.run` 与 `.timetable` 成对保存、回读、路径重绑定和静态运行预检。
Defined 专用原版动态验收仍待完成。

整秒发车间隔任务使用同一批处理入口的 `headway_sweep` 参数。每个计划间隔单独保存到
`runs/<计划间隔秒数>/project` 和 `evidence`，任务状态显示当前候选，全部继续使用原版零号延误场景。
同一交路沿用默认模式，不同交路使用 `comparison_mode="shared_fixed_block"` 并从图档验证共用闭塞区段。
用[原版追踪间隔核验](native-headway.md)复核完整范围和原始通行权证据。

`opentrack_edit_runfile_parameters` 可写入运行窗口、步长、延误场景和平均延误、
黏着、运行性能、断点和已验证记录格式的显示/输出及调度开关，也可写标签字号、
延误格式、移动闭塞通信和优化周期及安全距离。时间倍率使用原版标签，例如 `5:1` 或 `Best`。用
`opentrack_inspect_runfile_parameters` 查看 `editable_options`。选项编辑写入一个
新 `.run`，保留档案绑定及未选记录。存档可写与改动后实跑的证据分别记录。

## 多工程集中验收

`scripts/native_validation_queue.py` 读取一个 UTF-8 JSON 清单。外层用 `schema_version: 1` 和
`cases`。每个案例提供小写连字符 `id`、运行请求的相对路径 `request`、其 `request_sha256`
及一行 `focus`。运行请求沿用 `opentrack_simulation_control` 的 `action: "start"` 参数，
并完整绑定源工程各文件的 SHA-256。可以为案例声明 `required_files` 及 `manual_checks`。

```powershell
python -X utf8 -B scripts/native_validation_queue.py --root D:/RailWork --queue D:/RailWork/verification/queue.json --report D:/RailWork/verification/dry-run.json
```

默认干跑复用原版工作进程启动之前的工程检查，报告冻结输入、任务位置、预计输出和人工检查项。
可重复使用 `--case` 选择部分案例。进入原版集中验收阶段后，`--execute` 按队列顺序提交并等待
现有运行任务。这个模式须使用新的 `--report` 文件。需要原版界面操作的交互案例须在当前案例结束后再继续。

## 原版交互运行

启动请求加上 `"mode": "interactive"`，只运行一个场景。源 `.run` 需要配置一个严格
处在运行窗口内的 `Break Time`。跨日时同时配置 `Break Day Offset`。交互任务打开原版
窗口，保留断点和模拟步长，在隔离副本启用多线程、当前时钟、列车及消息显示。
`timeout_s` 按真实时间计算，包含暂停期间。

在相应任务图档旁的原版 **Simulation** 面板操作。等消息窗口出现 `Pause of Simulation`，
确认对应的时间。点 **Step** 后读两次 `Current Time`，验证只前进一步；点 **Start** 续跑。
需要人工暂停时选择较慢的倍率，再在时钟推进期间点 **Pause**。读取最终时刻表及消息，
按同一任务的车次、距离、停站和终到验收。

第一份 Reading 原版任务从 10:21:30 单步到 10:21:31，再续跑至终点。第二份工程在
`5:1` 倍率下从 10:23:30 续跑，10:24:39 手动暂停，单步至 10:24:40，再恢复运行。
原版的站场动画在暂停点显示 RDG09、相邻轨段颜色和信号位置。原版面板也确认加载了
`XL` 标签和 `M:SS` 延误格式。 [厂商动画说明](https://www.opentrack.ch/mobile/opentrack_e/opentrack_e.html#simulation)

使用 `status` 查看所属任务及最终验收，实时操作从原版窗口进行。局部人工进路按下节操作。
独立远程控制接口和共享输出目录的多轮累计统计仍待验证。

### 使用原版运行固定、移动闭塞或 CBTC 案例

通过 `opentrack_edit_current_operating_plan` 对跟踪同一交路的车次执行 `update_course`，
在 `fields.spacing_mode` 分别写入 `discrete`、`moving` 或 `moving_cbtc`。
用 `opentrack_edit_runfile_parameters` 另存通信周期、优化周期和安全余量。比较各次运行时保持
轨网拓扑、列车、时刻表和环境参数一致，逐项改变设置，并在原版窗口内选定有跟驰的时窗。
用[同径路参考距离验收](native-run-evaluation.md#验收同径路两列车的参考距离间隔)核对两车轨迹与终到。

## 为暂停中的列车手动预留进路

使用 `mode: interactive`，在列车进站停稳后、其下一条进路预留前设置断点。读取原版当前
时钟、车次标签和对应主信号。右键该车次标签，选 **Set Dispatching Manual**。再次打开
相同车次的菜单，应显示 **Set Dispatching Automatic** 以及 **Reserve Route**。先确认车次、
出站主信号和当前进路目录中的准确名称，再从 **Reserve Route** 的子菜单选定该进路。
选择后检查原版信号和轨段显示，然后使用 **Start** 恢复运行。原版可能在授予进路时推进一个
模拟步长。重复打开菜单并选择 **Set Dispatching Automatic** 可把列车交回原版自动调度。

Reading 验收中，RDG09 在 10:25:02 被 `S:RDG:8` 拦停。10:26:34 在原版窗口为该车
选择 `R:RDG-WB`，原版预留文件以 10:26:34 记录从 2.025 km 至 4.225 km 的区间，
出站信号显示绿灯。原版在 10:26:35 记录发车，10:28:50 终到。该工作流使用原版车次菜单，
不需要启动 OTD 网络服务。
