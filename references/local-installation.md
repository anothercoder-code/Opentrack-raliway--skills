# 本地安装

将完整的 `railnet-studio-advanced-hakimi` 目录放入 Codex 的 skills 目录。更新前保留可恢复前态，
不覆盖用户未纳入本次更新的本地修改。入口见[SKILL.md](../SKILL.md)，
当前可用范围见[操作范围](operation-scope.md)。

使用Python **3.13.x**，在同一解释器安装 `backend/OTAI/requirements.txt` 的固定依赖；
配套后端协议为 `0.33.1-zeroaccept1`，这是兼容性标识而不是原版软件版本。
CLI自动选择包内 `backend/OTAI`。`--root` 或 `OTAI_DATA_ROOT` 是实际数据根；
`OTAI_ROOT`若显式设置，是包含 `OTAI/server.py` 的后端父目录，不是工程目录。
版本或必需能力契约不匹配时应报错，不能回退另一安装。所有占位符应换成真实授权路径。

```text
python -X utf8 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> tools
python -X utf8 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_capabilities --json "{}"
python -X utf8 -B <SKILL>/backend/OTAI/server.py --root <DATA_ROOT> stdio
```

原版英文铁路OpenTrack **1.7**、合法原生模板及车辆资料另行提供。包内不含商业EXE、
OpenStep运行库、私人供体、用户工程或许可证材料。安装Skill不授予许可；业务前必须按
[软件授权](software-authorization.md)确认有效完整授权。未确认时只做允许的元数据/帮助或Skill维护。

新工程先按所选接口核对真实资源和SHA、执行根及文档绑定。新原版名称、路径和文本采用
可打印英文ASCII。fresh-only发布器不覆盖既有项目；现有工程修改保留原路径并写后回读。
移动目录不能自动重绑原生固定路径。Windows读写只在对应操作报告支持的本地固定NTFS条件下执行。

可选Inspector组件保留源码及静态证据，不代表已加载或通过原版验收。原生绘图是单独的
原版工作流，需精确指纹、ABI、主线程和原版保存许可检查，见[原生运行图](native-running-diagram.md)。
资源不全时说明具体缺项，只继续其输入已满足的授权工作；不能伪造哈希、输出或原版验收。
