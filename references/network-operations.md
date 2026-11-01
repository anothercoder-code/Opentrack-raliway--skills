# Directional topology and movement definitions

> Current readiness: the legacy whole-project/draft mutation pipeline is
> quarantined. `opentrack_generate_operations`, `opentrack_stage_changes` and
> related editor/publication writers return `LEGACY_GEOMETRY_DISABLED`; appearing
> in tool discovery does not enable them. Batch/draft mutation forms below are
> retained behavioral/reference material, not instructions to execute today.
> Independently enabled reads/exports or bounded `current_archive` operations
> must be selected through their actual schema; there is no generic replacement
> alias. Do not bypass the guard by invoking legacy internals.

The topology engine is independent Python code over decoded double-vertex records. It uses reciprocal related halves, Edge references and document connectors. Coordinates never determine connectivity. It does not call OpenTrack search selectors.

## Inspect and search

```json
{"kind":"routes","start":{"document":"BJTU1","end_id":379},"limit":5}
```

Call `opentrack_search_network`. Modes:

- `topology`: simple directed walks between arbitrary directional Ends; signals are not required.
- `routes`: stop at the next main signal. Ordinary Route endpoints must be main-signal Ends.
- `paths`: chains of already defined primary Routes, matched by native IDs and expanded across document continuations.

Use document-qualified End IDs, not Signal graphic IDs. `via`, `avoid_nodes` and `avoid_edges` support ordered waypoints and exclusions. Distances are integer metres. Results include vertex/edge sequences, switch choices and exclusive native safety resources. `truncated`, `hop_cutoff`, expansion and result limits must be retained in conclusions; a bounded failure is not a proof of no path.

`opentrack_inspect_topology` shows loaded Ends, attached signals and outgoing transitions. `opentrack_list_routes` shows primary Route IDs, owner, expanded movement and resource footprint. Remote continuation records are not presented as independent ordinary Routes.

## Create definitions through a draft

The quarantined legacy draft path used `opentrack_stage_changes` with ordered operations:

```json
{
  "changes":[
    {"kind":"define_route","name":"R:AgentCross","nodes":[
      {"document":"BJTU1","end_id":379},
      {"document":"BJTU1","end_id":250},
      {"document":"BJTU2","end_id":3}
    ]},
    {"kind":"define_path","name":"P:AgentCross","routes":[
      {"document":"BJTU1","start_id":379,"name":"R:AgentCross"}
    ]},
    {"kind":"define_itinerary","name":"I:AgentCross","paths":["P:AgentCross"]}
  ]
}
```

Route definitions validate directed continuity, loops and intermediate main signals; maintain unique owner-local array IDs, route indication ownership and End-model release groups; and support the verified local/single-document-boundary serialization shape. Aspect defaults come from existing owner Routes or verified metric track-speed indication; other systems need explicit `signal_aspects`. Multi-boundary continuation and full protection/attribute parity remain under the full replication requirements.

Path references select exactly one native Route by document/start End plus ID or name. Successive Routes must meet at the same directional End. Itinerary definitions update both the infrastructure `OTDest` and library `OTDestInfo`, including extended Path IDs. Continuation excludes immediate identical Paths; a setting back requires the next first End's actualRelated within the previous final Route, before its last vertex. Actual reversal behavior remains unverified. Validate and deliver the requested native definitions without requiring simulation trials. [Itinerary controls](itinerary-controls.md) covers editing, copy/rename/delete, Add, replacement and catalog reset. Local itinerary priority and full operating behavior are not certified by this constructor.

### Original Route controls

All three definitions accept an optional ASCII `description` (default empty).
Route generation also writes these verified original fields:

| Input | Original meaning |
|---|---|
| `reserve_with_previous` | `Res. with prev. R.`; default false |
| `discrete_for_moving_block` | `Discr. Mov. Block`; default false |
| `slow_speed_only_for_head` | Restriction applies to the train head; default false |
| `allow_occupied_entry` | `Entry in occ. Block`; default false |
| `occupied_entry_use_speed`, `occupied_entry_speed_kmh` | Enable the occupied-entry speed limit, with a stored default of 40 km/h |
| `occupied_entry_use_time`, `occupied_entry_wait_s` | Enable the occupied-entry waiting time, default 0 seconds |
| `approach_zone_length_m`, `approach_zone_speed_kmh` | Approach-zone distance and target speed, default 0 |
| `reservation_point_m`, `use_reservation_point` | Stored reservation-point distance, default 5000 m and disabled |
| `release_point_m`, `use_release_point` | Release-point distance; omitted enable flag follows the original old-record rule `release_point_m > 0` |

These are serialized controls. No native dispatch, occupied-entry movement,
deadlock prevention or actual braking behavior is executed or certified.
New Routes clear inherited overlap references unless an explicit exact Overlap
is selected. Shunting/Overlap creation, ordered release boundaries and local
slow-speed-zone endpoints are described in [protection](protection.md).
Cross-document companion records receive the same controls with local release
groups. The single-boundary limit still applies.

`opentrack_list_routes` returns `properties` and its `security_array_version`.
The original stock `topoOst`/`topoWest` samples use parent v5; v6 inserts a group
before Route flags/release references. Do not shift those fields by guessing.
Generation upgrades **all** loaded v5 security descendants in the draft before
cloning, with native defaults `5000, false, release_point_m > 0`, then records
the count in `serialization_migrations.OTSecurityArray`. Shared parent class
objects, Shunting subclass tails, reference identity and native round trips are
covered by frozen original-sample regressions. Unverified versions are rejected.

`opentrack_list_paths` returns descriptions. Catalog `kind: itineraries` returns
each library name, actual document path, starting End, description and extended
Path references; it does not infer alternative priorities from names such as P1.

## Document references and publication

`OTDestInfo.contents[2]` is an infrastructure document filename. A visible library name can still fail to load if this path points to the old template. `repair_itinerary_documents` rebuilds references from the selected documents' real itinerary definitions. Draft creation and isolated publication always rebase these paths. Validation checks missing document files, definitions and Path ID references.

The currently quarantined `opentrack_publish_draft` implementation was designed to create a fresh separate project and friendly `.run` without changing the source or stopping a running original application. Existing target names are rejected. Applying back to the original uses the existing closed-application/digest/backup checks.

Current tests establish independent topology/search behavior and archive/reference round trips. They do not establish complete original search parity, native dispatch behavior or completion of the full product replica.

## Original bulk Path deletion

Use `network_operations: [{"kind":"delete_all_paths","document":"BJTU1","end_ids":[19],"dependent_itineraries":"delete"}]`.
Empty `end_ids` means every main-signal route-start End in that document, as in
original Functions → Delete all Paths. An explicit non-main-signal selection
does not fall back to all. These are directional End IDs, not Signal graphic IDs.

Default `dependent_itineraries: "reject"` returns a typed dependency report.
Explicit `delete` removes each affected **whole Itinerary**, including those
owned by another selected document, from its document and destination catalog.
The native command preserves Course Itinerary strings; this operation does too.
Inspect resulting validation. Rebind affected Courses or explicitly use
`course_lifecycle: [{"kind":"reset_course_itineraries","course_ids":[...]}]`
in the same batch when pruning is intended. Courses and timetable rows survive.

`network_changes_json` contains the full changes; responses preview ten records.
The command also supports Stage and persistent editor undo/redo. Generated
multi-document Itineraries now follow the original encoder: embed the first
Path only, with every Path retained in ordered native references. The fix avoids
embedding foreign infrastructure into the owner document.
