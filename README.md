# Opentrack-raliway--skills

面向 OpenTrack 1.7 的铁路工程 Skill，帮助 AI 根据实际需求准备、检查和修改原生工程，并协助完成原版加载、保存、重载、仿真和运行图导出等验证。

A railway engineering Skill for OpenTrack 1.7. It helps an AI prepare, inspect, and modify native projects according to actual requirements, and assists with validation of native loading, saving, reloading, simulation, and train diagram export.

**使用铁路业务功能前，必须持有覆盖使用者、设备及用途的有效、合法的原版 OpenTrack 完整软件授权，并获得当前任务和数据的使用授权。** 本仓库不包含 OpenTrack 商业软件、运行库、用户工程、私人模板或许可证材料。授权确认方法见[软件授权说明](references/software-authorization.md)。

**Before using railway functions, you must hold a valid, legal full licence for the original OpenTrack software covering the user, device, and intended purpose, and have authorization for the specific task and data.** This repository does not include the commercial OpenTrack application, runtime libraries, user projects, private templates, or licence materials. See [software authorization](references/software-authorization.md) for the confirmation process.

## 可以做什么 / Capabilities

- 按已提供接口检查和处理线路拓扑、进路、车辆、时刻表及相关原生数据。
- 在各自输入合同范围内使用工程初始化、数据生成及文件发布工具；结合原版软件验证工程。
- 在实际轨迹和对应原生接口可用的条件下，协助生成软件内的列车运行图及导出结果。
- 直接操作可用工具；需要用户协助时，按用户意愿提供分步指导。

- Inspect and process infrastructure topology, routes, rolling stock, timetables, and related native data through the provided interfaces.
- Use project initialization, data generation, and file publication tools within their respective input contracts; validate projects with the original application.
- Assist with producing and exporting train diagrams in the software when actual trajectories and the relevant native interfaces are available.
- Operate available tools directly; when user assistance is needed, provide step-by-step guidance according to the user's preference.

三站示例、复杂站场和多线交汇网格是示例，不是所有工程必须采用的布局。各操作的可用性取决于接口、输入资源、授权及运行环境；详见[操作范围](references/operation-scope.md)。

The three-station example, complex yards, and multi-line junction grids are examples, not required layouts for every project. Availability depends on the interface, input resources, authorization, and runtime environment; see [operation scope](references/operation-scope.md).

## 安装与使用 / Installation and usage

需要 Python **3.13.x**。将本仓库克隆到名为 `railnet-studio-advanced-hakimi` 的目录，并按所用 AI 工具的方式安装 Skill。Windows PowerShell 示例：

Python **3.13.x** is required. Clone this repository into a directory named `railnet-studio-advanced-hakimi`, then install the Skill according to your AI tool's instructions. Example for Windows PowerShell:

```powershell
git clone https://github.com/anothercoder-code/Opentrack-raliway--skills.git railnet-studio-advanced-hakimi
cd railnet-studio-advanced-hakimi
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/OTAI/requirements.txt
```

将下例中的 `D:/RailWork` 替换为实际的数据根目录。以下两条是工具发现和能力查询，不需要读取原生工程：

Replace `D:/RailWork` below with the actual data root. These commands discover tools and query capabilities without reading a native project:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B scripts/ot.py --root D:/RailWork tools
.\.venv\Scripts\python.exe -X utf8 -B scripts/ot.py --root D:/RailWork call opentrack_capabilities --json '{}'
```

`--root` 或 `OTAI_DATA_ROOT` 指向实际数据根；`OTAI_ROOT` 如需设置，则指向包含 `OTAI/server.py` 的配套后端父目录。详细步骤见[本地安装](references/local-installation.md)。

`--root` or `OTAI_DATA_ROOT` identifies the actual data root. If set, `OTAI_ROOT` identifies the paired backend's parent directory containing `OTAI/server.py`. See [local installation](references/local-installation.md) for details.

开始铁路业务前，按[授权流程](references/software-authorization.md)确认许可与适用范围。原版软件中新增的名称、文本、文件名及执行路径使用可打印英文 ASCII；现有模板中的查找名称应保持原样。

Before starting railway work, follow the [authorization process](references/software-authorization.md) to confirm the licence and its scope. Use printable English ASCII for new names, text, filenames, and execution paths in the original application; preserve existing template lookup names exactly.

## 使用边界与验收 / Scope and validation

工具列表中的登记项不代表都可执行或与原版功能等价。部分旧几何写入接口已封存；应使用实际支持的接口和输入合同，不绕过限制。新建发布器只接受新目标，修改现有工程时应保留其路径并核对写回结果。

Registration in the tool list does not mean every entry is usable or equivalent to an original application feature. Some legacy geometry-writing interfaces are quarantined; use the supported interfaces and their input contracts without bypassing those restrictions. Fresh-project publishers only accept new targets; when modifying an existing project, preserve its paths and verify written results.

预览、文件发布、原版加载、原版保存、真正重载、仿真运行和原生运行图导出是不同的验收步骤。历史示例只能证明对应案例，不能替代当前工程的验证；具体证据要求见[验收层次](references/acceptance-levels.md)。

Preview, file publication, native loading, native saving, true reloading, simulation, and native train diagram export are separate validation steps. Historical examples only establish results for those cases and do not replace validation of the current project; see [validation levels](references/acceptance-levels.md).

## 目录 / Directory

- [SKILL.md](SKILL.md)：Skill 入口、工作方式和关键约束。
- [references/](references/)：操作合同、授权和验收说明。
- [scripts/](scripts/)：CLI 与专项工作流入口。
- [backend/OTAI/](backend/OTAI/)：配套后端和依赖清单。
- [assets/](assets/)：示例数据及辅助资源。
- [native-inspector-guard/](native-inspector-guard/)：可选 Inspector 组件的源码和说明；不代表已通过原版验收。

- [SKILL.md](SKILL.md): Skill entry point, workflow, and key constraints.
- [references/](references/): Operation contracts, authorization, and validation guidance.
- [scripts/](scripts/): CLI and specialized workflow entry points.
- [backend/OTAI/](backend/OTAI/): Paired backend and dependency list.
- [assets/](assets/): Example data and supporting resources.
- [native-inspector-guard/](native-inspector-guard/): Source and documentation for the optional Inspector component; its inclusion does not establish native acceptance.

## 许可证 / Licence

本仓库的许可证见 [LICENSE](LICENSE)。原版 OpenTrack 软件授权需单独取得，不由本仓库授予。

See [LICENSE](LICENSE) for this repository's licence. A licence for the original OpenTrack software must be obtained separately and is not granted by this repository.
