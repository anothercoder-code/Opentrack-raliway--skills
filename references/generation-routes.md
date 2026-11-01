# Route/Path/Itinerary compilation from an explicit directed graph

Use discovered `opentrack_compile_route_bundle` for information generation from a
resolved directional End graph. This is broader than a fixed three-by-three
scenario and narrower than native infrastructure creation. It does not read or
write archives, discover actual signals, or infer connectivity from coordinates.

## Actual input fields

- `project`, optional `run_file`, and explicit `route_name_prefix`.
- `nodes`: each has `document`, integer `end_id`, explicit boolean `main_signal`,
  and optional ordered integer-code list `signal_aspects` for main-signal nodes. IDs are supplied
  directional Ends, not invented signal IDs or drawing coordinates.
- `links`: directed `{source:{document,end_id}, target:{document,end_id},
  length_m}` transitions; finite nonnegative metres. Reverse connectivity needs
  its own valid directed data. Crossing lines do not imply connectivity.
- `paths`: `{name,start,end,via?:[End,...],nodes?:[End,...]}`. Use explicit `nodes`
  or ordered `via` to disambiguate if multiple paths match. Do not silently pick
  a shortest candidate. Names are preserved.
- `itineraries`: `{name,paths:[exact_name,...]}`; an empty list is allowed.
- `cycle_policy`: default `reject`; `simple_paths` explicitly excludes repeated
  directional Ends. This is not unrestricted cycle support.
- `max_expansions`: default 50000, maximum 500000; `max_routes`: default/max 10000.
  Exhausting a search limit fails closed, not “all routes found so far.”

The compiler enumerates next-main-signal Routes, resolves uniquely requested
Paths, checks consecutive Itinerary joins and validates output against production
input models. `ROUTE_BUNDLE_INVALID` covers invalid graph/ambiguity/budget failure.
Inspect and fix the stated cause; never describe a truncated search as complete.

## Output and handoff

`evidence_level=user_graph_compiled`, `native_archive_written=false` and
`native_simulation_verified=false` explicitly bound the result. Inspect `counts`,
`routes`, `paths`, `itineraries`, `path_distances_m`, `cycle_policy` and
`complete_within_policy`. Completeness is within the supplied graph and policy,
not completeness of the user's unread original project or interlocking logic.

`native_apply_spec.ordered_batches` contains real `GenerateOperations` inputs,
ordered Routes → Paths → Itineraries in supported-size batches. It is an apply
**specification**, not an executed action or atomic transaction. The named legacy
`opentrack_generate_operations` writer is currently quarantined with
`LEGACY_GEOMETRY_DISABLED`; these are schema-valid specifications, not presently
executable persistence instructions. For a supported replacement, explicitly map
and review the matching current_archive/native workflow before applying anything.
After any actual supported write, review every returned saved result, and set each later batch's `project` to the previous
real `draft_project`; never reuse a speculative receipt. Native validation still
must verify existing target names, End identities, signal meanings, continuity,
archive support and stale bindings. No automatic reverse movement, crossing
protection, signal aspect or native result is inferred.

For an information-only workflow, carry these definitions into a coherent
`opentrack_prepare_operations` batch with stock/services as limits permit, or
retain ordered definition batches as separate reviewed artifacts. Explain any
external-catalog assertions needed between batches. Do not confuse a prepared
catalog assertion with a native persistence receipt.
