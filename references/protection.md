# Shuntings, Overlaps and Route protection

This is a retained description of the legacy stock-English
`Shuntings/Overlaps`, `Release Groups`, and `Slow Speed Zone` batch design.
The generic `opentrack_generate_operations` and `opentrack_stage_changes`
writers below are now quarantined with `LEGACY_GEOMETRY_DISABLED`. They are
not executable alternatives for a new task, even when all old dependencies
are installed. Keep the guard; do not call the legacy classes directly or
remove it to replay this reference.

For current work, inspect the actually available typed current-archive tools
and [interface index](archive-interface-index.md). Use only their stated
Shunting/protection/read/write contracts; this reference does not supply an
active equivalent whole-project batch. If the needed write is missing, name
that gap and use an authorized original-app workflow or separately audited
implementation, rather than claiming an unavailable batch completed it.

## Historical dependency batch (not a current runbook)

1. Use `opentrack_search_network` with `kind: topology` and exact directional
   End IDs to find a Shunting movement. Main Signals are not required; do not
   guess connections from drawing coordinates.
2. In the old batch schema, `shuntings` belonged to the now-quarantined
   `opentrack_generate_operations`. Each item supplied
   `name`, directed `nodes`, optional `description`, `speed_kmh` (default 40),
   `release_time_s` and `reservation_time_s` (both default 0).
3. The generator creates the native Shunting **and its same-name automatic
   Path**. Use this Path name directly in `itineraries[].paths`, alongside
   ordinary Paths. Do not create another Path with the same name or put the raw
   Shunting into a Route list.
4. To use that movement as an Overlap, set `routes[].overlap` to its exact
   `{document, start_id, name}`. Its start must equal the Route terminal End.
   Use `release_time_s` on the Shunting for the Overlap's release delay.

The batch order is stations/rolling stock → Shuntings → Routes →
`route_protection_updates` → Paths/Itineraries → Courses/timetables.
That historical batch accepted at most 1000 definition/update operations before
service-pattern expansion; an oversized combined batch returns `GENERATION_SIZE`.
Catalog `kind: shuntings` returns automatic Path IDs, geometry, stored speed and
release time. `opentrack_list_paths`/`opentrack_trace_path` include these automatic
Paths. Reported Shunting Edge limits include the stored speed cap.

## Route boundaries and partial edits

`routes` also accepts:

- `release_group_boundaries`: ordered `{document, end_id}` entries on the
  Route, including its start and end. Intermediate boundaries split release
  groups. To represent original Group, supply first/last; for Ungroup, supply
  every End. Cross-document Routes partition these by document and retain each
  local segment's first End. Read back effective boundaries in the result.
- `slow_speed_zone: {start: EndRef, end: EndRef}`: ordered distinct endpoints
  on a local Route. The head-only flag is `slow_speed_only_for_head`. These
  endpoints define where a signal indication's restriction applies; they are
  separate from approach-zone speed/length.
- `overlap`: an exact Shunting selector. The terminal companion carries the
  binding on a continued Route. `opentrack_list_routes.terminal_properties`
  exposes the terminal part's data.

The old compact-profile batch represented an existing Route update as follows.
This is schema/history illustration, not an executable current route through the
quarantined generator:

```json
{
  "route_protection_updates": [{
    "route": {"document":"BJTU1","start_id":3,"name":"R:Protected"},
    "slow_speed_zone": null
  }]
}
```

Supply the actual project and exact Route selector. Omitted fields remain
unchanged; explicit null clears the zone/Overlap or resets release boundaries
to the supported defaults. The example clears only the slow-speed zone.
The quarantined `opentrack_stage_changes` formerly accepted
`kind: set_route_protection` and the old editor offered snapshot undo/redo.
Neither statement exposes a current usable edit/history route. Check the active
typed operation and actual saved output for any replacement workflow.

## Check and deliver

Review Shunting/automatic-Path bindings, Route primary/terminal properties,
Itinerary references and validation. Missing Overlaps, invalid release objects,
reversed/off-Route endpoints and disconnected movements are errors. Splitting
an Edge updates Shunting chains. Deleting geometry requires review/cascade of
dependent Shuntings, Overlap Routes, Paths, Itineraries and Courses. Deleting a
Signal can preserve an independent Shunting over the retained track.

For a requested new project, use a currently supported typed/profile publisher
and retain source files; legacy `opentrack_publish_draft` is also quarantined and
cannot publish the old batch shown above. For an existing-project edit, apply the reviewed dependency closure at
that project's current paths through its supported update/native-Save workflow;
do not create another formal project just to satisfy this example. A fresh-only
publisher does not gain overwrite support. This particular data-generation
scope is one-document Shuntings, local slow-speed zones, and one-boundary Route
continuation. Other cases report explicit unsupported errors. Do not claim
native dispatch, release timing, sensor behavior or simulation acceptance from
archive checks. An isolated publication that does not replace loaded inputs needs no shutdown;
replacing current loaded files still requires the documented object/cache unload
and dirty-state procedure.
