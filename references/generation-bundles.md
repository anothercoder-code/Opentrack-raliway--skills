# Information-only bundles: actual tool, narrower evidence

`opentrack_prepare_operations` accepts production `GenerateOperations` definitions
without importing native archive dependencies. Use it for an information request,
preview or when native parsing is unavailable. Confirm discovery in the current
server; this is not a substitute spelling for `opentrack_generate_operations`.

## Input contract

- `operations`: the real `GenerateOperations` object, including `project`, optional
  `run_file`, label and supported arrays. It prepares definitions, new Courses,
  `patterns` and explicit `timetables`; do not wrap the human intake template here.
- `external_catalog`: name lists for `engines`, `categories`, `formations`,
  `stations`, `paths`, `itineraries`, `courses`, `speed_types`; `routes` is a list
  of typed Route selectors. Prefer actual catalog evidence, but a user-supplied
  catalog can be used as an explicit assertion. Adding a name does not verify it
  exists in a project or grant permission to overwrite it.
- Optional `previous_operations` and `expected_previous_sha256`: compare against
  an earlier prepared payload. Use the actual returned hash; a stale baseline
  errors rather than silently changing the baseline.
- `include_csv` defaults false; request true for CSV output.
- `offset` defaults 0, `limit` defaults 50 (maximum 200): timetable preview paging.
  Check `has_more`/`total_count`; a page is not the complete timetable. Requested
  CSV covers all prepared rows, not preserved rows from an unread native project.

The output includes canonical `operations`, `prepared_sha256`, `dependency_order`,
`entity_changes`, optional `difference`, counts and timetable preview/CSV. A
baseline `difference` identifies changed sections, not an archive byte diff.
The prepared hash is not a native source digest, identifier reservation, apply
receipt or promise of idempotent application.

## Evidence and next step

Inspect `evidence_level`, `native_archive_created`, `native_apply_performed` and
`native_simulation_verified`. Information-only success is
`schema_and_input_reference_validation`; the native flags remain false.
Reference presence, duplicate identifiers, bounded expansion, chronology, dwell
and formation-position checks do not verify physical topology/Route continuity,
archive templates, traction/braking adequacy or native execution. External
catalog identifiers and speed types remain caller assertions even on success.

Supported pure preparation omits maintenance/import operations. If the tool
returns `PREPARATION_SCOPE`, separate a useful supported definition batch only
if doing so preserves the requested meaning; retain unsupported commands and
report their need for native validation. Do not drop them silently.

The prepared `operations` shape is historically compatible with
`opentrack_generate_operations`, but that native writer is currently quarantined
with `LEGACY_GEOMETRY_DISABLED`. Information-preparation success does not enable
it. Use a matching current_archive tool or original-app workflow only after
reviewing its different actual contract; no automatic alias/conversion is supplied.
Other native dependencies may separately fail with `NATIVE_DEPENDENCY_MISSING`;
report the missing dependency and keep the useful information bundle. No fake
`draft_id` or archive-ready assertion. Preserve the authorized execution host and
data root; a separate local path is available only when already authorized or
newly agreed, never as a silent environment change.
