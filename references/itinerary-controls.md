# Itinerary data controls

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

The historical batch contract used `opentrack_generate_operations` with ordered `network_operations`; that writer is now quarantined.
Inspect exact names with `opentrack_list_catalog(kind: itineraries)` and optional
`include_itinerary_details: true`. `itinerary_usage: used|unused` includes disabled
Courses. `itinerary_query_field: name|description` narrows case-folded searches.

```json
{
  "network_operations": [
    {"kind":"duplicate_itinerary","name":"I:BJN-JNW_1","new_name":"I:Express"},
    {"kind":"edit_itinerary","name":"I:Express","description":"Express service"},
    {"kind":"append_itinerary","name":"I:Express","source":"I:JNW-NJN_1"},
    {"kind":"rename_itinerary","name":"I:Express","new_name":"I:ExpressFinal"}
  ]
}
```

- `edit_itinerary`: optional `description` and/or ordered `paths`. Omitted values
  survive. The first Path determines owning document; safety margins survive.
- `rename_itinerary`: fresh `new_name`; original behavior changes only the first
  occurrence in each Course. Repeated later names can remain unbound.
- `duplicate_itinerary`: explicit fresh `new_name`; original copy clears the
  description and independently copies safety margins. Overwrite/localized default
  naming is unsupported.
- `append_itinerary`: target `name`, source `source`; exact same directional End
  **and document** at the join. Source and target attributes survive; self-Add is
  unsupported.
- `replace_itinerary_paths`: `name`, zero-based `start_index`, `count`, new `paths`.
  Interior borders retain first/last Ends. Prefix/suffix may change their outer
  End. An aliased repeated-Path selection is explicitly rejected.
- `delete_itineraries`: exact `names`, or `selection: unused` without names.
  Remove whole definitions/catalog infos; Course strings and timetables survive.
- `reset_itinerary_catalog`: rebuild infos from loaded definitions, removing
  inactive entries, adding missing active entries and refreshing Path refs.

New/edit/replacement continuation excludes immediate identical Paths. At a
setting back, the next first End's actualRelated must lie **inside the previous
final Route, before its last vertex**. Automatic Shunting Paths are supported.
Append uses its stricter exact-join rule. These checks generate native data;
actual train reversal/dispatch is unverified.

The native controller can retain stale Path caches after editing. The default
Agent operation composes an explicit selected-info refresh. Edit/replacement can
set `catalog_sync: preserve`; `reset_itinerary_catalog` refreshes all loaded
definitions. Drafts always rebase document filenames. Optional catalog details
show `catalog_paths_match_definition` and saved safety margins in metres.

Read full `network_changes_json`, validation and bounded previews. Deleting a
used Itinerary, or renaming only its first repeated Course occurrence, can leave
invalid bindings. Explicit Course rebind/reset commands are separate. Stage and
persistent editor support these same data operations and snapshot undo/redo.

See [safety margins](itinerary-margins.md) for profile generation/editing, paged lookup and text exchange. Native UI selection/dialogs, incremental search cursor/collation and full original-function parity remain incomplete. The source
contract is `OTAI/contracts/itinerary-controls.md` and exact original function
evidence is `OTAI/artifacts/research/itinerary-controls-v029.json`.
