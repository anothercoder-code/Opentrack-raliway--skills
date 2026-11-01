> Historical wave12/v11 baseline record. Counts, A–B–A–B–A schedules,
> fixed terminal geometry and "not launched" statements describe that example
> and API profile, not the current Skill's overall design or runtime capability.
> See [contract scope](README.md) and current edition/acceptance references.

# OpenTrack current archive MCP + Skill — wave12

Extends the existing `opentrack_generate_current_operating_archives` endpoint with
an **explicit `station_profile="terminal_area"`**. Default `point_only` keeps the
wave11 geographic StationVertex rules and refuses terminal areas, stop plans,
chains and a Connection template. Terminal mode refuses the old point-only
stations/plan/schedule fields; it requires `terminal_profile` and a tenth SHA-bound
source, `connection_template`. Neither profile silently selects the other.

The new from-zero example builds **74 double vertices, 92 Edges, 12 signals,
12 Routes, 12 Paths, 6 Itineraries** and six dedicated 500m single-Edge terminal
areas. Each terminal binds the same StationModel to both halves of ordinary S
(type1) and reference A (type2); ordinary S contributes no timetable visit. B is
a type2 pass reference. The old point-only resolver is not weakened to accept
area members. The actual directional exit signal is checked against the proven
native type1/main4 profile, not a guessed GUI icon or enum.

It creates six single-Engine/no-trailer Train **definitions**, 144 Courses and
720 planned rows: **576 pass rows (flags2), 144 final-visit stops (flags3)**.
Initial and intermediate A visits remain pass. Each Course follows A–B–A–B–A;
no global station-name deduplication or pair double-counting is used. Six 24-Course
same-Train/same-Itinerary chains contain **138 reciprocal native Connection pairs
(276 saved records), six roots, six tails and 132 internal Courses**. Records are
fresh-only: reapplication to existing Connections is refused, not duplicated.

The actual consist is 209m; its complete single Engine must fit the 500m area.
500m/501m native-integer boundaries were tested. The actual Category minimum is
**420 seconds**, never 420 minutes or a maximum. Planned layovers are at least
1292s in this example. Native minimum/maximum-sentinel encoding, exact final-index4
to first-index0 pairing, same actual directional terminal End, ordered chains,
absence of forks/merges/day-wrap, per-leg Edge/Engine speed lower bounds and the
0..86400 planned/run window are checked. Expected counts are explicit and checked
against decoded output, not accepted from input metadata alone.

## This is static configuration, not a simulated operating result

The original app is not launched. No Wine preparation or user-local Codex is used.
Actual times stay unset. Saved stop flags and Connections do **not** establish
physical halts, braking safety, body/occupancy continuity, reservation transfer,
a six-unit fleet, conflict-free circulation or a completed one-day simulation.
The six tail Courses have no successors and are intentionally configured to park;
this plan alone neither proves nor disproves deadlock. The 100m approach/departure
segments are separation choices, not braking-distance evidence. General multi-Edge
platforms, reverse stopping, multi-unit/trailer consists and arbitrary line naming
are outside this reviewed terminal profile. Native type1 associations can be valid
station-area members; they were never universally corrupt archives.

The reviewed terminal identities are H1/H2/H3/V1/V2/V3 with corresponding TRAIN_01
through TRAIN_06, I:terminal:* and S*_IN. Each selected chain has 2..24 Courses.
The production example selects all six and all 24; a two-Course fixture is only a
bounded regression case. Other arbitrary networks remain in the explicit point
profile unless a separate terminal contract is reviewed.

All ten sources are SHA-bound and reread around commit. Preview is default.
Publication is one fresh-directory atomic no-replace operation containing the
network, six catalogs, optional minimal `.run`, manifest and empty output folder.
A no-follow early existing-target check only rejects work; the audited publisher
still owns the final commit and race checks. Committed postcheck errors preserve
foreign data and identify the committed bundle. Original header/registration bytes
remain unchanged; type templates do not grant a licence or calibrate rolling stock.

The optional `.run` uses an explicit target execution root and exactly 0..86400
for terminal mode. `C:/OpenTrackProjects/TeachingTerminalGrid` is a declared teaching
destination, not an observed host. Generic run path/hash/name/window verification
is separate from the terminal semantic verifier. `complete_runtime_configuration`
and `execution_root_verified` remain false; original runtime globals are unverified.

Install `OTAI/requirements-server-tested.txt`; from extracted MCP root:
```
python -B OTAI/server.py --root DATA_ROOT --profile generation stdio
python -B verification/wave12/build_terminal_operating.py /tmp/fresh-terminal-grid
python -B verification/wave12/run_current.py
```
The example root must not exist. Skill ZIP pairs with this MCP ZIP; set OTAI_ROOT
to the extracted MCP root and OTAI_DATA_ROOT to authorized data. The existing
Skill default-generation allowlist is retained and tested without OTAI_PROFILE
or PYTHONPATH overrides. No original executable/DLL is included.

Current example: `OTAI/artifacts/wave12/generated-terminal-operating`.
Contract: `OTAI/contracts/wave12-terminal-area-generation.md`.
Historical wave10 point semantics are superseded by wave11; wave11 remains frozen.
Tool/constructor counts are not a claim of complete original-function equivalence.

Large terminal requests should be written to a UTF-8 JSON request file, then
`python -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_generate_current_operating_archives --args-file /absolute/path/request.json`.
Do not place the complete 144-Course JSON in one `--json` shell argument: operating
systems impose per-argument size limits. The supported file input uses the same
JSON input handling and strict profile validation; it is not an alternate semantic path.

Function coverage is64 bounded native writes /24 getters /15 composites;67
registered tools include3 blocked legacy entrypoints. The two additional write
classifications are existing Station/Incident name adapters only for non-nil
string saved-value effects, supported by selector/field/coder evidence. This
does not cover nil behavior, recovered Foundation IMPs, memory/retain lifetime
equivalence, or full referential rename. Terminal profile expands the existing
operating composite and is not counted again as a new constructor/tool.

### Engine position correction (candidate 2)
OTTrainEngine stores `posInTrain`, not quantity. This terminal profile accepts exactly one Engine reference at position 1 and no trailers. Three actual units require three separate references (positions 1/2/3); this profile rejects them. A single reference at position 3 does not mean three units or 627m. The historical quantity-based negative-test explanation was withdrawn; see `ENGINE-POSITION-ERRATUM.md` in wave12-audit. No native execution was performed.
