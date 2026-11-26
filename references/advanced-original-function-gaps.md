# Advanced AI toolbox coverage and remaining gaps

## Purpose and acceptance model

OpenTrack remains the simulation solver. This Skill is the AI-facing toolbox
and orchestration contract. Its current acceptance model is:

1. **AI toolbox coverage** asks whether each required task family has real
   registered tools, semantic capabilities and prerequisites.
2. **AI orchestration reachability** asks whether the agent can select and
   compose those tools in dependency order, stop on failure, publish only
   reviewed boundaries and preserve evidence levels.

The historical 176-item inventory and 89 bounded archive-function records are
source evidence for finding omissions. They are not the current release
denominator and do not require one dedicated solver per original method.

## Current profile and capability snapshot

| Item | Current count |
|---|---:|
| `ai` profile entrypoints | 21 |
| `generation` profile tools | 219 |
| `all` profile tools | 249 |
| semantic capabilities | 11 |
| reviewed publication writers | 15 |
| blocked legacy geometry/editor tools | 8 |
| historical requirement inventory | 176 |
| bounded archive-function records | 89 (65 write, 24 read) |
| capability implementation tools | 28 |
| direct AI capability tools | 13 |
| bridge-reachable reviewed writers | 15 |
| low-level writers hidden from `ai` | 15 |

The `ai` profile exposes planning, inspection, reality-station and bound-run
validation, operation/route preparation, outcome aggregation and
`opentrack_publish_railway_plan`. Detail-level writers stay hidden. The bridge
executes one action from a hash-bound compiled plan with one writer named by
that action. A multi-step task therefore uses repeated bridge calls, not a
hidden solver or continuation token. The live machine-readable snapshot is
[ai-toolbox-status.json](coverage/ai-toolbox-status.json).

## Task-family coverage

| Task family | Status | Capabilities and registered tools | Boundary |
|---|---|---|---|
| Project/archive inspection | `supported` | `railway.inspect_project`: `opentrack_inspect_project`, `opentrack_validate_project`, `opentrack_get_worksheet`, `opentrack_inspect_topology` | Saved-data and static evidence only |
| Plan information | `supported` | `railway.plan_information_only`: `opentrack_prepare_operations`, `opentrack_compile_route_bundle` | Caller-supplied identities remain assertions |
| Reality-station validation | `supported` | `railway.reality_station_plan`: `opentrack_validate_reality_station_plan`, `opentrack_inspect_railway` | Valid planning does not set `ready_for_native_write` |
| Single through platform | `composed` | Reference validator, corridor builder, operating archives and station-run candidate | One bounded face and direction, with native checks `not_run` |
| Multi-track/isolated island example | `composed` | RailML rebuild, facilities apply and Route/Path/Itinerary composition | Reviewed RailML domains only, no general station compiler |
| Explicit network archives | `composed` | `opentrack_generate_current_network_archives` | Exact Ends, directed links and no inferred crossing |
| Route/Path/Itinerary and protection | `composed` | Current route, path, itinerary and protection tools | Static resources do not prove deadlock freedom |
| Train/Course/timetable/connection | `composed` | Operating archives, Course, timetable and connection tools | Physical circulation and full live controllers remain partial |
| Station-run candidate preparation | `composed` | `opentrack_prepare_station_run_candidate` | Candidate creation is offline and does not open OpenTrack |
| Native evidence analysis | `requires_native_app` | Bound run and verification readers | Only supplied original-run outputs count as native simulation |
| End-to-end station replication and normal train run | `requires_native_app` | Inspection, topology, facilities, Route, timetable and candidate tools plus original OpenTrack | Actual load, Save, reload, stop, departure and arrival remain `not_run` |
| General real-station compiler | `partial` | Validator plus bounded network and RailML writers | No universal source-to-native geometry compiler |
| Compound throat geometry | `unreachable` | None proven | Fails with `UNSUPPORTED_COMPOUND_TURNOUT` |

## Native write scope

The current AI toolbox can publish these bounded native domains through the
15 reviewed writers:

- Bounded network archives with explicit Vertex, Edge, signal, Route, Path and
  Itinerary identities.
- Bounded RailML multi-track station and facility rebuilds.
- Route, Path, Itinerary and route-protection records for supported saved-data
  domains.
- Operating archives, Course, timetable and connection records.
- Fresh station-run candidate projects and launch inputs from a reviewed
  movement bundle.

The following are not generally native-writable through one arbitrary request:

- A universal source-to-native real-station compiler.
- Arbitrary compound turnout, slip, diamond-crossing and ladder-throat geometry.
- General island width, height, area and capacity synthesis.
- Complete signal-family, aspect and lamp authoring.
- Physical fleet circulation, coupling and split/join behavior.
- Dynamic deadlock and complete interlocking proof.
- Actual original-application Save, reload, stop, departure and downstream
  arrival evidence.

An unsupported request must return a structured limitation before a writer
executes. Current validator codes include `UNSUPPORTED_COMPOUND_TURNOUT` and
`UNSUPPORTED_NONCONTIGUOUS_PLATFORM`. Adjacent drawing lines and invented
connectors are not substitutes for missing source evidence.

## Reachable composition paths

### Single through-platform station

1. Inspect the project and bind source facts.
2. Validate the one-face, one-direction station request.
3. Publish the bounded corridor to a fresh target.
4. Add or inspect operating data and prepare a fresh station-run candidate.
5. Read back archive members as a separate process.

The archived [Reading P9 request](../assets/reference-platform/reading-p9.request.example.json)
is an executable-shaped input after replacing its real hashed resources. Its
historical run does not establish a current GUI Save or current project run.

### Multi-track island station

1. Use a sourced semantic plan with two explicit faces, directions, exact
   Edge-End spans, stop posts, exit signals and directed throat resources.
2. Validate it with `opentrack_validate_reality_station_plan`.
3. Compose reviewed RailML or network writers to create the bounded geometry.
4. Apply facilities, then Routes, Paths and Itineraries.
5. Add operating data and prepare the run candidate.

The [semantic example](../assets/reference-platform/reality-station.semantic.example.json)
passes offline planning. The
[publication composition example](../assets/reference-platform/reality-station.publication-plan.example.json)
is explicitly `documentation_only_symbolic` and cannot be passed directly to
the bridge. The
[multi-track template](../assets/reference-platform/reality-station.multi-track.request.template.json)
is documentation and contract material, not a final native plan.

### Unsupported compound geometry

The [unsupported example](../assets/reference-platform/reality-station.unsupported.example.json)
must return a structured limitation before any writer executes. This is the
preferred result over inventing a connector or selecting an unrelated fixed
template.

## Template gap inventory

The reusable template set is under
[`assets/reference-platform/templates/`](../assets/reference-platform/templates/).
Each file is a shape to copy and resolve from actual evidence.

| Needed input | Supplied template |
|---|---|
| Source and provenance normalization | [source-register.template.json](../assets/reference-platform/templates/source-register.template.json) |
| General multi-track directed topology and supported simple turnout links | [topology.template.json](../assets/reference-platform/templates/topology.template.json) |
| Native document, track, Edge, End, signal and stop-post mapping | [native-id-map.template.json](../assets/reference-platform/templates/native-id-map.template.json) |
| Platform dimensions, faces, usable lengths and contiguous Edge spans | [platform-dimensions.template.json](../assets/reference-platform/templates/platform-dimensions.template.json) |
| Throat resources, Routes, Paths and Itineraries | [throat-routes.template.json](../assets/reference-platform/templates/throat-routes.template.json) |
| Formation, planned station call, dwell, service and run window | [rolling-stock-service.template.json](../assets/reference-platform/templates/rolling-stock-service.template.json) |
| One bound publication and member-hash receipt | [publication-receipt.template.json](../assets/reference-platform/templates/publication-receipt.template.json) |
| Final native Save, reload, Inspector, stop and arrival evidence | [native-acceptance.template.json](../assets/reference-platform/templates/native-acceptance.template.json) |
| Structured unsupported/failure output | [structured-unsupported.template.json](../assets/reference-platform/templates/structured-unsupported.template.json) |

The original six reference-platform assets remain useful. The single-corridor
request is directly shaped for its bounded builder. The semantic example is
validated by the reality-station planner. The multi-track request remains a
documentation and contract example. The publication example is symbolic and
cannot be passed directly to the bridge. The unsupported example asserts the
expected fail-closed diagnostics.

Representative implementation tests are
`backend/OTAI/tests/test_semantic_planning.py`,
`backend/OTAI/tests/test_reality_station_semantics.py`,
`backend/OTAI/tests/test_semantic_publication.py`,
`backend/OTAI/tests/test_railml_multiedge_platform.py`,
`backend/OTAI/tests/test_railml_station_rebuild.py` and
`backend/OTAI/tests/test_railml_cross_document_platform.py`.

## Partial or unreachable task families

- A universal request-to-native real-station topology compiler.
- General island width, height, area, face and capacity synthesis.
- Arbitrary compound turnouts, slips, diamond crossings and ladder geometry.
- Complete signal-family and lamp authoring.
- General deadlock prevention and static proof of fail-safe behavior.
- General turnround, join/split activation and physical vehicle circulation.
- Complete native timetable preferences and connection-controller parity.
- Current GUI Save, true unload/reload and Inspector observation.

These are capability gaps, not a demand for one solver per historical function.
A future implementation should fill a reusable boundary with source evidence,
typed input and focused rejection tests.

## Native-app-required paths

The following remain outside the current offline acceptance and are `not_run`:

1. Open the original OpenTrack application.
2. Load the current candidate project.
3. Perform GUI Save.
4. Unload and perform a true reload.
5. Inspect platform, track, stopping area, signals, Routes and Paths.
6. Observe expected signal and lamp presentation.
7. Observe route reservation and release.
8. Observe a zero-speed platform stop.
9. Observe planned departure.
10. Observe downstream arrival.

Historical Reading P9 evidence may be cited only with its recorded version,
case, input hashes and limitations. It cannot promote a current project to
native acceptance.

## Historical 176 inventory relationship

`references/coverage/requirements.json` preserves all 176 source rows. The
historical audit records 89 `not_verified`, 80 `partial` and 7 qualified
subset/command/targeted-check states, with no parent marked complete native
parity. Those counts remain useful for source discovery and gap review.

`references/coverage/完整复刻验收表.md` is a historical evidence timeline.
Its Wave11/Wave12 totals, test counts and release snapshots belong to their
recorded stages and do not define the current AI toolbox release.

## Workload model

Estimates are planning judgments after inspecting the current code and tests.

| Work scope | Estimate |
|---|---:|
| Truth-sync, evaluator strengthening and release closure for the current AI toolbox | 16–40 person-hours |
| One integrated realistic station using existing tools plus final native acceptance | 80–200 person-hours |
| General real-station topology compiler as a capability expansion | 400–800 person-hours |
| Final native acceptance cycle for the already supported toolchain | separately bounded after candidate scope is frozen |
| Historical full equivalence across all 176 parent requirements | approximately 3,300–7,100 person-hours, if that superseded objective were pursued |

The final row is historical and is not the current release KPI.

## Current evidence and next gate

Offline tests establish schema behavior, plan binding, registry reachability,
failure closure and fresh archive readback where their fixtures provide it.
The release gate additionally checks the exact ZIP, extracted manifest,
profile counts and package smoke.

All native observations remain `not_run` until one consolidated authorized
phase opens original OpenTrack, saves and reloads the selected candidate,
inspects the required objects, and runs the bounded station scenario.
