# Wave8 current saved-data additions (review candidate)

Two endpoints add bounded data workflows, not full simulation or GUI control.
Keep the original 176-feature requirements unchanged. Tool count is not function
coverage; review these additions separately before changing aggregate counts.

## Native Connection commands

`opentrack_apply_current_connections` accepts five actual SHA-bound source files:
Timetable9, Course11 catalog, Train16/Category19 catalog, Station catalog and an
explicit real Connection6 stock template. The five files must be distinct and
located in the same authorized project catalog directory. Copying the packaged
stock template into a test project is explicit fixture preparation, not proof
that the original project stored that template there. No fabricated wire layout.

Commands: bound `insert`, indexed `delete`, `turnround_to`, `turnround_from`.
Use exact course_id, row index and target_course_id (delete uses connection_index
instead). Inspect the authoritative schema. Preview is default; save only to an
explicit fresh target_path. All five dependencies are rechecked before/after
publication. Existing Connection owner and station must match its row; targets
must be real Courses with a timetable visit at the target Station. First-match
and repeated-target semantics are retained, not replaced with uniqueness rules.

Native per-owner Category default is retained, including the proven 420-second
fallback if the Course's Train/Category lookup is absent. Reports record default
provenance per created connection. This fallback is not a claim that every Train
binding is resolved. Engine/Itinerary/geometry/run windows are outside this check.
Turnround writes reciprocal saved records. It does not prove executable vehicle
circulation, coupling, braking, capacity, or one-day simulation completion.

## Narrow six-catalog batch

`opentrack_batch_current_catalogs` accepts distinct, same-directory SHA-bound
depot, trains, courses, dest, stations and timetable catalogs. It exposes only:

- Engine cw_value 0..100 finite float and understands_radio strict boolean.
- Course acceleration_percent and delayed_acceleration_percent strict 50..100,
  and printable ASCII comment up to 240 characters. Not braking percentage.
- Planned arrival/departure shifts by integer seconds for selected existing
  Courses. Actual times remain unchanged; include_actual=true is rejected.
  Undefined planned time must have day offset 0; day type/range is checked even
  for nil/HH:MM:SS. Midnight is normalized; invalid late rows abort the batch.

Default preview does not save. Save uses a fresh target_directory with the
existing atomic no-replace six-catalog publisher, never replaces original files.
This is a catalog increment, not a complete relocated Project. No documents,
.run file, corridors or infrastructure geometry are validated or included.

The Engine cw float batch is genuine reuse of the prior Python batch operation,
not equivalence to the original C integer setter. Native Course setters clamp;
this API rejects values outside the narrower domain. Six original timetable
methods retain AST equality; the explicit current-only time helper adaptation
includes the undefined-day fix. No legacy Project stubs or GUI automation.

## Legacy whole-project quarantine

Legacy create_project, generate_operations, stage_changes, start_editor,
edit_editor, publish_draft, apply_draft and create_demo_line are explicitly
blocked with LEGACY_GEOMETRY_DISABLED, independently of optional dependency
availability. Old worksheet show_grid incorrectly mapped a protected Document
flag, and legacy factories assigned an unverified group18 identifier. No such
field is changed or repaired by this release. Old draft publication is blocked
as well. Read-only worksheet output no longer mislabels that flag as show_grid;
it reports show_grid as unavailable and does not expose the protected value.

This does not disable bounded current_archive APIs, including the tested Edge,
Route, Path, Itinerary and catalog operations. It also does not establish that
arbitrary topology generation is complete. Do not restore optional legacy
libraries to try to bypass the explicit quarantine.
