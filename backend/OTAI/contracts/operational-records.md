# Original 1.7 operational record contract

Baseline: stock English `OpenTrack.app/OpenTrack.exe`, SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Evidence: `artifacts/research/operational-layouts.txt`, original manual sections
5.1.2 and 6.2, and frozen original Demo objects under
`tests/fixtures/stock-operational`. Native methods were inspected statically;
no native code was invoked. These are verified serialization operations, not a
claim that all native initialization, physics or dispatch behavior is reproduced.

## Course fields and v0.6 correction

Original `OTCourse.encodeWithCoder:` at `0x456b6c` maps group 0 to Course ID,
1 to entry speed **in m/s**, 2 to Itineraries, 3 to Train name, 4 to speed type,
5 to enabled, 6 to on-time acceleration percentage, group 7 slot 0 to output
offset in metres, 8 to reservation/release mode, 9 to delayed-course acceleration
percentage, 10/11 to description/comment, group 12 to reservation/release times,
13 to display train number and 14 to Kind/course type.

v0.6 incorrectly named group 6 `priority`, and assigned `course_type` to group 13.
v0.7 rejects `priority` with an explicit migration message; it never silently
interprets dispatch priority as a physical acceleration factor. Dispatch priority
belongs to a Train Category and is not set by this Course parameter. Existing
archives are not automatically rewritten. If an older request used `priority`,
review its generated Courses and explicitly set the intended acceleration
percentages in a new draft. Default percentages remain 100.

The public input uses `entering_speed_kmh` and converts to native m/s. Train
number and Kind are independently settable optional ASCII strings. The golden
stock Course `IC4000` has acceleration 93%, display number `IC4.1.100` and empty
Kind; independent assertions prevent reader/writer agreement from hiding swaps.

## Timetable fields

The original `OTTimetable.encodeWithCoder:` at `0x67b390` serializes these fields.
The distinct runtime offsets explain the order; use **archive group indices**
for edits, not runtime byte offsets.

| Archive group | Meaning | Runtime ivar offset |
|---|---|---|
| 0 | Internal format version, current 17 | local coder value |
| 1 | Course ID | 4 |
| 2 | Interval reference Course ID | 76 |
| 3 / 4 | Row index / maximum row index | 44 / 48 |
| 5 | Station sign | 52 |
| 6 / 7 | Arrival / departure time strings | 12 / 20 |
| 8 | Minimum dwell, numeric string in seconds | 56 |
| 9 | OTConnection array | 72 |
| 10 | Packed stop (1) and timing-station (2) flags | 60 / 61 |
| 11 | Seconds from interval reference, float | 80 |
| 12 | Mean delay, numeric string in seconds | 84 |
| 13 / 14 | Actual arrival / departure strings | 28 / 36 |
| 15 | Four day offsets: arrival, departure, actual arrival, actual departure | 8 / 16 / 24 / 32 |
| 16 | Delay distribution name | 88 |
| 17 | Delta mass in tonnes, float | 68 |
| 18 | Track ID string | 64 |

v0.6 generation incorrectly assigned `track_id` to group 2 and left group 18
empty. v0.7 fixes this mapping. New generation uses the original unset interval
reference `0`. The native decoder at `0x67b315` also recognizes `-1` and an empty
string as unset; existing values are preserved. These constants are confirmed
in the binary's constant NSStrings, not inferred from a failing test.

For all chronological comparisons, `absolute_seconds = day_offset * 86400 +
HH:MM:SS`. Generation supports explicit day offsets -366…366. Pattern offsets
and time shifts carry into previous/following days; the tool never guesses
midnight from descending same-day clock strings. Undefined scheduled times use
`HH:MM:SS`. Newly generated actual times are cleared and their day offsets zero.

`Start Day Offset` / `Stop Day Offset` are real `.run` keys. The simulation-input
edit persists these with clock strings and updates corridor time windows using
absolute seconds. This edits inputs; it does not start or certify a simulation.

Original Timetable class v7 has 17 groups; v8 has 18. Native decoder branches
default missing delta mass to zero and missing track to an empty string. Before
generating new v9 rows, all v7/v8 rows in the **draft** catalog are upgraded with
those defaults and internal version 17. v9/current rows remain intact. Older or
unexpected layouts are rejected instead of inferred. This avoids writing
incompatible layouts of the same native class into one new catalog.

## Mixed train formations

`OTTrain` group 2 contains deceleration array, Engine references and Trailer
records, in that order. `OTTrainEngine[1]` is position, not quantity.

Original `OTTrailer.encodeWithCoder:` at `0x6ba458` writes inherited OTVehicle
groups followed by:

| Group | Meaning |
|---|---|
| 1 | Trailer name |
| 2 | Reserved, mass_t, length_m, rotating mass factor, axle count, Cw |
| 3 | Reserved, position in train, number of items |
| 4 | Maximum speed in km/h |
| 5 | Auxiliary power loss in kW |
| 6 | Delta-load power-loss factor in kW/t, introduced in v3 |

The original `+[OTTrailer initialize]` at `0x6b9f64` sets archive class version 3.
The v2 Demo sample omits group 6; decoder `0x6ba429` defaults it to zero. Audited
v0/v1 defaults for absent maximum speed/power loss are 1000 km/h and zero. The
generator upgrades existing Trailer v0/v1/v2 records together in the draft when
adding v3 records, preserving stored values and supplying only native defaults.

The public model uses `count` to expand physical records. Optional `positions`
must contain exactly `count` unique numbers. All powered/trailer positions form
1…N with no duplicate or out-of-range explicit positions; omitted positions use
remaining slots. Trailer mass/length are totals **per record**. `number_of_items`
is a resistance parameter described in the original manual, not a multiplier
for mass/length. Aggregate length is the sum of all Engine and Trailer records;
the formation's speed limit is their minimum. No rolling-stock circulation,
coupling execution or calibrated resistance calculation is certified.

## Connections and interval references

`OTConnection.encodeWithCoder:` at `0x7116ec`, current class version 6:

| Group | Meaning |
|---|---|
| 0 / 1 | Owner Course ID / target Course ID |
| 2 / 6 | Owner station / target station |
| 3 / 5 | Minimum / maximum wait strings |
| 4 | Packed join (1), split (2), entry (4), dispo (8) flags |
| 7 | Connection time-reference type |
| 8 | Dispatching distance in km |

Generation supports passenger/entry connection records and optional join/split
flags. Maximum wait `None` is the native `HH:MM:SS` placeholder. Time-reference
type and dispatch distance remain the native zero defaults; generating dispo
connections and executing dispatch/coupling behavior remain unsupported. Known
older Connection versions can be upgraded to v6 using decoder defaults.

Connections can reference Courses created later in the same batch. Final
preflight checks exact target Course and station-row references before any
project write. Owner Course/station fields are synchronized; cloning a Course
rebases connection owner IDs. Course IDs containing original-style spaces such
as `RE 5830` are supported without trimming or case normalization.

`keep_interval_reference` links repeated services to the first Course, with
per-row offsets in seconds. The first service uses unset reference `0`.
`serialization_migrations` reports catalog record upgrades in the draft result.
Static validation checks reference consistency; it does not prove feasible
transfer times, dispatch headways, join/split execution or absence of deadlocks.
