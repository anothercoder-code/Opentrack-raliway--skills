# Opentrack-raliway--skills

原版 OpenTrack 是铁路仿真求解器。本 Skill 是面向 AI 的工具箱和编排契约，帮助 AI 检查工程、选择可复用工具、编译依赖计划、发布有边界的候选并评价各层证据。

The original OpenTrack application remains the railway solver. This Skill is the AI-facing toolkit and orchestration contract for inspecting projects, selecting reusable tools, compiling dependency plans, publishing bounded candidates, and evaluating evidence.

**使用铁路业务功能前，必须持有覆盖使用者、设备及用途的有效、合法的原版 OpenTrack 完整软件授权，并获得当前任务和数据的使用授权。** 本仓库不包含 OpenTrack 商业软件、运行库、用户工程、私人模板或许可证材料。授权确认方法见[软件授权说明](references/software-authorization.md)。

**Before using railway functions, you must hold a valid, legal full licence for the original OpenTrack software covering the user, device, and intended purpose, and have authorization for the specific task and data.** This repository does not include the commercial OpenTrack application, runtime libraries, user projects, private templates, or licence materials. See [software authorization](references/software-authorization.md) for the confirmation process.

## 可以做什么 / Capabilities

- 按已提供接口检查和处理线路拓扑、进路、车辆、时刻表及相关原生数据。
- 用语义能力目录把需求整理为有依赖、输入哈希和证据边界的执行计划。
- 在各自输入合同范围内使用工程初始化、数据生成及文件发布工具；结合原版软件验证工程。
- 在实际轨迹和对应原生接口可用的条件下，协助生成软件内的列车运行图及导出结果。
- 直接操作可用工具；需要用户协助时，按用户意愿提供分步指导。
- 通过多个通用工具族的依赖有序调用完成复杂任务，而不要求为每个原版函数制作一一对应的求解器。

- Inspect and process infrastructure topology, routes, rolling stock, timetables, and related native data through the provided interfaces.
- Turn a railway requirement into a dependency-ordered plan through the semantic capability catalog.
- Use project initialization, data generation, and file publication tools within their respective input contracts; validate projects with the original application.
- Assist with producing and exporting train diagrams in the software when actual trajectories and the relevant native interfaces are available.
- Operate available tools directly; when user assistance is needed, provide step-by-step guidance according to the user's preference.
- Complete complex work by composing general tool families in dependency order instead of requiring a one-to-one solver for every original function.

三站示例、复杂站场和多线交汇网格是示例，不是所有工程必须采用的布局。各操作的可用性取决于接口、输入资源、授权及运行环境；详见[操作范围](references/operation-scope.md)。

The three-station example, complex yards, and multi-line junction grids are examples, not required layouts for every project. Availability depends on the interface, input resources, authorization, and runtime environment; see [operation scope](references/operation-scope.md).

## 安装与使用 / Installation and usage

需要 Python **3.13.x**。开发 checkout 可以使用目录名 `railnet-studio-advanced-hakimi`，但 Skill 声明名和安装目录都是 **`opentrack-network-rail`**。Windows PowerShell 示例：

Python **3.13.x** is required. The development checkout may use the directory name `railnet-studio-advanced-hakimi`, but both the declared Skill name and installed directory are **`opentrack-network-rail`**. Example for Windows PowerShell:

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
.\.venv\Scripts\python.exe -X utf8 -B scripts/ot.py --root D:/RailWork --profile ai tools
```

`--root` 或 `OTAI_DATA_ROOT` 指向实际数据根；`OTAI_ROOT` 如需设置，则指向包含 `OTAI/server.py` 的配套后端父目录。详细步骤见[本地安装](references/local-installation.md)。

`--root` or `OTAI_DATA_ROOT` identifies the actual data root. If set, `OTAI_ROOT` identifies the paired backend's parent directory containing `OTAI/server.py`. See [local installation](references/local-installation.md) for details.

Use the `ai` profile as the compact semantic entry point. Compile the request,
then call `opentrack_publish_railway_plan` once for each hash-bound action and
reviewed writer chosen by the plan. The gateway loads the hidden writer's live
Pydantic schema, forces its supported preview switch to publication and accepts
only a saved receipt with either a completed commit or a verified atomic
no-replace copy whose source stayed unchanged. The `ai` profile currently
exposes 21 entrypoints, including direct planning, inspection and bound native
evidence readers plus the bridge. Switch to `generation` or `all`
for diagnostics of a named implementation tool. Those profiles do not expose
the semantic publication gateway as an AI entry point. Existing references that
name the `generation` profile remain valid for detailed inspection.

Skill 的发现目录名必须与 frontmatter 的 `name: opentrack-network-rail` 一致。安装、校验和回滚步骤见[本地安装](references/local-installation.md)；不要直接把带开发缓存的 checkout 当作发行安装。

The Skill discovery directory must match the frontmatter name
`opentrack-network-rail`. See [local installation](references/local-installation.md)
for checksum verification, installation and rollback. Do not install the
development checkout with its caches.

AI 默认工作模式是先理解需求，再检查实际工程、选择语义能力、编译依赖计划、预览或暂存并逐项验证。详见 [需求正规形式](references/requirement-normal-form.md)、[能力组合](references/capability-and-composition-model.md) 和 [结果证据矩阵](references/outcome-verification.md)。

The AI workflow normalizes the requirement, inspects the actual project,
selects semantic capabilities, compiles a dependency plan, previews or stages,
then verifies each outcome. See [requirement normal form](references/requirement-normal-form.md),
[capability composition](references/capability-and-composition-model.md), and
[outcome verification](references/outcome-verification.md).

开始铁路业务前，按[授权流程](references/software-authorization.md)确认许可与适用范围。原版软件中新增的名称、文本、文件名及执行路径使用可打印英文 ASCII；现有模板中的查找名称应保持原样。

Before starting railway work, follow the [authorization process](references/software-authorization.md) to confirm the licence and its scope. Use printable English ASCII for new names, text, filenames, and execution paths in the original application; preserve existing template lookup names exactly.

## 使用边界与验收 / Scope and validation

工具列表中的登记项不代表都可执行，也不代表已形成可编排的任务路径。当前任务族使用 `supported`、`composed`、`partial`、`unreachable` 和 `requires_native_app` 描述。部分旧几何写入接口已封存；应使用实际支持的接口和输入合同，不绕过限制。新建发布器只接受新目标，修改现有工程时应保留其路径并核对写回结果。

Registration in the tool list does not establish a usable orchestration path. Current task families use `supported`, `composed`, `partial`, `unreachable`, and `requires_native_app`. Some legacy geometry-writing interfaces are quarantined; use the supported interfaces and their input contracts without bypassing those restrictions. Fresh-project publishers only accept new targets; when modifying an existing project, preserve its paths and verify written results.

机器可读的当前状态见 [AI toolbox status](references/coverage/ai-toolbox-status.json)，任务族覆盖与未实现能力见 [advanced original-function gaps](references/advanced-original-function-gaps.md)。历史 176 项清单继续作为来源库存，不作为当前发行完成率。

See [AI toolbox status](references/coverage/ai-toolbox-status.json) for the
machine-readable current state and [advanced original-function gaps](references/advanced-original-function-gaps.md) for task-family coverage and remaining gaps. The historical 176-item inventory remains source evidence and is not the current release-completion denominator.

预览、文件发布、原版加载、原版保存、真正重载、仿真运行和原生运行图导出是不同的验收步骤。历史示例只能证明对应案例，不能替代当前工程的验证；具体证据要求见[验收层次](references/acceptance-levels.md)。

Preview, file publication, native loading, native saving, true reloading, simulation, and native train diagram export are separate validation steps. Historical examples only establish results for those cases and do not replace validation of the current project; see [validation levels](references/acceptance-levels.md).

## 目录 / Directory

- [SKILL.md](SKILL.md)：Skill 入口、工作方式和关键约束。
- [references/](references/)：操作合同、授权和验收说明。
- [scripts/](scripts/)：CLI 与专项工作流入口。
- [backend/OTAI/](backend/OTAI/)：配套后端和依赖清单。
- [assets/](assets/)：示例数据及辅助资源。
- [native-inspector-guard/](native-inspector-guard/)：可选 Inspector 组件源码；先用 `build.cmd` 生成二进制，再运行离线 `test.cmd`；不代表已通过原版验收。

- [SKILL.md](SKILL.md): Skill entry point, workflow, and key constraints.
- [references/](references/): Operation contracts, authorization, and validation guidance.
- [scripts/](scripts/): CLI and specialized workflow entry points.
- [backend/OTAI/](backend/OTAI/): Paired backend and dependency list.
- [assets/](assets/): Example data and supporting resources.
- [native-inspector-guard/](native-inspector-guard/): Source for the optional Inspector component; build with `build.cmd` before running offline `test.cmd`. Its inclusion does not establish native acceptance.

## 许可证 / Licence

本仓库的许可证见 [LICENSE](LICENSE)。原版 OpenTrack 软件授权需单独取得，不由本仓库授予。

See [LICENSE](LICENSE) for this repository's licence. A licence for the original OpenTrack software must be obtained separately and is not granted by this repository.
