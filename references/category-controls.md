# Current Train Category controls

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

Use the current original OpenTrack 1.7 Category v19 format. This Skill/MCP is
under local development; do not add old API or archive compatibility layers
unless explicitly requested. Keep the original English application baseline.

The historical, currently quarantined batch contract defined `categories` or `rolling_stock_operations` with
`kind: update_categories`, exact `names` and only the fields to change. Query
`opentrack_list_catalog` with `kind: categories`, or inspect a Course's
`category_details` through `opentrack_get_service`.

Beyond priority and delay/performance tables, current fields include:

- `stop_at_every_station_time_s`, `timing_stations_type_code`.
- `foreground_color` and `background_color` (calibrated RGB or white).
- Signed `dwell_variation_early` / `dwell_variation_delayed` and their
  `*_unit_code` (0 seconds, 1 percent of planned dwell).
- `delay_add_type_code`, `default_connection_time_s`.
- `departure_process_time_s`, `departure_process_starts_at_departure_time`.
- `track_name_creation_type_code` and early/delayed `*_delay_offset_s`.

Early offset must be <= -1 s and delayed offset >= 1 s. Readback exposes
`pre_departure_process_time_s`; it is zero for starts-at-departure, otherwise
the saved process time. The native saved start flag is inverted; let the API
encode it instead of writing it as a normal bit.

Omit fields to preserve them. Partial changes preserve other Category settings,
tables and colors. Review the full stock diff and binding validation, then save
an isolated project as needed. Category policies do not automatically rewrite
existing timetables; automatic default application and runtime dwell/performance
behavior are separate work. No GUI or simulator is started.
