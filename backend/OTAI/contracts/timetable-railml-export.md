# Original RailML 2.2 timetable export

`opentrack_export_timetable(format="railml_2_2")` writes a fresh XML artifact
and full JSON manifest from current original stock English OpenTrack 1.7 saved
data. It never changes the input project or starts OpenTrack. RailML timetable
import remains incomplete; proprietary timetable XML is a separate format.

## Function evidence before implementation

`artifacts/research/timetable-railml-export-v027.json` pins the original binary,
bank and C hashes. A metadata-driven pass regenerated 76 functions and reduced
its recorded unresolved calls from 37 to 13. Reviewed string receivers use
NSString length; timetable wait getters retain their object return. The shared
Course number/ID getter uses their common object/no-explicit-argument signature.
No instruction-level review was used for this pass. Remaining importer shared
calls and aggregate returns stay unverified.

The writer follows OTOutputController's original Header, Stations, RollingStock,
PlannedPublishedCalculated, IntervalTrains and Footer functions (entries
`0x546d14`, `0x546e40`, `0x54728c`, `0x547508`, `0x548d9c`, `0x546e04`), plus
their model/getter/coder callees. Generated C is not recovered original source.
An independent XML parser and real MCP verify the supported data operation;
no native parser/GUI or XSD acceptance is certified.

## Arguments and data

`course_ids` selects exact saved timetable Courses; empty selects all. Rows must
have consistent contiguous indices and last indices. Native output writes all
saved Stations and all formations even when only some Courses are selected.
The railway infrastructure graph, full vehicles/traction/braking and operational
state are not part of this timetable export.

`railml` options:

| Field | Behavior |
|---|---|
| `dataset_name` | Explicit original set title; null uses project name with a warning |
| `metadata_date` | Explicit date text for reproducible export; null uses local original-style text |
| `planned` | Scheduled times; default true |
| `published` | Publishes the same saved planned strings with scope=published |
| `calculated` | Requests actual strings; defaults false |
| `only_active` | Keeps enabled Course definitions; filters connection targets too |
| `existing_stations_only` | Trims to existing endpoint stations and skips missing interior stations |
| `station_filter` | ASCII uppercase, prefix/suffix replacement and original trailing-space removal |

If all three time options are false, the original writes scheduled times anyway.
Calculated output requires explicit `saved_actual:"as_valid"`; otherwise actual
blocks are omitted and reported. Calculated-only plus omit can contain no times.
Actual validity is transient and cannot be recovered from these archives. No
option here certifies that native actual data is valid.

The station filter performs uppercase first, replaces the first N characters
if current length is at least N, then the last N using the resulting length.
Zero inserts/appends replacement strings. Finally trailing spaces are removed
while preserving the first character. A null filter does none of these steps.
Existence filtering uses original signs before name transformation.

Formation length/mass are saved unprepared integer summaries: each Engine ref
and Trailer record contributes once; `number_of_items` does not multiply them.
Missing Engines contribute zero with warnings, as the original nil lookup does.
Transient preparation and delta mass are unavailable; zero delta is explicit.
To avoid guessing unrecovered wide return/conversion precision, absolute summed
dimensions are bounded below 2^24 and cumulative sums to signed int32. Larger
values reject with `TIMETABLE_RAILML_METRICS_PRECISION`/numeric errors. This is a
bounded saved-data export, not full runtime metric parity.

## Preserved original behavior and losses

- Station XML uses the native typo `abbrevation`, plus code/name and description.
  Valid raw coordinates are printed **latitude then longitude**. Original numeric
  prefix conversion can accept nonnumeric nonempty strings as zero; those raw
  coordinates are preserved with warnings, without XSD validity claims.
- Each Course produces one trainPart and operational train. Part additional
  number prefers saved Course train_number; train additional number remains CID.
  Description and formation refs follow the original writer.
- Defined clock strings receive `.0`; only positive day offsets are emitted.
  Raw dwell text other than exactly `"0"` emits `PT<raw>S`, including `"0.0"`.
- Connections retain train/trainPart refs and meet/join/split/none. Undefined
  minimum becomes zero; only positive maximum values are emitted. Native wait
  validation accepts second=60 and then reduces it modulo 60.
- `connStationSign` falls back to the connection's owner station when empty.
  If that effective sign differs from the timetable row's sign, the original
  wrongly writes `ocpRef="tp-<target CID>"`. This bug is preserved and reported.
  Reference checks are type-specific: an existing trainPart ID is not an OCP.
- Interval groups use first-row direct references. Reference train is first,
  children follow Course/index order; no recursive flattening or time offset
  serialization is invented. Filters/selection can leave a root-only group.
- Native ID normalization can produce collisions or non-NCNames. Output is
  retained with full diagnostics. Unknown/missing targets are not silently fixed.

The full manifest records omitted Course controls/Itineraries, timing flags,
delays/distributions/delta load, interval offsets, connection location/time code/
distance, vehicle parameters and runtime validity. XML is not a database backup.
The fixed metadata source text follows the original layout; it is not evidence
that OpenTrack generated the file. Course ordering is applied to a copy; native
Foundation dictionary enumeration and non-ASCII collation are not replicated.

Limits: 10000 selected rows/connections and Stations/formations, 2 MB escaped
ASCII XML. Existing caption contracts and explicit encoding errors apply.
The response previews 20 warnings and 50 skipped Courses; follow `manifest` for
all details. `skipped_course_count`/preview flags expose truncation. Exported
bytes can be checked with the read-only RailML inspector; import still is absent.
