# Three-horizontal / three-vertical native payload compiler

Before any railway business command, complete [full original-software authorization](software-authorization.md); metadata/help alone may be used while unconfirmed.

`../scripts/grid_generation.py` creates an explicit geometry and operational-data
plan, **not a simulation**. It uses the actual `opentrack_ai/models.py` Pydantic
contracts without importing unavailable native/archive dependencies. This is
schema validation and static connectivity checking, not real server integration.

## Current writer availability

This legacy compiler's plan/validation is not native execution. Its emitted old
editor/generation/publish calls are currently quarantined with
`LEGACY_GEOMETRY_DISABLED`; real ID-binding receipts cannot be invented to get
past that status. The command sequence below documents the intended/historical
handoff, not an enabled current construction pipeline. A different currently
supported initializer or typed operation needs its own explicit schema mapping;
this is not automatically supplied by the compiler.

## Default and explicit limits

- Six 40 km lines, two physical tracks per line, one operating direction on each.
- 168 paired vertices, 156 Edges, 168 directional main signals, 156 Routes,
  12 Paths, 12 Itineraries, 30 station signs and 288 explicit Courses/1,440 rows.
- Each line's physical chainages are 0, 9600, 9900, 10100, 10400, 19600, 19900,
  20100, 20400, 29600, 29900, 30100, 30400 and 40000 metres.
- Each 200 m crossing section is preceded by a 300 m holding section in either
  direction. Stops are assigned to the approach directional End, not inside the
  crossing. Native station halt-point selection/whole-body clearance is **not
  verified** merely by these assignments.
- Each of nine at-grade intersections shares one native safety Element across
  its four directional crossing Edges via `merge_elements(edge_ids=[...])`.
  A merged Element provides a common conflict resource; it does not connect
  tracks. Confirm the resulting native resources and reservation behavior.
- No inter-line turns, switches, crossovers or circulation are assumed. Thus
  each operating line is connected; the six lines are not passenger-routing
  connected to each other. This is the agreed no-turns scenario, not a full
  switching-grid design. Additional turnout/routing scope requires another plan.
- Synthetic 200 m, 400 t, 80 km/h, 200 kN, 4,000 kW formation; constant-power
  engineering proxy, braking 0.6 m/s². No calibrated vehicle model is claimed.
- Drawing coordinates are not physical lengths. At station `S1/S2/S3`, the two
  direction-specific stopping chainages are nominal station chainage ±100 m.

## Commands

From `<SKILL>/scripts`:

```sh
python grid_generation.py plan /tmp/grid-plan.json --root <actual-data-root>
python grid_generation.py validate /tmp/grid-plan.json --root <actual-data-root>
python -m unittest test_grid_generation -v
```

`build_plan(full_day.scenario())` also accepts the existing helper's validated
scenario dict. It contains one create-project payload and twelve geometry
batches of 41 changes each (all aliases created/used in the same batch).

1. Invoke `opentrack_create_project` with `plan.create_project` under an unused
   project name; then `opentrack_start_editor` using its real returned paths.
2. For each geometry batch, call `editor_payload(batch, actual_session_id,
   actual_revision)`, then invoke `opentrack_edit_editor`. Read the returned
   `draft_id` via `opentrack_get_draft`; save its full manifest. Editor responses
   alone do **not** include allocated geometry IDs. Refresh revision each time.
3. Supply the twelve genuine geometry manifests to bind. Never predict numeric
   IDs or use the synthetic receipt fixture from tests as execution evidence:

```sh
python grid_generation.py bind /tmp/grid-plan.json --root <actual-data-root> \
  --manifest /actual/geometry-manifest-1.json \
  --manifest /actual/geometry-manifest-2.json \
  --project /actual/current/project --run-file /actual/current/BJTU-demo.run \
  --speed-type 'EXACT VERIFIED TARGET COURSE SPEED TYPE' \
  --output /tmp/grid-bound.json
```

The example abbreviates the manifest list; **all twelve** are required by ID
resolution. `speed_type` is a Course preference string, NOT a numeric Edge
speed-table key. Binding is blocked until the exact target preference is known.

4. Apply `safety_changes` in the same actual editor session at its current
   revision. Read back the new draft and inspect all nine shared Elements.
   Do not call `reset_elements` afterward: it would undo the intentional shared
   crossing resources.
5. Apply the seven `generation_batches` in order: stock/stations; 100 Routes;
   56 Routes; Paths/Itineraries; 100/100/88 Courses. **Before every batch**, rebind
   `project` and `run_file` to the preceding tool result's latest draft paths,
   including the safety-edit result before the first generation batch. Do not
   send every batch against the same old project.
6. Read/trace each persisted Path and inspect each Course family. Validate with
   `preparation` scope, configure the full-day run window using the real schema,
   publish an isolated project, then use an authorized real native execution
   path. Native completion requires recorded 24-hour end time, all 288 expected
   unique services, clean run/trajectory/collision evidence, and the main
   full-day acceptance gates. Plan validation or archive generation is never
   completion.

## Evidence boundaries

The independent tests deliberately use **test-double receipts** only to exercise
ID binding and real Pydantic schemas. They do not serialize a native archive,
execute OpenTrack, verify physical feasibility or prove signal-system parity.
Production `bind()` validates receipt shape, End uniqueness, Edge endpoints and
lengths and directional Signal receipt existence; actual provenance must come
from successful live calls/checkpoints and current native read-back.

The missing OTUndo dependency restriction recorded in the old cloud snapshot was
historical environment evidence, not a current instruction or a prohibition on
an authorized local task. Discover the current paired backend and actual native
runtime before deciding what is possible. This legacy planner remains a separate
single-document/no-turn scenario; for the accepted switching-grid design read
[the nine-station yard workflow](grid-station-yard.md).
