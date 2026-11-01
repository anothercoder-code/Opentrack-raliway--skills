# Multi-system Engine diagrams

Read the original saved Engine with `list_catalog(kind:"engines",
include_curves:true)`. Results include system codes, interpolation flags, signed
electrical braking, loss bands, display axes and adhesion percentages.

## Generate

Use `engines[].tractive_effort_diagrams` as an alternative to legacy
`nominal_power_kw` or `traction_points`. Each system can belong to only one
diagram; a diagram may serve several systems. Different diagrams may end at
different speeds. System code 4 is AC 25kV 50Hz; 2 is AC 15kV 16 2/3Hz.
These codes differ from scalar Engine voltage/drive menu tags.

Example diagram inside a complete Engine definition:

```json
{
  "description": "Synthetic AC25 curve",
  "power_system_codes": [4],
  "traction_points": [
    {"speed_kmh": 80, "force_kn": 320},
    {"speed_kmh": 400, "force_kn": 64, "interpolation": "hyperbolic"}
  ],
  "braking_points": [
    {"speed_kmh": 0, "force_kn": 0},
    {"speed_kmh": 400, "force_kn": -100}
  ],
  "loss_function": [
    {"from_speed_kmh": 0, "loss_factor": 0.16, "fixed_loss_kw": 45},
    {"from_speed_kmh": 200, "loss_factor": 0.18, "fixed_loss_kw": 60}
  ]
}
```

The first speed need not be zero. Interpolation belongs to the segment on the
point's left; use `linear` or `hyperbolic`. Traction is nonnegative; electrical
braking force is nonpositive. These force curves are distinct from a formation's
deceleration table.

`loss_factor:0.16` means 16% extra power loss. It is not efficiency 0.16 or a
percentage input 16. Speed bands are ordered, with the final row extending
upward; a first threshold above zero is allowed. `maximum_power_kw` optionally
sets stored power independently of the chosen curve source. Without it, explicit
curve generation derives a mathematical peak, not a calibrated train rating.

Empty point arrays and unassigned `power_system_codes:[]` are editable incomplete
states. Inspect `curve_data_covers_declared_speed` and the returned warning.
Archive validity alone does not make this data simulation-ready.

## Edit

Use `rolling_stock_operations` with `kind:"edit_engine_diagrams"`, exact Engine
`names`, and ordered `edits`:

```json
{
  "kind": "edit_engine_diagrams",
  "names": ["EMU400"],
  "edits": [
    {"action": "duplicate", "index": 0, "description": "Alternative data"},
    {"action": "update", "index": 1, "power_system_codes": [2], "loss_function": []}
  ],
  "recompute_engine_limits": true
}
```

`add` accepts a full `diagram` and optional `before_index`. `update` accepts an
`index` and supplied diagram fields. `duplicate` accepts an index and optional
description/codes/insertion index. Omitted codes select the next free native
system. `delete` removes the indexed diagram while retaining one. Indexes refer
to the list produced by preceding commands. Code swaps are checked at the end.

Omission preserves data; null is rejected. Empty loss or point lists explicitly
clear them. Default recomputation updates maximum speed/force and signed minimum
braking force, while preserving stored power. Set `recompute_engine_limits:false`
to preserve scalar limits. Read back actual values and review the full
`rolling_stock_changes_json`; editor undo restores the whole saved operation.

New/editable diagrams use v3; versions 0..2 decode in read-only views and migrate
in stock-write drafts. Remaining color spaces and full native electrical runtime
behavior still need work. Rolling-stock XML is described separately.
No native program, GUI or simulation is started.


## Curve text and color

Use `import_text` inside `edit_engine_diagrams`:

```json
{"kind":"edit_engine_diagrams","names":["EMU400"],"edits":[
  {"action":"import_text","index":0,"existing":"replace","content":"Curve A\n0 320 H\n400 80\n0 -100\n400 -60"},
  {"action":"update","index":0,"color":{"space":"calibrated_rgb","red":0.0,"green":0.2,"blue":1.0,"alpha":1.0}}
]}
```

Supply inline `content` or scoped `file_path`. `replace`/`insert` preserve existing
caption, supply, color, axes and losses; `new` appends and accepts a description
and supply list. New data uses original constructor scales; it does not run the
view auto-scale command. H applies to the next source row, before sign splitting,
first-speed duplicate removal and sorting. Input bytes are snapshotted once.

`opentrack_export_engine_curves` selects `engine_names`, optional zero-based
`diagram_indices`, and `format=opentrack_text|json`. It writes fresh files plus a
full hash/ownership/warning manifest. Text omits other saved diagram attributes;
zero-force braking points can move to traction on reimport and numeric captions
can become extra points. Review warnings before treating the exchange as lossless.
Mapped JSON is a readback report, not the native text input format.

Color supports calibrated RGB or calibrated white components in 0..1; omit it
to preserve unknown spaces. Text input is ASCII, limited to 2 MB per draft and
1022 characters per line, with signed-int32 conversion and native digit gating.
Imported empty data is editable and incomplete, not proof of runnable traction.


## Individual points and scales

Read one diagram with `opentrack_get_engine_diagram` (`engine_name`, `index`,
`curve`, `offset`, `limit`). It returns exact curve/index references and at most
200 rows, plus data-state diagnostics. Use those indices in an ordered batch:

```json
{"kind":"edit_engine_diagrams","names":["EMU400"],"edits":[
  {"action":"set_scale","index":0,"axis_maximum_speed_kmh":500,"axis_maximum_force_kn":400,"axis_minimum_force_kn":-200},
  {"action":"add_point","index":0,"speed_kmh":300,"force_kn":160,"interpolation":"hyperbolic"},
  {"action":"update_point","index":0,"curve":"traction","point_index":0,"force_kn":330},
  {"action":"auto_scale","index":0,"limits_source":"curves"}
]}
```

New points use force sign (zero is traction), per-array speed uniqueness and
sorting. Add/move outside the plot bounds are ignored and reported; check
`point_command_results` before claiming insertion. `if_speed_exists=error` makes
a duplicate an atomic error. Selected-value `update_point` writes signed-int32
values directly and keeps array membership/order, including editable duplicate
or wrong-sign states. `move_point` keeps type/order and clamps force to its
original curve sign. The segment to the left uses the point's interpolation.

Delete exact references with `delete_points.points`, or clear both arrays with
`all_points=true`. Shared native objects within a diagram are selected/deleted
together. Set scale maxima clamp to 10 and positive minima to zero. Auto-scale
uses all Engine supplies' limits, with `saved_engine` as the native default;
`curves` explicitly refreshes these limits first. Its axes snapshot that command's
prefix. Parent limit recomputation runs after the group and preserves stored kW.

Review full diffs and unknown/invalid point-state counts. These commands persist
original data; they do not reproduce mouse events or certify native simulation.
The exact native rule/precision contract is `OTAI/contracts/engine-points.md`,
available in the MCP package and through schema/evidence tools.
