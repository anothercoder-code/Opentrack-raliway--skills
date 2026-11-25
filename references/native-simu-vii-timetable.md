# 原版 SIMU VII 时刻表导入

`opentrack_import_native_simu_vii_timetable` 将 SIMU VII 的首站时钟、走行秒、停站和站停秒写入已有 Course 的原生 `.timetable`。使用完整工程清单和 SHA-256 验证原生站序、交路及已有连接。输出是可纳入完整工程重定位的时刻表增量。

```json
{
  "source_project": {
    "project_directory": "OTAI/workspaces/Example",
    "files": {"example.run": "<SHA-256>", "OTData/example.timetable": "<SHA-256>"},
    "complete_project_inventory": true,
    "run_file": "example.run",
    "execution_root": "D:/opentrack/OTAI/workspaces/Example"
  },
  "exchange": {"path": "OTAI/workspaces/Inputs/SimuVIIExample.txt", "sha256": "<SHA-256>"},
  "course_by_simu_id": {"SIM804": "IVT01"},
  "station_by_simu_sign": {},
  "endpoint_clocks": "mirror_for_run",
  "derive_arrivals_for_run": true,
  "preview_only": true
}
```

填写完整的源文件清单。站码默认按原生代码匹配，也可使用 `station_by_simu_sign` 显式绑定。
在 Skill 目录执行 `python scripts/ot.py --root D:/opentrack --profile all call opentrack_import_native_simu_vii_timetable --args-file <请求.json>`。保存时指定新 `target_directory`，并设置 `preview_only: false`。

## 输入

```text
FAHRPLAN
ZUG
SIM804
West B10:22:45 0
PLAT 192 X 64
East 1 X 90
END
```

- 接收以空格或 Tab 分隔的 ASCII。首 token 为 `FAHRPLAN`，`ZUG` 或含 `BED` 的记录后另起一行写车次号。原版的 `0`、`99999` 标记在运营内容中跳过，`END` 收尾。
- 首站允许 `BHH:MM:SS`、`B HH:MM:SS` 或 `HH:MM:SS`，后接显式停时。正停时会写停车位和 `发车－停时` 的到达，首站站停字段使用原版默认 0。
- 后站停时为 0 时，写 `站码 0 走行秒`。正停时时，写 `站码 停时 过渡字段 走行秒`。原版在这个分支跳过过渡字段。紧跟站码的独立 `K1`／`H1` 合并进站码。
- 后站累计发车按 `上一站发车＋走行秒＋本站停时`。当前支持同一运营日内、正整数走行秒及非负整数停时。首站和后站允许任意已匹配原生站序，重复车次块需先独立处理。
- 默认保留原版单边时刻。以 `derive_arrivals_for_run: true` 从后站发车减去该站停时，推导后站到达。以 `endpoint_clocks: mirror_for_run` 另行补齐首站缺失的到达。回执标明推导项与原始走行秒，既有股道、实际时刻、接续和其它引用保留。

## 验证范围

原版依据为读取器 `0x695fa4`、时刻表行写入 `0x688b7c`、原生构造 `0x678b34` 和编码 `0x67b390`。本机 Demo 和 Training 未发现随附厂商输入件。样件依据原版规则构造，原生目标采用已有原版开行实绩的 IVT01 工程。已另存并独立冷读原版保留和运行补齐策略。运行补齐项目在 1 股道写入 10:23:49 到、10:27:01 发、192 秒站停，并通过静态运行预检。厂商原件兼容性、跨日/分秒变体和新项目原版运行待验收。
