# Generate and inspect original rolling stock

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

The currently quarantined legacy batch contract used `opentrack_generate_operations` with Engines → Categories → formations →
Courses in one batch. Inspect `opentrack_get_schema` for `OTEngine`, `OTTrain`
and `OTTrainCategory` before assigning native field meanings. No native software
is started; data checks finish the generation task.

For existing-record partial changes, simultaneous renames and dependency-aware
deletion, read [maintenance](stock-maintenance.md). Creation with
`replace_existing` rebuilds curves/consists and may apply creation defaults;
use `rolling_stock_operations` to preserve omitted fields.

## Categories

`categories` items use unique `name`, `dispatching_priority` (1 is highest),
`look_ahead_distance_m`, `look_ahead_time_s`, and an inspected native
`dispatching_type_code`. Bind `formations[].category` to that exact name. This
is where dispatch priority belongs; the deprecated Course `priority` is rejected.

Category inputs also cover initial/station delay flags and parameters, delay
thresholds, delay-dependent `delay_priorities`, and on-time/delayed performance
tables. Probability intervals use `minimum`, `maximum`, `probability_percent`;
ordered non-overlapping intervals must sum to 100%. Delay priorities use
`delay_s` and `priority`, with increasing thresholds. `use_on_time_performance`
or `use_delayed_performance` requires a nonempty corresponding table.

Native distribution/dispatch menu tags are returned and accepted as codes.
Do not guess a strategy name for an unknown tag. The interface stores tables;
it does not sample delays or establish that a dispatch policy works in a run.
Unspecified wrapper data and later unsupported attributes remain intact.

## Engines

Alongside mass/length/speed/force and full-range traction points or an explicit
constant-power proxy, optional inputs cover `cw_value`, `strahl_resistance_factor`,
`adhesion_code`, `minimum_force_kn`, `drive_type_code`, `voltage_type_code`,
cross-section girth/area, and `understands_balise`, `understands_loop`,
`understands_radio`, `rack_and_pinion`. Codes preserve original menu values;
they are not a claim that every signalling/electrical behavior is implemented.

The stored maximum kW can be supplied as `maximum_power_kw`; otherwise generation
uses nominal proxy power or the peak explicit curve data. Read scalars through `list_catalog(kind: engines)` or
service `engine_details`. Request `include_curves: true` only when the actual
points are needed. For multiple supply diagrams, electrical braking, loss-function
input and ordered diagram editing, read [Engine diagrams](engine-diagrams.md).

## Formations and braking

Mixed consists retain explicit Engine/Trailer positions and totals. Additional
formation inputs cover native train-type tag, acceleration delays, drawbar
limits, braking delay/release speed, resistance coefficients/formula codes and
available curve-resistance/speed-hold fields. Omitted optional inputs preserve
the selected template. Audited older stock layouts migrate in the draft; an unknown layout is rejected
with `ROLLING_STOCK_VERSION`; do not silently upgrade an unaudited class.

`braking_points` supplies increasing integer `speed_kmh`, positive
`deceleration_mps2`, optional positive `secondary_deceleration_mps2`. It must
start at zero and cover all unit speed limits. Native values are negative; new
tables use native table formula 0. A speed-dependent primary table has a native
NaN average marker. Public JSON returns `null` for that marker, not a fake zero
or nonstandard NaN. Engine/Train data checks are not a calibrated braking or
physics acceptance claim.
