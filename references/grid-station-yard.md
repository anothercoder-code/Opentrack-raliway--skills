# Native nine-station turning-yard profile

**案例与合同边界：**本文涉及的站数、股道数、网格或走廊是现成辅助入口和验收案例的范围，不是所有复杂设计的固定规定。其他设计先按[需求组织设计](complex-design-workflow.md)，再选择符合实际合同的实现路径。

**Prerequisite:** first complete [full original-software authorization](software-authorization.md). User task permission or a passing original save guard is not confirmation of a valid full software licence. No native-data work or GUI-guided workaround before confirmation.

Use `scripts/grid_yard.py` when the requested design matches this **bounded**
3-by-3 network. `scripts/grid_generation.py` is a different planning/interface
tool; its line graph is not this native turning-yard generator.

The profile creates nine documents `J11` through `J33`, six common catalogs and
`grid.run` (**16 native inputs**). Each station has one common horizontal bay
with eight tracks/four island drawings, 24 binary turnouts and 32 owner-aligned
directional signals. Twelve adjacent station pairs have double-track links;
there are 24 reciprocal directional connector pairs. Each station has twelve
local core movements, including eight turns. Inter-line junctions are outside
the platforms, 1.2 km after the platform end; a common native core resource
provides conservative mutual exclusion. Other non-connecting approach crossings
are explicitly treated as grade-separated. Diagram pixels do not set Edge metres.

The fixed plan contains 24 through services, eight turns via J22 and one H2
follower scheduled 15 seconds behind H2E1: 33 Courses, 32 Itineraries and 99
timetable rows. Each journey covers three stations/12 km; planned legs are seven
minutes, the first two events pass, and the final event stops. The inherited
209 m proxy vehicle is uncalibrated; obtain the user's acceptance of that
inheritance rather than silently claiming a real calibrated vehicle model.

## Inputs and commands

Use Python 3.13.x and the paired backend. Supply the six **external native
donors** described in [generation inputs](generation-inputs.md). The profile is
bound to the verified donor SHA-256 identities in
`assets/grid-yard-profile/profile-provenance.json`. Paths may change; identity
does not. Do not replace hashes to make arbitrary donors pass. A missing donor
requires locating or preparing the actual native source, not a placeholder.
No donor archives or original OpenTrack executable are bundled.

Copy `assets/grid-yard-profile/request.example.json` to a working request and
replace the six paths with real traversal-free paths relative to the authorized
data root. Set `execution_root` to the actual desired Windows path using English
printable ASCII and forward slashes. It must lie inside `--root`.

```powershell
python scripts/grid_yard.py preview --root D:/RailWork --request D:/RailWork/request.json
python scripts/grid_yard.py stage --root D:/RailWork --request D:/RailWork/request.json --target OTAI/workspaces/grid-candidate --receipt OTAI/workspaces/grid-candidate.json
python scripts/grid_yard.py publish --root D:/RailWork --request D:/RailWork/request.json --target OTProjects/MyGrid --receipt OTAI/workspaces/grid-publication-candidate.json
```

Preview writes no project files; an explicitly requested fresh `--receipt` writes
only its JSON. Stage is restricted to `OTAI/workspaces`; its native bindings
still target the requested execution root, so do not run it from the staging
directory. Publish requires the fresh target to equal `execution_root`. Both
use the existing Windows fixed-local-NTFS no-replace publisher and fresh-byte
validation. A post-commit exception does not imply rollback; inspect any
published result before retrying.

For an existing project, edit that same project instead. This fresh-only
generator is not an overwrite API or an instruction to make another variant.
Prepare the changed closure, unload dirty documents/Inspector/catalog caches,
retain a before-state and apply only reviewed changes at the existing paths.
Do not repeatedly ask the user to import correctly bound catalogs.

## Implementation and evidence

The bundled profile reuses the successful case's native topology, Route/Path/
Itinerary and operating constructors. It applies an explicit final graphic
layout table, English captions and the four reviewed approach extensions in
memory before publishing once. The table contains numeric graphic fields and
caption text, not a native donor archive. The validator reconstructs all
documents and references from the resulting bytes and checks counts, reciprocal
connections, physical distances, stopping areas, shared resources, signal
alignment and actual run bindings. No historical output folders are moved.

The source case completed a stock-native run of all 33 journeys/396 km with
33 terminal stops, 99 station events, 66 core reservations/releases and 280
disjoint core lease-pair checks. It retained **117 WARNING** (34 signal stops,
52 Route braking, 17 late departures, one late passing and 13 late arrivals),
with zero ERROR/FATAL. Its whole-network collector has 33 course IDs and nine
stations. These are finite-case results, not a continuous collision certificate,
capacity optimization or a GUI Save/reload/lamp test of every new project.

The portable adapter passed a separate complete offline generation/validation
using the six actual bound donors. It did **not** launch OpenTrack during this
release. For any newly published target, require its own native load, crossing,
journey completion and fresh-output checks. Use
[native running diagrams](native-running-diagram.md) for actual curve capture
and original EPS/TIFF export; external schematic previews are a separate output.
