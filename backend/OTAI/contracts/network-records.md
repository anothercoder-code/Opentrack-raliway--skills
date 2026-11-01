# Original security arrays and movement definitions

Target: original English OpenTrack 1.7, executable SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
This contract comes from the original native coder methods and stock archives,
not the enhancement DLL. Static disassembly windows do not execute the program.

`OTRoute v0` inherits `OTSecurityArray`, `OTOrgArray v2` and `OTMutableArray`.
Archive group indices below are unrelated to runtime byte offsets.

| Group | Contents |
|---|---|
| 0 | Local directional End array |
| 1 | Name |
| 2 | Array ID, start End ID |
| 3 | Description |
| 4 | Signal indication list |
| 5 | Release-point metres, announce metres, release seconds, reserve seconds, first remote index, dirty flag (`iiiiii`) |
| 6 | Occupied-entry flags, speed km/h, wait seconds (`iff`) |
| 7 | Overlap name |
| 8 | Approach-zone metres, speed km/h (`ff`) |
| 9 | Overlap start End ID |
| 10, parent v6 only | Reservation-point metres, use reservation point, use release point (`iii`) |
| 10 in v5 / 11 in v6 | Route flags (`i`) |
| 11 in v5 / 12 in v6 | Release-group End array, slow-zone start End, slow-zone end End (`@@@`) |

Occupied flags: allow entry 1, use speed 2, use wait time 4, discrete moving
block 8. Route flags: reservation with previous 1, slow speed for head only 2.
The generator writes scalar controls and clears inherited overlap references
unless explicitly bound. Shunting/Overlap wrappers, release-boundary edits and
local slow-speed zones follow [protection.md](protection.md). Descriptions in Paths/Itineraries are inherited
group 3. Library `OTDestInfo` points to the document containing `OTDest`.

Original `OTSecurityArray.encodeWithCoder:` at `0x5c2c3c` establishes groups 4–10;
its `initWithCoder:` at `0x5c28bc` branches on the saved parent version. For v5,
the code at `0x5c2c12` supplies 5000 m, disables the reservation-point control
and enables the release-point control exactly when the saved release distance
is positive. Migration inserts this group in every loaded v5 descendant before
setting any shared class version to 6. Existing Route/Shunting tails remain
the same objects in the same order. Only v5/v6 are accepted for this operation.

`OTRoute.encodeWithCoder:` at `0x5a7538` establishes Route flag bits and the
three object references. The corresponding flag getters/setters are recorded
in `artifacts/research/network-layouts.txt`. Full-model persistence, independent
topology checks and scalar round trips are tested; native setter side effects,
simulation initialization and dispatch execution are not invoked.

Frozen source samples:

- `topoOst.opentrack`: SHA-256 `55f03e67a8b9c028bae2662b0a69f595de80e62b98f96e7fb97aab4de93b408a`.
- `topoWest.opentrack`: SHA-256 `bf8705256f94f84c44768b8fe8f673abe41f6e57cb409ed4dc357989941d6a46`.

Both contain original parent v5 Routes and Shuntings. The frozen manifest is
`tests/fixtures/stock-network/fixture-manifest.json`; original inputs are never
rewritten by tests or generation. No numeric local-itinerary priority field is
invented from a Route name or Course acceleration field.
