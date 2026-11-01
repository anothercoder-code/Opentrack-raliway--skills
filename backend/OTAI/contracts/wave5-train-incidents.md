# Integration note

The text below preserves the reviewed candidate provenance and narrow field contract. Wave5 registers the corresponding typed MCP tools via `current_archive/upcoming_tools.py`, uses shared recursive graph reference checks and the reviewed atomic save core, and adds independent transport/Skill verification. Candidate-only paths and statements about unregistered adapters below are historical provenance, not the current integration status. See Skill `references/wave5-archive-functions.md` and `verification/wave5/` for integrated scope and tests.

# Current Incident archive integration unit

## Closed domain

`incident_operations.py` exports pure bytes-in/bytes-out `create_train_incident` and `patch_train_incident`. No file writes, registry/MCP modification, GUI, OpenTrack.exe, simulation, legacy product, or external publication. Runtime dependency: existing `opentrack_ai.current_archive.writer/catalogs` from wave4, read-only. Tests use the separate pytypedstream 0.1.0 generic reader, **not** an official OpenTrack application loader. “Official reader” here means upstream typedstream implementation; native app acceptance remains untested.

Creation accepts CourseList3 marker17 with unique Course11 IDs and a mutable g1 event array. Any present incidents must match the deliberately narrow current12 Train profile below; v10, alternate types, stale references, and nondefault unsupported fields fail closed. No conversion or mutation of Schweiz occurs. g4 Course array and all original objects except the event container (and selected incident in edits) are retained unchanged by the serialized graph; source bytes are immutable.

- type1 = `Train`: 0x4e1870 + literal `00872764`; not a guessed enum. Read-only C review of 0x65cc34 shows types1/12/14 resolve `courseID` through CourseList and check Course.use. API only supports type1 and requires an actual enabled Course11 in this same input, verified with BJTU G1046/G2551. No Station, Signal, document, Route, Path, or distribution reference is introduced. `documentName='0'` is an init sentinel, not an unresolved external document.
- names: exact nonempty printable ASCII, max2000; unique among incident container. This is an API guard, not a native string limit.
- course_id: exact existing enabled Course11 name; no wildcard or cross-project reuse.
- begin/end: explicit canonical HH:MM:SS, same day, ordered; day offsets0. C setters0x4e1f80/0x4e204c replace string fields. Canonical/time-order validation is an API guard, not emulation of OpenTrack's time parser. No time edit API yet.
- enabled: exact bool; creation defaults **False** for conservative authored data, whereas native init uses true. Setter0x4e229c accepts native char; archive encoder normalizes its nonzero state to flag bit0. API intentionally excludes raw char values.
- reduced_speed_kmh: finite float32 (Python int/float excluding bool), quantize to float32, negative values clamp0 according to 0x4e1d6c. Native NaN/Inf effects are outside API. Other numeric fields remain audited defaults.
- edits: exactly `name`, `enabled`, `reduced_speed_kmh`, nonempty dict. Name replacement allocates a new NSString, never changes a possibly shared string. Duplicate names, unknown fields/types/versions, shared/cyclic root or event-array owner, shared incident, and incidents outside g1 fail closed.

## Schema (current12 / 25 groups)

C source: initialize0x4e08b0 sets12; encode0x4e33e8 defines group order. Inheritance OTIncident12→NSObject0. g20 is NSMutableArray0→NSArray0→NSObject0.

|g|wire|field|construction value/default|
|--|--|--|--|
|0|@|incidentName|explicit|
|1|@|courseID|explicit enabled existing Course|
|2|@|documentName|'0'|
|3,4|@|beginTime,endTime|explicit canonical time|
|5|iii|arrayID,arrayStartID,incidentType|-1,-1,1|
|6|ffff|reducedSpeed,tractiveFactor,mtbf,mttr|explicit speed,1,0,0|
|7|i|use/headOnly/discrete/periodic bits|explicit bool; other bits0|
|8..13|@|begin/end line,track,kilometration|all empty|
|14|f|waitTimeWhileStop|0|
|15|ii|begin/end dayOffset|0,0|
|16|@|comment|empty|
|17|ffff|period1Occ/Free,period2Occ/Free|0,0,0,0|
|18|@|durationDistribution|empty|
|19|f|probabilityPercentage|100|
|20|@|arrayOfArrayStartIDs|new empty mutable array|
|21|@|beginDistribution|empty|
|22|f|signalStopProbability|100|
|23|@|signalStopDurationDistribution|empty|
|24|f|limitedPower|-1|

Init0x4e08d0 provides all defaults. Explicit name replaces localized Untitled; type1 replaces -1; Course replaces empty; explicit times replace `HH:MM:SS`; enabled defaults false rather than native true. Thus construction is **init-derived field composition + explicit setters**, not original init equivalence, not copied legacy template, not App-produced fixture. Runtime active/partialActive and edge arrays are not archive groups and are not created or simulated.

Static literal evidence is supplied from the full function-bank's bounded, hash-backed constant-string annotation. These are labeled *classic constant string candidates*, not runtime execution proof. Empty string, document `'0'`, time placeholder and Train label are retained with byte/source hashes. C files are Ghidra decompilation, not recovered original source; Objective-C dynamic call types remain inferred.

Decoder0x4e2d98 explicitly fills g22/g23 for v<11 and g24 for v<12. Real Schweiz contains Incident10/22 and17 Course11. This is audited historical evidence only; API rejects it and never emits mixed OTIncident class versions. No general old-version support.

## Verified and unverified

Run from workspace: `python opentrack-upcoming-functions/incidents/tests/test_incidents.py`.

Tests write `output/current-train-incident.courses`, reload that exact file with upstream reader, verify12/25, values, same-project Course reference,36 existing Course objects and other root containers unchanged; source and stock hashes unchanged. Tests cover multiple current events, rename isolation, clamped negatives, float32 max, nonfinite/overflow/bool rejection, duplicate/stale refs, legacy/mismatched type and shared parent rejection. Output manifest records derivation and hashes. Tested numeric/name/time samples are not exhaustive native-domain equivalence.

Unverified/out of scope: runtime triggering, train motion, dispatch, all Signal/Station/position/Route/Path event types, distributions, period settings, arbitrary imported Incident12 profiles, Unicode strings, native GUI compatibility, native class-version table behavior with mixed class versions. Integration still needs the caller's expected-SHA/path/atomic-save and MCP adapter; this unit does not claim MCP round-trip completion. No existing registry edits.
