# Current persisted Route / Path / Itinerary functions

Scope: **current saved-data functions**, not GUI, simulation, original Objective-C
runtime execution, or full-project correctness. No old-version migration. The
fixture BJTU project is synthetic infrastructure; these tests make no operational
railway safety claim. All inputs are read-only bytes; mutations return a new archive
only after reload checks. Integrator owns atomic publication and project validation.

## Hooks

- `inspect_archive(data, kind, name, array_id=None, start_id=None)` returns exact
  description, IDs, saved object count, and ordered raw info references. It does
  not pretend to resolve foreign documents or expand runtime tails.
- `set_description(data, kind, name, description, array_id=None, start_id=None)`:
  returns `(archive_bytes, change_report)`. `kind` is OTRoute, OTPath or OTDest.
  Name/optional IDs must identify exactly one current record. Empty text clears.
  New NSString allocation avoids changing other aliases of the old string.
- `create_local_path(data, name, array_id, routes, description='')`: returns
  `(archive_bytes, change_report)`. Each Route selector requires exact `name`,
  `array_id`, `start_id`. Composes native init/add/rebuild/save saved-data behavior.

## Input domains and limits

Descriptions/names are Python Unicode serialized as NSString v1 UTF-8. This is
verified wire behavior, not a claim that native GUI input validation or character
collation is reproduced. Unpaired surrogates and embedded NUL reject. A 1 MiB
UTF-8 limit and 10,000-Route list cap are **interface safety limits**, not recovered
native limits. Text has no physical unit; IDs are signed 32-bit integer identities;
Route order is list order, not a numeric physical unit.

Creation requires OTDocument v4, current local OTEndModel v7, Route v0 with
SecurityArray v6, Path v0, OrgArray v2, and a populated existing OTPathList v0.
Every selected Route has no continuation (`continuation=-1`), at least two Ends,
is in its first End's Route list, and all Ends are identity-members of this
same document's model collection. Adjacent Routes share the exact directional End
object. Repeated Routes and return to the initial End reject. The first End already
has a nonempty unaliased PathList with verified Path/ArrayInfo templates.

Creation now uses original `createNewRspID` (`0x004c7188`): the owning End's
`highestGivenRspID` (group 19, int32) increases by one and that value is the new
Path ID. `array_id` is an explicit expected fresh ID and must equal this value;
historical unused-ID holes are no longer accepted. The API rejects overflow,
negative high-water marks, duplicate Route/Shunting/Path IDs, and a high-water
mark lower than any existing allocated ID in those owner lists. INT32_MAX-1 may
allocate INT32_MAX; INT32_MAX cannot allocate again. Original C has no shown
bounds checks; these are conservative API guards. Source files remain unchanged;
the fresh output changes only the appended Path and this counter. Existing End
references (model list, route arrays, signals, edges and elements) retain identity;
unknown/nested incoming owners reject rather than clone the End. Class/version,
complete layouts and encoder-supported reference roles are checked.

A name must be nonempty and unique **within this document**. Existing ext-info
names/IDs that would be captured reject. The former hole-reuse policy was not the
native allocator and is superseded, not retained as a supported generation mode.
There is **no global/project-wide uniqueness claim**: an integrating project
operation must check its complete loaded document/catalog set itself before
publication. This hook must not be advertised as a complete project operation.

Existing cross-document Path replacements, cross-document creation, automatic
Shunting Paths, empty PathList allocation, corrupt high-water repair, rename/duplicate,
Itinerary sequence edits and runtime expansion are unsupported. In particular,
current BJTU Paths span documents; their chains are not blindly replaced with a
shorter local sequence. Their descriptions may be safely edited without touching
any saved references.

## Function evidence

| Original entry | Original selector | Saved-data implementation |
|---|---|---|
| 0x52c2c8 | OTOrgArray.setArrayDescription: | Replace description reference only |
| 0x52c2f8 | OTOrgArray.arrayDescription | Read description reference |
| 0x52c664 | OTOrgArray.encodeWithCoder: | Super, name, ID/start-ID, description; description is group 3 |
| 0x559398 | OTPath.initWithCapacity: | Independent routeInfoArray, then OrgArray init |
| 0x52c164 | OTOrgArray.initWithCapacity: | Empty name/description; identity initialized -1 before explicit assignment |
| 0x55a050 | OTPath.rebuildRouteInfoArray | Ordered new OTArrayInfo(name, arrayID, arrayStartID) for each Route |
| 0x4c4770 | OTEndModel.addToPathList: | Append Path; no counter or other binding update in this method |
| 0x55a600 | OTPath.encodeWithCoder: | Persist only first Route object and complete info array |
| 0x478058 | OTDest.encodeWithCoder: | Persist only first Path object and complete info/margins |
| 0x5a7538 | OTRoute.encodeWithCoder: | Remove continuation before serialization; our fresh saved graphs are never expanded |

These are Ghidra C outputs plus Objective-C metadata, not recovered original source.
`evidence/function-evidence.json` pins exact file hashes and the frozen writer.
0x5593f8 was researched but Route replacement is NOT claimed implemented.

## Actual-file verification

Run `python opentrack-path-functions/test_path_functions.py` from workspace root.
It uses frozen standalone writer and independent official pytypedstream 0.1.0
reader. No source fixture is overwritten.

- 18 writes: three current BJTU docs × Route/Path/Dest × UTF-8 edit/empty clear.
  Official-reader graph fingerprints preserve every reachable non-description
  field and all reference identities, not just JSON projections.
- New local Path in current BJTU1: real Route chain 19→67→29, explicit ID 100.
  Actual output `.opentrack` file is fresh-read by official reader. Exactly one
  runtime Route is saved; two ordered infos survive; first Route aliases the
  original Route object. Removing only the added Path makes canonical whole-graph
  bytes exactly equal to the original, proving no existing fields/refs changed.
- Invalid ID, exhausted range, cross-doc continuation, disconnected chain, unknown
  identity and invalid strings reject without replacement bytes or source changes.

`evidence/verification.json` contains exact fixture and output hashes and assertions.
A native executable is not a gate for these narrow archive-function claims. It
would be required before claiming full native application/simulation equivalence.

### Review hardening

Creation additionally rejects duplicate IDs anywhere in the document model
collection, End objects outside that collection, incorrect superclass versions
for Doc/End/NSString/NSMutableArray/PathList/ArrayInfo, aliased PathList ownership,
and a PathList backing array referenced by any other graph edge. A fourth test
mutates real-fixture model IDs and superclass versions and verifies rejection.
Frozen implementation SHA-256:
`6a4db2ce2908b4aa890243602479c691661cc0ef060a2d9f5b04bf8ebcae5f99`.
