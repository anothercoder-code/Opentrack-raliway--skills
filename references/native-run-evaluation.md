# 原版运行结果核验

从原版运行的新输出核对预期车次。用车次 ID 和 `.tt` 中的站名分别标识
行程与到发位置。对已有项目，先从绑定的原生时刻表取得应到站名、停站序列和车次，
不要用最后一条实际到达事件反推预期终点。

`opentrack_evaluate_native_run` 可通过 MCP 或
`python -X utf8 -B scripts/ot.py --root D:/RailWork --profile all call opentrack_evaluate_native_run --args-file D:/RailWork/expected-run.json` 使用。
下面是一个指定终点与停车条件的请求。

```json
{
  "output_directory": "OTAI/workspaces/ReadingP9/output",
  "evidence_directory": "OTAI/workspaces/ReadingP9Evidence",
  "window_end_s": 37800,
  "include_supplementary": true,
  "courses": [
    {
      "course_id": "RDG09",
      "origin_station": "Twyford-side boundary",
      "terminal_station": "Tilehurst-side boundary",
      "distance_m": 4225,
      "required_stops": [
        {
          "station": "Reading Platform 9",
          "min_dwell_s": 120,
          "position_min_m": 1700,
          "position_max_m": 2025
        }
      ]
    }
  ]
}
```

评估读取所选车次的实际到发、计划差、速度和位置，并与当次原版统计及协议交叉核对。
停站同时需要实际到发时刻、连续零速、停站期间位置不变和发车后正速度。OpenTrack
可将匀速或静止有效区间压缩成两个端点。报告保留这些端点，可与 `.tt` 的整数秒复核。
位置是原版沿车次进路的参考距离。报告区分车次预期到达、协议中的计划结束钟点以及
消息里的明确仿真结束事件。原版脚本结果可能省略后者；需要时用
`require_end_message=true` 要求明确记录。

需要证据绑定时，提供含 `before.json`、`process.json` 与 `inputs/` 的本地
运行证据目录。核对冻结输入哈希、原版 EXE 指纹、退出状态、输出目录和输出文件时间。
有启动时记录的输出 SHA-256 时也进行核验。未提供启动证据时仍可核对实际车次
记录，报告只给出数据结论。`expected_incidents` 可给出 Incidents 协议名称，
或对象 `{"name":"SECTOR_A","target":"Route R_A"}` 同时检查该实体的开始和结束
消息。对象也可限定 `course_id`、`started_clock` 和 `stopped_clock`，并按原版消息
顺序核对起止。记录中没有动态事件数据时，区分协议所列故障与实际触发。

运行任务可额外检查原版物理峰值和信号预留间隔。任务按要求开启输出并在原版退出后
记录 SHA-256。独立验收需读取同一次任务的流程证据及原版输出。

在 Reading 功率事件工程的验收请求中，增加
`"expected_physical_peaks": [{"course_id":"RDG09","quantity":"mechanical_power_kw","begin_s":37502,"end_s":37562,"peak_min":1999.99,"peak_max":2000.01,"minimum_moving_samples":100}]`。
九站信号事件工程则增加
`"expected_signal_reservation_headways": [{"signal_label":"W_HOME_A_S_J22_W_HOME","leading_course":"H2E1","following_course":"H2E1_FOLLOW","minimum_s":160}]`。

每项车次必须出现在相同请求的 `courses`。物理峰值从所选绝对秒窗口内的移动
样本计算，支持牵引力、机械功率和输入功率。信号标签来自每趟列车的 `.sigpos`，
并由冻结图档绑定到唯一的原版信号 ID。
验收从 `.step1` 提取以该信号为起点的唯一预留段，通过其原版时间差
检查预留间隔。测量列车实际通过信号的间隔时使用通过时刻或位置轨迹。

## 验收同股道物理联挂

用 `opentrack_verify_native_platform_join` 读取一次封存运行。`run` 填该次运行的
`output_directory` 和 `evidence_directory`。`receiver` 和 `donor` 各填现有完程验收
所用的 `course_id`、始发和终到站名、距离及容差。`station_sign` 填原版联挂站站码。
可用 `expected_platform` 指定目标工作表和方向端 `{"document":"R4","end_id":108}`。
如母车多次访问同站，可用 `main_visit_index` 指定冻结时刻表行。输出中对应信号还须能唯一定位。
运行前启用 `.run` 中的 `Output Station- & Signalpositions`，并保留两车的 `.tt`、`.vt`、`.st1`、
`.sigpos`、`OT_Messages.txt`、流程记录及其原版输出 SHA-256。

`.sigpos` 的 `Itineraries` 标头列出计划备选序，正文的物理主信号行按实际使用的进路序列生成。
工具在每个车次自身的距离轴上核对冻结图档中的平台信号、方向端和停车 Edge，区分里程相同的
备选股道。供车终到停车时刻须与双车 `Trains joined at <站码>` 消息一致。受车在参考端停稳，
供车车头在同一 Edge 上到达与受车编组长相符的位置，随后受车实际续行。到发时刻同时从 `.tt`
复核。这个入口适用于有明确主信号和停车参考端的同向联挂，以及联挂前同一车次没有改变编组的情况。

历史封存 R4 D1 联挂中，`M18MAIN02` 和 `M18DET03` 的参考端分别在各自距离轴的 30,000 m
和 60,000 m。两车在 R4 `End 108`、`Edge 318` 联挂。供车在 `88545.75 s` 停稳，距参考端
209.1 m，冻结受车长 209 m。不同股道的联挂还需对应原版运行证据。

## 验收同径路两列车的参考距离间隔

原版任务及事后验收均接受 `expected_following_separations`，可将以下字段加入验收请求。

```json
{
  "expected_following_separations": [
    {
      "leading_course": "H2E1",
      "following_course": "H2E1_FOLLOW",
      "begin_s": 32680,
      "end_s": 33105,
      "minimum_reference_gap_m": 600
    }
  ]
}
```

两车都要列在验收请求的 `courses`，且原生存档只选同一个定向交路、使用相同的距离输出偏移。
选择两车均已发出且尚未终到的时间窗。工具核对冻结车次档案、原版 `.st1` 哈希、轨迹交路标头和
采样覆盖。它用每个小时间段前的前车样本和后面的后车样本计算保守下界，并扣除原版输出精度。
报告给出最低间隔的位置样本、时窗和两车存档闭塞模式。此量为交路参考距离差。

九站样例对两班同径路车核验 09:04:40 至 09:11:45。两车全程各走 12 km。固定闭塞时后车
09:04:33 发出、09:18:11 终到，移动闭塞时分别为 09:03:28、09:17:40。保守间隔下界在
固定闭塞、移动闭塞、CBTC 三个案例中分别约为 1,745、694 和 720 m。移动闭塞在相同条件下
把设置中的安全余量从 45 改为 240 m，保守间隔下界约为 914 m。将通信周期或优化周期
分别从 1 改为 12 秒时，本案例的两车距离时间样本相同。配置方法见[原版仿真任务](native-simulation-jobs.md)。

补充数据包括站点和道岔动作统计、原版 `.occ` 的预约/物理占用/释放周期、沿车次的
预约/释放阶梯及加速度、机械功率、输入功率和能量序列。原版 `.occ` 用 `-1` 表示
没有记录的事件时间，返回值保留为 null。`sum_logged_occupation_duration_s`
是有双端时间记录的单周期占用时长之和。协议提供对所选占用对象计算的占用率。
原版有预留准备结束时间时会在 `SR` 后输出 `EP`。周期回读保留
`pre_reservation_s`，其中分别是原预约起点和准备结束。将 `.occ` 导入原生工作表
占用图时，`EP` 以原版点类型 7 保存。
读取原始数据页用 `opentrack_read_native_evaluation_file`，输入
`{"source":{"path":"OTAI/workspaces/ReadingP9/output/OT_RDG09.vt","sha256":"…"},"offset":0,"limit":200}`。
支持 `.tt/.vt/.vs/.st1/.step1/.step2/.as/.at/.Ps/.Pis/.Wis/.tsvP/.occ/.Pt/.ins/.sig`，含全局
`OT_Physic.tsvP` 与 `OT_StationStatistics.txt`。

要检查指定咽喉是否有不同列车同时预留或占用，提供完整的运行证据目录，在请求中添加
`"exclusive_occupation_groups": [{"document":"J22","group":"J22_Safety23","courses":["H2E1","H2W1"]}]`，
并将车次换成当前项目确实使用该资源的车次。评估从冻结的 `.run` 图档读取原版安全组，
核对对应占用组覆盖同一组轨段，再从 `.occ` 的 `SR/SO/EO/ER` 分别比较预留和物理占用
时段。若缺少完整周期或指定列车的记录，评估失败。时间重叠以原生输出的 0.01 秒精度判断。
九站样例中 33 列车均终到，J22 安全组的 20 个轨段记录了 17 个完整周期，预留和物理占用
均没有跨车重叠。这项检查覆盖所选资源及本次仿真的记录。

原版验证样例覆盖 Reading 站台的停靠和离站，以及 Cross6 的路线限速、开始和结束
事件、占用对象与道岔统计。当前格式契约以英文 Windows 1.7 输出为准。
