# Current stock function candidates — integration draft

## Scope and delivery

`stock_operations.py` imports only the frozen independent `current_archive.writer` and strict `catalogs` accessors. It never imports the old writer, runs OpenTrack.exe, uses GUI, or writes caller files. Input is real typedstream bytes, not a JSON shadow model. Output is new native bytes with own-codec fresh reload. Filesystem path policy, expected source SHA, same-project Engine catalog resolution and atomic no-replace output belong to the main integration layer and are **not implemented here**. Do not expose the binding operation until both source archive hashes are checked by that layer.

All changes are evaluated on freshly decoded private graphs. Failure returns no output and cannot modify caller's immutable bytes or source files. Unknown fields, wrong class/version/shape, ambiguous/missing identities, nonfinite floats, float overflow, bool-to-number coercion, invalid reference index and shared reference records fail closed. Only current Train v16, Category v19, Engine v2 and TrainEngine v0 are accepted. No migration.

## Six scalar function candidates

| API field | Original setter | Current archive group.slot | Encoding/unit | Native setter behavior |
|---|---|---|---|---|
| maximum_acceleration_mps2 | 0x006c1410 | Train 4.0 | f / m/s² (audited rolling_stock mapping) | direct assignment; no physical bounds |
| braking_delay_s | 0x006c1c90 | Train 16.0 | f / s | direct assignment |
| braking_release_speed_kmh | 0x006c1d14 | Train 16.1 | f / km/h | direct assignment, not m/s conversion |
| default_connection_time_s | 0x006c49f0 | Category 20.0 | f / s | direct assignment |
| departure_process_time_s | 0x006c4604 | Category 21.0 | f / s | assign then clamp negative to zero |
| departure_process_starts_at_departure_time | 0x006c45b0 | Category 22.0 | i / boolean | setter accepts char; supported API uses strict boolean, encoder emits **not** boolean |

Train encoder 0x006c2dbc and Category encoder 0x006c513c establish actual coder order; Category decoder 0x006c4b44 confirms archived 0 means true. Extracted decompiler files and per-file SHA256 are in `evidence/functions.json`. These are Ghidra decompilations, not recovered original source. Binary identity is in each original header.

### Input boundaries

For the five float inputs the API accepts finite representable IEEE binary32 values, rounded once as Objective-C float arguments would be. Maximum finite magnitude is `3.4028234663852886e38`; subnormal rounding/underflow follow binary32. It rejects NaN/infinity and overflow as explicit API safety policy, **not** a discovered native setter constraint. Negative values are permitted for unguarded setters because C supplies no lower bound; this is intentionally not advertised as safe physical model validation. `departure_process_time_s` clamps negative values to 0 like the native setter. Boolean is strict true/false; arbitrary native signed-char input is intentionally not supported.

No references or other scalar slots are changed, and no derived fields are recomputed: these specific setters do not recompute them. These are archive setter equivalents, not simulation correctness. Saved reports include requested, before_native, after_native, group/slot/unit and address. Binary32 rounding is visible in after_native.

## Existing Engine name binding candidate

`rebind_engine_archive(train_blob, engine_blob, train_name, zero_based_reference_index, engine_name)`:

- Train encoder 0x006c2dbc: group 2 slot 1 is `engineArray`.
- TrainEngine encoder 0x006d800c: group 0 `@` is engineName, group 1 `i` is posInTrain.
- TrainEngine setter 0x006d7f90 replaces the name object reference; it does not edit an existing NSString's bytes.
- Require unique, exact Engine v2 name in the supplied current Engine graph; the caller must prove that graph belongs to the same project. No dangling name creation, new engine import, or rename.
- Select an existing reference by 0-based array index; require integer `0 <= index < len(engineArray)`. This is a selection bound, not posInTrain semantics.
- Replace only that reference's name with a new NSString, protecting shared old strings. Keep its existing posInTrain integer and array order. Reject reference records shared by any other graph slot rather than quietly clone them.
- No inferred physical position semantics, no append/remove/reorder and no aggregate recalculation. Unchanged target is a byte-exact no-op.

The setter's opaque Objective-C memory-management selector is not renamed speculatively. This implementation claims logical stored-name replacement, not runtime retain/copy identity equivalence.

### Explicitly not closed

`addEngineWithName:` 0x006bb3e8 computes `numberOfItems + 1`; `addEngineWithName:atPosition:` 0x006bb418 creates a TrainEngine and appends it. `removeEngineAtIndex:` 0x006bb484 additionally invokes `decreasePosInTrainForPosInTrainBiggerThan:`. Therefore a generic array append/removal is not a sufficient implementation of full formation editing. Need independently audited item-count/position/update helpers and collision constraints before closing that function family.

## Evidence and limits

Run `python opentrack-stock-functions/tests/test_stock_operations.py` from workspace root. Six unittest methods pass, covering all six scalar operations, binding/no-op, failure cases, old-version rejection and source-function hashes. Seven output native archives are in evidence/. Each successful case writes a fresh output file, reads it from disk through own codec **and independently through upstream pytypedstream 0.1.0**, and compares all nonselected values plus object-reference topology. The independent reader is test-only; it is not the native OpenTrack application.

Fixture is the existing native `resources/native-shapes.archive` copied into memory, with explicit sample Train/Category names because original names were sanitized empty. Binding test additionally names the existing Engine and copies the fixture's native TrainEngine prototype into the Train's existing empty engine array. This is a controlled current-format native-fixture-derived test, **not** proof on a real populated user project and **not** original-app reload. Original source fixture bytes are checked unchanged. Next integration gate: actual project current-class fixtures, full MCP/path/hash atomicity tests, then user app validation if separately authorized.

## Explicit Engine template factory

`clone_engine_archive(blob, template_name, new_name)` requires a strict Engine catalog array containing a uniquely named **current v2** template and a fresh, nonempty NUL-free new name. It deep-copies the complete template subgraph, supplies a new name NSString, then appends to the existing catalog. All unspecified scalar values, curve content and internal alias topology are retained; mutable graphs are not newly shared with the original template. Original template and every other record stay unchanged. No implicit first template, zero defaults, migration, replace-existing or performance recalculation occurs.

Basis is audited `generation.py` `template`/`store` deepcopy+append behavior. This factory intentionally does **not** claim native `OTEngine.copyWithZone:` 0x004cc85c equivalence: that function initializes a new engine then copies only some fields through setters, potentially retaining different defaults. Factory is an archive-level template creation operation, not an additional reverse-engineered native method-completion claim.

Final focused suite has **7 unittest methods** and **8 operation outputs** (6 scalar + binding + factory), plus prepared input archive. Factory fixture is an Engine-only catalog array derived from native current-shapes Engine prototype. Independent upstream fresh disk reload verifies unchanged original Engine graph, new name, all other fields, clone internal sharing and no accidental aliases back into the original Engine. These remain controlled native-template tests, not a populated production project.

## Populated BJTU current-project evidence (added verification)

The final **8-test** suite additionally uses the existing unmodified BJTU `OTData/empty.trains` and `empty.depot` directly (despite filenames, they contain populated current records). All six scalar changes pass independent disk reload with the **selected object identity only** excluded from full nonselected-value/reference-topology comparison. New Engine creation from existing `Re 460` also passes: all seven original engines are unchanged; new Engine preserves every non-name field and curve graph. A subsequent in-memory mutation of a cloned OTDPoint confirms the original template curve is isolated and unchanged. No derived fields are recalculated by template creation.

**Important discovered boundary:** the two BJTU trains share one OTTrainEngine reference record. Existing-binding replacement safely rejects this exact real case rather than affecting both trains. Successful binding evidence remains the controlled nonshared native-template case. A future copy-on-write binding strategy needs its own explicit identity contract/review. See `evidence/bjtu-results.json` for original source hashes, each output hash and this rejection status. Original BJTU inputs are asserted byte-for-byte unchanged.

Affected BJTU owners are `CR400AF_8_PROXY_350` and `CopyOfCR400AF_8_PROXY_350`. Native `OTTrainEngine.setEngineName:` acts on its shared record and would consequently affect every owner. Our user-facing train-selected binding candidate has a deliberately narrower **exclusive-owner** domain; it rejects shared records instead of pretending native shared-object mutation is Train-only. No COW splitting is performed or implied.

Audit correction: departure-time clamping is implemented as `0.0 if value < 0.0 else value`, not `max(0.0,value)`. Thus IEEE negative zero and negative inputs that round to binary32 negative zero remain negative zero, matching the original assign-then-compare C. The final **9-test** suite checks the exact `0x80000000` float bits after own and independent decoding of a modified real BJTU Category archive.

Second audit correction: exclusive ownership checks include (a) reference-record direct incoming edges, (b) parent engine-array direct incoming edges, and (c) each Train-to-array-to-reference path including repeated array positions. All must be exactly one. Counting unique graph edges to the reference alone missed the case where two Trains share one parent array; this is now rejected and regression-tested using BJTU-derived bytes. Final suite: **10 tests passed**. Binding remains internal/exclusive-owner only.
