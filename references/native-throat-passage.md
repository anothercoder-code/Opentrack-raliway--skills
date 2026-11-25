# 原版跨图档咽喉通过核验

`opentrack_verify_native_throat_passage` 从一次已封存的 OpenTrack 原版运行核对一个车次的跨图档通过和监测组占用。将 `output_directory`、`evidence_directory`、`course_outcome` 和 `passage` 写入请求。文件路径均相对于数据根目录。

```powershell
python scripts/ot.py --root D:/opentrack --profile generation call opentrack_verify_native_throat_passage --args-file D:/opentrack/OTAI/workspaces/ParNativeDiagramBatch_20261123/throat-passage-historical-request.json
```

- `course_outcome` 使用与完程评估相同的结构，必须有终到站。建议明确实际停站目标位置和最短停车时间。
- `passage` 包含同一车次 `course_id`、按经过顺序列出的所有跨图档 `boundaries`、以及需核验的 `groups`。边界使用 `from_document`、`from_end_id`、`to_document`、`to_end_id` 指定存档进路上跨界前后的有向 End。工具从存档另行回读两侧的互反 Connector ID。每组使用 `document`、`group` 和完整的原版 `edge_ids`。
- 车次必须启用，且只有一条已存档的 Itinerary。核验读取原版协议与输入输出散列、`.st1` 车头轨迹、`.step1/.step2` 进路授权和释放轨迹、`.occ` 组日志。跨界时刻以车头严格位于界面两侧的原始样本区间报告。每处界面都要有更早的进路授权。
- 监测组边集按实际进路拆成物理连续段。报告每个原版 `SR/SO/EO/ER` 循环覆盖的段索引与车头所处位置。组可能覆盖离散区段，区段之间的轨道独立于组成员。循环日志只能证明该组层面的观测。对排他与两车授权交接，使用另有完整 Safety Element 与对照条件的[原版联锁核验](native-interlocking.md)。
- 若两个原版进路轨迹收尾于同一时钟，且列车已完成位移，`.occ` 终末释放可对应收尾时钟。该情况单列为 `simulation_end_release_clock_only`。这与可观察到的 `.step2` 释放前沿分别报告。

在已有原版 Reading RDG09 封存运行上已核对进界 1100 m 的 37325.32–37325.52 秒、出界 3125 m 的 37571.23–37571.43 秒。进站与站台组占用持续至 37529.00 秒，出站组从 37500.91 秒开始占用。进站组出现 37534.20 秒的释放前沿，出站组只对应进路轨迹的 37680.00 秒收尾时钟。

最终验收队列的 `reading-both-throats` 与 `reading-retained-crossing` 可使用同结构的 `throat_passage`。干跑会核对冻结快照中的有向边界、实际 Connector、监测成员、计划停车和必须产生的原版文件。原版运行完成后，队列先按本次启动和文件散列核验，再执行上述通过检查。两项改造的历史对照和离线干跑已就绪，改造后实绩需要最后的原版运行。
