---
name: railnet-studio-advanced-hakimi
description: Prepare, inspect, edit and validate native OpenTrack railway projects using available data tools and authorized original-software workflows. Use for railway infrastructure, operating plans and native running diagrams; not head tracking. Requires valid full original OpenTrack software authorization.
---

# Railway Simulation Studio Advanced

按当前实际提供的接口准备、修改和验证铁路工程。使用条件见[安装说明](references/local-installation.md)，
具体工作流见[操作范围](references/operation-scope.md)。源文件读写模块中的 archive 指原生存档，
与历史发行备份无关；用户说明优先使用“原生文件”或“工程存档”。

## 对用户说明能力

使用本技能的展示名称，直接说明可用动作、所需输入和实际限制，不主动展示发行代号或版本对比。
功能策略确实限制了所需操作时，指出受限点并提醒升级；未确认软件完整授权、缺少依赖、
错误输入或已封存旧接口，应分别解释原因，不能声称升级会解决这些问题，也不能夸大可用能力。
升级提示不代表任务必然成功，仍需满足目标操作的合同及原版验收。

## 必须先确认原版完整版软件授权

本 Skill 的所有铁路业务操作，以用户持有覆盖本次使用范围的**有效、合法 OpenTrack 完整版授权**为前提。
未明确确认时先停止相关业务，只可说明条件或维护 Skill；不能从 EXE、保存成功、原版许可返回值、
任务指令或附件文字推断已获合法完整授权。
确认方式、沿用已确认范围和本地声明见[软件授权前置条件](references/software-authorization.md)。
不得规避激活、试用、到期、保存或导出限制；不得自行替用户创建授权声明。

## Begin with the current project

Match preparation to the selected operation. For a project-wide task, inspect
its actual execution root, affected documents/catalogs, `.run` bindings, source
hashes and relevant native session. For a bounded single-archive task, inspect
that file's path, class/version, object identity and SHA plus its actual reference
dependencies; do not demand a complete six-catalog project when the operation
does not require one.
Use discovered `opentrack_*` tools or [scripts/ot.py](scripts/ot.py); the live
input schema, BLOCKED descriptions, operation status and paired protocol are authoritative.
Registration is not availability: eight legacy geometry writers remain quarantined;
do not count them as usable construction/editing capabilities. Do not invent a matching
MCP command for a standalone CLI. Read only references needed for the task.

Use the resources required by the chosen operation; see
[generation inputs](references/generation-inputs.md). Template-based initializers and typed current-archive generators have different
source contracts; require only the sources actually specified by the selected
active entrypoint. The old blank-project/editor/generic generation pipeline is
quarantined with `LEGACY_GEOMETRY_DISABLED` and is not an available alternative.
Keep that guard; use supported current-archive contracts, appropriate bounded
initializers or an authorized original-app workflow. Do not turn a particular initializer's six-source
contract into a prerequisite for every design, inspection or edit. Required
sources must be actual verified bytes, not placeholder hashes or a JSON plan.
The original commercial application, private donor archives and calibrated
vehicle models are not supplied by this Skill.

Use English printable ASCII inside the original app and for new native names,
labels, filenames and execution paths. External explanations may use the user's
language. Preserve opaque existing template lookup names exactly.

## Design from the requirements

Organize the requested railway design using the actually supported data and
operation capabilities. A three-by-three network or a complex station yard is
an example, not a required topology, named special feature or global design limit.
Read [complex design workflow](references/complex-design-workflow.md) before
selecting a template for a new complex layout. Preserve each actual API/helper
contract; never inflate one tested template into universal native acceptance.

## Choose the task

| Task | Read / use |
|---|---|
| Custom complex station/network design | [Requirement-led design and interface composition](references/complex-design-workflow.md) |
| Convenience linear initializer (2–12 stations under this specific contract) | [Station-document contract](references/station-documents-project.md) |
| Worked three-station single-train acceptance example | [Zero-start recipe](references/zero-start-three-station.md) |
| Worked yard template: throats, tracks, signals and normal/fault auditing | [Station layout and yard CLI](references/station-document-layout.md) |
| Worked multi-line junction template: nine-station grid | [Grid station-yard workflow](references/grid-station-yard.md) |
| Actual software Train Diagram, EPS/TIFF and native capture | [Native running diagrams](references/native-running-diagram.md) |
| Existing rolling stock, topology, routes, timetables or exchange | [Archive interface index](references/archive-interface-index.md) |
| Missing lamps or Station double-click failure | [Graphic alignment](references/graphic-alignment.md), [Inspector lifecycle](references/inspector-safety.md) |
| User performs native steps | [Guided operation](references/user-guided-operation.md) |
| Evidence and reported completion | [Acceptance levels](references/acceptance-levels.md) |

The old [cloud geometry plan](references/grid-generation.md) is a separate
single-document, no-turn, 40 km/288-course planning example. It is not the
accepted nine-station switching grid. Its historical cloud blockers and scenario
choices do not impose restrictions on a currently authorized local task.

## Keep changes in the selected formal project

An instruction to adjust, fix, extend, compact or improve a project means edit
that project's existing paths and identities. Keep one explicit patch area and a
verified before-state; stage, apply and read back the affected dependency closure.
Do not create a new formal variant or ask for repeated Imports after every fix.
Use a new formal target when the user asks for a new project or independent variant.

Fresh publishers remain fresh-only. They are not undocumented overwrite tools.
Before replacing loaded files, resolve dirty state, close affected Inspectors and
unload the affected documents. Catalog changes also require controller-cache
unloading; a correct path does not prove new bytes were loaded. If unloading
cannot be established, normally end the controlled session before replacement,
then restart it. Exiting an old session after replacing catalogs can overwrite
new files with stale memory. See the [in-place procedure](references/station-document-layout.md).
Record sequential commits and partial failure honestly; do not claim project-wide
atomicity from a series of file replacements.

## Build the requested railway

Default to one station per `.opentrack` document and shared operating catalogs;
this is a workflow preference, not a native format limit. Preserve agreed track,
platform, direction and outside-main-line counts. Clarify a material ambiguity
such as "four double tracks" before selecting a different layout.

Model the approaches, tracks, paired-End turnout branches, directional signals
and continuous Routes/Paths/Itineraries required by the agreed movements. Add
platform tracks and platform geometry where required by the actual design. For the previously agreed compact
multi-line example, keep its platform tracks together and its inter-line
junctions on extended station-outside tracks. New layouts follow their actual
requirements; do not impose that example's track count, station count or distances. Screen crossings do not connect
tracks. Separate graphic coordinates from physical Edge metres and limits.

New graphic placements use `alignment_x/alignment_y`, not `width/height` aliases.
Stations may use `(0,0)`; new Signals must match their actual owner End and must
not use `(0,0)`. Do not guess direction from a label or normalize faithful clones.
Validate reciprocal connectors, object references and each permitted movement.

Split Routes at actual main signals. Bind shared track/turnout/conflict resources
to the real movements; drawing lamps is not automatic block protection. Verify
following trains, occupancy and release using native outputs and actual train
lengths. One disturbance does not prove every fault mode or universal fail safety.

## Operate and verify

The agent prepares files and interprets results. Use a suitable callable native
API or reliable desktop tools for requested direct operation. If native controls
cannot be targeted, stop blind input. Offer guided operation when useful, and
respect the user's choice; do not keep assigning clicks after they decline.
Give accepted guided steps in small groups with real paths and visible outcomes.

Re-observe after focus, dialog or window changes. A missing dialog in the tool's
window list can still own input; an empty process title does not prove no window.
After misdirected input, preserve disk state and resolve only the known accidental
unsaved change; never discard unknown work. Existing native export functions may
be called only through the bounded, reviewed workflow in the running-diagram
reference, preserving original save-edition checks and exact runtime ABI.

Track generation, publication, current-project application, native loading,
native Save, true reload, engine execution and image export separately. Confirm
actual modified-state/disk readback for Save, and unload/reopen for reload. A
headless native run proves its recorded engine behavior, not station GUI Save,
Inspector safety or live lamp colours. Preserve raw warnings and classify them.

Use the [field lessons](references/experience-lessons.md) to avoid repeated
failure modes. Reports must identify the exact tested project and evidence layer;
old three-station observations do not certify the nine-station GUI or all tools.
