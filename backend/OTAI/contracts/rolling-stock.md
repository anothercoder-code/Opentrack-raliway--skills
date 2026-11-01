# Original 1.7 rolling-stock data contract

Baseline EXE SHA-256:
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Evidence: original manual chapter 5, `artifacts/research/rolling-stock-layouts.txt`
and `rolling-stock-metadata.json`, plus frozen stock sample objects in
`tests/fixtures/stock-operational`. All method inspection is static. This contract
defines data generation/readback; it does not reimplement physics or dispatch.

## Categories and real dispatch priority

`OTTrainList[1]` contains Category records. `OTTrainCategory.encodeWithCoder:`
starts at `0x6c513c`. Both stock v11 and current v19 share these first 15 groups:

| Group | Meaning |
|---|---|
| 0, slot 0 / 1 | Reserved / packed flags |
| 1 / 2 | Name / foreground colour |
| 3, slots 0 / 1 | Dispatch priority / look-ahead distance in whole metres |
| 4 | Initial delay mean seconds, maximum seconds, percentage |
| 5 / 6 | Maximum station delay seconds / look-ahead seconds |
| 7 | Small, medium, large delay thresholds in seconds |
| 8 / 9 | Station delay percentage / initial delay distribution native tag |
| 10 / 11 | Initial delay interval wrapper / dispatch selection native tag |
| 12 | Delay-dependent priority table wrapper |
| 13 / 14 | On-time / delayed performance interval wrappers |

Packed flags: use=1, initial delay=2, station delay=4, on-time performance=8,
delayed performance=16, stop at every station=32. Other bits are preserved.
Category priority **1 is higher than 2**. It is unrelated to Course acceleration
percentage. Duplicate names require explicit `replace_existing`.

Interval records contain `(minimum, maximum, probability_percent)` floats.
Delay-priority records contain `(delay_s float, priority int)`. Input probability
tables are ordered, non-overlapping and sum to 100%; priority thresholds strictly
increase. Native menu codes are exposed as codes instead of guessing labels or
claiming an executed distribution. The tool does not sample random delays.

Current v19 colors, dwell variation, departure process and station/default
policies are supported by [Category controls](category-controls.md). Omitted
values and wrappers are preserved; no old Category migration is provided.

## Engines

`OTEngine.encodeWithCoder:` at `0x4ccc54` writes inherited OTVehicle groups then:

| Group | Meaning |
|---|---|
| 2 | Reserved, mass tonnes, length metres, rotating mass factor, axle count, Cw |
| 3 / 4 / 5 | Adhesion mass tonnes / Strahl resistance factor / adhesion code |
| 6 / 7 / 8 | Maximum force kN / maximum speed km/h / maximum power kW |
| 9 / 10 | Driven axles / traction motor count |
| 11 | Packed balise (1), loop (2), radio (4), rack traction (8) flags |
| 12 / 13 | Drive type / voltage type native codes |
| 14 / 15 | Cross-section girth metres / area square metres |
| 16 / 17 | Tractive-effort diagram array / minimum force kN |

The generator sets maximum power to the supplied nominal kW or derives the peak
of the explicit speed/force data. It never leaves a different template power
unchanged after defining a new curve. This is stored data, not an independent
motor/efficiency model. A nominal-power curve remains explicitly uncalibrated.
Unspecified optional parameters preserve template values; supplied flags update
only their own bits. `include_curves: true` returns full point data; normal
catalog/service queries return scalar parameters and diagram counts.

Multiple saved supply diagrams and efficiency curves are supported by the
Engine-diagram contract. Full electrical-system runtime behavior remains outside
these data operations; unknown menu-code meanings are not guessed.

## Trains

`OTTrain.encodeWithCoder:` at `0x6c2dbc` verifies:

| Group | Meaning |
|---|---|
| 1 | Train type, reserved integer, average native deceleration |
| 2 / 3 / 4 | Deceleration/Engine/Trailer arrays; category name; maximum acceleration |
| 5 / 6 / 7 | Native Excl coefficient triple; resistance formula tag; Incl coefficient triple |
| 9 / 12 | Acceleration delay seconds; braking formula tag and braking percentage |
| 14 / 15 | Maximum drawbar force kN; packed use-drawbar (1), use-minimum-hold (2) flags |
| 16 / 17 / 18 | Braking delay seconds and release speed km/h; delay type; curve-resistance formula |
| 19 / 20 / 22 | Curve-resistance percentage; minimum speed-hold seconds; acceleration delay at stop |

Old v12 records end at group 18; later fields are available in current v16.
Audited versions 0..16 decode to current defaults and migrate in stock-write
drafts; see [decoder versions](stock-versions.md). Unknown layouts are rejected. Optional attributes preserve existing values when
omitted. The coefficient names follow native Excl/Incl fields; formula/unit
interpretations are not guessed by a substitute physics engine.

`braking_points` uses positive input decelerations, stored as negative native
values at increasing speeds covering the declared unit speed range. New
constant or explicit tables select original table formula code 0. A varying
primary table stores the native NaN average marker, also present in original
stock examples. Public JSON represents that marker as `null`, never invalid JSON
NaN. This preserves native data representation without claiming braking-distance
or simulator equivalence. Full ETCS/ATC/braked-weight and resistance behavior
remain unverified original-function coverage.
