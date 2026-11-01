# Integration note

The text below preserves the reviewed candidate provenance and narrow field contract. Wave5 registers the corresponding typed MCP tools via `current_archive/upcoming_tools.py`, uses shared recursive graph reference checks and the reviewed atomic save core, and adds independent transport/Skill verification. Candidate-only paths and statements about unregistered adapters below are historical provenance, not the current integration status. See Skill `references/wave5-archive-functions.md` and `verification/wave5/` for integrated scope and tests.

# Current Route archive template factory — narrow, verified domain

## What is implemented
`create_route_from_template(bytes, template={name,array_id,start_id}, name=..., end_ids=[...], description='') -> (replacement_bytes, report)` creates an actual **new OTRoute object** in the current OTDocument graph, appends it to the starting End's native RouteList, allocates a new owner-scoped RSP identity, saves native typedstream bytes, and fresh-decodes them. It is not a JSON route_bundle or a description-only update.

The template and explicit End list must specify **the same existing directed movement**. This revision intentionally does not invent a new movement, choose a default template, search routes, edit geometry, change inherited operational parameters, or create signals. It can represent a distinct named Route over a known movement. All original objects, including Path/Itinerary and old Routes, are preserved; the only changes to old objects are one owner RouteList append and that owner's ID counter.

## Domain and rejections
- Current `OTDocument4`; complete `OTRoute0 → OTSecurityArray6 → OTOrgArray2 → OTMutableArray0 → NSObject0` hierarchy.
- Exact explicit template name/array-ID/start-ID; nonempty new name. One document only. Caller must check project-wide uniqueness before multi-document integration.
- At least two distinct local `OTEndModel7` nodes; related End reciprocity; each successive pair resolves through exactly one existing `OTEdgeModel3`; positive persisted length; edge/end identities belong to this document; terminal signal/end references reciprocal; no connectors.
- Both terminals have existing main SignalModel11: C main types `{1,2,24,25,26}`. No intermediate main signal. Narrow aspect domain is existing signal show-type `2`, exactly one existing template indication code `0`, with its backref already on that template. No lookup-table guess and no arbitrary user aspect code.
- No continuation (`g5[4] == -1`), dirty or occupied/discrete flags, start/end protection zones, overlap name/start-ID, or unknown groupStartElems references. Group member references must remain on the explicitly confirmed chain. Unknown hierarchies, malformed layouts, duplicate IDs, stale/exhausted owner counter, dangling saved name/ID capture, hidden/aliased owner containers and invalid topology reject.
- Existing nonempty RouteList is required by the explicit owner template. Nil owner-container construction is **not implemented**, although `End.addToRouteList 0x4c460c` proves native nil/empty owner allocation is possible. This is a deliberately smaller supported domain, not a claim that native C forbids nil.
- Recursive incoming-reference inventory includes inline GenericStruct/Array nesting and object cycles; hidden RouteList/backing-array aliases and aliases to archive root reject. Every owner RouteList/PathList member must have the complete current hierarchy/schema. Nonempty owner ShuntingList is conservatively unsupported pending a complete member-schema audit (empty/nil remains accepted). Strict NeXT-compatible input wire-length decoding is required.
- Pure bytes transaction; failures yield no replacement and never modify input files. Integration must commit only returned verified bytes. No registry, MCP tools, upload, GUI, simulation or runtime binary is included.

## Exact inherited field map (13 groups)
| group | encoding | semantics |
|---|---|---|
|0|@|new NSMutableArray referencing existing chain Ends|
|1|@|fresh explicit name NSString|
|2|ii|new array ID / owning first-End model ID|
|3|@|fresh explicit description NSString|
|4|@|new OTSigIndList/new backing array/new individual OTSigInd; owner backrefs point to new Route|
|5|iiiiii|release distance, announce distance, release time, reserve time, first-End-in-other-doc index, dirty flag|
|6|iff|occupied/discrete bitfield, occupied-entry speed, occupied-entry wait|
|7|@|overlap name, empty in this domain; independent new string|
|8|ff|approach-zone length/speed, preserved from explicit template|
|9|i|overlap start-End ID, -1 in this domain|
|10|iii|reservation distance, use-reservation-distance, use-release-distance|
|11|i|reserve-with-previous + 2*slow-speed-only-head|
|12|@@@|new groupStartElems array preserving existing member references; nil start/end zones|

Scalar parameters are template data, not inferred constructor defaults. New object/array allocation prevents old mutable lists or backrefs being overwritten. Class descriptors and existing infrastructure references are shared intentionally.

## Not native init/copy equivalence
`0x5a4e58` initializes releaseTime=5, releaseDistance=0, announceDistance=400 after Security initialization. `Security.init 0x5bcf88` initializes reservationDistance=5000, use-flags false, occupied speed40, time0, overlap ID -1, and runtime members. `Org.init 0x52c164` sets IDs=-1. We do not interpret unknown DAT string constants as verified defaults.

`Route.copy 0x5a4f20` initializes a new object, copies selected properties, copies every indication then resets its routeOrEnd, and preserves group member object identities. It **does not simply copy all archive scalars** (for example announce distance/occupied flags/description are not copied by this method). This factory retains explicit template persisted parameters and sets explicit identity/text. Therefore it reports `native_init_or_copy_equivalent: false` and must not be counted as a full reproduction of either method.

## ID correction — important for integration
End group19 is **highestGivenRspID**, not `next_id`. `End.encode 0x4c7910` names the field. `createNewRspID 0x4c7188` does:
`highestGivenRspID = highestGivenRspID + 1; return highestGivenRspID;`
`resetAllRspID 0x4c71b8` initializes -1 and allocates across RouteList, ShuntingList and PathList: this proves their shared owner-local namespace. We verify all existing IDs <= highest counter and unique across those lists; stale state fails rather than silently applying max(). No counter overflow is emulated.
The old `operations.py::Definitions.next_id` treats the field as a next-ID and must **not** be reused as C evidence. Published files remain untouched.

## Continuation/reload and SignalInfo scope
`Route.encode 0x5a7538` strips continuation first, encodes Security and Route groups, then appends continuation back at runtime. `0x5a5874` and `0x5a575c` gate those effects on continuation. The supported input has no continuation; its saved chain is already complete and those native branches are no-ops. No runtime tail is blindly written.
`Route.decode 0x5a7480` rebinds each saved indication to self. The factory already stores those correct references. `Security.decode 0x5c28bc` additionally constructs runtime occupied indication, course array etc. Those are **not persisted fields** and are not synthesized into the archive.
The selected current BJTU documents contain SignalModel and SigInd objects, no SignalInfo archive objects. `trackSpeedIndicationForSignal 0x5ca0fc` proves show-type2 uses code0; `speedKmhForTrainType:handleOccEntry 0x5ca55c` dispatches that case directly (code0 => native track-speed sentinel1000), not through an external SignalInfo lookup. We preserve signal objects and reciprocal End references and do not claim to implement runtime dispatch/image resources or other signal systems. Any wider SignalInfo-dependent domain remains unsupported, not mocked.

## Validation and provenance
Run `python opentrack-upcoming-functions/route-factory/tests/test_route_factory.py` from workspace. It adds only read-only published wave3 module and independent pytypedstream-0.1.0 test oracle to sys.path; it does not import old Project/hsr.

Three original fixture inputs: published wave3 `tests/fixtures/bjtu/OTDocuments/BJTU{1,2,3}.opentrack`, with hashes in `artifacts/verification.json`. Their manifest says frozen unlaunched package, and Route descriptions explicitly say synthetic infrastructure. They are **existing current fixture archives, not evidence of application-created infrastructure or GUI acceptance**. Their bytes are unchanged. Outputs are new `.opentrack` copies under this module's artifacts only.

Every positive output is saved then independently fresh-decoded by upstream official typedstream reader. Checks include new object identity, shared existing geometry identity, independent arrays and indications, correct backrefs, owning list membership, and native allocator change. Removing only the added Route and restoring the prior counter yields byte-for-byte identical canonical serialization of the original entire graph. The production function now enforces the same rollback invariant internally.

## Integrated dependency document domain

Every supplied dependency archive, including non-target files, must match current OTDocument4 hierarchy and the supported 21-group layout. All known Route/Path/Itinerary and ArrayInfo/ExtInfo records, plus each End owner RSP wrapper/member, are checked before collision analysis. A nonempty ShuntingList is refused **anywhere in the supplied document set**, not merely at the selected owner. This is an explicit API safety subset; it is not a claim that native OpenTrack forbids shunting in other documents.
