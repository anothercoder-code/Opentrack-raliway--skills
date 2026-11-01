# Original rolling-stock decoder versions

Target: stock English OpenTrack 1.7, original EXE SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Function-first evidence is `artifacts/research/stock-version-functions-v019.json`.
Coder variadic addresses were restored before assigning archive indices. This
is data compatibility; native allocation, retain/release and caches are not run.

`rolling_stock_operations: [{"kind":"migrate_rolling_stock"}]` upgrades a draft's
Engine/diagram and Train/Trailer catalogs. Optional `entities` selects `engines`
or `formations`. Stock edits and XML imports prepare audited versions in their
draft. Check `serialization_migrations`; unrelated generation commands do not
upgrade stock. Read-only catalogs/curve queries decode copied old objects.
XML exports decode a copy and report `decoded_view_migrations`. None changes
source files. Current record scalar/unknown fields are preserved when omitted.
Unknown future versions and mismatched group encodings fail explicitly.

| Record and original decoder | Audited source versions | Current layout and defaults |
|---|---|---|
| OTEngine `0x4cc994` | 0..2 | v0 single diagram becomes an array; pre-v2 minimum force is 0. Stored speed/force/power and OTVehicle internal version are preserved. |
| OTDDiagram `0x472944` | 0..3 | v0 gets empty electrical braking, generic system 1, black and visible; pre-v2 minimum force -200 and empty description; pre-v3 empty efficiency wrapper. Nil old point/system arrays become empty. Visibility is a nonzero BOOL, not bit 0. |
| OTTrain `0x6c28d4` | 0..16 | Append only fields missing from that version. Before v13 renumber Engines then Trailers, starting at 1, through `resetPosInTrain` (`0x6bb9b0`). |
| OTTrailer | 0..3 | Existing audited speed/power-loss/delta-load defaults; see native operational-record contract. |

The Train decoder introduces these groups:

| Version | Groups | Missing-field defaults |
|---|---|---|
| 1 | 3,4 | Category 1 for type 0, Category 2 for type 1, otherwise Category 3; maximum acceleration 3 |
| 2 | 5 | Excl 1.5, .003, .00085 (type 2: last coefficient .0016) |
| 3 | 6 | Formula 0 |
| 4 | 7,8 | Incl 3.3, .02422, .000552; VEin 100, PLig 131 |
| 5 | 9 | Acceleration delay 0 |
| 6 | 10,11 | Corrected .01, -.1, -1.5; disabled |
| 7 | 12,13 | Braking formula 0, percentage 100; C1 .069, C2 .006 |
| 8 | 14 | Maximum drawbar force 1000 |
| 9 | 15 | Use drawbar/hold flags disabled |
| 10 | 16 | Braking delay/release speed 0 |
| 11 | 17 | Braking delay type 0 |
| 12 | 18 | Curve-resistance formula 1 |
| 13 | 19 | Curve resistance 100 percent |
| 14 | 20 | Minimum time to hold speed 0 |
| 15 | 21 | Starting rolling resistance disabled, offset/factor 0 |
| 16 | 22 | Acceleration delay at stop 0 |

Old flag decoding follows original signed comparison/unsigned subtraction,
then the current encoder's BOOL packing. Shared object identities are retained.
Nil Train arrays remain nil, as in the original decoder; library data can have
no powered references. Such definitions are readable/exportable and receive an
unpowered-definition warning. They do not establish standalone powered motion.
Generated new powered formations still require their explicit Engine bindings.

## Time-field correction after API 0.18

Original `OTTrain.encodeWithCoder:` (`0x6c2dbc`) unambiguously encodes
`minTimeToHoldSpeed_s` at group **20** and `accelerationDelayAtStop_s` at **22**.
API versions through 0.18 mapped them in reverse. Version 0.19 fixes read/write
mapping. Existing saved group values are not swapped: their intended origin
cannot be inferred safely. Re-submit explicit intended values if these fields
were configured through an earlier API. Partial edits alter only their proper
group. The independent regression anchors the indices in restored original C
arguments, rather than assuming the API's own mapping is correct.

Tests cover each constructed old-version wire branch, serialization, malformed
versions, idempotence, nil/unpowered definitions, source preservation, public
draft operations and real MCP publication. Constructed fixtures are not captured
native old-version archives. No original application loading or simulation
acceptance was performed.
