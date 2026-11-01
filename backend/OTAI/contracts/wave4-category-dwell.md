# Category dwell: current native archive function candidates

## Delivery status and provenance

Historical pure-module candidate `category_dwell.py`, importing the frozen current `writer`, `catalogs`, and `stock_operations.CATEGORY_LAYOUT`. The recorded extraction used no GUI/native simulation, legacy writer, source download or external publication and did not modify that frozen baseline. No JSON-only shadow data: `patch_archive(bytes, exact_category_name, changes)` decodes native typedstream bytes into private graph objects, modifies the selected scalar slots, encodes genuine native bytes and freshly decodes them. `read_archive(bytes,name)` reads persisted values, not caches. Filesystem authorization, expected SHA, atomic no-overwrite output and MCP dispatch/transport were integration gates for that extraction. **The historical module result alone did not establish MCP completion.** Current wrapper availability is determined by the actual schema and edition, not this old status paragraph.

The 16 evidence C files are actual reads from `opentrack-wave3/OTAI/resources/function-bank.zip`; these are Ghidra pseudocode, NOT recovered original C source. `evidence/functions.json` contains original bank member and SHA256 for every extracted file. Original binary SHA256: `f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`. Encoder `0x006c513c` and decoder `0x006c4b44` establish current coder field order. No defaults/prototype factory or synthesized replacement objects are used.

## Exact fields

All slots are zero-based. Class `OTTrainCategory` **v19**, superclass exactly `NSObject` v0, exact 25 typed groups. Container `OTTrainList` v3 with `OTMutableArray` v0 / `NSObject` v0 ancestry and current array records; Train v16 catalog validated too.

| API | group.slot / encoding | getter | setter | Native finite-domain behavior |
|---|---|---|---|---|
| stop_at_every_station_time_s | 15.0 / f | 0x6c4414 | 0x6c4420 | Negative -> +0, otherwise preserves argument |
| dwell_variation_early | 18.0 / f | 0x6c48d0 | 0x6c48e0 | Direct assignment, signed values intentional |
| dwell_variation_delayed | 18.1 / f | 0x6c48f4 | 0x6c4904 | Direct assignment |
| dwell_variation_early_unit_code | 18.2 / i | 0x6c4918 | 0x6c4928 | Direct int32 assignment |
| dwell_variation_delayed_unit_code | 18.3 / i | 0x6c493c | 0x6c494c | Direct int32 assignment |
| dwell_variation_early_delay_offset_s | 24.0 / f | 0x6c4960 | 0x6c4970 | <= -1 retained, else -1 |
| dwell_variation_delayed_delay_offset_s | 24.1 / f | 0x6c49a0 | 0x6c49b0 | >= +1 retained, else +1 |

Group 18 is `ffii`, group 24 is `ff`. Unit codes 0=seconds, 1=percent of planned dwell follow baseline audited `contracts/category-controls.md` and `rolling_stock.py` readback mapping. Unit getter/setter C itself only proves raw int32 storage, not labels. Unknown unit integers stay raw, with a null human label, rather than guessing semantics. Both unit inputs accept signed int32 -2147483648 through 2147483647, including unknown codes: **encoding-valid**, not asserted physically meaningful. Group 0 flags are read as raw signed integer plus unsigned unknown-bit mask outside `0x3f`, and never rewritten. Timing/dispatch/delay-add/track policy enums remain untouched.

### Finite-domain and -0 contract

Float input accepts strict Python int/float (not bool or strings), requires finite IEEE binary32 after one rounding. Maximum finite magnitude: 3.4028234663852886e38. Overflows/NaN/infinity are rejected as API policy, not claimed native restrictions. Small magnitudes may underflow to signed zero. Setter 0x6c4420 and delayed offset 0x6c49b0 contain x87 flag/NaN decompiler expressions; implementation claims only the clear finite domain. No NaN equivalence claim. For finite comparison, `-0.0 >= 0` preserves -0.0; do not implement using `max(0,value)` which can lose its sign. The direct variation setters preserve -0 too. Offset setters correctly clamp either zero to -1/+1 respectively. Fresh internal verification compares packed float bits, not merely numeric equality.

Readback does not apply setter clamps retroactively: it returns the actual persisted values. Mutating a field does not silently normalize other fields. All original getters here simply return the saved member. No simulation clocks, effective dwell, random realization, train arrival/departure times, counters or derived performance/cache state are computed or archived. No defaultConnection/departureProcess implementation is duplicated.

## Graph safety

Exact nonempty name selection; all category identities must be unique. Require complete Category field shape and four current interval/priority/performance array wrappers and backing arrays. Wrong versions/ancestry, missing tables or unsupported shapes reject. Exactly one incoming reference (including references nested in typed arrays/structs) to the selected Category and its containing catalog array is required, preventing silent effects on another owner or repeated catalog position. Untouched array/string sharing is preserved rather than split. Scalar assignment changes no references. We do not assert every nested interval element's business semantics: these untouched subgraphs are preserved and reader round-tripped, not newly edited. An entire unrelated graph is not migrated or repaired.

## Reproducible verification

Run from workspace root:

```
python opentrack-following-functions/category-dwell/tests/test_category_dwell.py
```

Five unittest methods pass. **52 native output archives** originate directly from unchanged populated BJTU `tests/fixtures/bjtu/OTData/empty.trains`: three real categories and two real trains. No renamed/sanitized fixture, selected-category reconstruction, or invented prototype. Every success saves to a distinct evidence `.trains` file, reads from disk using independent upstream pytypedstream 0.1.0, compares the selected slot's raw bits, and compares the entire graph (including all other Category/Train fields and reference identity topology) with only that one selected scalar omitted. Cases include zero, -0, negative, positive, maximum/minimum float32 and int32, unknown integer code, and underflow. `bjtu-results.json` records source/output hashes, bit patterns and fresh-reader verification.

`rejections.json` records shared Category, shared catalog, nested typed-array alias, duplicate position, missing table, truncated Category, Category18, and wrong-superclass refusals. Additional tests reject bool/string/coercion, NaN/infinity, overflow, unknown field, absent name and empty updates; preserve unknown flags/enum and verify every extracted C hash against source ZIP. Input archive is asserted byte-for-byte unchanged.

The independent reader is upstream pytypedstream, **not official OpenTrack application**. No app reload, simulator operation or physical validity is claimed. Audit linkage: map these 14 named native getter/setter addresses to the full function index, associate existing Category feature rows in the original 176-command inventory, and retain status `native_archive_candidate_verified` until actual MCP integration/path/transport gates pass.


## Wave4 integration addendum
Production module is in current_archive; candidate evidence above is retained provenance, not the final MCP gate. See artifacts/wave4/transport-verification.json and wave4-audit for actual typed transport/fresh-save verification. All current ownership scans delegate graph_references; legal object cycles retain identity, unsupported inline container cycles/unknown values reject. All responses are strict JSON with explicit nonfinite labels/raw bit metadata; finite setter-input semantics are unchanged.
