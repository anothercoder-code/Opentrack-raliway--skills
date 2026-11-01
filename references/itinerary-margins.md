# Itinerary safety margins

Generate profiles in `itineraries[].safety_margins`, with `position_m` and
`safety_margin_m` in metres. Values persist as signed float32. Include profiles
in the same generation batch as the related network and service definitions.

Edit existing profiles in ordered `network_operations`:

```json
{
  "network_operations":[
    {"kind":"edit_itinerary_margins","name":"I:BJN-JNW_1","edits":[
      {"action":"add"},
      {"action":"update","index":0,"position_m":0,"safety_margin_m":50},
      {"action":"add"},
      {"action":"update","index":1,"position_m":1000,"safety_margin_m":80}
    ]}
  ]
}
```

`add` inherits the last row or starts at `(0,0)`. With `selected_indices`, it
inserts after the last selected row and inherits it. `insert(index)` uses the
original direct model rule, requiring a nonempty array and inheriting the prior
row (row 0 at index 0). `delete(indices)` removes rows in descending order;
`clear` removes all rows. `sort` invokes the recovered native ordering.

`update` changes the chosen current row. Position edits sort immediately;
margin-only edits preserve order. Both fields affect the same selected object.
Inspect the full `network_changes_json` for the resulting index after sorting.
Later commands use the new indices.

Shared native rows/arrays retain their identities. A row update can affect other
loaded Itineraries, and import/clear affect other owners of the same array.
Inspect shared-profile changes and alias groups in the full diff. Read pages
give the first `reference_index` for repeated rows. Add/insert create a fresh
row; duplicating an Itinerary independently copies every row occurrence.

Read `opentrack_get_itinerary_margins(name, limit, offset, distances_m)` for pages
and position queries. Before the first row the margin is zero. The first exact
duplicate match wins; just after that position the last preceding duplicate can
win. The original Foundation merge can reorder equal keys, so do not assume a
stable sort or deduplicate positions. Queries preserve saved order and flag an
unsorted profile. Catalog details give a 20-row preview and full count.

`opentrack_export_itinerary_margins(names, format="native_text")` returns fresh
two-column text files and a complete loss/hash manifest. `format="json"`
preserves all saved values/order and batch-local row/array/wrapper reference
IDs. Native text rounds to two decimals using the old CRT rule; review rounding,
signed-position, reorder and repeated-row identity warnings.
`cross_itinerary_shared_references_not_represented` names other loaded owners
whose wrapper/array/row relationships text cannot represent, even if all owners
are exported or a shared container is empty. Prefer mapped JSON to retain this
reference description; do not infer that text import detaches existing shared
arrays or reconstructs sharing in independent profiles.

Reimport through `edits: [{"action":"import_text","file_path":"<returned file>"}]`,
or supply inline `content`. Import **replaces** the profile and sorts. Original
parsing accepts a digit after optional spaces, uses tabs between fields,
normalizes decimal commas, reads numeric prefixes and uses zero for invalid
fields. Negative-position and leading-tab rows are skipped. No accepted rows
clears the profile. Never assume a rounded text export is a lossless backup.

Review validation and publish a fresh project. Stage and the persistent editor
support the same changes with snapshot undo/redo. These are original saved data
operations; actual moving-block safety/control behavior is not certified.
Exact limits and function evidence are in `OTAI/contracts/itinerary-margins.md`.
