# Automatic timetable station rows

Target: current original stock English OpenTrack 1.7, EXE SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Function-first evidence: `artifacts/research/timetable-creation-v021.json` and
portable bank `bank-v021-timetable-r2`. This is a local development interface.

`create_timetable_skeletons` accepts unique existing `course_ids` (1–1000)
and optional `replace_existing` (false). Saved rows require explicit replacement.
The operation is available in generation, Stage and persistent editor history.
Definitions/Course edits/lifecycle and ordered rolling-stock edits precede the
ordered timetable commands, so same-batch Category updates are applied.

## Original station selection

`OTTimetableController.newTimetableForCourse:` (0x685230) calls the collector
(0x68a310) on the Course's **first** Itinerary. It does not merge alternatives.
Loaded Path/document/ID references must match. Route traces include verified
continuations into other documents. Unloaded or ambiguous references reject.

The collector includes the first End when it belongs to a station, then walks
each Path/Route for station vertices or halt/exit signals. Halt signal types are
6, 8–11, 16–21, 28–38, 51 and 52. Exit signals are main types 1, 2, 24, 25 or 26
with main subtype 4. Ordinary candidates need a nonempty station sign.
`OTStationEndModel` is a distinct original OTEndModel subclass without extra
ivars. Existing archives containing it are recognized by graph, worksheet and
protection readers. This does not provide a station-vertex creation command.

The reverse cleanup removes blank station signs and reports unnamed station
vertices. In the ordinary same-station run it retains the first station vertex,
otherwise the last plain candidate. Separate station revisits remain. Literal
identity removal matters: revisiting the same object may remove a farther alias,
leaving adjacent equal signs. The subsequent native row pass suppresses these
but keeps candidate-count minus one as maxIndex. The API preserves this reviewed
quirk and reports `NATIVE_TIMETABLE_ALIAS_INDICES`; index validation prevents
publishing such data as valid. It does not silently substitute a group-by rule.

## Saved defaults

- The initial row never has a stop or dwell. Later rows use current Train
  Category `stop_at_every_station`; positive `stop_at_every_station_time_s`
  becomes a float32 value and then truncates toward zero to an integer string.
  Nonpositive dwell writes zero. This is not nearest-integer rounding.
- Timing policy code 1 selects every station. Other codes use Station database
  `timing_station` (group 7); no station DB entry retains the native true default
  while separate binding validation reports the missing station.
- Track policy 1 uses the vertex name, then its related End name. Policy 2 uses
  the first nonempty Edge track name in own first/second, related first/second
  order. Other codes leave it empty. This is not necessarily the traversed Edge.
- With no bound Category, native false/zero/default policies are used and a
  warning is returned. Missing Train/Category bindings still fail validation.
- Arrival/departure strings are `HH:MM:SS`, day offsets zero, mean delay zero,
  no connections, interval reference `0`, interval offset zero and empty track
  unless a track policy supplies one. Constructor timing starts true.

`define_station` can set `timing_station`; omission preserves the existing
value (or the native blueprint on a new station). Catalog queries expose it.

## Agent workflow and verification

Create station rows once per requested Course, inspect the full
`timetable_changes_json` provenance and compact previews, then fill times with
`update_timetable_rows` or an explicit timetable. No travel time is invented.
`TIMETABLE_PLANNED_TIMES_UNDEFINED` warns under generation and errors under
static preparation, including missing endpoint departure/arrival. Zero/one-row
results retain the existing strict `TIMETABLE_MISSING` error.

All selected Courses are planned before table mutation; a missing Course or
replacement conflict fails without source writes. A draft permits at most 1000
creation targets and 100000 End visits across distinct first Itineraries;
Itinerary selections are cached within the operation. Existing shared row and
connection budgets also apply. Summaries count rows written by operations,
including replacement rows, rather than net database growth.

Verification covers independent signal/identity/track cases, current native
serialization round trips, constructed StationEnd subclass persistence, empty
timetable dictionaries, same-batch defaults, editor undo and real compact MCP
generation/fill/publication. The subclass fixture is constructed from verified
metadata, not a captured native golden. No original application, GUI, controller
method, random dwell/performance logic or simulation is executed. Raw C remains
machine-generated and is not fully recovered original source.
