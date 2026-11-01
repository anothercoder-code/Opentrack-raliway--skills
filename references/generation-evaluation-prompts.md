# Natural user scenarios for independent forward testing

Use the Skill and public schemas to handle each request independently. Confine
these offline tests and outputs to an isolated temporary directory on the
authorized test host; do not mutate source projects, launch applications, upload
or bypass denied resources during these tests. These are user prompts, not
expected-answer fixtures or permanent restrictions on other authorized tasks.
A quoted prompt's server-only restriction applies to that test scenario only.

## Night services

“先只给我信息包和CSV，不要动原工程。已有编组 NIGHT_SET、两个方向的
Itinerary I:A_B 和 I:B_A、站名 A/B，速度类别 Reihe R；这些名字是我提供
的。A 到 B 从当天23:50起，每15分钟一班共6班，途中20分钟；B 到 A
从次日00:00起同样每15分钟一班共6班，途中25分钟。车次N101起奇数
下行、N102起偶数上行。请检查跨日和引用，给我总量和可以复用的输入。”

## Stock plus connection

“在同一信息包定义 Engine E_TEST：80吨、20米、120km/h、240kN、4000kW，
接受未标定的恒功率代理。编组 T_TEST 用1台E_TEST加2辆各40吨、25米、
120km/h的拖车。已有A/B/C三个站和I:ABC行程，类别Reihe R。
生成X1从A 08:00出发，B 08:20到08:22开，C 08:45到；X2从A 08:10开，
C 08:55到，但我想让X1在B等X2接续。不要发布，先检查再给预览。”

## Existing project blocked

“请基于服务器项目OTProjects/BJTU批量生成早高峰车次并落成独立项目，
已有材料都在服务器。若依赖缺失，先给我能检查的数据和准确阻塞说明，
不要去我的电脑运行Codex，也不要重新下载被403拒绝的包。先查清可用
路径和编组再确定输入。暂不验收全天仿真。”

## Revision and scope

“把刚才的信息包作为基线：夜间班次间隔从15分钟改为20分钟，其余不变。
同时删除旧车次OLD1，并把既有行程I:OLD改名I:NEW。我要看到差异和
哪些事情已经实际验证，暂时不要改原档，也不需要模拟器运行。”
