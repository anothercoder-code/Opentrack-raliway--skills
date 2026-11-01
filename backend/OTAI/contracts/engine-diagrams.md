# Original Engine diagrams and loss-function data

These are saved-data operations for stock English OpenTrack 1.7. Native menus,
controllers, simulation caches and running trains are not executed.

## Sources and independent anchors

The original manual sections 5.2.2-5.2.6 describe diagram duplication/deletion,
one diagram per supply system, several systems per diagram, interpolation to the
left of a point and speed-band power losses. The unmodified original Engine
fixture in `tests/fixtures/stock-operational/OTEngine.archive` contains points
(80,275,1), (200,110,2), (230,80,1), supply code 1, and two loss rows:
(0,0.16,45) and (70,0.18,45), subject to native float32 representation.

`OTAI/artifacts/research/engine-diagrams-layouts.txt` records bounded original
coding/selection instructions. OTDDiagram v3 has:

| Group | Native saved data |
|---|---|
| 0 | seven ints: speed scale, maximum force scale, good/normal/bad adhesion percentages, displayed adhesion code, show flags |
| 1 | acceleration/traction OTDPoint array |
| 2 | electrical braking OTDPoint array |
| 3 | NSNumber supply identifiers |
| 4 | NSColor, preserved by current editing |
| 5 | signed minimum force scale |
| 6 | NSString description/name |
| 7 | OTEfficiencyArray, inherited OTMutableArray wrapper |

OTDPoint stores integer speed in km/h, signed force in kN and point type.
Native interpolation tests type 1 for a straight segment; canonical type 2 is
hyperbolic. The right endpoint controls the segment on its left. The first point
need not be at zero: native lookup extends its value below that speed.
Electrical braking forces are nonpositive. Data generation accepts empty or
single-point plots as explicit unfinished data, matching editable native states.
The existing legacy top-level traction input retains its zero-start/full-range
generation contract.

The native minimum Engine force is obtained from the electrical braking array
(OTDDiagram.getEngineForceMin_kN at 0x4718ec); it can be negative. It is not a
minimum positive traction requirement. Diagram maximum-force scales are kN,
despite legacy native identifiers containing the word Power.

## Power systems

New `power_system_codes` are explicit positive signed-int32 codes; an empty list
means no assigned system. A positive code can occur in only one diagram of an
Engine. Scalar Engine voltage/drive menu codes are separate fields.

The original RailML string mapper verifies codes 2=AC 15kV 16 2/3Hz,
3=AC 10kV 50Hz, 4=AC 25kV 50Hz, 5=AC 50kV 50Hz, 6=DC 600V,
7=DC 750V, 8=DC 1200V, 9=DC 1500V, 10=DC 2400V, 11=DC 3000V,
12=DC 6000V, 13=AC 11kV 16 2/3Hz, 14=DC 1000V.
Unknown codes remain numeric, with a null label; a label is not invented.

OTEngine.diagramForPowerSupplyType: (0x4cc6f0) checks the exact cached code,
then code 1 for a nonzero requested supply, then 20 and 21. These are native
selection observations, not a claim that the API initializes the native cache.
The native first-available order (0x4cbb68) is 1,20,21,2..12,201,202,101..120.
Duplication with omitted codes uses that order. If exhausted, explicitly supply
unused codes or an empty list; the API does not silently assign a negative tag.

## Loss function and stored power

OTEfficiency v0 is one `iff` group: from-speed km/h, fractional loss factor,
fixed kW loss. The sanitized blueprint extension derives this one class from the
independent original Engine fixture; the previous 54 shapes are retained and a
recoverable pre-extension resource copy is saved. New zero defaults are (0,0,0).

The loss factor is an extra loss fraction, not efficiency and not a percentage
number. Mechanical power 6000 kW with factor 0.16 and fixed loss 45 kW requires
6000*(1+0.16)+45 = 7005 kW at the locomotive; trailer loss is separate.
The native lookup selects the last threshold <= speed, uses the first row below
the first threshold and extends the final row upward. Empty data represents no
defined loss rows. Creation/editing preserves those thresholds without inserting
an assumed zero boundary.

`maximum_power_kw` can explicitly set stored power metadata. With explicit
curve generation and no override, the API derives the mathematical maximum v*F:
linear segments include interior quadratic extrema; a hyperbolic segment has
linear v*F and uses endpoints. This does not simulate native integer-grid force,
adhesion or energy behavior. `nominal_power_kw` remains the separately selected
uncalibrated proxy-curve input.

## Generate, edit and persist

Engine generation chooses exactly one of legacy `traction_points`,
`nominal_power_kw` or `tractive_effort_diagrams`. Each explicit diagram specifies
systems, traction/braking points, optional loss rows and display attributes.
Different supply diagrams may have different speed extents. The generation
result reports whether assigned curve data spans the declared Engine speed;
unfinished/unassigned data does not establish simulation readiness.

`rolling_stock_operations: [{kind:"edit_engine_diagrams", names:[...], edits:[...]}]`
supports ordered `update`, `add`, `duplicate` and `delete` actions. Indexes refer
to the list after preceding actions. Partial updates preserve omitted fields and
reject explicit null. The assignment check occurs after the ordered group, so
two diagrams can swap codes atomically. Duplication copies all saved data with
independent point/loss objects, then chooses the explicit or next free supply.
Deletion retains at least one diagram, matching the original editor guard.

Default `recompute_engine_limits:true` follows native setMaxPowerAndSpeed:
maximum speed/traction force from traction points, minimum force from electrical
braking points. It preserves stored power metadata. Disable it explicitly to
preserve those scalar limits. Whole-list replacement through `update_engines`
preserves other Engine attributes and can derive/override stored power.

Editing uses diagram v3; audited versions 0..2 migrate first. Older readback supplies an empty loss
function. Other layouts are rejected instead of silently migrated. Older Engine
layouts lacking the force-minimum slot cannot request limit recomputation.
Curve and loss object versions, encodings and counts survive native round trips.
The persistent editor can undo the whole operation, including limits.

Requests share 100000 processed point/loss/system rows and 10000 expanded diagram
commands per draft, in addition to existing stock/batch limits. Full differences
remain in the draft manifest and rolling-stock change artifact; nested previews
remain bounded. Original project files are preserved until a separately enabled
apply operation.

Curve text, supported rolling-stock RailML and calibrated RGB/white colors
are covered by their separate contracts, as are old diagram migrations.
Remaining color spaces and other original editing commands need work. These implemented saved
data operations do not establish all original-function parity or native runtime
acceptance.
