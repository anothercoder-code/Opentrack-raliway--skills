# Current Course / Timetable template factories

## Evidence and provenance

Reads actual decompiled C from `resources/function-bank.zip`, copied in `evidence/`.
These are Ghidra translations with reviewed Objective-C metadata, not original source.
Stock executable SHA256: `f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
`resolved-strings.json` preserves exact original constant-string annotations/byte hashes:
008b1c6c=`0`, 008b1c78=empty, 008b1c9c=`-1`, 008b1c90=`HH:MM:SS`.

| Function IDs | Extraction / implemented scope |
|---|---|
| 454fe4, 456b6c, 4567d8 | Current Course class11, encoder group order, current decoder; no legacy branches implemented |
| 455004 | Init inspected; no speculative blank constructor. Existing explicit template mandatory; unknown/unset fields inherited |
| 67887c, 67b390 | Current Timetable class9, internal17, group order |
| 67889c, 678b34 | Init inspected; actual time unset marker and four day offsets; no arbitrary inferred defaults |
| 67af18 | Current decoding; nil/empty/0/-1 interval reference forces offset0 |

## API and persistence

`generate(blobs, *, template_id, course_id, train, itineraries, stops, fields=None)`.
`blobs` must contain exactly bytes for courses/trains/dest/stations/timetable.
Returns **native archive bytes**, `{'courses':..., 'timetable':...}`. No JSON-only storage.
Uses frozen current_archive writer (`d1a905…40d4`). Integration owns source SHA guards,
path safety, fresh-copy staging and atomic multi-file commit; factory never writes a source.
`new_course`/`new_timetable` expose graph operations for integration batch composition.
These pure factories perform no source-file migration/replacement, GUI action, native simulation, network upload or publication. That function-layer boundary does not prohibit a separately authorized local-agent or original-application workflow.

Required templates are **existing names/keys inside supplied actual catalogs**, not
hidden synthetic prototypes. COW copies only root/container/group shells and changed
strings. Class metadata, unmodified references, old objects and their sharing remain
identical. New Course itinerary container and each new row connection array are separate. Source root is not mutated.

## Function → slot/type/unit/reference → accepted input boundary

Bounds below are conservative **factory policy**, not a claim that the native UI has
these exact ranges. Omitted fields inherit the explicit current template.

### Course11 (`456b6c`)
| Group | Field / type / unit | Accepted explicit values |
|---|---|---|
| 0 @ | Course ID | New unique printable ASCII 1..200, no `#`, excludes reserved0/-1; preserves spaces/case |
| 1 f | enteringSpeed_ms | public km/h finite0..1000, divided by3.6 |
| 2 @ | destNameArray | explicit1..1000 unique names, exact current DestInfo1 catalog matches |
| 3 @ | trainName | explicit exact Train16 catalog match |
| 4 @ | speed type | printable ASCII<=2000; inherited if omitted |
| 5 i | enabled | strict bool |
| 6,9 i | acceleration on-time/delayed % | strict int50..100; supported post-clamp range of original setters 0x456004 / 0x456090 (out-of-range API input rejected, not silently clamped) |
| 7 ff | outputOffset_m / reserved | offset finite±1e6m; reserved preserved |
| 8 i | reservation mode | discrete0/moving2/moving_cbtc3 |
| 10,11 @ | description/comment | printable ASCII<=2000, nonnil |
| 12 ff | reserve/release s | finite0..86400 each |
| 13,14 @ | display train number / kind | printable ASCII<=2000, nonnil |

Train and Itinerary references are native **name strings**, not in-file pointers to
objects in other files. Existence/uniqueness validated; physical route connectivity,
Train speed type compatibility, document paths and running feasibility not certified.
Unknown references reject. No auto-creation. Existing dictionaries/catalogs read-only.

### Timetable9 (`67b390`)
Every row requires explicit `template_key`, station_sign, arrival, departure,
arrival_day_offset and departure_day_offset. 1..10000 rows; existing timetable owner
cannot be replaced. New native dictionary keys exactly `CourseID#index` (0-based),
maxIndex=count-1. Existing keys/counts validated; no silently overwritten keys.

| Group | Field/type/unit | Accepted values / handling |
|---|---|---|
| 0 i | internal version | must already17 |
| 1 @;3,4 i | owner,index,maxIndex | generated from current Course and list position |
| 2 @;11 f | interval ref / offset seconds | exact current Course with station row; no self-ref; ±31622400s finite |
| 5 @ | station sign | exact Station3 dictionary key; key/sign consistency validated |
| 6,7 @ | planned times | strict00:00:00..23:59:59 or None→native HH:MM:SS |
| 8 @ | dwell numeric seconds | explicit finite0..86400; inherited finite nonnegative; stop dwell checked |
| 9 @ | connections | explicit template must have empty native array; nonempty rejected, no guessed owner rewrite |
| 10 i | stop/timing flags | inherited must0..3; optional strict bool overrides |
| 12 @ | mean delay seconds | explicit finite0..86400 or inherited |
| 13,14 @ | actual times | reset HH:MM:SS, never copy prior run results |
| 15 iiii | four days | planned strict integer±366; actual offsets reset0,0 |
| 16 @ | distribution name | printable ASCII<=2000 or inherited; distribution existence not asserted |
| 17 f | delta mass tonnes | explicit finite±1e6 or inherited |
| 18 @ | track text | printable ASCII<=2000 or inherited; not physical track validation |

Undefined planned time must have day0. At least one planned time per row. All defined
planned times chronological by day*86400+clock; no guessed midnight.
For nil/empty/0/-1 interval ref, **stored** offset always0; explicit nonzero rejects.
An inherited nonzero offset is ignored only for these decoder-unset references,
matching original decoder. Real BJTU G1046#0/#1 have zero offsets; no garbage
source value is claimed. Actual day resets and nil ref retained.

## Verification and sources clearly distinguished

`python opentrack-course-factories/test_factories.py` runs ten tests (many rejection
subcases). Real **frozen/unlaunched BJTU** fixture: Course11 36→37, Timetable9 74→76.
Generated copy files in evidence/ are re-read using both own writer reader and
independent official `pytypedstream` from `opentrack-archive-research/vendor`.
Verified native versions, names, reference strings, dictionary keys/count, days,
indices, km/h→m/s, all four unset interval cases, valid reference offset, COW aliases,
every existing Course/Timetable standalone encoded graph unchanged and all five
source file bytes unchanged. No runtime/simulator acceptance claimed.

Current prototype `resources/native-shapes.archive`: **not used as generation input**.
Stock-extracted sample archives: **not used as generation input**. Their binary C
metadata informs field contract only. This result is actual BJTU current archive
addition, not stock/prototype substitution. Generic official reader verifies format
and graph only; it does not execute Objective-C decode methods or simulate trains.
