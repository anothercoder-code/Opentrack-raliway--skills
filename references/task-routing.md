# Task-specific operations and readiness

First complete [full software authorization](software-authorization.md). Then
normalize the request with [requirement normal form](requirement-normal-form.md),
select [semantic capabilities](capability-and-composition-model.md), and create
the [dependency plan](workflow-plan-and-execution.md) before choosing a raw tool.
Record final evidence with [outcome verification](outcome-verification.md).
Use actual tool descriptions, input schemas and capabilities. Registration is
not readiness: the legacy whole-project mutation tools listed below are
registered with explicit blocked handlers in this release.

| Current task family | Candidate entrypoints / reference; inspect the exact contract |
|---|---|
| Inspect current saved archives, selected stock, Station/Edge/run or signals | `opentrack_inspect_current_archive` and the discovered current inspectors; [archive index](archive-interface-index.md) |
| Typed current field/timetable/formation edits | Discovered `opentrack_edit_current_*` / preview operations; [current functions](current-archive-functions.md) and the matching wave contract |
| Create explicit current network archives | `opentrack_generate_current_network_archives`; [network generation](wave9-network-generation.md); its complete input/persistence restrictions remain authoritative |
| Create current operating archives or a Course from templates | `opentrack_generate_current_operating_archives`, `opentrack_generate_current_course`; [operating generation](wave11-operating-generation.md) |
| Complete supported template-based project | [Project initializer](project-initialization.md), [station documents](station-documents-project.md); do not assume any initializer expresses every design |
| Reconstruct a named real station and run through it | Validate the evidence and topology with `opentrack_validate_reality_station_plan`, then [compose native objects](reality-station-template.md); use the single-corridor request only for one straight through platform face |
| Custom complex design | [Requirements and composition](complex-design-workflow.md); select supported primitives or original workflow and state actual implementation gaps |
| Reusable worked yard/grid templates | [Yard](station-document-layout.md), [grid](grid-station-yard.md); examples and helper contracts, not mandatory designs |
| Information-only operations or supplied graph compilation | `opentrack_prepare_operations`, `opentrack_compile_route_bundle`; [bundles](generation-bundles.md), [route compiler](generation-routes.md). Their old native apply specification names a currently disabled writer |
| Current connections | Discover the current record/batch interfaces and their exact write scope; [connection reference](connection-commands.md) is not proof every historical batch action is enabled |
| Rolling stock, curves, XML/RailML or timetable export | Select the actually discovered inspection/exchange operation and its dependency/read/write scope; see [archive index](archive-interface-index.md) |
| Missing services or departures | [Workflows](workflows.md); diagnose actual bindings before adding duplicate definitions |
| Saved results / native simulation / software Train Diagram | [Acceptance levels](acceptance-levels.md), [native contracts](native-contracts.md), [native running diagram](native-running-diagram.md) |
| Function/schema investigation | `opentrack_read_function` or schema/evidence tools within their actual availability; [coverage](coverage-and-evidence.md). Metadata or decompiled text is not a callable method |

When the discovered `ai` profile is available, start with its semantic
capability, planning, inspection, reality-station and bound-evidence entries,
then use the task table to resolve the underlying implementation contracts.
The `ai` profile currently has 21 entrypoints; the 15 low-level writers are
reachable only through the hash-bound publication bridge.

| Semantic operation | Tool |
|---|---|
| Search railway capabilities and limitations | `opentrack_get_railway_capabilities` |
| Compile a typed dependency plan | `opentrack_compile_railway_plan` |
| Resolve actual project state and gaps | `opentrack_inspect_railway` |
| Audit results returned after separately executed tools | `opentrack_apply_railway_plan` |
| Aggregate assertion evidence | `opentrack_verify_railway_outcomes` |
| Publish one dependency-ready action to one reviewed writer | `opentrack_publish_railway_plan` |
| Validate a sourced reality-station plan | `opentrack_validate_reality_station_plan` |

## Explicitly quarantined legacy mutation tools

`legacy_geometry_guard.py` and the registry reject these with
`LEGACY_GEOMETRY_DISABLED`, independently of optional parser dependencies:

- `opentrack_create_project`
- `opentrack_generate_operations`
- `opentrack_stage_changes`
- `opentrack_start_editor`
- `opentrack_edit_editor`
- `opentrack_publish_draft`
- `opentrack_apply_draft`
- `opentrack_create_demo_line`

Their old references preserve field semantics and historical test scope, not
current permission to execute writes. Do not call internal helpers or remove the
guard to work around this. A bounded current_archive tool is not a spelling alias
for an old batch and may support fewer/different operations. Inspect its schema
and saved-data proof before choosing it. Uncovered requirements stay explicit
rather than being silently reduced to a template or reported complete. When
several supported primitives or an authorized original workflow can express the
same requested railway behavior, choose the clearest safe combination and
validate its result instead of requiring one dedicated solver per original
function.
