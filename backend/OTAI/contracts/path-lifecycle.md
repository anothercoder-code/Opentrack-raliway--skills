# Original bulk Path deletion and Itinerary persistence

Targets original stock English OpenTrack 1.7. Use
`opentrack_generate_operations.network_operations` or a Stage/editor change:

```json
{"kind":"delete_all_paths","document":"BJTU1","end_ids":[19],"dependent_itineraries":"delete"}
```

This reproduces the saved-data consequences of **Functions → Delete all Paths**
(release 1.7 item 34). Empty `end_ids` selects every route-start End in the named
document. A nonempty selection stays local to those exact directional End IDs;
selecting only a non-main-signal End produces no deletions. Unknown IDs, Signal
graphic IDs and duplicate selections reject. Original main types are
1, 2, 24, 25 and 26. Routes, Shuntings/Overlaps and unrelated Paths remain.

Original `OTDocument.deleteAllPaths:` first collects selected Paths, identifies
dependent whole Itineraries, confirms that consequence, deletes the Itineraries,
then removes Paths in reverse order from each End. This interface expresses
that choice as `dependent_itineraries`: `reject` reports dependencies without
writing; `delete` stages their whole document definitions and catalog entries
for deletion. The original source project remains unchanged in both cases.

Dependencies use document, owning End, native Path ID/name and saved object
references. They include Itineraries owned by other selected documents. Removing
one Path removes the entire affected Itinerary, not only that step. A remaining
Path used elsewhere survives. Malformed or ambiguous saved references reject.

Original `destHasChanged` calls `OTCourseController.update`; it refreshes/sorts
the Course view rather than removing saved Itinerary strings. This operation
therefore preserves Course definitions and timetable records. A draft can
report missing Course Itineraries afterwards. `reset_course_itineraries` is an
explicit separate command, available in the same batch after `network_operations`.
Binding a replacement Itinerary can be a more appropriate choice than pruning.
No implicit Course deletion, timetable deletion or service replanning occurs.

Generation responses give counts and ten-item previews. `network_changes_json`
contains all removed Paths, Itineraries and affected Course references. Stage
returns full changes; persistent editor undo/redo restores complete snapshots.
Existing generation/source-digest/publication rules apply. Bounds are 10000
selected Ends, 10000 removed Paths and 10000 affected Itineraries per command,
within the shared 1000-operation batch limit.

## First-Path-only original encoding

`OTDest.encodeWithCoder:` removes entries after index zero with
`withRebuildingPathInfoArray=false`, encodes its superclass and all Path info,
then rebuilds the transient expanded array. Generated Itineraries now persist
only their first actual Path in group zero and retain all `OTArrayExtInfo`
references. Embedding every Path pulled foreign infrastructure graphs into the
owner document and produced dangling-graphic errors for cross-document chains.
The fix preserves all ordered Path references and avoids those foreign objects.

## Function/source evidence

`artifacts/research/path-lifecycle-v028.json` pins the original binary, bank,
reviewed C hashes and focused recovery records. Main entries:

| Original method | Entry | Implemented data behavior |
|---|---|---|
| `OTDocument.deleteAllPaths:` | `0x49f48c` | Selection, whole-Itinerary consequences, document scope |
| `OTEndModel.deleteAllPaths` | `0x4c4d1c` | Main-signal gate and Path-list removal |
| `OTDestInspector.deleteDestWithName:` | `0x48abc0` | Document definition and catalog entry removal |
| `OTDocument.informDocAboutDeletedPath:` / `informDestAboutDeletedPath:` | `0x4a1d94` / `0x4a1e8c` | Cross-document dependent Itineraries |
| `OTController.destHasChanged` / `OTCourseController.update` | `0x42b310` / `0x45d1c8` | Course references survive |
| `OTSignalModel.isMainSignal` | `0x5d0814` | Exact accepted signal types |
| `OTDest.encodeWithCoder:` | `0x478058` | First Path object plus complete Path references |

`OTSource/generated/recovery-catalog.json` and the compiled restored signal
predicate were consulted. `otsource-reference-v028.json` records 34 current CLI
cases and unchanged source fingerprints. The bulk command and RailML importer
are marked deferred in that source catalog; a compiled signal predicate does
not establish their implementation. This change does not alter OTSource.

Tests cover native archive reload, valid multi-document Itinerary generation,
selected/all/non-main cases, dependent whole-Itinerary removal, unchanged
Courses/timetables, explicit pruning, persistent undo/redo and real compact MCP
publication. They do not certify native GUI notifications or a full simulation.
No instruction-level fallback or native OpenTrack launch was used.
