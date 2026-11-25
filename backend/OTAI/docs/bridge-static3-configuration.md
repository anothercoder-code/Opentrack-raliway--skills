> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# static3 配套后端与 Skill 桥接修复

## 修复原因

旧 Skill 未设置 OTAI_ROOT 时默认寻找 D:/opentrack/OTAI/server.py。该路径可能是旧版0.30.0.dev0，导致新版工具 UNKNOWN_TOOL，并把旧版运行错误归属新版。本版移除该默认，不再静默调用旧目录。

## 两种交付方式

1. **完整总包**：`MCP/OTAI/skills/opentrack-rail/scripts/ot.py` 精确定位同包 `MCP/OTAI/server.py`。
2. **独立 Skill.zip**：`opentrack-rail` 中附 `backend/OTAI/` 配套源码，桥接精确使用该后端。仍需要 Python 3.12 及依赖，不含原版程序/许可证/六类用户模板。

显式设置 `OTAI_ROOT` 时优先使用该设置；它必须是**包含 OTAI 文件夹的父目录**，不是 server.py，也不是 OTAI 文件夹本身。设置错或指向旧版就报错，不回退去找其他安装。

## Windows PowerShell 例子

以下均为需替换的示例路径；助手未访问这些本地路径。

完整总包解压到 `C:\Work\OpenTrack-Skill-MCP-static3`：

```powershell
$env:OTAI_ROOT = 'C:\Work\OpenTrack-Skill-MCP-static3\MCP'
$env:OTAI_DATA_ROOT = 'C:\Work\AuthorizedRailData'
python -B "$env:OTAI_ROOT\OTAI\skills\opentrack-rail\scripts\ot.py" tools
```

独立 Skill 解压到 `C:\Skills\opentrack-rail`，如果之前设置过指向旧版的变量，应先明确移除旧值（或改成正确的新backend父目录）：

```powershell
Remove-Item Env:OTAI_ROOT -ErrorAction SilentlyContinue
$env:OTAI_DATA_ROOT = 'C:\Work\AuthorizedRailData'
python -m pip install -r 'C:\Skills\opentrack-rail\backend\OTAI\requirements-server-tested.txt'
python -B 'C:\Skills\opentrack-rail\scripts\ot.py' tools
```

也可显式设置 `$env:OTAI_ROOT = 'C:\Skills\opentrack-rail\backend'`。

## 检查失败如何处理

- 缺配套后端：重新解压完整 Skill.zip，或设置正确的 OTAI_ROOT；不是只复制 ot.py。
- 版本不匹配：当前桥接要求 `0.31.0-static3`，使用同一交付包的后端。不要把0.30目录重命名或编辑版本号伪装兼容。
- 缺依赖：使用运行ot.py的同一Python环境安装该后端固定依赖。
- 缺工具：工具发现必须含当前关键能力，所请求工具也必须在所选profile存在。错误会指出工具与所需配置，不静默调用旧版。
- `OTAI_DATA_ROOT` 只是授权数据位置，不用于选择后端；请求的 `--root` 明确参数优先。

桥接版本/工具检查不是签名认证，不证明原版兼容。用户报告中0.30样例原版成功仍只属于0.30；0.31的新档案导出、Windows原版读取/运行与警告处理仍未验收。GUI显示结束与日志有无End属于不同证据，不擅自改写结果completed状态。

> Windows范围：本版解决桥接配置、版本/依赖诊断及UTF-8传输；未做Windows实测。标准Windows Python缺少本工具安全存档读取所需dir_fd/O_NOFOLLOW能力，因此文件读取/预览及保存会明确拒绝，不提供不安全fallback。工具发现与纯内存数据处理不等于Windows存档操作已兼容。详见《平台兼容范围.md》。

这些PowerShell命令演示桥接及工具发现，不是Windows文件读写成功的声明；不应把目录配置正确解释为可安全读取该电脑上的存档。
