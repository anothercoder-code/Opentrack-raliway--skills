# OTPath existing append — extracted, guarded archive operation

Status: **standalone module + tests; not integrated/published**. Imports frozen
`opentrack-wave2/OTAI/opentrack_ai/current_archive` codec/schema. No GUI, simulator,
local Codex, native executable, legacy format or registry edits.

## Source findings (decompiler output, not recovered original source)

| Function | Recovered behavior | This interface |
|---|---|---|
| `0x55971c addObject:withRebuildingRouteInfoArray:` | Calls superclass addObject(arg1); rebuild only when char arg2 is exactly 1. No type, continuity, duplicate or self check. | Add one **Route**, rebuild=true only. Route type is proven by `0x5599e0` call site, not method spelling. |
| `0x55958c addObject:` | Super append then unconditional rebuild. | Same successful persisted result in guarded Route domain. |
| `0x5595fc addObjectsFromOTArray:` | Super append elements then rebuild. | Existing **Path source is flattened to its resolved Routes**; never inserted as a nested Path. |
| `0x52846c OTMutableArray.addObjectsFromOTArray:` | `arg1.embeddedArray` passed to Foundation `embeddedArray.addObjectsFromArray:`. No hand-written loop or snapshot. | Self/overlap unsupported. Foundation self-alias behavior was NOT inferred or executed; no invented snapshot-as-native claim. |
| `0x55a050 rebuildRouteInfoArray` | removeAllObjects; iterate current runtime count, create OTArrayInfo, copy name, ID, start ID in order. No deduplication. | Exact order/identities; guard excludes repeat/cycle. Fresh info objects, no shared-info mutation. |
| `0x55a600 encodeWithCoder:` | If ID=-1 adjusts start ID; removes runtime indexes 1..count-1 without rebuild; superclass encode; encode full infos; update runtime. | Reject unresolved negative identities; persist **one first Route + all infos**, fresh-reload resolve all Routes. Runtime reconstruction is a Python data operation, not native application execution. |
| `0x5599e0 updateIfNeeded:` | Trim runtime to first; for next info, append route continuation, use prior Route.lastObject's End.findRouteForArrayInfo; add found Route with rebuild=false; stop on failed lookup. | Reject partial/unresolved/continuation chains rather than save partial recovery. |
| `0x4c4034 End.findRouteForArrayInfo:` / `0x5b83b4 RouteList.getRouteWithArrayID:andArrayStartID:` | Requires open document; searches owning End RouteList by nonnegative ID/start, then fallback name (may assign IDs). | Exact ID+name+start resolution, actual End ownership and uniqueness. No guessing/fallback identity reassignment. Native “open” is replaced by fully decoded explicit input bytes, not simulated GUI state. |
| `0x5be53c continuesInOtherDoc` | True for indexOfFirstEndInOtherDoc >=0; negative means false. | Require current-fixture sentinel -1 (narrower API guard). |
| `0x5a575c appendObjectsOfContinuation` | Cross-doc continuation can change zones/groups and append nodes. | Not emulated; all such Routes rejected. |
| `0x4754f4 Dest.updateIfNeeded:` | Resolves next Path from previous Path.lastEnd with document-aware fallbacks, and updates saved document labels. | Any potential target Itinerary dependency in supplied document set rejects, even a last Path. No stale boundary is committed. |
| `0x559398 initWithCapacity:` / `0x55a5b0 initWithCoder:` / `0x5597a8 removeObjectsInRange:withRebuildingRouteInfoArray:` | Initialize info storage / read infos / conditional rebuild. | Evidence included to distinguish runtime from persisted lists; not advertised as new operations. |

## API

```python
outputs, report = append_existing(
    documents={"BJTU1": archive_bytes, "BJTU2": other_bytes, "BJTU3": other_bytes},
    target_document="BJTU1",
    target_ref={"name":"P:CURRENT_LOCAL_TEST", "array_id":100, "start_id":19},
    source_kind="OTRoute",  # or OTPath (flattened)
    source_ref={"name":"R:BJTU1_29-BJTU1_379_0", "array_id":0, "start_id":29},
    complete_document_set=True,  # explicit caller attestation, required
    source_document="BJTU1",  # optional, defaults to target
)
```

Input: nonempty explicit document-key → bytes dictionary and mandatory explicit
`complete_document_set=True` caller attestation. Missing/false/non-bool attestation
rejects; the module cannot discover omitted files. IDs are exact nonnegative
signed int32; bool is rejected. Nonempty names. Current OTDocument v4 / Route v0 /
Path v0 / End v7 and their complete class hierarchies only. Existing Path must have
one persisted first Route, nonempty valid infos, matching actual first Route,
correct owning End PathList. Each next Route must be in previous last End's RouteList,
identified without ID/name ambiguity, with all End objects in the local model list.

Output: new dict, only target bytes replaced; report carries hashes/counts/refs.
No input/disk mutation, so errors cannot partially commit. `Unsupported` is the
validation ValueError; low-level malformed-stream errors may also propagate without
output. Caller owns disk transaction. No auto-save, publish or external side effect.

**API guardrails, NOT original C constraints:** same document only; complete
nonempty chain; 1..10,000 Routes resource guard (no recovered native max);
nonnegative explicit identity; sentinel -1; no repeated Route, revisited End,
self append, aliased info backing array, multiple PathList ownership, ambiguous
lookup, unresolved or unsupported schemas. The original method has no recovered
loop/cycle maximum and performs no topology validation. Original uint count-minus-1
in update is an additional reason NOT to treat empty infos as valid.

All supplied documents are parsed and scanned for target direct OTDest pointers and
saved OTArrayExtInfo identity **or name fallback**, conservatively ignoring doc-label
mismatches for rejection. This can over-reject same IDs from unrelated documents;
it cannot silently waive a mapped dependency because of an uncertain label.
Guarantee is scoped to the **provided complete document collection**. No knowledge
or integrity claim about external omitted archives. Cross-doc source rejects even
with mappings: continuation/source document semantics require separate extraction.

## Evidence / tests

`python opentrack-next-functions/path-append/test_path_append.py`

1. **Real-source, derived-current positive**: prior verified
   `opentrack-path-functions/evidence/BJTU1-new-local-path.opentrack` (SHA256
   `c0ccf72b5d84b56186f16f7a1ff675dd322a425d2cc8f2088bd1b28d00375dec`). It was created
   from the real BJTU1 fixture in the earlier create-local-path test. It already
   contains two-route `P:CURRENT_LOCAL_TEST`; this module appends existing real
   Route 29→379, does not create another Path. Persisted count stays one, infos
   become three. This is **not claimed to be an original BJTU-authored Path**.
2. Written output is re-read using independently installed public
   `python-typedstream` official upstream reader, not the codec under test. All
   non-target-info graph fields and object alias references compare identically;
   first Route resolves to the same graph object as the owning RouteList entry;
   other document bytes unchanged. This is structural archive verification,
   **not proprietary OpenTrack application acceptance**.
3. Path-to-Path source flattening uses explicitly **prototype** source Path on a
   real graph, not mislabeled real-world fixture. Independent reload/all-other-
   graph equality pass.
4. All 12 original BJTU1/2/3 Paths contain cross-document chains; all reject atomically.
   There is no fabricated original-fixture append success.
5. Self append, missing document, wrong kind, overlapping/disconnected chain,
   saved dependency, first-route mismatch, empty infos, info aliases, duplicate
   model identity, wrong Route identity, unknown superclass versions reject.

Evidence C files are byte-for-byte extracted from frozen `resources/function-bank.zip`.
`evidence/source-manifest.json` records hashes. `evidence/verification.json` records
actual successful checks and output hashes. No native execution was used.
