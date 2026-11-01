# Original rolling-stock RailML 2.2

Use `opentrack_export_rolling_stock` for fresh XML artifacts. Null selections
mean all; `formation_names` plus null `engine_names` selects the required Engine
closure. Empty lists explicitly select none. Read the returned hashes, sample
count and full manifest warnings. Curves are sampled using original integer
rules; this format does not preserve all native stock fields.

Import through one generation batch:

```json
{
  "project":"OTProjects/Example",
  "rolling_stock_imports":[{
    "file_path":"OTProjects/Example/input.railml",
    "on_conflict":"error",
    "category":"Existing Category",
    "recompute_limits":true
  }]
}
```

Inspect actual Category names first, or define a fresh Category in the same
batch. `category` is an explicit override; omitting it keeps native `Untitled`,
which may lack a binding. `recompute_limits` is an explicit post-import command;
native XML import by itself leaves reset force/power maxima. Stored power is
not inferred from the XML power attribute, which the original importer ignores.

Imports follow Engine/Category definitions and precede formations and Courses.
Add service patterns and their Itineraries/timetables to the same batch when
needed. Review `rolling-stock-changes.json`, binding validation and CSV, then
publish the draft under a fresh project name. No GUI or simulation is required.

Use `on_conflict: keep` or `replace` only as intended. `clear_catalogs` removes
selected saved definitions in the draft on each rollingstock block; it does
not repair existing Course dependencies. Prefer a blank native project for a
replacement stock database.

Important native behavior:

- XML curves truncate to integer km/h/kN. Unit conversion checks *Name* fields,
  and only adjacent duplicate converted speeds are skipped.
- Engine vehicleCount is not expanded. Trailer counts aggregate mass/length;
  repeated refs to the same Trailer ID can compound that aggregation.
- Missing refs are skipped, and omitted reference attributes retain state.
  Read warnings instead of silently reindexing or multiplying records.
- Export omits Category/braking/resistance, display/loss data and other fields;
  a text/XML round trip is not a complete native archive backup.

Current Engine v2/diagram v3/Train v16 records and ASCII imported captions are
audited. Earlier audited layouts decode through the stock-version contract. Generic
namespace-prefix/XSD support and other RailML domains remain separate gaps. Read `review_notes` with function
pseudocode; shared stack dispatch can still mislead generated C.

For legacy exports choose `format: "railml_1_00"` or `"railml_1_03"`. Both omit
tractive-effort curves; 1.03 exports auxiliary loss tables. Trailer auxiliary
power is kW, and IDs use original names/catalog positions. Review omission and
duplicate/missing-reference warnings. The original generic legacy importer is a
ToDo stub; the 2.2 importer rejects known legacy formats.
