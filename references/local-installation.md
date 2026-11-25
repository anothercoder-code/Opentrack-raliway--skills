# Portable paired installation

This distribution is Full **full1**, dated 2026-11-23. Basic **basic2** is a separate distribution.
Both use paired backend protocol **0.33.1-zeroaccept1**, Python **3.13.x** and the
pinned dependencies in their packaged `backend/OTAI/requirements.txt`.
This Full archive is named `opentrack-network-rail`; follow the selected Basic archive's own folder
name and entrypoint. Read [edition scope](editions.md) before selecting a package.

Extract the archive, then install its single Skill folder in the user's Codex
skills directory. Preserve a recoverable before-state and local modifications
when updating an existing installation. The old `basic1` archive is historical;
its contents and scope differ from `basic2` and it need not be overwritten.
Choose one active edition for ordinary discovery unless there is a deliberate
reason to keep both. Installation is not proof of native acceptance.

The standalone CLI uses `backend/OTAI`. The co-packaged
`OTAI/skills/opentrack-rail` layout uses its surrounding paired backend instead.
`OTAI_ROOT`, if explicitly set, is the parent containing `OTAI/server.py`;
`OTAI_DATA_ROOT` is the authorized data root. Individual profile CLIs may take
`--root`; inspect their actual `--help`. There is no fallback to another installed
backend when versions, layouts or edition capabilities do not match.

The original English railway OpenTrack **1.7**, proprietary native templates and
vehicle data must be supplied separately with permission. Neither edition ships
the original commercial EXE, OpenStep runtime, private donor archives, current
user preferences, screenshots or raw private project evidence. Own helper source
or a native bridge is not a replacement simulator and must preserve original
license/edition checks. No Skill command starts a native helper just by being read.

Before a new project, inspect and hash actual donor resources, declare the true
execution root and native document paths, and use the selected profile's complete
input contract. New native names, labels, paths and entered values use printable
English ASCII. A fresh publisher requires a new target; existing projects use
reviewed in-place updates. Moving an extracted project does not automatically
rewrite its internal fixed-root bindings.

Full's optional Inspector guard retains static/offline evidence only;
`runtime_verified=false`. Its installed files do not establish that the original
process loaded it. Native diagram export is a distinct, bounded original-runtime
workflow with its own fingerprint, ABI, main-thread and saving-edition guards;
read [native running diagrams](native-running-diagram.md) before any invocation.
Basic excludes that native bridge and the advanced yard/grid entrypoints.

After the software-authorization prerequisite has been met, if other dependencies
or native resources are absent, finish only the inspection/preparation whose own
inputs are available and state the exact missing prerequisite. Before software
authorization, restrict work to the allowed metadata/help or Skill maintenance. Do not fake
hashes, silently use old local installations or relabel preview output as a saved
project. Full workflow routing starts in [SKILL.md](../SKILL.md).

## 软件授权

安装 Skill 不授予 OpenTrack 许可。开始任何铁路业务前，先按[完整版软件授权](software-authorization.md)确认并记录用户的有效完整授权；没有确认不能继续生成、读改工程、仿真、导出或指导同等操作。
