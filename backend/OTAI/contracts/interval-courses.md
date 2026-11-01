# Original interval Courses and connection properties

Current stock English OpenTrack 1.7. Primary C evidence and hashes are frozen in
`artifacts/research/interval-courses-v022.json`; bank `bank-v022-interval`.
The focused pass exports 898 functions without failed entries. These are
machine-generated functions, not recovered original source or native execution.

## Create sequential copies

Use `create_interval_courses` in ordered `timetable_operations`, Stage or editor:

```json
{"kind":"create_interval_courses","source_course_id":"G9001","count":12,"number_step":2,"number_position":0,"interval_s":900}
```

`count` is the number of **additional** copies. An exact existing source Course
and nonempty, contiguous timetable are required. Each new Course copies the
preceding copy, as `intervalPressed:` (0x692794) updates the selected Course
between iterations. Both time offsets and connection numbering are sequential.

`number_position` is a zero-based ASCII numeric block (0–31), and `number_step`
is its signed, nonzero change. Preserve existing leading-zero width; an absent
block appends `.<step>` using the original `%@.%i` format. Native menu tags
101–105 mean second block, step 1–5; the API exposes those two choices directly.
It does not interpret literal `number_step:101` as a menu tag. Numeric blocks
must remain within nonnegative signed int32; arithmetic overflow is explicitly
unsupported. Negative or reserved new IDs reject. Source/self collisions and
duplicate generated IDs reject before table mutation.

Existing target rows require `replace_existing:true`. With `update_courses:true`
(default), existing target Course definitions also require that flag and are
replaced from the preceding source definition. All persisted current Course
attributes, Train/Itinerary bindings, enabled state and speed controls are copied.
With `update_courses:false`, Course definitions are preserved. Missing target
definitions can leave orphan timetable rows with validation errors; no formation
or definition is guessed. Invalid drafts cannot be published as valid data.

The first source row's valid interval reference becomes the reference of every
copied row; otherwise the source Course is the root. Each row's own saved offset
accumulates the signed step in float32. There is no recursive root chasing.
Each copied connection gets the new owner ID and the same numeric transformation
of its target ID. A negative/reserved target result leaves that old target
unchanged with `NATIVE_CONNECTION_NUMBER_UNCHANGED`. Target existence/station
checks run after the entire batch, allowing paired families in one operation
batch. Missing final bindings reject as in other timetable commands.

Copies include saved actual strings and their day offsets, unchanged. Native
transient actual-validity, connection tag and dispatching state are not encoded
and are not reconstructed. Rows and connection items are copied independently,
including when the source archive aliases the same object at several positions.
The native coder's known flags and current timetable header are written.

## Native planned-time arithmetic

`interval_s` is signed integral seconds including any day component. Zero time
step is allowed; Course numbering must still change. The native float32 step is
returned as `native_step_s`, with a warning if float32 changes the requested
integer. Planned arrival/departure is read with its day offset in float32 and
shifted through the original saved-time behavior:

- Undefined strings remain undefined.
- A defined time whose absolute value is already negative remains unchanged.
- A nonnegative input shifted below zero becomes `HH:MM:SS`, day zero.
- Nonnegative results are split into day and clock. Large absolute seconds can
  lose second resolution through float32, as in the original getters/setters.

This differs from the generic calendar `shift_timetable_rows` operation, which
supports negative day offsets. Native clearing/skipping produces explicit
warnings. Undefined planned data still fails static preparation. Output day
offsets share the API's ±366 bound. No travel time is computed.

## Connection property propagation

`edit_timetable_connections.propagate_interval:true` applies to indexed updates
only. It mirrors `connectionChangedOfCourseID:...connectionObject:` (0x6acab4).
After source updates, copy the **whole** supported property set to the same
connection index at matching row index/station in the original direct family:
direct dependents, siblings with the same reference, and that reference Course
only when its own row has no interval reference. Nested references are not
recursively followed. A missing connection slot is skipped.

Copied properties: target station, minimum/maximum wait, join, split, location
and time-reference type. A target Course ID and dispatching distance remain
specific to each connection. This is not partial per-field propagation; other
source properties overwrite the corresponding target properties even when the
source patch changed only one field. Inspect arrays before requesting it.

Appending, deletion and clear operations retain their explicit local command
semantics; the propagation option rejects those combinations. Original ordinary
insertion/deletion is local, including in interval families; the previous
automatic-family backlog assumption was incorrect. Use the separate
`plan_timetable_connections` commands for original insertion/deletion and
compound Turnround helpers; see [connection commands](connection-commands.md).
The corrected root membership is shared with row-property operations; full
native undefined-time/cache quirks of every other field controller are not
established by this implementation.

## Budgets and verification

Interval definitions share the draft's 1000 Course-definition limit, 1000
requested timetable-creation targets, 10000 rows and 10000 connections. Counts
describe writes, including replacement, not net database growth. All requested
copies are planned before the table/catalog is committed; failed batches leave
source files unchanged. Full creations, warnings and row provenance are in
`timetable_changes_json`; response previews are bounded.

Tests cover paired families, missing-block/padding rules, signed steps, float32
resolution, actual data, aliases, unbound rows, explicit replacement, budgets,
native root membership, whole-property propagation, missing slots and editor
undo. Real compact MCP and extracted-package verification cover generation,
errors, persistence and isolated publication. They do not establish native GUI,
controller cache, dispatch, circulation, calibrated performance or simulation
acceptance. No original program is launched.
