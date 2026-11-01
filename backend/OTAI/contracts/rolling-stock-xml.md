# Original rolling-stock RailML data exchange

Target: original English OpenTrack 1.7, SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
These are saved-data operations. No native application/controller, process
memory, save dialog or simulation is executed. Export metadata identifies OTAI.

## Export

`opentrack_export_rolling_stock` writes a fresh `rolling-stock.railml` and
manifest. Null selections choose all catalogs; selecting formations with a null
Engine selection chooses their Engine dependency closure. Empty lists select
none. Explicit selections cannot omit valid Engine dependencies. IDs retain
original catalog indices. Native invalid-reference fallback and formation-ID
collisions are reported, rather than silently relabelled.

The native 2.2 layout includes Engine dimensions, mass/adhesion mass, speed,
one propulsion per assigned diagram/system, endpoint-derived power in W and
rotating mass factor. The description uses the original supply labels; a diagram
containing diesel code 20/21 marks every exported propulsion as diesel.
Unassigned diagrams emit no propulsion. Trailers use formation/array indices
and export aggregate mass/length, speed, fixed auxiliary power in W and rotating
mass. Formations export original consist positions and vehicleCount=1.

Curves are sampled at every integer speed from 0 through the diagram maximum.
They are not raw saved knots. The none-adhesion sample uses the original integer
linear/hyperbolic curve rule, right-point interpolation type, array-order and
duplicate behavior, zero-speed first-point rule and int32 arithmetic. A saved
Engine speed below a diagram's extent limits its sampled table; excess requests
use the original final-cell fallback. The power attribute uses saved endpoints,
float32 products and integer truncation, not an interior maximum.

The original XML transform uses numeric character references for `"&<>`, Latin-1
160..255 and the two explicit smart quotes. ID punctuation replacement follows
the original helper. Formation caption cleanup removes LF, then trailing spaces
while retaining a first single space. ASCII/Latin-1 and those quotes are audited
for export. XML-forbidden controls and other unaudited cString conversions fail
explicitly. The declared ISO-8859-1 document is emitted as ASCII plus references.

## Import in one generation batch

Use `rolling_stock_imports` in `opentrack_generate_operations`, or an ordered
`import_rolling_stock_xml` change. Imports run after Engine/Category definitions
and before explicit formations, infrastructure and Courses, allowing later
services to bind newly imported formations in the same batch.

Exactly one inline `content` or scoped `file_path` supplies bytes. File input is
captured twice for a stable snapshot, hashed and consumed once. Later XML edits
do not change the draft. XML source bytes share a 20 MB batch budget; processed
source points share 100000, stock definitions/references 10000 and each Engine
supports 64 propulsions. DTD/custom entities/external resources are rejected;
there is no schema/network fetch. Standard XML predefined/numeric references
are decoded normally. Native element names are unprefixed, with the default
namespace accepted; generic prefixed-name/XSD conformance is not claimed.

`on_conflict` explicitly chooses error/keep/replace instead of native dialogs.
`clear_catalogs` explicitly clears selected Engine/formation catalogs on each
rollingstock block. Category/Course references are not silently removed; static
validation can reject publication of a draft with dangling bindings.

Imported vehicle attributes set integer dimensions/mass/speed; nonintegral
numeric values truncate. The propulsion power attribute is ignored by the
original importer. Power type becomes generic electric 1 or diesel 20;
descriptions and rotating mass factor are retained. Curves use float32 XML
intermediate points, then truncate speed and force to integer km/h/kN. The
conversion gate checks xValueName/yValueName, not xValueUnit/yValueUnit. Only
adjacent equal converted speeds are skipped, using an initial previous speed
of -1. The importer neither sorts nor sign-splits these traction points.

Vehicle-ID dictionaries and per-formation reference state follow the original:
undefined refs are skipped with warnings; Engine vehicleCount does not expand
references. Trailer vehicleCount>=2 mutates the dictionary source's mass,
length and power before copying it, so repeated refs can compound scaling.
Counts below 2 set number_of_items=1 without undoing prior aggregate scaling.
Omitted reference attributes retain prior state within the formation. Explicit
positions, including duplicates, are preserved and reported; automatic positions
use record count+1, not the maximum occupied position.

Fresh objects use reviewed init/reset defaults, not unrelated sample values:
Engine flags=7, axles/driven axles/motors=4, force/power extrema reset to zero;
Train braking=-0.6 m/s2, acceleration=3, original resistance constants, no
hold-speed flag and curve resistance percentage=100. Caption persistence is
currently audited for ASCII. Engine 0..2, diagram 0..3 and Train 0..16 catalogs migrate to current layouts
in the draft before import; Trailer 0..2 uses audited v3 defaults. Unsupported
future layouts fail explicitly. See [decoder versions](stock-versions.md).

Native import leaves reset Engine force/power maxima and Category `Untitled`.
`recompute_limits:true` explicitly runs the separately reviewed diagram-limit
data command; stored power remains independent. `category` explicitly overrides
the saved Category binding. Otherwise the native default is retained, and an
absent Category causes a visible binding validation error. These options are
reported additions, not hidden changes to import behavior.

Full before/after records, XML input hashes, counts, ignored fields and warnings
are saved in `rolling-stock-changes.json`; normal responses carry bounded
previews. Publication rebases native references and checks bindings separately.

## Function evidence and verification boundary

Primary functions: exporter 0x5409b0; XML start/attributes/end 0x6d4894,
0x6d4c4c, 0x6d52b8; curve evaluator 0x4cbeb8; sample table 0x472220/0x472718;
power 0x47171c; diagram append 0x4cba80; object init/reset and native coder methods.
The evidence manifest records exact C hashes and specific instruction windows.

Some shared dispatch stack branches remain misleading in generated C. Vehicle
name/length/speed/mass mapping was checked at 0x6d4d22..0x6d4e88 against original
selector pointers and setters. At 0x6d4f6e the same argument word can hold an
object, int or float, so its common ABI stays explicitly untyped. The original
FISTP sites set x87 RC=truncate at 0x4717f9..0x47180e and 0x6d5aa2..0x6d5ad3;
Ghidra's ROUND spelling alone is not evidence of nearest rounding.

The handwritten XML fixture follows the reviewed original field layout; it is
not a captured native export. Tests cover independent numeric expectations,
saved round trips, collisions, snapshots, invalid inputs, same-batch Course
bindings and real MCP import/export/publication. No original application
loading, XSD validation or simulation acceptance is claimed. Legacy 1.00/1.03,
other RailML domains, earlier layouts, unaudited encodings and full original
business parity remain unfinished.

## Original 1.00 and 1.03 exports

Select `format: railml_1_00` or `railml_1_03` with the same export tool. The
original default legacy wrapper selects 1.03. The generic original import menu
is a ToDo stub; these formats are explicitly rejected by the 2.2 importer.

Legacy IDs use escaped Engine names, Trailer name + original Train catalog
index + consist position, and cleaned Train captions. The dataset ID has no
2.2 rollingstock- prefix. Missing Engine references remain named references;
there is no 2.2 first-Engine fallback. Duplicate IDs are reported and retained.

Version 1.00 writes vehicle attributes and trainOrder/vehicleType. Version
1.03 adds per-diagram/system propulsion with empty power/engine/transmission,
auxSupply with empty nomPower, and mechPowerFactor/power loss tables. Both
versions omit tractive-effort curves. Trailer auxPowerConsumption is in **kW**,
unlike 2.2 W. Version 1.03 adds the first Trailer's delta-load loss factor.

Empty loss data exports zero rows at speed 0 and diagram maximum. Each saved
loss band writes two equal-value rows; after the first band its start is a
float32 speed plus float32-rounded .001, and its end is the next threshold or
diagram maximum. Floats use three decimal places. Auxiliary rows share a
100000-row bound. Metadata truthfully identifies OTAI, so byte-identical native
output is not claimed. The header and legacy schema-location spelling follow
the original function, without claiming XSD validation.

Engine 0..2, diagram 0..3 and Train 0..16 decode to a copied current view before
export. Source files and old saved values are preserved. See
[decoder versions](stock-versions.md). Evidence: original exporter 0x53fde0,
wrapper 0x53fdc8 and the v019 reviewed function manifest.
