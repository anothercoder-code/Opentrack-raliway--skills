# Optional full-day acceptance: a worked traffic scenario

Before railway business, complete [full original-software authorization](software-authorization.md).
This is an optional acceptance plan, not a simulation result or a requirement for
ordinary generation. Use it when the current task requests full-day traffic.

## Derive acceptance from the current request

Choose the actual authorized host, data root, project, traffic identity set,
absolute run window and terminal policy. A prior server-only instruction is
historical task scope, not a prohibition on an already authorized local workflow.
If the current user does require server-only execution, preserve that scope;
do not silently switch to a desktop. Missing dependencies or a failed source
fetch never justify bypassing authorization or inventing receipts.

A full-day run need not use three horizontal and three vertical lines. Station
count, line count, turn movements, platforms, service frequency and the end-of-
window policy come from the design. Continuous traffic may legitimately have
trains active at a day boundary; requiring every train to have exited by midnight
is a condition of the finite example below, not a universal railway rule.

Keep generation, static preparation, actual engine execution, per-train results
and resource checks separate. Do not make an information-only task wait for an
unrequested full-day run. If native acceptance is requested but blocked, finish
independent work and report precisely which acceptance items remain unobserved.

## Explicitly selected legacy example

`scripts/full_day.py plan` and `scripts/grid_generation.py` describe the fixed
`grid3x3-full-day-v1` planning example. Use those helpers only if the user selects
or approves this complete scenario. Their validators check that scenario; changing
its numbers is not evidence that a general design was accepted.

- Six 40 km double-track lines H1–H3/V1–V3, one physical track per direction,
  twelve direction-specific service families; stops at 0/10/20/30/40 km.
- Nine at-grade crossing complexes J11–J33 with actual shared conflict resources,
  no inter-line turns. The old single-document compiler is not the separate
  nine-station turning-yard case. If one station per file is required, choose a
  workflow that actually creates those documents instead of silently using this
  single-document plan.
- Directional holding/halting locations outside crossing clearance, including
  explicitly adequate full-body holding length; the example uses >=300 m for a
  200 m formation. These values are not defaults for every station or train.
- Uncalibrated engineering proxy: 400 t, 200 m, 80 km/h, 200 kN, 4,000 kW and
  0.6 m/s2 braking input. It is not manufacturer data or a calibrated vehicle.
- Exactly 24 hourly departures per family, 288 unique enabled Courses and 1,440
  planned rows. Family offsets 0/20/.../220 s; final departure 23:03:40, final
  planned arrival 23:39:40. Five scheduled stops use +0/+540/+1080/+1620/+2160 s,
  with 60 s dwell at the three intermediate stops.
- Run window day 0 00:00:00 to day 1 00:00:00 (86,400 s), initial Step 1 s.
  This example requires all 288 services to finish and clear by the end without
  mid-run reset. Extra draining time is a separate diagnostic, not a passing
  result for that declared finite window. Record supported/unknown randomness.

The scenario remains **plan-only / native full-day acceptance unverified**.
The different 33-course turning-grid case and its later H2 export do not certify
this 288-course day run. A plan, generated CSV, test-double receipt or configured
End value is not an actual simulation.

## Generate and verify the selected design

1. Inspect current capabilities and real schemas, actual resources and project
   bindings. An executable hash does not prove a runnable licensed engine.
2. Select a currently supported current_archive initializer/typed operation or
   an authorized original-app workflow. The old blank/editor/stage/generation/
   publish pipeline is quarantined with `LEGACY_GEOMETRY_DISABLED`, not restored
   merely by installing parser dependencies. Keep the requested document layout;
   any missing general construction capability is an implementation gap. Preserve
   originals and use actual returned identities and persistence receipts.
3. Build actual directed connections, required turnouts/signals, stopping/holding
   areas and conflict resources. For the selected at-grade example, do not replace
   conflicts with grade separation merely to obtain a pass. For another design,
   use its expressly declared crossing semantics.
4. Build continuous signal-bounded Routes, Paths and Itineraries; then the selected
   stock, Courses and timetable. Validate exact expected ID sets, every binding,
   lengths, directions, resource ownership and static preparation.
5. Publish/apply through the matching persistence contract and read the actual
   bytes. A frozen input manifest and separate new output directory identify the
   run; fresh-only publishers are not in-place overwrite tools.
6. Execute only through the current authorized original-runtime workflow. The
   paired saved-data backend does not itself supply a general start/pause/run-to-
   time engine controller. Original script execution and any supported native
   bridge are separate operations; see [native contracts](native-contracts.md).
7. Check departure, station passage/stops, terminal behavior, Course completion,
   absolute end time and the declared boundary policy independently. For this
   finite example, reconcile all 288 expected identities with no duplicates or
   extras and final active count zero. Other scenarios use their actual plan.
8. Inspect actual reservation/release and conflicting occupation intervals with
   full train-body clearance. Retain WARNING severity and classify queuing,
   braking and delay; zero ERROR/FATAL is not zero warnings or a safety certificate.
9. Deliver input/output hashes, real controls and native events/exports, actual
   planned-versus-observed timings and unresolved scope. The generic text protocol
   matcher does not prove every Course completed or that resource conflicts were
   prevented. Use applicable per-train/resource auditors and state their coverage.

## Helpers and backend selection

These are **example-planning** commands, after the required authorization:

```text
python scripts/full_day.py plan <SCENARIO.json> --root <DATA_ROOT>
python scripts/full_day.py validate-plan <SCENARIO.json> --root <DATA_ROOT>
```

For actual tools use the installed paired bridge and current schemas:

```text
python scripts/ot.py --root <DATA_ROOT> --profile all tools
python scripts/ot.py --root <DATA_ROOT> --profile all call <DISCOVERED_TOOL> --args-file <REVIEWED_ARGS.json>
```

The optional `full_day.py call --root <DATA_ROOT> --tool <ALLOWED_TOOL> --args-file
<REVIEWED_ARGS.json> --checkpoint <CHECKPOINT_DIR>` is a checkpoint wrapper around
that same installed `scripts/ot.py`, not a search for `DATA_ROOT/OTAI/server.py`
or a missing separate evidence server. Its key binds the data root, tool/args,
paired bridge and selected backend entry paths/hashes. Data root and installed
backend are distinct. It forwards UTF-8 argument files with explicit profile;
it does not execute an OpenTrack binary.

An identical successful mutating call may return its prior **tool response**,
not a new native observation. Read-only checks run afresh. Failed/interrupted
mutations are not automatically replayed: inspect actual state and checkpoint
provenance before a deliberate retry. Subsequent editor calls still need the
latest revision and draft. Wrapper `succeeded` does not promote a nested
`blocked/unknown` result or mark simulation complete.

## Historical environment findings are not current prerequisites

An older cloud snapshot lacked archive-parser modules and a native runtime;
it reported a Linux host without Wine and an unavailable separate evidence
server. Those are dated observations, not present installation facts or bans on
local work. The current package's actual dependency/adapter inventory decides
what can run. Do not direct users to missing old files or ask for a denied
source ZIP to recreate that historical layout.

Full-day completion, absolute-day evidence and conflict-occupation coverage still
need the selected project's real exports and parsers. Existing yard/grid audits
are scenario-specific. None of this reference, the old snapshot or a different
successful short run supplies the missing full-day result.
