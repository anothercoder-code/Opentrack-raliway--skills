# OpenTrack OTD 实时仿真控制

`opentrack_ai.native_otd` 是独立的 Windows 客户端，适用于已经启动并隔离的 OpenTrack
1.7.6 原版仿真。客户端发送原版支持的 SOAP 命令。配套记录器接收仿真、时刻、信号、进路和
区段回调。命令已按原版代码核对并做模拟响应测试，回调已用合成原版格式在真实本机 HTTP
传输中收录。原版进程的联网和命令执行效果仍待实测。
[OpenTrack API](https://www.opentrack.ch/opentrack/opentrack_e/api/opentrack_api_e.html)

## 原版进程配置

1. 在隔离的测试环境和独立的 Windows 用户配置中，用 `-otd` 启动已授权的原版。原版在此模式下显示 **OTD Settings**。
2. 在 **OTD Settings** 选择 SOAP 模式，并核对本地 **OTD Server Port**。原版默认本地服务端口为 `9002`。同一面板中的目标主机与端口用于原版向调度台发送回调，默认是 `localhost:9004`。点击 **OK** 会写入该用户的原版设置。
3. 在面板中单独启动 OTD 服务，并记录当前进程 PID。原版服务绑定 `0.0.0.0`。测试网络应事先隔离，再启动监听。客户端始终连接 `127.0.0.1`，并核对所选端口、拥有该监听的进程及原版程序 SHA-256。`--isolated-test-network` 由操作方确认这一前提，客户端本身不会配置系统网络或启动监听。

从 Skill 的 `backend/OTAI` 目录运行。`--data-root` 指向已有原版完整版授权声明的工作区。将例中的 `1234` 换为实际测试 PID，并按面板填写端口。

```powershell
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network version
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network watchdog --value 18
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network pause 36840
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network step
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network route reserve RDG09 "<原版 OTD 进路 ID>" 37594
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network speed RDG09 37594 35
python -m opentrack_ai.native_otd --data-root D:/opentrack --port 9002 --process-id 1234 --isolated-test-network timetable departure RDG09 RDG 37596
```

| 操作 | 原版消息 | 客户端确认 |
| --- | --- | --- |
| `version` | `getOpenTrackVersionRequest` | `getOpenTrackVersionResponse` 的版本号 |
| `watchdog` | `getLifeRequest`，携带 `Watchdog value` | 值加一且模块为 `OT` |
| `pause` | `pauseSimulation time`，单位为仿真秒 | 空响应体 HTTP 200 |
| `step` | `stepSimulation` | 空响应体 HTTP 200 |
| `start`／`end` | `startSimulation`／`endSimulation` 带指定时刻 | 空响应体 HTTP 200 |
| `route allow`／`disallow`／`reserve`／`cancel` | `setRouteAllowed`／`setRouteDisallowed`／`setRouteReserve`／`cancelRoute` | 空响应体 HTTP 200 |
| `speed` | `setRequestedSpeed`。省略速度值时发 `resetRequestedSpeed` | 空响应体 HTTP 200 |
| `timetable arrival`／`departure`／`dwell` | `setArrivalTime`／`setDepartureTime`／`setDwellTime`，到发取仿真绝对秒，停站取持续秒数 | 空响应体 HTTP 200 |

仿真命令的 HTTP 确认先于原版向仿真控制器转交命令。返回值 `application_confirmed: false`
保留这个区别。运行时用独立回调、界面状态及当次原版输出来确认动作。进路命令使用原版
OTD 进路 ID。常规 OTD 模式由图档名、始端 ID 和进路名组成，例如
`<Document>-<StartEndID>-<RouteName>`。如已启用原版仅进路名模式，以该模式的原版导出为准。

## 记录本机原版格式回调

将原版 OTD 回调目标设为 `127.0.0.1` 和已选本机端口。用下列命令运行短时记录器。

```powershell
python -m opentrack_ai.native_otd_callbacks --data-root D:/opentrack --port 9004 --duration-s 60 --max-events 1000 --output OTAI/workspaces/OTD-test-events.json
```

记录器仅绑定 IPv4 回环，支持原版 SOAP 和单记录 DIME。文件包含原版事件名、仿真秒、适用的
车次／信号／车站／进路／区段标识及收到的消息 SHA-256。将其与同一仿真任务的车次和
输出记录交叉核对。回调信封可由本机进程生成，因此单独的回调文件无法认证发送方。

原版取证范围为 OpenTrack 1.7.6。`0058dec4` 解析命令字段，`00590ff0` 把命令转交给仿真，
`005c6298` 构造响应。`00594d58–005957d0` 构造回调，`005bd8b0` 生成 OTD 进路 ID，
`0040c2ac` 提供监听绑定的实现证据。
