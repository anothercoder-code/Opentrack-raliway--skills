# Copy existing interval services

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

The quarantined legacy batch used `patterns` for supplied stops/time offsets and
`create_interval_courses` to repeat an existing Course with
its saved timetable, bindings, flags and connections. Inspect the source with
`opentrack_get_service` once; preserve exact IDs and check all connected families.

```json
{
  "timetable_operations":[
    {"kind":"create_interval_courses","source_course_id":"G9001","count":12,"number_step":2,"interval_s":900},
    {"kind":"create_interval_courses","source_course_id":"G9002","count":12,"number_step":2,"interval_s":900}
  ]
}
```

This creates 12 additional copies per direction in one draft. Each copy uses
the preceding copy. Course attributes and timetable/connection fields persist;
connected IDs use the same numeric rule, so generate paired families together.
Final binding checks see the entire batch. Use one coherent generation call.

`number_position` selects a zero-based numeric block (default 0). Leading zeros
retain their width; a missing block appends `.<number_step>`. Native menu tags
101–105 map to `number_position:1` and steps 1–5. The input fields are explicit
choices, not raw menu tags. Negative/reserved IDs and numeric overflow reject.

`interval_s` is signed seconds. Native float32 precision applies; negative
results clear to undefined, while already-negative absolute source times are
not shifted. Inspect `native_step_s` and creation warnings. Use generic
`shift_timetable_rows` for explicit calendar arithmetic across negative days.

Target collisions require `replace_existing:true`. By default Course definitions
are copied too. `update_courses:false` preserves existing definitions and can
leave invalid orphan timetable rows when a target definition is absent. Validate
the actual bindings rather than guessing missing vehicles. Saved actual times
are copied unchanged, without certifying runtime validity. If fresh actual data
is needed, add an explicit `reset_timetable_actual` after creation.

For original connection-property linkage, use indexed
`edit_timetable_connections` updates with `propagate_interval:true`. It copies
the whole target-station/wait/join/split/location/time-reference property set at
the same connection index through the direct interval family. A reference row
is a root only when it has no own reference; nested families are not traversed.
Target Course IDs and dispatching distances stay specific to each connection.
Missing slots skip. Inspect target arrays first. Append/delete/clear cannot use
this option. Original ordinary insertion/deletion is local even in interval
families. Use [connection commands](connection-commands.md) for original local
commands and compound Turnround helpers.

Review full `timetable_changes_json`, compact previews, counts and validation,
then publish an isolated project. Counts include writes/replacements. This
workflow creates no native run and does not prove collision freedom. The
packaged contract `OTAI/contracts/interval-courses.md` records exact evidence,
budgets and scope.
