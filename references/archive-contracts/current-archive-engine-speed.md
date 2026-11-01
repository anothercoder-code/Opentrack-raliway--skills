# Current archive function: Engine maximum speed

This is direct saved-data work, not computer use, icon/UI automation or a JSON
shadow state. The archive codec/accessors are independent implementations, not
recovered copies of unavailable legacy helpers. Runtime uses Python stdlib;
`pytypedstream==0.1.0` is the test-only independent decoding oracle (LGPL-3.0-or-later;
license texts in OTAI/licenses/pytypedstream-test-oracle).

## Function/field/input/output correspondence

Original bank functions were read through the production function tool; exact
pseudocode, metadata and hashes are retained in
`artifacts/current-archive/engine-speed-function-evidence.json`.

- `OTEngine.setEngineSpeedMax:` 0x004cbe00: assigns integer argument to speedMax.
- `getEngineSpeedMax` 0x004cb4c4: returns that integer.
- `getEngineSpeedMax_kmh` 0x004cb4d0: calls the above without conversion. This is
  independent evidence for km/h, not a unit inferred just from our field name.
- `encodeWithCoder:` 0x004ccc54 emits speedMax as `i` after forceMax; including
  inherited OTVehicle groups, this is OTEngine v2 group 7.

The callable API deliberately accepts strict integers 1..1000 km/h. This is a
safety bound of this interface, NOT a recovered bound/clamp in the original
setter. Booleans, fractions, strings, zero and values above 1000 are rejected.
Only that scalar is writable. No rename, train/category binding, curve rewriting,
reference repair, dispatch/runtime cache mutation or traction feasibility claim.

## Tools and actual persistence

`opentrack_inspect_current_archive`: scoped `source_path`, current catalog kind,
pagination. Reads real file bytes, validates supported record versions, exact
group encodings and superclass chains, returns source SHA-256 and identities.
Catalog accessors support current CourseList3/Course11, TrainList3/Train16,
Engine2, Station3, TrainEngine0 and observed Foundation container/string layouts.
Unknown versions/layouts, duplicate IDs, station key/sign conflicts fail closed.
These are single-catalog checks, not cross-project reference validation.

`opentrack_patch_current_engine`: source_path + expected_sha256 + exact
engine_name + maximum_speed_kmh. Default `preview_only=true` decodes, edits a
private graph, reencodes and freshly decodes the prospective archive. It returns
old/new value, unit, group/type, output hash and function evidence, with no write.
To save set `preview_only=false` and explicit `target_path`. Source and target
must be relative paths within configured OTProjects or OTAI/workspaces; symlink
escapes are rejected. Target parent must already exist. Existing target and source
reuse are rejected. The output is an entire newly encoded archive, not a JSON file.

Saving writes a temporary sibling, flushes+fsyncs, then atomically links to a
fresh target (no replacement). It rereads the actual target file, decodes and
validates the result, then confirms the original source bytes are unchanged.
Pre-publication failure removes only its own temporary file. After publication,
a failed post-check returns ARCHIVE_COMMITTED_POSTCHECK_FAILED with
commit_completed=true, target and expected hash; published files are not deleted,
and concurrent replacements are never removed. The source is never edited. Source SHA
mismatch fails before writing. The caller decides when/where to use the fresh
archive; no project .run references or existing files are silently rewritten.

## Evidence and exact scope

`tests/test_current_archive_stdio.py` uses production MCP on an actual copied
BJTU depot, then a separate new CLI process to reopen saved output. The original
and saved archives are independently read by official pytypedstream; all wire
events match except the selected speed integer. All original object/reference
indices and unaffected field values remain equal. Source bytes do not change.
Adversarial cases include stale digest, existing target, source-as-target,
unknown Engine, out-of-scope/symlink paths, invalid units/types/ranges and wrong
catalog. Receipts: `artifacts/current-archive/mcp-engine-save-reload.json`.

Sample categories must not be conflated: this test uses the provided **BJTU
unlaunched project fixture**, not native-shapes sanitized prototypes or a new
original-program capture. Codec-only broader checks include separate stock-extracted
and native-shapes samples, explicitly identified in their reports.
The function's acceptance is its checked inputs/outputs, encoding, identities and
save/fresh-load behavior. A GUI/engine launch is not an extra gate for this saved
scalar function. No such launch was performed or claimed.

Other four-catalog scalar round-trips are low-level field-fidelity tests, not
additional public setter claims. Course acceleration=90 is within the original
setter's observed 50..100 clamp range; that clamp/transient flag is not implemented
by the generic accessor. Train delay=2.5 only tests a finite saved float; no NaN
setter interpretation is claimed. Station timing=0 tests its saved integer slot.
