# Historical geometry-editor contract — current writes quarantined

**Current release status:** the legacy blank/create, stage/editor mutation and
publish/apply pipeline is explicitly blocked with `LEGACY_GEOMETRY_DISABLED`,
independently of missing parser dependencies. The registry replaces those handlers
with the guard. Do not follow the mutating examples below as executable current
instructions or remove the guard to regain them. They document the former API's
semantics and limits. Existing reads are separate and can still require dependencies.

For current work select an applicable `current_archive` initializer or typed
operation from actual discovery, use supported standalone profiles where they
fit, or a separately authorized original-app workflow. Those are not drop-in
aliases for this old editor. Any missing general geometry capability remains a
real implementation gap, not a requirement to force the user's design into a
fixed example. See [complex design](complex-design-workflow.md).

Discover exact arguments from the current tool schemas. The editor/draft tools
in this reference create isolated archives and leave their source untouched. This
is their transaction contract, not a claim that every workflow is draft-only;
current-project updates use the separately reviewed in-place procedure.

## Start and edit

1. Create an empty project with `opentrack_create_project` (`project_name`,
   `documents`), or inspect an existing selected `.run` and bindings first.
2. `opentrack_start_editor` returns `session_id`, `revision`, the current
   `draft_project`, its `draft_id` and validation.
3. Call `opentrack_edit_editor` with the latest `expected_revision`, action
   `edit` and typed `changes`. All geometry edits are one atomic history step.
4. Inspect the returned changes, graph and validation. Invalid construction
   drafts may be continued, but publication rejects an invalid draft.
5. Use action `undo`/`redo` with the current revision. State and snapshots survive
   a server restart. Editing after undo creates a new visible branch; old
   snapshots remain recoverable. A stale revision does not perform an edit.
6. Publish the selected `draft_id` using `opentrack_publish_draft` and a fresh
   project name. No original application shutdown is needed for publication.

`opentrack_get_editor` reads the current revision and selected snapshot. The
commit file lock is released by the OS on process exit; there is no stale PID
lock to delete blindly.

## Supported change kinds

| Kind | Meaning |
|---|---|
| `create_document` | New empty worksheet, with its own document identifier |
| `create_vertex` | Reciprocal half pair and initial safety Elements |
| `move_vertex` | Move/rotate the pair and attached Signals together |
| `vertex_attributes` | Name, kilometre reference, stationEndType, switch time/default leg, joint/axle flags |
| `create_edge` | Connect two specified halves in one document; positive integer metres, directional speeds, grade/radius |
| `edge_attributes` | Distance, grade/radius, speed table, rack/equal-speed flags, wire/tunnel sections, track/line text |
| `reverse_edge` | Swap endpoints and directional speeds, negate gradient |
| `create_signal` | One metric main/combined/audited ETCS-main Signal on an eligible directional half |
| `link_connectors`, `unlink_connector` | Reciprocal document-name/local-ID links on empty connector halves |
| `merge_elements`, `reset_elements` | Explicit safety grouping or default physical half-vertex components |
| `exclusion_link` | Native outgoing/incoming Edge link; its target contributes exclusive resources |
| `split_edge` | Preserve total length, speeds, Route identities and Path mileage; retain the old exclusive section |
| `delete_graphic` | Remove vertex pair, Edge or Signal after dependency review |

An `EndRef` is `{document,end_id}`. In the same batch, a new vertex can be named
with `vertex_key`; later geometry changes may use
`{document,vertex_key,side:0}` or side 1. Return values provide the allocated
numeric IDs for later searches/definition drafts. A Signal's graphic ID is not
its End ID. Drawing coordinates and kilometre references are not Edge lengths.

Switch branches belong on the same half. Connecting them through opposite
halves changes permitted movements. A connector half has no Edge/Signal; its
related half also cannot have a Signal. Each half supports at most two incident
Edges. Speed tables use explicit train-type keys and separate forward/reverse
km/h. Native strings remain ASCII on the audited legacy cString interface;
editor labels/history can be Unicode.

`opentrack_trace_path` reports `direction` and `speed_limits_kmh` for each Edge.
Direction follows actual endpoint traversal, including after `reverse_edge`.
Its legacy scalar `limit_kmh` is the minimum across train types in that
direction; select the actual train type for a class-specific speed decision.

Deleting a used graphic returns `GRAPHIC_IN_USE` and dependent Routes, Paths,
Itineraries and Courses. `cascade_definitions_and_services:true` explicitly
removes them and their timetable rows in the new draft. It never silently
reassigns a Course to another journey. Measuring-instrument dependencies and
direct exclusion-linked Edge splitting need additional contracts and currently
return explicit unsupported errors.

## Verification boundary

The sanitized class-shape archive has a pinned fingerprint. Empty projects copy
no rail layout, service, vehicle or timetable. Creation, supported offline edits,
undo/redo and isolated publication do not technically need an installed original
EXE; runtime or binary inspection still does. All railway business still requires
confirmed valid full software authorization; offline availability is not a licence waiver. Prototype extraction is from frozen, hashed
archives and does not claim native constructor equivalence.

This is a general independent archive editor subset. Vertex cut/join,
zero-length Edge handling, every Signal system/property and event/instrument
dependencies remain incomplete Agent capabilities. For an archive-editing deliverable, reimplementing the native GUI or simulation
engine is not required. If the current request includes original loading, saving
or simulation, complete that separate native workflow; a historical generation-
focused objective does not override the current user. Supported archive edits
still need their own verification. Read
`OTAI/contracts/geometry.md` through the registered evidence when exact field
order matters; archive group 20 is stationEndType and group 23 is joint/axle
flags. Runtime byte offsets are separate.
