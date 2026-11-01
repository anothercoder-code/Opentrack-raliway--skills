# Timetable database commands and exchange

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

To derive station rows from an existing Course, use
`{"kind":"create_timetable_skeletons","course_ids":["G9001"],"replace_existing":true}`
inside `timetable_operations`. Use only the first bound Itinerary; alternative
Itineraries are not combined. Exact loaded Path/document references are required.
The operation applies current Category stop/dwell/timing/track defaults after
same-batch stock edits. Station database `timing_station` is editable through
`stations`. Dwell is float32 then integer truncation; the first row never stops.
The resulting times are undefined `HH:MM:SS`, not calculated running times.
Fill planned times explicitly before static preparation; generation warns and
preparation fails while endpoint times or whole rows remain undefined.
Omit `replace_existing` to reject replacement. Review source-End provenance,
selection warnings and full JSON diffs. A native repeated-object alias quirk can
leave inconsistent maxIndex values; validation reports it rather than hiding it.
See packaged `OTAI/contracts/timetable-creation.md` for the exact reviewed rules.

Read exact Course/index rows from the selected timetable before row edits. The historical batch path used
`opentrack_generate_operations` with ordered `timetable_operations`, or
the same operation kinds in Stage/editor; all of those legacy writer paths are currently quarantined. Indices are zero-based and refer to
the state after earlier operations. Explicit `rows` and whole `course_ids` are
alternative selectors.

```json
{
  "timetable_operations": [
    {"kind":"update_timetable_rows","rows":[{"course_id":"G9001","index":0}],"track_id":"Platform 2","mean_delay_s":30},
    {"kind":"shift_timetable_rows","course_ids":["G9001"],"seconds":60}
  ]
}
```

Partial edits preserve omitted fields. Null arrival/departure clears that time
and day; empty optional text clears text. Connections `[]` explicitly replaces
the entire row connection list. Actual times remain during planned edits.
Use `insert_timetable_rows` with stops and optional `before_index` (null appends).
`delete_timetable_rows` reindexes existing records and checks incoming station
connections; explicit `reference_policy: "detach"` removes affected dependencies.
An incomplete remaining timetable is a reviewable invalid draft, not ready data.

`create_interval_courses` copies an existing Course/timetable sequentially with
native time and connection-number rules; see [interval Courses](interval-courses.md).

`propagate_interval` affects the original direct reference family at matching
station/index; `propagate_delays` separately affects delay/distribution. Time
changes propagate deltas, clear undefined values, or apply stored offsets when
newly defining a time. Conflicting origins reject. Whole-row connection lists
are applied to explicitly selected rows only. No native preferences are read.
Fractional offsets requiring subsecond output from an undefined time remain
unsupported. `set_timetable_interval` edits references/offsets without shifting
times; null detaches while preserving an omitted offset. Cycles reject.

`edit_timetable_connections` uses one `row`, optional indexed `updates`,
`delete_indices`, `append`, or `clear`. Update/delete indices refer to the old
list and cannot overlap. Location is exit/entry/dispo; time-reference type is a
separate raw native integer. Null maximum_wait_s clears its limit. Join/split,
minimum wait and dispatching distance remain independent.

Indexed updates can set `propagate_interval:true` to copy the original whole
property set by corresponding connection index through the direct family.
Target Course IDs and dispatching distances remain specific to each connection;
missing slots skip. Append/delete/clear remain separate local commands.

`reset_timetable_actual` clears saved actual strings/days. `copy_actual_to_planned`
copies defined saved actual values without certifying the unpersisted native
validity flag. `sync_timetable` removes orphan rows; explicit detach cleans
dependent connections/interval references. Station renaming can optionally use
`rebind_station_connections` for one unambiguous new target after the last old
visit disappears. Review reference errors rather than inventing targets.

Use `opentrack_export_timetable` for a fresh artifact: `opentrack_17` (16/8
columns), `opentrack_16` (14/7), or mapped `json`. Native text uses tabs and
`// Connections:`; it cannot represent actual times/dispatching distance. Legacy
also omits track/mass/time type. Read omitted-field warnings and output hashes.
Text location flags 16/32 differ from archive bits 4/8; let the interface convert.

Import with `kind: "import_timetable_text"`, exactly one of `content` or
`file_path`, and `existing: "reject" | "replace" | "merge"`. File paths must
stay inside existing project/data/workspace read roots. Prefer files for large
inputs or CLI use. Input bytes are snapshotted; later changes do not alter the
draft. Merge preserves omitted-format fields, actual data and unlisted connections.

For new Course IDs, supply `templates: [{course_id,template_id}]` or one
`default_template_id` with correct formation and direction. Explicit
`create_unbound_courses: true` creates unbound definitions with validation errors
for later binding; never treat them as simulation-ready.

Review validation, `timetable_changes_json`, CSV and current native text export.
Generation emits full diffs to files with compact response previews. Shared
budgets apply across definitions, imports and edits. Unknown formats and
Original proprietary XML is described in [timetable XML](timetable-xml.md).
RailML timetable and other exchange variants are not covered here. The packaged contract
`OTAI/contracts/timetable-editing.md` records primary evidence and scope limits.
