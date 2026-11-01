# Current native Connection operations — wave8 integration

The pure layer `native_connections.apply(blobs, commands)` returns **one new Timetable archive**
and strict-JSON receipt. Four actions: `insert`, `delete`, `turnround_to`,
`turnround_from`. The pure layer performs no JSON-record round-trip, GUI, simulator, migration,
external upload, registry, file transaction or source write. The wave8 wrapper
adds registration and secure publication as detailed below. Wave6/7 remain unmodified.

## Contract

Five immutable byte dependencies: `timetable`, `courses`, `trains`, `stations`,
`connection_template`. The last is the genuine stock `OTConnection.archive`,
not a made-up wire layout. Commands are frozen `Command(action, course_id,
index, target_course_id=None, connection_index=None)` instances; booleans are
not indices. 1–1000 commands execute sequentially on **one object graph**, then
one output serialization. A late error returns no output; source bytes cannot
be mutated. The wave8 MCP fresh-copy caller resolves all five files in the
same authorized dataset, recheck **all** receipt dependency SHA-256s and publish
only the returned timetable bytes atomically. The pure module supplies no filesystem service; the separate wave8 wrapper
uses the existing audited shared publisher.

Named `insert` matches the non-turnround branch of `0x6913d0`; it is **not** the
unbound GUI button `0x692384`, which inserts target `"0"`. This API deliberately
excludes unbound/reserved targets, requires real owner and target Courses,
current Station, and a target timetable visit at that station. That last check
is a stricter API guard for ordinary insertion, not a claimed original rule.
Delete changes only the indexed membership, no reciprocal or family deletion.

Original semantics: duplicate target connections use **first match** (`67a658`),
not duplicate elimination. Timetable first/last use zero/max index and station
lookup uses ascending first match (`68c4c0`, `68c500`, `68c584`). The API requires
complete contiguous indices and consistent maxIndex; ambiguous Course/Train/
Category names are rejected rather than guessing a catalog match.

Default lookup is actual Course11 train name → Train16 category name →
Category19 group20 default seconds (`422a6c`, `469204`, `6cbcd0`). Missing Train
or Category gives native 420 seconds, not a fabricated category. Each side uses
its own owner's default. Negative default yields undefined `HH:MM:SS`.
Nonnegative finite binary32 is reduced modulo86400 and truncated. Fractional
seconds are supported because the original v023 evidence (authorized
01-agent.zip member copied under evidence/) includes the exact 24-byte block
at68f38b: FNSTCW → MOV AH,0x0c → FLDCW → FISTP → restore CW.
Its SHA was verified; RC bits10–11 equal11 for every prior CW, so this is
**not** an inference from FISTP alone. See rounding-block-audit.json.

Turnround follows `6913d0`, with `691aec`, `691e30`, `691ff4`, `6921b8` helpers:
- to: effective owner last row; target starts here → split primary + plain start
  reciprocal; else join primary + join at first matching target station.
- from: effective owner first row; target ends here → plain primary + split at
  target end; else plain primary + split at first matching target station.
- new start reciprocal **raw nil max wait** is retained; other new objects use
  `HH:MM:SS`. Existing min/max/type/distance remain unchanged. Helper join/split
  ORs its bit only. Primary clears location bits and overwrites join/split bits.
- allocation before reciprocal lookup is preserved, including self-turnround's
  two-object case. No circulation or physical feasibility is asserted.

## Full native map and preservation

Connection6 exact groups, from `7116ec`/`7114b4`:

| group | encoding | persisted field |
|---:|---|---|
|0|@|courseID name string/nil|
|1|@|connCourseID name string/nil|
|2|@|stationSign string/nil|
|3|@|connChangeTime string/nil|
|4|i|join bit1; split bit2; entry bit4; disposition bit8; exit neither|
|5|@|connMaxChangeTime string/nil (nil remains distinct)|
|6|@|connStationSign string/nil|
|7|i|connectionTimeType, preserved raw int32|
|8|f|dispatchingDistance_km, preserved raw binary32 including NaN payload|

There is no extra serialized human-name field: course/station references are
names, not object pointers. Runtime connTag/dispatchingConnection are not coder
groups and are not invented. Unknown flag bits/conflicting locations are
rejected because the original decoder/encoder would normalize them, not
silently masked. Unknown class versions/layouts are rejected. Other original
objects and slots remain directly in the graph, not narrowed into a JSON
schema. Timetable9 has 19 groups and internal format17; connectionArray is
**group9 @**. All other TT fields (scheduled/actual/day offsets/interval/track/
distribution/mass etc.) remain untouched. Noncanonical unbound interval offsets
are rejected because `67af18` would normalize them on native reload.

An identity-based original-object snapshot checks **every preexisting object,
class chain and group**, allowing only explicit connection fields and touched
array membership/count. This includes deleted objects until verification;
unknown unrelated fields, alias identities and float bits are not ignored.
Writer fresh reload verifies the full output graph. Tests additionally read
actual new files with independent official python-typedstream0.1.0 and compare
all groups, names, values, traversal identity/alias topology. NaN raw payload is
separately verified with the wire-preserving current codec and strict report
`bits_le`; official Python float equality cannot establish NaN payloads.

## Shared ownership facts (not assumptions)

Frozen BJTU `empty.timetable` SHA256
`46918c039ede68778a21d0d269f009ae894329333e3af76195ba7b24f580737d` has **74
rows, 74 distinct empty connection arrays, no Connections**. This is measured
in the included regression. No claim is made about other datasets.
`67af18` directly retains decoded connectionArray. `67a934` directly adds to
that array; `690ba4` directly removes membership. No per-command COW is shown.
Therefore touched shared rows/arrays/Connection objects are rejected (including
shared empty arrays). No silent unsharing, invented native normalization or
COW repair is implemented. Such a repair requires a distinct explicit API.

## Verification and limits

Run the packaged wave8 test gate from the extracted MCP root. Core tests import
wave8 business/codec code and the official reader from verification/vendor via
PYTHONPATH. Production code itself has no oracle dependency. Receipt records all source,
evidence, oracle and input/output hashes. No native application was executed.

Tests use real stock Connection6 and BJTU current catalogs; altered fixtures
are clearly derived by the test source and saved in `outputs/*-inputs/`.
Actual source input files remain byte-identical. Outputs cover insert/delete,
all four paired branches, self-turnround allocation order, duplicate connection
first-match, repeated station first-match, category resolution/fallback,
nonfinite report preservation, unsupported versions, missing targets/stations,
shared arrays/objects, late errors and noncanonical flags/interval values.
This is a bounded saved-data implementation, not complete OpenTrack function
parity, coupling execution, runtime cache validation or GUI equivalence.

## Wave8 integration addendum

The current endpoint is in current_archive/connection_tools.py. Contrary to the
isolated candidate status above, it now has five-file SHA/same-directory binding,
strict schema, whole-timetable Connection reference validation before and after
editing, and the shared secure fresh-copy publication layer. Per-owner native
420-second fallback remains explicit; full Train/Engine/Itinerary validation is
not claimed. The template is an explicit stock source copied to the dataset,
not an assertion that it originally belonged there. Tests have been ported to
self-contained package imports; their oracle comes from the test environment.
