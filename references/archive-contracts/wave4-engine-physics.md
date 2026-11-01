# Current Engine physics-field archive setters (integration draft)

Pure API: `patch_archive(blob: bytes, exact_engine_name: str, changes: dict) -> (bytes, report)` in `engine_physics.py`. No registration into frozen wave2 or integrating wave3. Caller owns authorized filesystem scope, input SHA checks, locking and atomic publish. No local computer, GUI, simulation or original executable was used or required.

## Feature IDs and current encoding

| Local feature ID | API field | Decompiled setter | OTEngine v2 group/slot | Native encoding | Unit |
|---|---|---|---|---|---|
| EP-01 | adhesion_load | 0x004cbd60 setEngineAdhLoad: | 3/0 | i | raw native mass integer; no conversion |
| EP-02 | force_max_kn | 0x004cbde0 setEngineForceMax: | 6/0 | i | kN |
| EP-03 | force_min_kn | 0x004cbdf0 setEngineForceMin: | 17/0 | i | kN |

All group numbers are zero-based and include OTVehicle superclass content. OTVehicle encoder 0x006df470 establishes groups 0–2; Engine encoder 0x004ccc54 and decoder 0x004cc994 establish the remaining order. Exact inheritance `OTEngine v2 -> OTVehicle v0 -> NSObject v0` required.

Unit proof: Engine 0x004cb49c/0x004cb4b0 `getEngineForce{Max,Min}_kN` call 0x004cb484/0x004cb490, which directly return the stored int (no division by 1000). 0x004cc798 setMaxPowerAndSpeed consumes Diagram 0x00471884/0x004718ec `_kN` extrema and directly invokes the setters; diagram getters directly compare point getY values. Real fixture Re 460 stores max=275/min=0. The API writes kN integers without scaling. Adhesion load appears multiplied by 9.81 in 0x004cc2d8 before comparison to kN effort; tonnes are a dimensional inference, not an independently declared storage-unit fact. Accordingly the API exposes raw native integers and does NOT label them validated tonnes.

## Original C domain / effects

- All three setters accept signed 32-bit int, with no sign, min/max ordering or physical-range checks; negative values and extremes are in setter domain, not necessarily physically valid.
- Force setters write only the selected scalar. They do NOT update points/curves or recompute other fields.
- Adhesion setter writes scalar first. Exactly zero then calls `firstTractiveEffortSpeedDiagram` (0x004cb4fc), followed by `setAdhDisp:0` (0x00471668). The helper returns nil for empty or nil diagram array, else index zero. No allocation; nil message is a no-op. Nonzero adhesion does not restore display.
- Diagram v3 encoder 0x00472db8 and decoder 0x00472944 map `adhDisplayed` to group 0 slot 5, `i`. Remaining fields and refs are not modified.
- Native object sharing is observable: every Engine/index holding that diagram sees its flag become zero. This is NOT copy-on-write semantics. Only first diagram of selected Engine is targeted, but another Engine may hold it at any index.
- Native dynamic dispatch can involve subclasses/overrides; these are outside this static archive adapter's supported class chain.
- UI controller 0x004d11c4 additionally raises engine total load when below adhesion load. That is a separate controller behavior, NOT part of 0x004cbd60 and deliberately NOT performed by this setter API.

## Conservative API guard domain

Exact Python int within [-2147483648,2147483647]; reject bool, all floats (including +0.0/-0.0), strings, null and overflow. Integer `-0` is identical to `0` and takes zero branch. Nonempty exact identity; reject ambiguous/empty engine catalog names. Current class/version/layout and parent chain required for accessed records. No old archive migration.

For zero branch, allow nil or empty diagram array (scalar-only change). For nonempty arrays require first item to be exact OTDDiagram v3 -> NSObject v0 with audited group layout. Reject nil element/unknown subclass/version/layout; nil *array* is supported but nil *element* is intentionally excluded. For nonzero and force-only patches, diagram schema is not validated because C does not touch it; the generic graph is still traversed for ownership safety.

Every patch requires the selected Engine and depot root to have exactly one recursive incoming occurrence (the root entry itself counts as one), rejecting hidden aliases to ownership ancestors. Zero with a first diagram additionally requires its parent array to have one incoming edge. Thus sharing an ancestor cannot bypass the leaf-diagram guard. For zero with first diagram, enumerate every graph OTEngine and all its diagram indices; reject if more than one owner path or more than one incoming graph reference exists (including typed Array/GenericStruct nesting). `SharedDiagramError.owners` lists engine identities/indexes; `.references` reports recursive incoming reference count. This rejects shared arrays too, including a shared diagram already at zero. It does not clone or rewrite refs. Native broader shared mutation domain remains documented above; API only promises independent edits. Unknown incoming owners conservatively cause rejection. The cycle-safe visitor counts each incoming edge before object deduplication, enumerates nested Engine owners, and fails closed on unrecognized value/container types.

## Tested domain / evidence

`python -m unittest discover -s opentrack-following-functions/engine-physics/tests -v`

Real BJTU current depot: `opentrack-wave2/OTAI/tests/fixtures/bjtu/OTData/empty.depot`; seven existing engines, selected Re 460. 18 real-fixture boundary requests across three fields (INT32 min/max, -1, 0, integer -0, 1), plus combined three-field patch and zero→nonzero sequence. Each output saved/re-read as bytes and independently decoded by upstream python-typedstream with class registry cleared. Independent generic full graph comparison normalizes only expected selected cells, preserving every other scalar, encoding, class chain, array ordering and object reference identity/topology. Production dump_verified adds its own codec verification, not used as the only oracle.

Derived copies (clearly `derived-` filenames, not claimed original examples) cover empty/nil arrays, shared diagram, shared parent array, shared nonfirst index, two diagrams, nil element, unknown Engine/Diagram parents and versions. Rejection cases cover all invalid numeric types and bad selections. Thirteen test methods pass, including typed Array, GenericStruct and nested Array/Struct hidden aliases (incoming=2), cycle termination, nested Engine inventory, and unknown container rejection. Nested shared Engine/diagram-array/depot-root ancestor tests cover zero and relevant force/nonzero patches. Hidden-alias combined-patch rejection verifies original bytes and both selected scalar/diagram flag remain unchanged. Native executable acceptance is not claimed; this is current archive-level setter equivalence over the guarded domain.

Evidence contains extracted lawful function-bank C files, complete SHA manifest, real-roundtrip JSON, saved outputs and test log. Original fixture and frozen sources remain unchanged. No external publication.


## Wave4 integration addendum
Production module is in current_archive; candidate evidence above is retained provenance, not the final MCP gate. See artifacts/wave4/transport-verification.json and wave4-audit for actual typed transport/fresh-save verification. All current ownership scans delegate graph_references; legal object cycles retain identity, unsupported inline container cycles/unknown values reject. All responses are strict JSON with explicit nonfinite labels/raw bit metadata; finite setter-input semantics are unchanged.
