# Maintain original Engines, formations and Categories

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

The quarantined legacy batch used `rolling_stock_operations` in `opentrack_generate_operations` for an ordered
batch after definitions, Course lifecycle and timetable operations. Inspect exact
names first. The same operations work in stage/edit-editor changes and support
the API's isolated snapshot undo.

## Update existing data

Use `update_engines`, `update_formations` or `update_categories`, with `names`
and supplied fields from the corresponding creation schema. Omitted fields are
preserved; null is rejected. Use this for maintenance: `replace_existing` in
creation can rebuild curves/consists and apply creation defaults.

```json
{
  "project": "OTProjects/MyLine",
  "rolling_stock_operations": [
    {"kind": "update_engines", "names": ["EMU400"], "understands_radio": true},
    {"kind": "update_formations", "names": ["EMU8"], "acceleration_delay_s": 3},
    {"kind": "update_categories", "names": ["High speed"], "dispatching_priority": 1}
  ]
}
```

Scalar edits preserve saved curves, braking data, consist positions and omitted
category distributions. Cross-field constraints use resulting saved values.
Supplied `engines` or `trailers` replaces only that list. Free positions avoid
preserved units; supply both lists when shrinking requires repositioning.
Supplied category names must exist. New braking data must cover all unit limits.

Explicit Engine `traction_points` or `nominal_power_kw` edits require a single
saved diagram and preserve independent voltage/efficiency/braking/color data.
Multiple diagrams survive scalar edits. Use `tractive_effort_diagrams` for full
replacement or `edit_engine_diagrams` for selected diagram changes; see
[Engine diagrams](engine-diagrams.md). Power proxies remain uncalibrated. A
scalar speed change must fit the combined diagram extent; review the timetable.

## Rename and delete

Use `rename_engines`, `rename_formations` or `rename_categories` with
`renames: [{"name":"old","new_name":"new"}]`. Swaps are simultaneous. Names are
exact, descriptions remain intact and category order is preserved. Engine names
rebind formation components; formation names rebind Courses; category names
rebind formations and diagram hidden-category names. Train Categories and
Conflict Categories are separate original namespaces.

Use `delete_engines`, `delete_formations` or `delete_categories` with `names`.
Default deletion reports referenced records. Supply `replacement` for an exact
surviving name, or explicit `reference_policy: "cascade"` to delete dependent
formations, Courses and their saved timetable/reference data. Review the complete
dependency diff before applying. At least one Train Category must remain.

Category deletion also maintains category-indexed coasting/performance signal
arrays and diagram hidden membership. Renaming preserves those index positions.
Unknown layouts or inconsistent array sizes are rejected with evidence details.
Read `OTAI/contracts/stock-maintenance.md` in the source/MCP package for the exact
saved-record contract; discovered input schemas remain authoritative.

Review `rolling_stock_changes_json`, validation and resulting service bindings.
Responses contain bounded previews; artifacts retain complete diffs and cascades.
These are original-format data operations. Native software is not started and
native loading/simulation acceptance remains separate.

## Decoder versions and corrected time fields

Use `rolling_stock_operations: [{"kind":"migrate_rolling_stock"}]` for an
explicit current-version draft. Optional `entities` selects `engines` and/or
`formations`. Stock edits/imports prepare Engine 0..2, diagram 0..3, Train 0..16
and Trailer 0..3 with original defaults. Check `serialization_migrations`.
Read-only views decode copies. Unknown future layouts fail explicitly.

After API 0.18, Train `minimum_time_to_hold_speed_s` correctly maps to group 20
and `acceleration_delay_at_stop_s` to group 22. Earlier APIs reversed them. Saved
values are preserved; re-submit explicit intended values if these fields were
set through an earlier API. See `OTAI/contracts/stock-versions.md` in the package.
