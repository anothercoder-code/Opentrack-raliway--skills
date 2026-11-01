# IT-01 Current same-project Path → Itinerary archive factory

## Status and exact tested domain
`create_itinerary` is a pure bytes→bytes-set **template-composition factory**, not a translation of the whole native `init`, `copy`, project editor, GUI or simulator. It is one new archive function, not five fully extracted native methods. Tested on complete real BJTU1/2/3 document set and `OTData/empty.dest`, with BJTU1 Path freshly derived by frozen wave2/current_archive/path_functions.create_local_path (same chain as prior verified `BJTU1-new-local-path.opentrack`). Source `P:CURRENT_LOCAL_TEST`, ID100/start19 contains connected local Routes 19→67→29. New Itinerary preserves first Path object identity and ordered path-info (one Path), ends19→29.

API accepts exactly ONE Path. Its Route chain must resolve completely, be local/current and connected. No cross-document Path, continuation Route, reversal, repeated Path, repeated End anywhere in expanded chain (adjacent Route join counted once), shunting path, nonempty margins, positive Itinerary ID allocator, old class versions, GUI or simulation. Single-Path is deliberately the verified bounded domain; no guessed multi-Path fixture is used. Attempt to build a second Path at BJTU1 End29 hit the existing newPath guard (owner PathList empty/no verified template), so multi-Path is not advertised.

## Inputs and output transaction
- `documents`: explicit complete project document-name→bytes collection.
- `catalog`: complete associated OTDestInfoList bytes.
- `expected_hashes`: exact SHA256 map for every document plus `$catalog`; extra/missing/mismatched inputs reject.
- `document_paths`: explicit document-name→exact native catalog filename mapping. No basename/OS-path normalization guesses; caller must establish mapping and project completeness. Hashes authenticate supplied scope, not an external filesystem inventory.
- `owner_document`, `name`, `path_refs=[{name,array_id,start_id}]`, `template_name`, optional description.
- Template MUST be named current OTDest in same owner document with empty margin array, and matched catalog row.
- Returns `({'documents': full new byte collection, 'catalog': new bytes}, receipt)`. Two dependencies change. Others are byte-identical. Caller/integrator MUST atomically commit the document+catalog bundle after preimage-hash checks. This module never writes user project paths.

## Actual owner and field contract
Current OTDocument v4 is 21 groups; `contents[5]` is OTMutableArray wrapper containing all defined OTDest. **Not End.DestList** on this current fixture. OTDest v1 hierarchy OTDest→OTOrgArray v2→OTMutableArray v0→NSObject v0, six groups `@ @ ii @ @ @`: first-Path backing array; name; arrayID/arrayStartID; description; ordered OTArrayExtInfo array; OTSafetyMarginArray.

All current BJTU OTDest IDs are `[-1,-1]`; new factory retains them, not an invented positive ID. Catalog uses name+explicit owner filename+first End ID and ordered Path name/ID/start/document tuples. Path ID100 and start19 remain references, not newly allocated. End highestGivenRspID/Document fields are untouched and whole-graph preservation is tested. Therefore collision policy is globally unique Itinerary **name** plus exact existing Path identities, not globally unique numeric Itinerary ID. New numeric Itinerary allocation would require a separate evidenced contract.

OTDestInfo v1 has `i @ @ i @`: marker17, name, docFileName, first-End ID, ordered extended Path infos. Root OTDestInfoList v0→OTMutableArray v0→NSObject v0. All preexisting document destinations and catalog rows must pair one-to-one and all referenced Path tuples resolve in supplied collection. Each persisted first-Path must be the identical local Path object. Catalog/document mapping errors, missing rows/documents and duplicate names fail closed.

New OTDest and catalog entry have separate parent objects; inside creation their info rows are shared, then separate archive serialization necessarily reconstructs distinct but equal rows. The document's first Path is shared with its owner End PathList, not deep-copied. Path/name references are not retargeted. New empty margin wrapper/backing array are independent from template. No claim of native nonempty margin-copy semantics.

## Decompiled-C evidence and non-equivalence
Evidence copied verbatim from frozen wave2 function-bank.zip. Ghidra decompilation is not recovered source; original binary SHA256 appears in each file.
- `0x474d60 initWithCapacity:` calls superclass and creates tempArray, pathInfoArray, safetyMarginArray, simRouteArray, slipInfoList, xInfoList; sets distanceToStationEnd=0/isTemporaryDest=false. Our persisted six-group template does **not** initialize or model all runtime fields/defaults.
- `0x4753a0 addObject:withRebuildingPathInfoArray:` always superclass-adds; rebuild occurs only flag==1. Our factory builds complete validated saved info explicitly; no runtime add/update invocation equivalence.
- `0x478058 encodeWithCoder:` removes all Paths after first with rebuilding disabled, encodes superclass then info+margin arrays and updates runtime. We preserve the first-object/full-info archive shape, not update/print/simulation side effects.
- `0x48373c OTDestInfo encodeWithCoder:` saves marker17, name, docFileName, endIdentification and pathInfoExtArray. Factory updates BOTH persistence owners.
- `0x47503c copyWithZone:` allocates/init, adds contained Path objects, sets arrayName, appends existing pathInfo references, removes default margins, then copies EACH margin before append. It is **not arbitrary deep-copy**. Factory is not this copy function (description/template usage differ); native copy is evidence-only, not exposed API.

Current operations.py define_itinerary (lines144 onward) supports the document[5]/catalog construction pattern; old Project/hsr imports are unnecessary for decoded bytes graphs. This module imports frozen wave2 opentrack_ai.current_archive.writer/path_functions codec helpers, not Project.

## Verification
Run `python test_itinerary_factory.py` from this directory (test resolves workspace dependencies). Five unittest methods / one positive bundle plus 18 rejection/ownership-guard inputs. Saves two outputs then independent upstream python-typedstream official reader fresh-reloads them. Checks first-Path pointer, document/catalog ordered-info equality, removes only added objects and compares all original graphs (including aliases), and ensures BJTU2/3 bytes unchanged. Catalog byte re-encoding can differ due shared encoding tokens; official structural graph including object alias references is the appropriate unchanged-graph check. Receipt records all input/output hashes and atomic bundle requirement. No OpenTrack.exe execution or native acceptance claim.

## Known non-product dependency note
The old scratch `opentrack-path-functions/path_functions.py` has an obsolete seven-group OTDest shape; the frozen/current wave2 and wave3 modules correctly use six. This factory has its own accurate six-group OTDest guard, imports frozen/current helpers directly, and never edits published sources. Tests use frozen/current newPath rather than stale draft code.

## Independent review hardening (candidate revision)
The former direct-only reference count missed hidden wrapper owners and nested Array references. `incoming_counts` now traverses every archived object's groups, nested wire Arrays/GenericStructs and sequences; object references are counted on every edge while object contents expand once. This terminates object cycles and detects root back-references; cyclic wire containers reject. Mutation requires document root with zero incoming references, document[5] wrapper with exactly one, its backing array with exactly one; catalog root zero/backing one. Unknown object owners are included rather than ignored or copied-on-write. Six derived sharing/loop fixtures cover wrapper/array/struct/document loop plus catalog loop/backing guard. Source bytes remain unchanged on rejection. A repeated initial End inside a Route is rejected, as is any repeated End across the expanded chain. These are API guards, not newly claimed native behavior.


## Wave4 integration addendum
Production module is in current_archive; candidate evidence above is retained provenance, not the final MCP gate. See artifacts/wave4/transport-verification.json and wave4-audit for actual typed transport/fresh-save verification. All current ownership scans delegate graph_references; legal object cycles retain identity, unsupported inline container cycles/unknown values reject. All responses are strict JSON with explicit nonfinite labels/raw bit metadata; finite setter-input semantics are unchanged.

The original candidate positive used an existing derived Path ID100. Final wave4 integration creates its test Path through the corrected native high-water allocator (10003 -> Path10004/counter10004), then the Itinerary factory preserves that existing Path10004 and counter unchanged. The historical Path100 evidence is not new-allocation proof.
