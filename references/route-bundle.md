# User-graph → Route / Path / Itinerary information compilation

**Independent implementation; not recovered original algorithm parity.** This
compiles information only. It never opens/writes an archive or starts OpenTrack.
The input graph and main-signal/aspect assertions belong to the caller; passing
these checks is not proof that they match any target native project.

## Entrypoints

- MCP: `opentrack_compile_route_bundle` (registered in the generation profile).
- Python: `opentrack_ai.route_bundle.compile_route_bundle(spec)`.
- CLI from OTAI: `python -m opentrack_ai.route_bundle graph.json` (or `-` stdin).
- Real input schema: `RouteBundleInput.model_json_schema()`.

## Minimal input

```json
{
  "project": "OTProjects/OwnGraph",
  "run_file": "own.run",
  "route_name_prefix": "R_own_",
  "cycle_policy": "reject",
  "nodes": [
    {"document": "Main", "end_id": 11, "main_signal": true, "signal_aspects": [0]},
    {"document": "Main", "end_id": 27, "main_signal": false},
    {"document": "Main", "end_id": 41, "main_signal": true, "signal_aspects": [0]},
    {"document": "Main", "end_id": 59, "main_signal": true}
  ],
  "links": [
    {"source": {"document": "Main", "end_id": 11}, "target": {"document": "Main", "end_id": 27}, "length_m": 100},
    {"source": {"document": "Main", "end_id": 27}, "target": {"document": "Main", "end_id": 41}, "length_m": 120},
    {"source": {"document": "Main", "end_id": 41}, "target": {"document": "Main", "end_id": 59}, "length_m": 150}
  ],
  "paths": [
    {"name": "P_own", "start": {"document": "Main", "end_id": 11}, "end": {"document": "Main", "end_id": 59}}
  ],
  "itineraries": [{"name": "I_own", "paths": ["P_own"]}]
}
```

The example's IDs/aspect codes are illustrative, **not** receipts for an actual
project. Use exact directional End/Connector IDs from an authorized graph export
or geometry manifest. Signal graphic IDs, raw paired-vertex drawing edges and
coordinates are not interchangeable with these resolved transitions. A reverse
movement requires its own directed connectivity; sharing physical track or a
conflict resource never creates adjacency. No crossing inference is performed.

The compiler discovers every simple next-main-signal movement, stopping at the
first main signal on each branch. Thus this example produces two Routes, one
Path and one Itinerary. The routes are sorted by full directional node sequence
and named `R_own_0001`, `R_own_0002`; supplied End IDs and Path/Itinerary names
are never padded, renumbered or silently changed. Changing graph content may
change generated Route names: this is not a persistent identifier allocator.
No aspect defaults are invented: each discovered Route start must supply codes.

## Selection, cycles and bounds

Path requests need a unique simple directed walk from `start` to `end`. Multiple
walks reject rather than silently taking the first/shortest. Disambiguate with
ordered `via: [EndRef, ...]` or an explicit `nodes: [EndRef, ...]` walk (including
both endpoints). Via entries are distinct intermediate Ends and remain ordered.
Routes are still discovered over the full graph, not only requested Paths.
Duplicate source-target transitions reject even if their lengths differ, because
the production Route payload selects nodes, not a parallel Edge identifier.

- `cycle_policy: reject` (default) rejects any directed graph cycle.
- `simple_paths` explicitly excludes repeated directional Ends; it is **not**
  exhaustive enumeration of cyclic train movements. Closed requested Paths and
  Itineraries that repeat a directional End are outside this compiler's scope.
- Itinerary Paths must share the exact directional End; no reversal is inferred.
- A Route crossing more than one document boundary rejects in line with the
  current native writer's verified continuation limit.
- Maximum 10,000 nodes, 50,000 links, 1,000 requested Paths / Itineraries; maximum
  walk length 4,096 nodes. Each native Path/Itinerary also obeys the real models.
- `max_expansions` defaults to 50,000 (maximum 500,000), shared by Route discovery
  and Path selection; `max_routes` defaults to 10,000 (maximum 10,000).
- Exhaustion **raises an error with no partial bundle**. Completeness is only
  claimed within the chosen simple-path policy and successfully completed bounds.

## Native apply contract and limits

`native_apply_spec.ordered_batches` contains real, validated
`GenerateOperations` payloads: Routes before Paths before Itineraries, no more
than 100 entities per batch in this compiler's emitted chunks. This is its
handoff policy, not the overall `GenerateOperations` operation budget. `tool` is `opentrack_generate_operations`.
Application is **not performed** by this compiler. Its named legacy
`opentrack_generate_operations` writer is currently blocked with
`LEGACY_GEOMETRY_DISABLED`. This output is not a usable bypass or a claim that
native application is enabled. If a matching current_archive or original workflow
is selected instead, map its actual schema and verify graph identity and name
collisions; do not silently rename the tool or assume parameter equivalence.
For each later batch replace its `project` with the previous call's returned
`draft_project`; otherwise independent calls would fork from the original and
lose preceding definitions. Keep `run_file` consistent. The sequence is not one
atomic transaction and does not publish or overwrite the source project.

Production `DefineRoute`, `DefinePath`, `DefineItinerary`, and
`GenerateOperations` models are imported directly without `archive`/typedstream.
Native signal types, actual adjacency, existing identifiers, class-shape
serialization, archive reload and draft validation remain the applying server's
responsibility. Compiler success must never be presented as native archive
completion or simulation acceptance. `native_archive_written` and
`native_simulation_verified` are always false.

## Evidence and coverage

Run from the repository root:

```sh
PYTHONPATH=OTAI python -m unittest discover -s OTAI/tests -p test_route_bundle.py -v
```

The suite covers direction, signal termination, explicit/ambiguous selection,
cycles, repeated IDs, external references, disconnected chains, parallel-edge
ambiguity, finite distances, bounds, real payload schema and CLI. This is
independent partial coverage for route/path/itinerary agent information
compilation (G03/G04/A06), not proof of original automatic-route-search parity
(M4.1.1) or of native persistence without its dependencies and fixtures.
