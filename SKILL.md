---
name: opentrack-network-rail
description: Prepare, inspect and edit OpenTrack railway projects using available network, station, operations and native diagram workflows; requires authorized original OpenTrack software.
---

# OpenTrack Network Rail

Maintained distribution, 2026-11-25. Paired backend
**0.33.1-zeroaccept1-v4** uses Python **3.13.x**. This is the single maintained
edition, not a promise of parity with every original OpenTrack function or a
railway safety certification. Read [installation](references/local-installation.md)
for the runtime, external native resources and paired backend layout.

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
For an empty current-format project, use `opentrack_initialize_empty_current_project`
with a saved worksheet header and the verified native shape archive.
The original commercial application, private donor archives and calibrated
vehicle models are not supplied by this Skill.

Use English printable ASCII inside the original app and for new native names,
labels, filenames and execution paths. External explanations may use the user's
language. Preserve opaque existing template lookup names exactly.

## Design from the requirements

Work from the railway that the user describes. Understand the actual operating
need, derive the required topology, facilities, movements and service plan, then
use the safest available combination of semantic native operations, validated
primitives and original-application workflows. Treat examples and generators as
starting material. Adapt their structure when the requirement differs, while
retaining every real format, reference and validation constraint.

For a custom layout or an unfamiliar real station, read
[complex design workflow](references/complex-design-workflow.md) and
[reality station template](references/reality-station-template.md). Inspect
existing examples and saved data for patterns before inventing a format. Do not
require a separate one-to-one solver for each original function, nor model the
railway as a fixed set of named templates. Verify the resulting semantics and
references, and state any unsupported aspect plainly.

## Choose the task

| Task | Read / use |
|---|---|
| Custom complex station/network design | [Requirement-led design and interface composition](references/complex-design-workflow.md) |
| Start a new native railway project with empty worksheets and catalogues | [Empty current-format project](references/generation-inputs.md#empty-current-format-project) |
| Stage native changes with persistent undo, redo and fresh revision publication | [Native editor sessions](references/native-editor.md) |
| Apply an explicitly reviewed worksheet edit in place and keep a recovery journal | [Reviewed worksheet application and rollback](references/reviewed-worksheet-rollback.md) |
| Apply several reviewed native project files in place and recover them from one journal | [Reviewed project files and rollback](references/reviewed-project-file-rollback.md) |
| Publish a runnable candidate from a reviewed station edit, with optional OTD rules and instrument recording | [Prepare a station run candidate](references/complex-design-workflow.md#从审核过的改线另存开行候选) |
| Reconstruct a requested real station and operate through it | [Reality station workflow](references/reality-station-template.md), [reference platform verification](references/reference-platform-workflow.md) |
| Collect real-station evidence and choose the exact platform-request template | [Reality station template and capability boundary](references/reality-station-template.md) |
| Relocate a station reference point while retaining booked stops and native schedules | [Station reference migration](references/native-station-reference.md) |
| Dry-review a simulation queue, run isolated original scenarios, or inspect an original interactive job | [Native simulation jobs](references/native-simulation-jobs.md) |
| Write the original Defined delay setting and per-visit mean delay values | [Native Defined delay](references/native-simulation-jobs.md) |
| Import a selected native station catalog or export original TSV, XML, or Google Earth KML | [Native station exchange](references/native-station-exchange.md) |
| Export original worksheet, Route, Path and Itinerary descriptions | [Native topology descriptions](references/native-topology-description.md) |
| Exchange RailML infrastructure or rebuild a multi-worksheet corridor or branched station | [Native infrastructure RailML](references/native-infrastructure-railml.md) |
| Import an original IVT or Siemens track table into an editable OpenTrack worksheet | [Native track table import](references/native-infrastructure-ivt.md) |
| Send typed commands to an isolated original OTD simulation, or record local OTD callbacks | [Native OTD control](references/native-otd-live-control.md) |
| Save original OTD dispatching-rule XML for reviewed native Routes | [Native OTD dispatching rules](references/dispatching-rules-otd.md) |
| Verify actual native services and read occupancy, incident, energy and plot data | [Native run evaluation](references/native-run-evaluation.md) |
| Edit power-supply areas, Maglev propulsion segments and groups, and measuring instruments, and read native monitoring output | [Native monitoring](references/native-monitoring.md) |
| Find saved worksheet objects and flag signed kilometre-point conflicts | [Native worksheet Finder](references/native-worksheet-query.md) |
| Create and edit native worksheet Plots from numeric series or original occupation records | [Native worksheet plots](references/native-worksheet-plots.md) |
| Edit native worksheet paper, margins, orientation and print pagination | [Native worksheet Page Layout](references/native-page-layout.md) |
| Embed an external PNG, TIFF or EPS in an editable native worksheet Picture | [Native worksheet pictures](references/native-worksheet-pictures.md) |
| Import or edit rich labels, create native signal-name labels, and manage temporary labels | [Native worksheet labels](references/native-worksheet-rich-labels.md) |
| Inspect or edit native Edge occupation monitor groups | [Native occupation groups](references/native-occupation-groups.md) |
| Verify sectional release, simultaneous section occupation and exclusive authority handover in original output | [Native interlocking effects](references/native-interlocking.md) |
| Verify a train's passage through document boundaries and station throat occupation in original output | [Native throat passage](references/native-throat-passage.md) |
| Verify a cross-document Route's speed zone and release locations in original output | [Native Route protection](references/native-route-protection.md) |
| Configure speed-restricted or timed-stop occupied-platform entry on an existing Route | [Native occupied entry](references/native-interlocking.md#写入定时停车接车) |
| Configure ordered platform alternatives and verify original dispatch during occupancy | [Native platform choice](references/native-platform-choice.md) |
| Move existing Courses, joins or splits to a reviewed station or platform and retain planned times | [Native Course platform rebind](references/native-course-platform-rebind.md) |
| Compare original two-train runs, sweep positive integer headways, or locate an observed origin or shared fixed-block restriction | [Native headway comparison](references/native-headway.md) |
| Measure arrivals, departures, through trains and busier windows from original station output | [Native station throughput](references/native-headway.md) |
| Aggregate punctuality and occupation over sealed original delay scenarios | [Native delay-batch statistics](references/native-delay-batch.md) |
| Transfer native Preferences options or author document sets | [Native Preferences import/export](references/native-preferences.md) |
| Inspect or edit native vertices, station reference points, stopping markers, track edges, safety groups and kilometre markers | [Saved geometry editing](references/saved-geometry-editing.md) |
| Reroute existing junction movements that share track and retire unused rails | [Saved junction rerouting](references/saved-geometry-editing.md#共用轨段的咽喉改造) |
| Edit Courses and dependent records or import selected native schedules, formations, Engines and Categories | [Operating plan editing](references/current-operating-plan-edit.md) |
| Import or export RailML 1.00 timetable records | [Native RailML 1.00 timetable exchange](references/native-timetable-railml-100.md) |
| Round-trip RailML 2.2 clocks and selected native timetable connections | [RailML timetable exchange](references/railml-timetable-export.md) |
| Import a Falko text timetable against existing native Courses and stations | [Native Falko timetable](references/native-falko-timetable.md) |
| Import a tabular FBS timetable against existing native Courses and stations | [Native FBS timetable](references/native-fbs-timetable.md) |
| Import a version-one Protim/PIF timetable against existing native Courses | [Native Protim/PIF timetable](references/native-protim-pif-timetable.md) |
| Import a SIMU VII timetable against existing native Courses | [Native SIMU VII timetable](references/native-simu-vii-timetable.md) |
| Write kilometre and route-relative events or exchange original incident TSV | [Native incident exchange](references/native-disruption-exchange.md) |
| Compare sealed original incident and control runs against each saved event | [Native incident effects](references/native-disruption-exchange.md) |
| Convenience linear initializer (2–12 stations under this specific contract) | [Station-document contract](references/station-documents-project.md) |
| Worked three-station single-train acceptance example | [Zero-start recipe](references/zero-start-three-station.md) |
| Worked yard template: throats, tracks, signals and normal/fault auditing | [Station layout and yard CLI](references/station-document-layout.md) |
| Worked multi-line junction template: nine-station grid | [Grid station-yard workflow](references/grid-station-yard.md) |
| Actual software Train Diagram, EPS/TIFF and native capture | [Native running diagrams](references/native-running-diagram.md) |
| Edit saved movements and approach settings, or import selected native Itineraries into existing trackwork | [Native movement editing](references/native-movement-editing.md) |
| Search and save Paths from exit signals through existing Routes | [Native exit-to-exit pathfinding](references/native-exit-pathfinding.md) |
| Save native candidates, catalog changes and RailML timetable clocks on Windows | [Native writing](references/native-writing.md) |
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

Understand and preserve the requested track, platform, direction and
outside-main-line arrangement. Start from the project's existing document and
catalog organization when editing it. For a new project, choose a clear
document partition that supports the requested movements; one station per
`.opentrack` document with shared operating catalogs is a useful default.
Clarify a material ambiguity such as "four double tracks" before selecting a
different layout.

Model the approaches, tracks, turnout branches, crossings, directional signals
and continuous Routes/Paths/Itineraries required by the agreed movements. Derive
the necessary object graph from the operating requirements, using supported
saved-data primitives or original controls as appropriate. For a real station,
cover every required platform face, throat movement, stop and route before
claiming the station is modelled. Screen crossings do not connect tracks.
Separate graphic coordinates from physical Edge metres and limits.

New graphic placements use `alignment_x/alignment_y`, not `width/height` aliases.
Stations may use `(0,0)`; new Signals must match their actual owner End and must
not use `(0,0)`. Do not guess direction from a label or normalize faithful
clones. Validate reciprocal connectors, object references and each permitted
movement. When the existing lower-level primitives do not cover a requested
topology, compose them into a bounded semantic workflow or use the original
application, rather than adding a narrowly hard-coded solution per function.

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

Historical files labelled current are current only for their recorded version/case;
read [evidence record scope](references/evidence-record-scope.md) before reusing
old summaries as a present capability or acceptance claim.

Track generation, publication, current-project application, native loading,
native Save, true reload, engine execution and image export separately. Confirm
actual modified-state/disk readback for Save, and unload/reopen for reload. A
headless native run proves its recorded engine behavior, not station GUI Save,
Inspector safety or live lamp colours. Preserve raw warnings and classify them.

Use the [field lessons](references/experience-lessons.md) to avoid repeated
failure modes. Reports must identify the exact tested project and evidence layer;
old examples do not certify a new station or all tools.
