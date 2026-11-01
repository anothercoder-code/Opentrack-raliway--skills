# Integration note

The text below preserves the reviewed candidate provenance and narrow field contract. Wave5 registers the corresponding typed MCP tools via `current_archive/upcoming_tools.py`, uses shared recursive graph reference checks and the reviewed atomic save core, and adds independent transport/Skill verification. Candidate-only paths and statements about unregistered adapters below are historical provenance, not the current integration status. See Skill `references/wave5-archive-functions.md` and `verification/wave5/` for integrated scope and tests.

# Station current-archive setters — integration unit, not registered

## Closed scope

`station_operations.patch_station_archive(bytes, station_sign, changes)` edits a real
current root NSDictionary/NSMutableDictionary containing OTStation v3, 10 groups,
encoder marker 17. The actual BJTU `empty.stations` contains BJN/JNW/NJN. The selected
`station_sign` is an exact lookup key; **display_name is NOT stationSign and NOT a
catalog rename**. No cross-catalog action, station district, line reference,
simulation, GUI, legacy migration, or native process invocation is implemented.

Supported fields:

| API field | Original setter | Archive field | Domain |
|---|---|---|---|
| display_name | 0x664170 | group 2 @ | Unicode string or native nil |
| altitude_raw | 0x6641e8 | group 3 i | signed int32, raw units |
| coord_x_raw | 0x664258 | group 5 ii, slot 0 | signed int32, raw units |
| coord_y_raw | 0x664274 | group 5 ii, slot 1 | signed int32, raw units |
| timing_point | 0x66429c | group 7 i | signed char [-128,127] or bool; coder writes 0/1 |

Groups/slots are zero-based. `field-contracts.json` supplies per-function hashes,
ABI types, original-C/API/tested domains and units. Coder 0x664904 explicitly writes
`isTimingStation != '\0'` as int, so e.g. -128, -1 and 2 are all stored as 1.
No native float exists for these setters: `-0.0` is rejected, not silently coerced.

## Evidence limitations

These are Ghidra decompilations of the recorded binary, not recovered original
source and not native-runtime execution. The name setter autoreleases the old
name and stores the result of messaging the argument through PTR_DAT_008adc5c.
This bank export does not resolve that pointer to the `copy` selector. The
implementation allocates a separate NSString graph node, giving conservative
copy isolation; no claim of arbitrary Objective-C object/copy subclass behavior
is made. Nil and string are the exposed subset, not the full object ABI domain.

The integer setters and coder establish **no physical coordinate or altitude
unit**. Names deliberately contain `_raw`: do not label as meters, degrees or
longitude/latitude. Longitude/latitude strings (groups 8/9) stay untouched.

Init 0x663d78 sets scalar defaults to zero, timing char to 1, and string pointers
to DAT_008ad72c; the bank resolves that as a static empty-string *candidate*.
A new-station composite is **not implemented**: exposing dictionary insertion,
identity setters and a fully proven default graph requires its own reviewed
contract. No template guessing or cross-catalog reference creation is performed.

## Alias and preservation policy

* Shared NSString display-name/key nodes are never modified in place. A fresh
  node (or nil) is assigned to just group 2. Any other aliases remain intact.
* A selected Station with other incoming edges or a referenced root dictionary
  is refused. No silent cloning or mutation of shared Station/container graphs.
* The private visitor covers archived objects, Array, GenericStruct, list and
  tuple nesting, counts repeated inline-wrapper edges and rejects cyclic inline
  wrappers. It is independent of unfinished wave4 helpers.
* Per-slot identity-aware snapshots protect non-target live objects, values and
  edges; untouched wire float bit patterns are preserved. Unreachable replaced
  name nodes may disappear, as expected. Runtime writer reload/fingerprint is a
  structural self-check, **not** the independent reader proof.

## Integration

`station_tools.py` defines strict `StationChanges`, `PatchStation`, and
`StationTools.patch_station`, with published wave3 `ArchiveTools.save_copy`.
No server/registry is changed and there is no `tool_definitions` registration.
When moving both modules into `current_archive`, change the adapter import from
`from station_operations ...` to `from .station_operations ...`.

The adapter preserves omitted-vs-null semantics using `exclude_unset=True`;
only display_name may be explicitly null. Preview defaults true. Real save
requires a fresh target, checks source SHA, and uses the existing atomic copy
service (source unchanged, no overwrite, guarded paths, post-save reload).

## Verification

Run from the shared workspace root:

```
python opentrack-upcoming-functions/stations/tests/test_stations.py
```

9 tests pass, including 256 signed-char cases, int32 endpoints, Unicode/nil,
alias isolation/refusal, current-shape rejection, strict schema, preview/save,
stale SHA, overwrite/traversal refusal and independent reader checks. Test-only
upstream `pytypedstream==0.1.0` is taken from published wave3 verification vendor;
it is not bundled in runtime modules.

`evidence/saved-copy/OTProjects/station/OTData/` retains actual source and edited
archive copies. `commit-receipt.json` records successful atomic publication;
`independent-freshload.json` is produced by a **separate Python process importing
only upstream pytypedstream**, not our archive writer. This is independent
reader compatibility, not official OpenTrack application acceptance.

Source SHA256: `538a67c64355f6699cc9293a84024a967601157f273b46092b0e62c2d47375d5`

Edited SHA256: `633901a407803f027274f2128f14ff9caaabba3b740d7219098941bbc3d30489`

`tests/build_evidence.py` creates those outputs once and refuses replacing an
existing target. The actual published source fixture remains unchanged.
