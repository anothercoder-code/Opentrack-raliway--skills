# Engine Z/V point text and color

The typed operation is `rolling_stock_operations[].kind=edit_engine_diagrams`
with an `import_text` edit. Supply exactly one of inline `content` or scoped
`file_path`. `existing=replace` clears the selected diagram's point arrays;
`insert` retains them; `new` appends a diagram. Existing diagrams require `index`
and preserve caption, supplies, color, axes and losses. New diagrams can receive
an explicit description/supply list; omitted supplies use the native next-free
order. Source bytes are snapshotted once per edit, before applying to Engines.

Reviewed original functions establish these rules:

| Original function | Entry | Saved-data rule |
|---|---|---|
| `firstCharacterInLineIsNumber:` | `0x4cde20` | Skip spaces only; first remaining character must be an ASCII digit |
| `replaceColonWithPoint:` | `0x4cde68` | Despite its name, replaces comma with decimal point |
| `engineZVImportPressed:` | `0x4d21a4` | First physical line is the caption; tab/space tokens use integer conversion; exact `H` is the optional third token |
| `convertArrayOfImportedPoints` | `0x4cdea0` | Carry each source row's H/type to the next source row, initially type 1 |
| `insertTractiveEffortSpeedDiagram:withImportedPointArray:` | `0x4cb684` | Negative force to braking; zero/positive to traction; first speed wins in each destination; then sort |
| `addTractiveEffortSpeedDiagramWithName:withImportedPointArray:` | `0x4cb800` | New caption and first-free supply with the same point insertion semantics |
| `engineZVExportPressed:` | `0x4d1bb8` | Traction then braking; emit H according to the next point's saved type |

The accepted text subset is ASCII, at most 2 MB of source bytes per batch,
signed-int32 values and at most 1022 characters per physical line. A leading
tab or minus sign does not pass the native numeric gate. Decimal tokens truncate
to their integer prefix. Invalid force tokens convert to zero. Incomplete numeric
rows are ignored and reported. Type shifting precedes sign splitting, duplicate
removal and sorting. Empty point sets are preserved as editable incomplete data.

New diagrams use native constructor axes 250 km/h, +400/-200 kN and black color.
The saved-data operation does not execute the native view auto-scale command.
Default diagram editing recomputes Engine speed/force extents and preserves
stored power; use `recompute_engine_limits=false` to preserve Engine extents.

`opentrack_export_engine_curves` writes fresh text artifacts or mapped JSON,
full file digests/ownership and a warning manifest. JSON is a saved-field report,
not the native point-text import format. Text omits supplies, color, adhesion,
axes, visibility and loss functions. Zero-force braking points become traction
when reimported; first-point types/caption spaces can normalize; numeric captions
can also be parsed as a point. These native text limitations are reported.

Diagram `color` accepts calibrated RGB or calibrated white components in 0..1.
NSColor v0 tag 1 uses four floats; tag 3 uses white/alpha floats. Independent
original Engine/TrainCategory fixtures verify both encodings. Unknown native
spaces are reported and preserved when omitted; they are not silently rewritten.

One request supports 100,000 processed point/loss/supply rows and 10,000 expanded
diagram commands. Export supports 1,000 diagrams/100,000 points. Responses contain
compact previews; full diffs, input digests and warnings remain in artifacts.
Failures cannot write partial changes into the source project.

RailML/XML, older diagram migrations, complete native point-edit commands and
view auto-scale behavior remain separate work. Native load/simulation acceptance
is not implied by these offline data and transport tests.
