# Original Course identity and references

Baseline: original stock English OpenTrack 1.7, audited EXE SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Primary evidence is saved original Demo data and bounded x86 windows in
`artifacts/research/course-lifecycle-layouts.txt`. Text annotations are heuristic
address lookups; instructions, metadata and frozen record fields are the evidence.
No native method, GUI or simulator is executed.

## Identifiers and rename

`OTCourseController.isValidCourseID:` (0x45c480) delegates to
`isValidRangeForCourseID:` (0x45c4a8). Together with the C-string version
(0x45c428), these exclude nil/empty, `0` and `-1`. The 1.6 manual's additional
digit wording is not enforced by this 1.7 method. Printable ASCII and 80-character
limits are API bounds, not inferred original rules. New Course, clone and rename
destinations reject reserved IDs; lifecycle selection also refuses reserved
source IDs because they cannot be distinguished safely from native sentinels.

`course_lifecycle` is an ordered typed batch after definitions, timetables and
`course_updates`. `rename_courses.renames` is simultaneous within each operation,
so swaps and cycles do not merge identities. Sources and destinations must each
be unique. Targets held by unselected Courses and dictionary-key collisions fail
before writing a draft. No substring replacement is used.

Native `OTTimetableController.courseIDChangedFrom:to:` (0x693974) copies timetable
rows under new `CourseID#index` keys, sets row owners, preserves interval settings,
then updates interval/connection references and removes old keys.
`OTTimetable.setCourseID:` (0x6794f8) also updates embedded connection owners.
The API applies these saved-data semantics with the following audited sites:

| Record/container | Course reference |
|---|---|
| OTCourse v0-v11 | group 0 identity |
| OTTimetable v7-v9 | dictionary key; group 1 owner; group 2 interval reference |
| OTConnection v0-v6 | group 0 owner; group 1 target |
| OTIncident v0-v12 | stable group 1 Course ID prefix |
| OTConflict v0-v1 | group 0 Course ID |
| OTTCorridorSimController v0-v2 | conflict keys `time#CourseID`; Course-keyed event/reservation/release dictionaries; v2 timetable dictionary |

The Incident coder/decoder (0x4e33e8/0x4e2d98), Conflict coder/decoder
(0x40f390/0x40f2dc) and corridor coder/decoder (0x674438/0x674284) establish these
roles and versions. Incident Course ID is decoded unconditionally before later
version branches; this operation preserves its remaining fields/version.
Corridor conflict insertion appends `#` and the exact Course ID to its time key.
Frozen original goldens independently anchor Incident v10, Conflict v1 and corridor
controller v1. Old-version reference cases are decoder-derived, not independent
goldens for every version. Course writes use the existing v11 draft migration.

## Delete and detach

`delete_courses` removes selected Courses and their own timetable rows. Default
`reference_policy: reject` reports incoming connections, dependent interval rows,
Course-specific Incidents and saved diagram data. `detach` explicitly removes
target connections, Course-specific Incidents and diagram entries, and resets
surviving interval references to `0`. Stored arrival/departure, day offsets and
interval offset values remain. Native `resetIntervalReference` (0x67a53c) sets
only the reference string; the API does not invent retiming.

Dependent Incident/connection references are removed from native arrays and
dictionaries. An unaudited direct containment fails preflight instead of nulling
an arbitrary field. Global Incidents using `0` remain. Other Courses, formations,
Engines, Categories, paths and infrastructure remain. Native Course deletion's
GUI offers timetable deletion separately; this typed operation always deletes
the selected Course's own timetable to avoid orphan data. It is an explicit
save-editing contract, not a reproduction of those dialogs or all native caches.

## Reset Itineraries

The manual section 6.1.2 and `resetDestCourseEditPressed:` (0x46687c) define
removal of unavailable Itinerary names. This differs from `OTCourse.reset`
(0x4557b0), which clears the temporary edit object and must not be used to reset
a persisted Course's identity/formation.

`reset_course_itineraries` keeps exact names present in both the selected
destination catalog and selected infrastructure definitions, retaining order and
all other attributes. Selected project documents define availability; no GUI
open-window state is read. An empty resulting list is retained in the reviewable
draft with `EMPTY_ITINERARY` validation failure. No replacement is invented.

## Persistence and bounds

Stage/editor accept the same three `kind` values directly. Changes are atomic
across the draft; immutable editor revisions support undo. Full lifecycle diffs
are saved in the manifest and `course-lifecycle.json`; ordinary generation
responses contain bounded previews. CSV reflects the resulting whole timetable.
Existing orphan rows are reported as `TIMETABLE_ORPHAN` and exported with blank
unbound vehicle columns rather than crashing or inventing bindings.

Shared limits: 1000 definition/edit operations and 10000 requested Course edit
targets per draft, including `course_updates` and lifecycle selections. Edits
cover only selected catalogs/documents/corridors, not unselected external projects,
output text files or live process state. Unknown saved layouts fail explicitly.
These archive operations do not establish full native Course dispatch behavior,
Incident functionality or native simulation acceptance.
