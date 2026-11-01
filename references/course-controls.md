# Course controls and bulk editing

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

These notes describe the original English `Courses/Services` properties and historical legacy batch forms, including Itinerary
priority order. Inspect exact Course, Train and Itinerary names first. Use the
compact generation profile; this workflow does not start OpenTrack.

## Create Courses or repeated patterns

`courses` and `patterns` accept:

- `spacing_mode`: `discrete`, `moving`, `moving_cbtc`. Original tags are 0, 2,
  3, not menu positions. Omitted creation values default to discrete.
- `additional_reservation_time_s`, `additional_release_time_s`: seconds added
  to Route times, default zero. They are separate from dwell, Step and the
  Route's own reserve/release settings.
- Existing acceleration, entry speed, output offset, display train number,
  Kind, description and comment fields remain available.

`itineraries` is an ordered preference list: first is priority 1. It is not a
chain of trips; each Itinerary contains its sequential Paths. Read actual ranks
in service `itinerary_preferences`. Category dispatch priority and Course
acceleration are separate properties.

## Update existing Courses

```json
{
  "course_updates": [{
    "course_ids": ["G9001", "G9003"],
    "spacing_mode": "moving_cbtc",
    "additional_release_time_s": 7.25,
    "itinerary_move": {"name":"I:Alternative", "priority":1}
  }]
}
```

Add the actual project and exact catalog names. Omitted fields remain unchanged.
Edits support Train/Itinerary bindings, speed type, enabled state, normal/delayed
acceleration, entry speed, output offset, the three controls above, description,
comment, display train number and Kind. `invert_enabled: true` implements `Inv`
and cannot combine with `enabled`. `itinerary_move` reorders one exact existing
name; a position past the list clamps to the last position, as in the original.
Use either a complete `itineraries` list or one move. Missing names reject the
complete draft operation.

Use an empty string to clear optional text; null is rejected. IDs/timetable keys
remain unchanged. Stage/editor also accepts `kind: update_courses` with the same
fields, including persistent snapshot undo/redo.

Review `course_update_targets`, change previews and `course_updates_json` for
the complete per-Course diff. The manifest also retains full details. CSV
previews include mode/code and additional times. Publish the reviewed draft as
a fresh project; original files remain unchanged. Isolated publication needs
no original-program shutdown.

## Old data and API bounds

Readback supports Course record v0–v11 with original-decoder defaults. Writes
upgrade all old Course records in the selected catalog to v11 and report
`serialization_migrations.OTCourse`. Reserved values and unknown saved spacing
codes remain on unrelated edits; unknown codes return `spacing_mode: null` plus
the raw code. Do not guess labels. The container contract is `OTCourseList v3`.

Printable ASCII IDs, including stock spaces/punctuation, bind exactly. Controls
and leading/trailing whitespace are rejected. Generation/Stage allow 1000
definition/update operations before pattern expansion. One update group selects
up to 1000 Courses; a draft accepts 10000 requested update targets. Existing
pattern/Course/timetable bounds still apply. These are API budgets. Native
moving-block operation and timings need separately requested acceptance.
