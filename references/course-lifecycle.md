# Course identity, deletion and Reset Itineraries

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

The quarantined legacy contract used `opentrack_generate_operations.course_lifecycle` for an ordered batch after
definitions, timetable generation and `course_updates`. Stage/editor accept each
operation directly in `changes`. Inspect exact Course IDs first.

```json
{
  "course_lifecycle": [
    {"kind":"rename_courses","renames":[{"course_id":"G9001","new_id":"G9101"}]},
    {"kind":"reset_course_itineraries","course_ids":["G9101"]}
  ]
}
```

Renames within one operation are simultaneous; swaps/cycles work. Unique exact
source/destination IDs and dictionary keys are required. References update across
selected timetable keys/owners, connection ends, interval references, Course-specific
Incidents and saved corridor diagrams. Names, descriptions, times, formation data
and unrelated records are preserved. Empty/`0`/`-1` new IDs are reserved by the
original 1.7 implementation; printable ASCII/length bounds are API constraints.
Lifecycle refuses reserved source IDs because native sentinels are ambiguous.

`delete_courses` always removes the selected Courses' own timetable rows. Its
default `reference_policy: "reject"` reports dependencies. When the requested
deletion includes cleanup, use `"detach"` to remove incoming connections,
Course-specific Incidents/diagram entries and reset surviving interval references
to `0`. Global Incidents using `0`, stored times and interval offsets remain.
This is an isolated draft operation; review the returned dependency information.

Original **Reset Itineraries** removes unavailable names, preserving order. Here
availability means exact definitions in selected project documents and the
destination catalog. It does not reset Course properties or inspect native open
windows. If no Itinerary remains, the draft reports `EMPTY_ITINERARY`; inspect and
bind an intended Itinerary before publication.

Review validation and `course_lifecycle_json`, whose full diff is also in the
manifest. Ordinary responses contain bounded previews. The resulting CSV includes
the whole timetable, reflecting renamed/deleted IDs. Orphan timetable rows are
reported and retain blank unbound vehicle columns. Generation/Stage share limits
of 1000 operations and 10000 requested Course edit targets, including partial edits.

This covers audited original saved reference layouts, not unselected external
files, arbitrary Incident editing, native controller state or dispatch/simulation
acceptance. The packaged contract is `OTAI/contracts/course-lifecycle.md`.
