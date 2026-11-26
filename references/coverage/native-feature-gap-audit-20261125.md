# Native feature gap audit — 25 November 2026

## Scope and evidence rules

This is a read-only audit of the advanced OpenTrack Skill at `D:\opentrack\skills\railnet-studio-advanced-hakimi`. It covers source/decompiled evidence, metadata and contracts, current function coverage, replica/coverage files, references, assets and tests. It does not launch or control OpenTrack, write a native project, execute a current-round station run, or certify any railway safety function.

Evidence is kept in separate levels:

| Level | Evidence | What it can establish |
|---:|---|---|
| 1 | Documentation and contract | Intended workflow, input shape and explicit exclusions |
| 2 | Static contract/source semantics | Supported archive fields, references and rejection rules in the inspected code |
| 3 | Actual Skill/MCP save to a fresh path | An Agent-visible operation reached its writer and produced files |
| 4 | Fresh-process independent readback | Output files survive a separate parse/read pass with intended values and references |
| 5 | Historical original-engine run | An earlier bounded scenario reached the original application and produced result evidence |
| 6 | Current-round GUI Save/reload, Inspector, lamps and actual run | Present-day application acceptance of archive loading, signalling, stopping, reopening and movement |

This audit reaches levels 1–5 only where the cited evidence exists. No level 6 acceptance was performed. A historical run attached to a fixed input remains historical evidence, and a passing test or registered tool is not proof of full native parity.

## Requirement and parent-function state

The authoritative parent inventory for this report is `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\requirements.json`. It declares 176 requirements and contains 176 rows. The source still has `goal_complete: false`.

| Parent state | Count |
|---|---:|
| `not_verified` | 89 |
| `partial` | 80 |
| `independent_subset_implemented_unverified_parity` | 2 |
| `implemented_verified_agent_command` | 2 |
| `generation_distributions_smoke_verified` | 1 |
| `verified_atomic_snapshot_subset` | 1 |
| `implemented_targeted_checks` | 1 |
| **Total** | **176** |

No parent has an explicit `complete` status. There are 169 parents in `not_verified` or `partial`. The seven remaining parents have qualified subset, command or targeted-check evidence and still do not establish full parent completion: `M3.1`, `M3.5`, `R17.22`, `R17.34`, `A02`, `A04`, `A05`.

`current_server_verification.native_verified` is true for **0 of 176** parents. This is a current acceptance-state flag, not proof that the corresponding original function is absent. The inventory itself uses `not_reassessed` in many operation mappings and warns that module-family candidates require inspection of the exact schema/action.

| Domain | Total | Parent-state detail |
|---|---:|---|
| M2 | 8 | 6 `not_verified`, 2 `partial` |
| M3 | 22 | 11 `not_verified`, 9 `partial`, 2 qualified subset |
| M4 | 17 | 2 `not_verified`, 15 `partial` |
| M5 | 24 | 6 `not_verified`, 18 `partial` |
| M6 | 15 | 3 `not_verified`, 12 `partial` |
| M7 | 6 | 6 `not_verified` |
| M8 | 17 | 13 `not_verified`, 4 `partial` |
| M9 | 9 | 8 `not_verified`, 1 `partial` |
| R17 | 40 | 34 `not_verified`, 4 `partial`, 2 implemented commands |
| A | 8 | 5 `partial`, 3 qualified subset/check statuses |
| G | 10 | 10 `partial` |

The area counts are M2 8 + M3 22 + M4 17 + M5 24 + M6 15 + M7 6 + M8 17 + M9 9 = 118. The R17 inventory adds 40 and the A/G supplements add 18, giving 176 total rows.

## Duplicate coverage files and interface counts

`references\coverage\current-function-coverage.json` and `backend\OTAI\replica\current-function-coverage.json` are byte-identical. Both have SHA-256 `3E8DCA1E19CE935EED162A8CAC87F187439C165486BED88393F6F2A36A179DA5`.

The two requirements copies are byte-identical:

- `references\coverage\requirements.json`: `FC3C538EEBA80E7192BCE75444CC098823048250A7501840078F7329A4D0B9EB`
- `backend\OTAI\replica\requirements.json`: `FC3C538EEBA80E7192BCE75444CC098823048250A7501840078F7329A4D0B9EB`

The parent counts above use the requested references copy.

The function-level file contains **89 rows**:

| Function status | Count |
|---|---:|
| `complete_supported_archive_function` | 65 |
| `complete_supported_archive_read_function` | 24 |

The 65/24 labels mean bounded supported archive write/read semantics, not equivalence to the complete original C-function domain.

| Declared operation kind | Count |
|---|---:|
| `write` | 43 |
| `read` | 24 |
| blank / absent | 22 |

The release metadata describes **65 writes, 24 getters and 15 composites**, but the 22 blank `operation_kind` rows mean the function file alone does not account for the composite classification row by row. Do not infer the missing 22 rows are all composites without inspecting their entries.

The current runtime registers **219 generation schemas** and **242 all-profile schemas**, with **3 explicitly blocked generation tools** and **8 explicitly blocked all-profile tools**. The profile counts include readers, validators, previews, application helpers and fail-closed registrations, so they are not completion counts. `goal_complete` remains `false`. Eight legacy geometry/editor entries are quarantined under `LEGACY_GEOMETRY_DISABLED`:

1. `opentrack_create_project`
2. `opentrack_generate_operations`
3. `opentrack_stage_changes`
4. `opentrack_start_editor`
5. `opentrack_edit_editor`
6. `opentrack_publish_draft`
7. `opentrack_apply_draft`
8. `opentrack_create_demo_line`

Registration, a schema being present, and a tool being callable are separate facts. The quarantined entries must not be counted as working construction or editing capabilities.

## Implemented interface classes

The audited evidence contains native archive field writes for Course, Train, Engine, TrainCategory, Timetable, Station catalog, Edge, Incident, Formation/position, Path append, DelayInterval and names.

Composite/template write families cover Routes, Paths, Itineraries, timetable catalogs, operating archives, topology/network archives, station/platform rebuilding, halt signals, rerouting, RailML facilities, route protection and run parameters. Their supported domains remain finite and explicit.

Read or verification-only functions cover native interlocking output, throat passage, platform choice, route protection, run outcomes, throughput, delay batches, occupancy and statistics. A verifier consuming an original run is not a replacement for the original simulation engine.

The old v0.15 document is historical. Its 35-tool count must not be presented as the current interface size or completed capability.

## Station and run capability matrix

| Capability | Current evidence | Acceptance boundary |
|---|---|---|
| Single through platform, stop and reopen | `opentrack_build_reference_platform_corridor` has a documented contract and the Reading P9 frozen historical run | Level 5 for that bounded case. Native results show RDG09 arrival `10:23:05`, departure `10:25:05`, 120 s dwell, standing at 2025 m, platform span 1700–2025 m, downstream arrival `10:27:19`, 4225 m course and positive onward speed. Two Late Arrival/Late Departure WARNINGs, no ERROR/FATAL in the recorded result. Current GUI and current-round run remain unverified |
| Multiple platform tracks | RailML facilities can write several tracks sharing one OCP with separate type-2 reference ends and exit signals; station rebuilding supports facing and passing-loop turnouts. Historical evidence documents a two-track 120 s stop at 750/850 m and different downstream ends | Bounded historical behavior and static save/readback only. There is no universal one-step multi-track real-station builder |
| Island platform | `test_railml_station_rebuild.py` constructs two independent loops and island faces, with station membership and cold readback checks | Static native-file contract/cold-read evidence for a bounded example. No general island-face/capacity model and no island-specific actual run were found |
| Throat and turnouts | Saved-geometry actions support edge creation/splitting/replacement/rerouting, main and halt signals, station-area edits and shared-throat rerouting while preserving Routes/Itineraries. RailML rebuilding handles simple paired-End turnouts and passing loops. An eight-track example documents 12 paired-End turnouts, 16 directional signals, 8 platform tracks and 4 island graphics | Bounded static/current regressions and specific historical native runs. No arbitrary compound/slip/crossing/ladder constructor or general real-layout synthesis |
| Interlocking authoring and verification | Route-protection fields, signal aspects, release/zone data and exclusions are editable within audited domains. `opentrack_verify_native_interlocking` validates original-run output. Historical evidence covers sectional release, simultaneous occupation, authority handover and exclusion comparisons | Saved-data authoring plus bounded historical verification. The Skill does not replace OpenTrack's dynamic interlocking engine and cannot certify all signal systems, deadlock avoidance or fail safety |
| Stop, dwell and onward movement | Reading P9 demonstrates a planned platform stop, a recorded zero-speed interval and downstream movement | Level 5 for Reading P9. Current-round GUI Save/reload and current-project actual run remain deferred |
| Turnround, split and join | There are helpers, contracts and focused tests, plus historical bounded evidence | General activation, vehicle circulation and coupling behavior remain incomplete, especially M6.3.6 |

The supplied `reality-station.multi-track.request.template.json` explicitly sets `satisfies_single_corridor_builder: false` and has a `template_status` field noting documentation/contract-only use. It must not be treated as an executable multi-track compiler.

## Concrete missing capabilities

1. A universal real-station request-to-native-topology compiler.
2. An executable multi-track and island-platform contract with general face, area, length, height and capacity semantics.
3. General platform-to-track mapping beyond contiguous, uninterrupted platform edges.
4. Arbitrary slips, crossings, compound turnouts, ladders and complex throat geometry.
5. Complete signal-family, aspect and Inspector authoring.
6. General deadlock prevention and signal-display verification.
7. General turnround, join and split activation with physical vehicle circulation.
8. Current live timetable preferences and complete native timetable/connection controller parity. Base local insert/delete, target-0 placeholders, paired Turnround helpers and first-target selection exist, while native coupling and circulation are incomplete.
9. General native dynamic verification without launching OpenTrack.
10. Current GUI Save, true unload/reload, Inspector inspection, lamp-color checks and a current end-to-end station run.

The multi-edge platform tests establish an important bounded rule: a platform may span contiguous Edges when the requested stopping Edge is exact, but gaps, branches and interior signals are rejected. The station rebuild and cross-document tests establish specific reciprocal-connector and station-membership cases. Those tests do not generalize to arbitrary real-station geometry.

## Reusable examples and evidence

The Skill has no root `examples/` directory. Its operative examples are under `assets/` and backend tests.

### Reference-platform requests

- `assets/reference-platform/reading-p9.request.example.json`: single through-platform example with 325 m platform, arrival 10:23, departure 10:25 and 209 m train.
- `assets/reference-platform/reality-station.request.template.json`: real-station request workflow template.
- `assets/reference-platform/reality-station.multi-track.request.template.json`: documentation/contract-only multi-track template.

### Yard and workflow assets

- `assets/grid-yard-profile/`: six request, final-layout, build, verify and provenance files.
- `references/reference-platform-workflow.md`: bounded single-platform workflow.
- `references/reality-station-template.md`: real-station evidence and input boundary.
- `references/native-infrastructure-railml.md`: facilities, multiple tracks and cross-document platform notes.
- `references/saved-geometry-editing.md`: saved topology and throat editing actions.
- `references/native-interlocking.md`, `native-throat-passage.md`, `native-platform-choice.md`, `native-route-protection.md` and `native-course-platform-rebind.md`: native-side verifier and rebind workflows.

### Focused backend tests

- `backend/OTAI/tests/test_railml_multiedge_platform.py`: contiguous multi-Edge platform, exact stopping Edge, both directions and rejection of gaps, branches and interior signals.
- `backend/OTAI/tests/test_railml_station_rebuild.py`: facing turnouts, reciprocal connectors, passing loops, two independent loops and island faces.
- `backend/OTAI/tests/test_railml_cross_document_platform.py`: two/three-worksheet platform across reciprocal connectors.
- `backend/OTAI/tests/test_reference_platform_reading_p9.py`: validates the frozen successful Reading P9 result and rejects the failed result.
- `backend/OTAI/tests/test_native_throat_passage.py`, `test_native_interlocking.py`, `test_native_platform_choice.py` and `test_native_platform_join.py`: bounded native-output and journey checks.

### AI planning and explicit-gap examples

- `assets/reference-platform/reality-station.semantic.example.json`: schema-shaped island-face and directed-throat example accepted by the pure planning validator.
- `assets/reference-platform/reality-station.unsupported.example.json`: fail-closed compound-turnout example that must return `UNSUPPORTED_COMPOUND_TURNOUT`.
- `backend/OTAI/tests/test_semantic_planning.py` and `backend/OTAI/tests/test_reality_station_semantics.py`: plan hashing, evidence-level separation, source closure and unsupported-boundary regressions.

The Reading P9 frozen result is `D:\opentrack\OTAI\workspaces\ReadingP9Verification_20261123\platform-verification.json`. Its native run flag is true and its message counts are six NORMAL and two WARNING. The stop/onward result is bounded to the recorded input hashes and the recorded train/course case.

## Planning estimates

These are audit judgments, not source-derived counts. They assume an experienced engineer already familiar with the current archive contracts and include targeted offline regressions plus independent archive readback. They exclude publication, deployed-service operations and repeated exploratory native GUI runs.

| Scope | Coarse estimate |
|---|---:|
| Fully accepted incremental bounded single through-platform scenario | 16–40 person-hours |
| One realistic multi-track/island/throat/interlocked station with stop and reopen | 160–360 person-hours |
| General arbitrary real-station compiler | 400–800 person-hours |
| Full 176-parent parity | approximately 3,300–7,100 person-hours |

The single-platform range is smaller because a generator, contracts, tests and historical native evidence already exist. For the realistic integrated station, the working split is source/topology mapping 24–40 h, platform faces/areas/stops 32–56 h, throat/resources/routes 40–80 h, signals/interlocking/protection and negatives 32–64 h, operations/timetable integration 24–40 h, and GUI/native acceptance/hardening 32–64 h. Shared work can reduce the upper total.

The full-parity range starts from 89 `not_verified` parents at 20–40 h and 80 `partial` parents at 12–24 h, giving 2,740–5,480 h, then adds 20–30% for integration and native acceptance. At 40 productive hours per week, two engineers would need roughly 9.5–20.5 months. This basis draws on the 89 audited function rows, 575-test historical package evidence, the remaining parent breadth, 1,139 UI controls and 649 unique selectors in the inventory, and missing cross-domain/native acceptance. Uncertainty is high because `not_verified` includes mappings that were never reassessed.

## Acceptance boundary and next consolidated gate

The allowed workflow is targeted offline regression and archive readback during feature development. Freeze, package, full regression, original OpenTrack launch, GUI inspection and actual running should be consolidated after the feature set is complete.

The next native gate must verify, in one authorized cycle:

1. Current-format save from the actual Skill/MCP path to an isolated output.
2. A genuinely separate process reading the saved files and confirming references.
3. Original OpenTrack opening and reloading the saved project without silent repair.
4. Inspector visibility of the platform, track, stopping area, signals, Routes and Paths.
5. Expected signal/lamp presentation and interlocking behavior.
6. A booked train entering, stopping for the planned dwell and departing onward.
7. Multi-track/island and throat cases beyond the fixed reference examples.
8. Negative cases proving rejection or safe handling of gaps, missing references and unsupported geometry.

Until those checks are observed, the correct conclusion is bounded archive generation and historical native evidence, not complete current native application parity.

## Key source paths

- `D:\opentrack\skills\railnet-studio-advanced-hakimi\SKILL.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\requirements.json`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\current-function-coverage.json`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\progress.json`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\完整复刻验收表.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\ui-control-inventory.json`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\coverage\rebuild-interface-matrix.json`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-writing.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\complex-design-workflow.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\reality-station-template.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\reference-platform-workflow.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-infrastructure-railml.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\saved-geometry-editing.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-interlocking.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-throat-passage.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-platform-choice.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-route-protection.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\native-course-platform-rebind.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\acceptance-levels.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\evidence-record-scope.md`
- `D:\opentrack\skills\railnet-studio-advanced-hakimi\references\station-document-layout.md`
