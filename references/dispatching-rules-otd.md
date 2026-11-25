# 原版 OTD 进路排斥规则

`opentrack_write_dispatching_rules_otd` 以同一工程 `.run` 指定的完整工作表集为基础，另存原版 OTD
`dispatching-rules.xml` 和 `launch-manifest.json`。输入绑定 `.run` 及每张工作表的路径和 SHA-256。
工程 `.opentrack` 中保留已有进路。原版在启动时读取外部规则，并与已有主进路匹配。

每条 `RuleRoute` 用 `document`、`start_end_id` 与 `route_name` 核对主进路。默认复合 ID 为
`<图档basename>-<起点End ID>-<Route名称>`。跨图主进路使用始发工作表和起点。可选 `route_id_mode=route_name`
使用原版名称模式，整个工程中的重名会导致拒绝。进路参与分配时每个只能挂一个规则集。通过 `applies_to`
指定受规则约束的申请进路，再在 `rules` 指定阻止申请的情况。

| `kind` | 输入与原版含义 |
| --- | --- |
| `conditions` | `conditions` 中的全部行同时满足才阻止申请。每行选 `reservation`（`reserved` 或 `free`）、`minimum_length_m`、`stop_code` 或默认另车预留。`stop_code=extendedDwell` 时填写 `extended_dwell_s`。 |
| `capacity` | `reserved_routes` 列出要观察的主进路，`maximum_other_trains` 是触发阈值。符合条件的不同预留列车数达到此值即禁止申请，同一列车只计一次。 |

`preview_only` 默认开启。用 `preview_only=false` 和工程之外的 `target_directory` 提交，工具复查所有绑定输入，
写盘并回读 XML 和启动清单。调车对象、连接器片段和直接轨段 ID 不能用作此工具的 OTD 主进路引用。

## 既有规则随径路改档

`opentrack_inspect_dispatching_rule_bindings` 读取既有 `source_manifest`、其绑定的 `project_run`
和完整 `documents`，报告每个主进路 ID 的挂载次数、条件次数及原生走行、道岔、闭塞资源和防护字段。

`opentrack_rebind_dispatching_rules_otd` 接收 `source_manifest`、`original`、`candidate`、`route_rebindings`。
两个工程分别提交自己的 `project_run` 和完整 `documents`，均使用路径与 SHA-256。每条审核记录
用 `old` 和 `new` 给出 `{document,start_end_id,route_name,array_id}`。
进路 ID 相同但轨段、连接器、安全单元、道岔设置、排他或释放资源变化时，仍须明确提交该进路的审核。
规则继续使用源包中的复合 ID 或名称模式。已审定的重绑同时应用于规则挂载和全部条件引用，
保留原规则顺序、值及其余 XML 字节。另存在两工程之外，并将新清单绑定到候选的 `.run` 和图档。

Grid 改名案只改原 XML 的两个引用，分别对应规则挂载及预约条件。Reading 的相同进路 ID
在改线后显式审核了两条实际资源范围，XML 与修改前逐字节相同，新清单据此绑定新图档。
两个案例均已完成正常命令行预检，规则实际生效仍须原版运行核对。

## 隔离仿真任务

在原有 `opentrack_simulation_control` 的 `start` 请求中加入 `dispatching_rules`。
用已发布 `launch-manifest.json` 相对于资料根的路径，并填写该文件的 SHA-256。
其同目录须有对应的 `dispatching-rules.xml`。任务会核对选定 `.run` 和每张工作表的路径与 SHA-256，
以及 XML 的 SHA-256 和长度。规则包使用导出生成时选定的 `.run` 和基础设施再次提交。

```json
{
  "dispatching_rules": {
    "path": "OTAI/workspaces/GridRules/launch-manifest.json",
    "sha256": "<实际 launch-manifest.json 的 SHA-256>"
  }
}
```

任务保存规则包的源快照，每个场景把核过哈希的 XML 复制到自己的 `project/otd-rules/` 和
`evidence/inputs/otd-rules/`。启动参数由任务生成，只追加 `-dispatchingrules` 和
`-dispatchingrulesfile=<本场景的绝对路径>`，名称模式再追加 `-routeidtype=routename`。
准备和启动的 JSON 证据分别记录绑定和实际参数。Windows 执行路径必须使用 ASCII 且规则文件路径不能含 `=`。
独立随机批次统计和发车间隔扫描核验也会回读任务级规则包，核对原版程序指纹、源工程、每个运行副本的
规则哈希以及原版启动参数。随机批次的零号对照和编号场景须绑定同一规则，合并多个间隔扫描任务时也须
使用同一规则包。输出的 `dispatching_rules` 给出本次汇总所用绑定。规则产生的预留变化仍需原版输出单独验证。

OpenTrack 1.7.6 的 `awakeFromNib`（`0x412cb4`）读取上述参数。`applicationDidFinishLaunching`
（`0x436360`）先导入规则并保存其进路字符串标识。脚本计时器（`0x436b54`）随后读取 `.run`、打开
工作表并启动仿真。`otd_prepareForSimulation`（`0x5fe5b0`）在此后的准备阶段把规则绑定到当前工程进路。
离线验收覆盖九图档工程的两个独立场景准备、启动参数和文件哈希。原版导入及规则对列车预留的效果待实跑验收。

对已完成并封存的控制组和启用组，可用[原版 OTD 进路排斥效果验收](native-otd-reservation-effect.md)
核对冻结输入、原版进路预留与释放时刻以及授权延后。
