# Original Itinerary inspector data controls

Version 0.29 uses typed `network_operations` through generation, Stage and the
persistent editor. Names identify exact selected-project definitions. No native
GUI, notifications, native object lifetime or simulation is executed.

| Command | Saved-data behavior |
|---|---|
| `edit_itinerary` | Change optional description and/or full ordered Path list. An omitted description is preserved; empty clears it. A changed first Path moves the definition to its document. Safety margins survive. |
| `rename_itinerary` | Fresh unique name. Rename definition/catalog and replace only the first occurrence in each Course, preserving priority order and subsequent duplicate strings. Timetable data is unchanged. |
| `duplicate_itinerary` | Explicit fresh `new_name`. Share resolved Path definitions, copy independent info/margin arrays, reset description to the original empty initializer value. Existing-name replacement and the localized `CopyOf` prefix are unverified. |
| `delete_itineraries` | Exact names, including inactive catalog-only entries; or `selection: unused` over catalog entries. Remove whole definitions and infos. Course strings and timetables survive, and validation exposes resulting missing bindings. |
| `reset_itinerary_catalog` | Clear infos and rebuild from all loaded definitions, removing inactive entries, adding missing active entries and refreshing Path references. Definitions and Courses survive. |
| `append_itinerary` | Target last End and source first End must have identical directional ID **and document**. Concatenate source Paths; target description/margins and source definition survive. Self-Add is explicitly unsupported. |
| `replace_itinerary_paths` | Zero-based contiguous interval. Interior replacement retains old first/last Ends; prefix/suffix may change their outer endpoint. Preserve description/margins; move owner when needed. Reject an aliased selection when original `indexOfObject` would target an earlier repeated Path. |

New/edit/replacement Path continuation follows original `fillNewContinuationArray`
and `fillReplaceContinuationArray`: immediately repeated Path objects are excluded.
The next first End must equal the previous last End, or its `actualRelated` End
must occur before the last vertex of the previous Path's final Route. A connector
resolves through the remote block End and its related vertex. Automatic Shunting
Paths participate. This allows a setting back inside the final Route. `Add` has
its separate stricter exact-boundary rule.

Original controller edits and Add can leave an existing OTDestInfo Path cache
stale. The default Agent operation explicitly composes the edit with original
`fillArrayInfoFromDest` for the selected entry (`catalog_sync: refresh_selected`).
Edit/replacement can choose `preserve` to retain cached Path refs/start ID.
Draft publication always rebases document filenames to the actual loaded owner.
`reset_itinerary_catalog` fully refreshes all loaded entries. This composition is
reported; it does not claim byte-identical native controller cache behavior.

`opentrack_list_catalog(kind: itineraries)` supports `itinerary_usage: all|used|unused`,
`itinerary_query_field: all|name|description`, and optional details: exact saved
definition Paths, Course reference indices, safety margin values and cache match.
Usage includes disabled Courses and every occurrence. Searches are case-folded
data queries; native incremental search cursor and Foundation collation are not
reproduced. Default results retain the existing compact view. Full mutation diffs
are saved in `network_changes_json`; previews are bounded.

Persistence embeds only the first Path and keeps all ordered ext infos, following
original OTDest.encodeWithCoder. Cross-document definitions are references rather
than embedded foreign graphic graphs.

## Evidence and limits

`artifacts/research/itinerary-controls-v029.json` records the exact bank, hashes,
34-function receiver/type pass, remaining inferred signature sites, OTSource
snapshots and additional simple callees read through `opentrack_read_function`.
The two expanded body ranges retain every old byte, stay in executable sections,
keep original metadata identities and contain no other bank entry. This recovers
omitted blocks; it does not certify all dynamic message semantics.

Key originals: OTDestInspector edit 0x48c838, rename 0x488354, delete 0x48ad94,
duplicate 0x48b3f0, Add 0x48a980, replace 0x48dd48, continuation 0x489b10/0x489d5c,
reset 0x48a82c/0x48a844 and refresh 0x487c04; OTCourseController first-occurrence
rename 0x45ee48 and usage 0x45c504; OTDest copy 0x47503c; OTOrgArray initializer
0x52c164; OTDestInfo copy 0x483530. Original overwrite
dialogs, ordering/collation, inactive definition loading, ambiguous repeated-Path
replacement, self-Add and remaining full-function scope are incomplete.

Tests establish typed data commands, archive reload, preservation, failure cases,
snapshot undo and real MCP/package behavior. They do not establish native runtime
acceptance or completion of the full 176-item original-function inventory.

Safety-margin data commands, paging/lookup and original text exchange are available in v0.30; see [safety margins](itinerary-margins.md).
