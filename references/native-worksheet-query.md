# 原版工作表 Finder 与公里标核对

`opentrack_query_native_worksheet` 读取 SHA-256 绑定的当前 v4 `.opentrack`。
结果提供原生图元 ID。可直接把返回的方向 End、信号或轨段 ID 用于对应原生写入入口。

| `query.kind` | 查询参数和行为 |
|---|---|
| `object_id` | `id` 为局部图元 ID。 |
| `vertex_name` | `name` 为原生点名，`match` 用 `exact` 或 `contains`，按大小写匹配。 |
| `signal_name` | `name` 为原生信号名，返回信号和方向 End 的 ID，匹配方式同上。 |
| `kilometre_point` | `kilometre_point` 为公里数，按原版单精度比较。 |
| `kilometre_conflicts` | 对每条轨段核对原版保存长度与有向公里标差。 |

若端点的公里标未设置，沿用原版取成对端公里标的规则。跨图档时，用 `related_worksheets`
提供相邻图档，逐个绑定路径和 SHA-256，同时提供 `project_run` 的路径和 SHA-256。工具确认图档
是同一运行文件声明的成员，再核对保存的图档名及双向连接器 ID。
无法解算的端点或轨段用 `unresolved_ids` 和
`unresolved_count` 报告。原版的未设置值是 `-99999`，轨段结果用 `uses_unset_kilometre`
标明这一情形。核对公里标冲突时各端先换算并按原版规则取整至米，再计算
`第二端 - 第一端 - 实长`，保留差值的方向。

```json
{
  "source": {"path": "OTAI/workspaces/Line/OTDocuments/RDG.opentrack", "sha256": "<SHA-256>"},
  "query": {"kind": "signal_name", "name": "S:RDG:9", "match": "exact"},
  "offset": 0,
  "limit": 200
}
```

```powershell
python -X utf8 -B scripts/ot.py --root D:/RailWork --profile generation call opentrack_query_native_worksheet --args-file D:/RailWork/finder.json
```

这是存档查询。原版 Finder 的窗口定位和临时选择属于交互会话。要给查到的主信号加
测量仪，使用[批量测量仪入口](native-monitoring.md)。
