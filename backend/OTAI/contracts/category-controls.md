# Current original Train Category controls

This is a local development interface for original English OpenTrack 1.7.
Unpublished previous API versions and old Category formats are not compatibility
targets. New Category definitions and advanced edits require current v19 records.
No old Category migration or legacy percentage reinterpretation is implemented.

Use `categories` to define a Category and `rolling_stock_operations` with
`kind: update_categories` to edit exact names. Catalog/service readback returns
these saved controls. Existing tables, unknown flags and omitted values survive
partial updates. Supported colors are calibrated RGB/white; omitted unsupported
native colors are retained.

Original `OTTrainCategory.encodeWithCoder:` (`0x6c513c`) defines 25 groups:

| Group | Current saved data |
|---|---|
| 0..14 | Flags, name/foreground color, dispatch priority/look-ahead, delay/performance tables and thresholds; see rolling-stock contract |
| 15 | `stop_at_every_station_time_s` |
| 16 | `timing_stations_type_code` |
| 17 | `background_color` |
| 18 | Signed `dwell_variation_early`, `dwell_variation_delayed`, their respective unit codes |
| 19 | `delay_add_type_code` |
| 20 | `default_connection_time_s` |
| 21 | `departure_process_time_s` |
| 22 | Inverse of `departure_process_starts_at_departure_time`: true writes 0, false writes 1 |
| 23 | `track_name_creation_type_code` |
| 24 | `dwell_variation_early_delay_offset_s`, `dwell_variation_delayed_delay_offset_s` |

`foreground_color` uses group 2. Native dwell units are 0=seconds, 1=percent
of planned dwell, independently for early and delayed trains. Signed variation
values are intentional (original 1.7 release notes, feature 23). Early delay
offset must be <= -1 s; delayed offset >= 1 s, matching original setter bounds.
Invalid input is rejected before saving. Unknown native integer policy codes
are preserved and remain unlabelled rather than assigned guessed meanings.

`pre_departure_process_time_s` is derived readback: zero when the start-mode is
at planned departure time, otherwise the saved process duration. It is verified
from the original getter; it is not a running simulation clock or dispatch event.

Example:

```json
{
  "project":"OTProjects/Example",
  "rolling_stock_operations":[{
    "kind":"update_categories", "names":["High Speed"],
    "stop_at_every_station":true, "stop_at_every_station_time_s":90,
    "dwell_variation_early":-15, "dwell_variation_early_unit_code":1,
    "dwell_variation_delayed":20, "dwell_variation_delayed_unit_code":0,
    "departure_process_time_s":30,
    "departure_process_starts_at_departure_time":true,
    "default_connection_time_s":240,
    "background_color":{"space":"calibrated_white","white":0.85}
  }]
}
```

The fields are saved Category policies. This operation does not alter already
defined timetable rows, calculate random performance, or run dwell/departure
logic. Explicit `create_timetable_skeletons` applies stop/timing/dwell/track
defaults; read [automatic creation](timetable-creation.md). Color spaces outside calibrated RGB/white and
other original Category commands remain on the complete function inventory.

Evidence: `artifacts/research/category-controls-v020.json`, original coder and
setters/getters, current native serialization blueprints, exact-group persistence,
partial edits, persistent undo and real MCP publication tests. No OpenTrack
application, UI or native method is executed.
