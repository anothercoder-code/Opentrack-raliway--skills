# Plan original connection and Turnround data

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

Inspect exact Course IDs, timetable indices, station signs and Train Categories
with `opentrack_get_service`. The historical implementation used one `opentrack_generate_operations` batch; that writer is currently quarantined:

```json
{
  "project":"<project>",
  "timetable_operations":[{
    "kind":"plan_timetable_connections",
    "commands":[
      {"action":"turnround_to","row":{"course_id":"G9001","index":0},"target_course_id":"G9002"}
    ]
  }]
}
```

`turnround_to` uses the owner's last row; `turnround_from` uses its first.
The target needs a visit to that station. To-target-start creates a primary
split and reciprocal plain start connection; to-target-midcourse joins both.
From-target-end or midcourse creates a plain primary and splits the target.
Each new record uses its own owner's Category default waiting time; missing
Category falls back to seven minutes. These commands generate data, not feasible
vehicle circulation or native coupling acceptance.

`insert` uses the selected row; omit `target_course_id` for an original target
`"0"` placeholder. The resulting draft is invalid until bound through indexed
`edit_timetable_connections` updates. `delete` requires `connection_index` and
no target ID; indices follow preceding commands in the batch. Ordinary insert
and delete are local, including in interval families. They do not delete a
reciprocal connection automatically.

Advanced helpers: `add_start`, `add_end`, `join_at_station`, `split_at_station`
and `split_at_end`. Station helpers use the first matching visit. Existing
connections are matched by target ID alone. Join/split helpers only set their
flag; they preserve existing station, waits and other flags. The primary
Turnround record resets station/location/join/split while retaining existing
wait/type/distance. Inspect before and after rather than assuming all fields
were reset.

A new start-helper reciprocal retains the original raw nil maximum wait.
Readback reports `maximum_wait_is_nil:true` and logical unlimited `HH:MM:SS`.
Archive persistence preserves nil; native text export warns that the raw nil
distinction cannot be represented. Do not normalize it during unrelated edits.

Up to 1000 commands per plan share the full draft's 10000 row-target and
connection-allocation limits. Inspect validation, bounded previews and full
`timetable_changes_json`, then publish an isolated valid project. Pair creation
does not adjust times, stops, train formations or simulation state. Detailed
rules and function hashes are in `OTAI/contracts/connection-commands.md` in the
MCP package.
