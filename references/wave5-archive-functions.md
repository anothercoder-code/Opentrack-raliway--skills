# Wave5 saved-data operations

These are current native typedstream archive operations, not simulation, GUI automation,
legacy migration or full-project validation. Always inspect the actual input first,
retain its SHA256, preview, then use an explicit fresh target with `preview_only:false`.
Never infer a source hash, new geometry or an omitted file. Core file publication is
atomic no-replace and rechecks every dependency. A postcommit error can report
`commit_completed:true`; inspect the exact target before retrying, never overwrite it.

## Station existing-record getters/setters

1. `opentrack_inspect_current_station(source_path, station_sign)` reads saved values.
2. `opentrack_edit_current_station(source:{path,sha256}, station_sign, changes)` previews.
3. Repeat with `preview_only:false,target_path` to save a distinct copy.

`display_name` is a Unicode string or explicit null/native nil. It is **not** a
stationSign/dictionary-key rename. Name assignment uses an isolated NSString node;
the decompiled selector pointer is unresolved, so arbitrary Objective-C copy/object
semantics are not claimed. `altitude_raw`, `coord_x_raw`, `coord_y_raw` are exact
signed int32. Units are unproven: do not call them meters/longitude/latitude.
`timing_point` accepts bool or signed char [-128,127]; native coder persists nonzero
as 1. Other nulls, floats and bool-for-int are rejected. No new Station constructor.

## New Route from explicit existing movement

`opentrack_create_current_route` requires `project_run`, complete `documents`
(name→{path,sha256}), `target_document`, exact `template` {name,array_id,start_id},
new `name`, explicit `end_ids` equal to the template chain and optional description.
The real `.run` infrastructure list and actual project `.opentrack` inventory must
match; a caller flag is not accepted as completeness proof. Non-target inputs stay
unchanged and participate in pre/post SHA checks. The new Route is a distinct
object with fresh owner-local identity `highestGivenRspID + 1`, new indication
objects and backrefs, referencing the existing same movement/geometry.

This is explicit-template field composition, **not native init/copy equivalence**,
not route-finding and not arbitrary new infrastructure. Restricted to current
noncontinuing route, main-signal/show-type2/code0 domain; nonempty ShuntingList,
unknown RSP hierarchy, aliasing owners, stale/overflow counter, missing documents,
name/identity capture and unsupported geometry are rejected. Output is one fresh
archive copy, not a complete relocated project or automatic source-project update.

## Train Incident current12 profile

`opentrack_inspect_current_train_incidents(source_path)` exposes the actual saved
Incident12 Train type1 events. Other event types/versions/profiles fail closed.
Creation requires `project_run`, Course `source`, `trains` (all path+SHA), `name`,
exact enabled `course_id`, canonical same-day `begin_time/end_time` HH:MM:SS, optional
`enabled` (defaults false) and finite float32 `reduced_speed_kmh` (defaults zero).
The run's unique CourseFile/TrainFile bindings must match the supplied files and the
selected Course must resolve to an actual current Train. This is the verified
saved-data dependency boundary, **not a runtime/full-Project dependency closure**.
There is no invented Station/Signal/Timetable reference or simulation effect.

`opentrack_edit_current_train_incident` uses the same dependencies, exact `name`
and nonempty `changes` containing only name/enabled/reduced_speed_kmh. Negative
finite speed clamps to zero by the original setter; bool/NaN/Inf/overflow are not
numeric inputs. Name is printable ASCII up to 2000 characters (API guard, not native
limit). Time order/canonical format is an API guard, not the native time parser.
Init-derived construction deliberately overrides localized name, type/course/times
and disabled default; it is not original-init equivalence or an App-created fixture.

For editing a previously saved copy, choose a valid project/run binding to that copy;
do not falsely reuse a run which still binds the original Course file.

## Evidence interpretation

Full original-C ABI domain, exposed API subset and tested samples are distinct.
Saved copies must be independently reloaded by an upstream typedstream reader in a
fresh process; this is independent archive compatibility, not the OpenTrack runtime.
The provided BJTU fixture is frozen unlaunched/synthetic infrastructure, not proof
of application-produced geometry. Unsupported layouts fail rather than using guessed
zeros, JSON-only substitutes, legacy promotion or mixed class versions.

## Integrated dependency document domain

Every supplied dependency archive, including non-target files, must match current OTDocument4 hierarchy and the supported 21-group layout. All known Route/Path/Itinerary and ArrayInfo/ExtInfo records, plus each End owner RSP wrapper/member, are checked before collision analysis. A nonempty ShuntingList is refused **anywhere in the supplied document set**, not merely at the selected owner. This is an explicit API safety subset; it is not a claim that native OpenTrack forbids shunting in other documents.
