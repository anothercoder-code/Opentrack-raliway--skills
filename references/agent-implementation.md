# Original-function implementation and evidence

## Development scope

This is a maintained local interface, not a promise of a stable universal API.
Prioritize the current original OpenTrack 1.7 format and the user's current task.
Do not add compatibility layers or unrelated recovery work merely because older
examples exist. When another format/version is actually required, assess that
specific requirement against real source evidence and the current schema.
The broader 176-item replication objective is historical tracking, not standing
authorization or a mandatory completion gate for an ordinary design/edit task.
Any business investigation still needs [software authorization](software-authorization.md).

## Function-first implementation

For a missing or uncertain original command, first query `opentrack_read_function` by class and selector, then read the function and its callees. Preserve bank ID, entry address and file hash in implementation evidence. C pseudocode is machine generated; inspect warnings, receiver-specific message types, variadic formats and aggregate returns before using it. Repair missing types, parameters and call relationships through metadata and the decompiler before implementing the operation. Read the page's `referenced_string_literals` to resolve verified-build constant-string layout candidates without changing the C. Do not switch to instruction-level review during implementation unless the user explicitly requests assembly analysis. Leave unresolved details unverified and continue function recovery. A function reader or metadata entry does not implement that native command. [Function evidence](function-decompilation.md) describes the workflow and remaining limits.


## Resolve a function or capability gap

For function-level work, use `opentrack_get_function_coverage` with a fresh snapshot. Read the selected coverage summary with [scripts/audit.py](../scripts/audit.py); its default auto scope can select an existing legacy summary or the packaged summary, and it does not regenerate source coverage. The read-only MCP never refreshes reports as a side effect. Filter by class/selector or local helper name; inspect the scope of any reported business relation.

`opentrack_get_native_class` can read a named class or category in `opentrack`, `foundation` or `appkit`. `opentrack_disassemble_method` requires an exact selector and method kind; it returns a bounded static instruction window with `complete_function:false`. It never executes the method.

Keep these evidence levels distinct: metadata visibility; instruction snippets; tested archive operations; approximate operational models; and actual native run acceptance. Registration counts and helper reachability do not establish native parity or complete behavioral test coverage. Absence of a manually verified mapping is not proof of zero data overlap.

When a requested capability is missing or quarantined, name the exact gap and
continue only useful work within the active supported scope. Do not remove
`LEGACY_GEOMETRY_DISABLED`, switch to an old backend, call its legacy classes
directly or invent protected saved-field values to make a design request pass.
Restoring a quarantined writer requires its separate saved-field/source audit;
a missing capability or a standing recovery objective does not authorize that
repair implicitly. Do not substitute the three-station demo constructor for arbitrary interlocking creation. If extending the interface is authorized, implement only the verified operation, add a behavior/failure regression, update public schemas/evidence and regenerate coverage. Do not expose arbitrary native selector execution to fill a coverage table.

