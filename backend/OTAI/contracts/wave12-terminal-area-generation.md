# Explicit terminal-area from-zero generation contract

Existing endpoint: `opentrack_generate_current_operating_archives`.
Default `station_profile="point_only"`: unchanged nine source roles and existing
stations + exactly one schedule/plan. `terminal_profile` and an actual
`connection_template` source are refused. Point-only parsing remains unchanged.

Explicit `station_profile="terminal_area"`: requires all ten `sources` with exact
path/SHA values (the nine earlier roles plus native `connection_template`),
`terminal_profile`, vehicle/template identity choices, network RSP specification,
operating prefix and optional explicit run configuration. Top-level point
`stations`, `schedule` and `plan` must be absent/null; unknown keys are refused.

`terminal_profile` contains:
- `stations`: explicit sign/name/placement/current raw2/4/1 profile, timing_point,
  `reference_end`, `ordinary_ends` (zero or one EndRef) and `stop` (null for pass
  references; otherwise entry/exit EndRefs, area_edge key, length_m,
  exit_signal_name, direction="forward_only"). Pair identity is resolved from
  the NEW generated graph, never guessed from the old grid's native IDs.
- `plan`: explicit course_id, train, itinerary, corridor, exactly five visits.
  Every visit explicitly supplies index0..4, max_index4, station_sign,
  absolute_seconds, stop, timing, flags_raw and actual_time=null. Only index4
  stops (raw3); all other visits are timing pass (raw2). No patch-after-claim path.
- `chains`: line_id, Train, Itinerary, terminal Station sign and 2..24 ordered
  course_ids. They partition the plan exactly once. Native bytes, not only these
  names, determine the actual final validation.
- `expected_counts`: courses, timetable_rows, terminal_stops, chains, pairs,
  connection_records, roots, tails, internal_courses. Full example is
  144/720/144/6/138/276/6/6/132. Strict arithmetic and actual decoded counts agree.
- `minimum_turnround_s=420`, `window_start_s=0`, `window_end_s=86400` are explicit
  reviewed-domain assertions, not new native defaults. Category actual minimum
  must match420s. The maximum native wait sentinel is not replaced with420.

Current terminal identities are H1..H3,V1..V3, corresponding TRAIN_01..06,
I:terminal:<line> and S1_IN..S6_IN. This is a named reviewed teaching-grid domain,
not a general arbitrary-fleet/line circulation API. The default point profile is
not restricted to these new terminal identities.

For each terminal, both S halves remain ordinary type1 associated with the same
StationModel as both A halves type2. B is pass-only type2. All pairs are reciprocal,
uniquely owned and non-Connector. Actual persisted Routes/Paths/Itineraries must
resolve to real Edges; only native type2 references count. S contributes zero
visits. Repeated laps remain separate; only consecutive shared route boundaries
are joined. The final reference must be reached through its exact S→A Edge,
with one incident Edge per half of each area double vertex, one proven directional
exit main signal, no reverse stop contract and sufficient whole consist length.
The reference's reverse half is not a reverse stopping authorization.

Services use actual directional speed-table mapping from the SHA-bound ordered
run TrainType names and Engine maximum; necessary per-leg free-flow bounds must
hold. The single Engine reference must have integer posInTrain=1 (position, not quantity), no trailers, and Category
stopAtEveryStation must not contradict final-only stopping. Circulation verifies
same actual Train/Itinerary/terminal directional End and consecutive planned
chronology, Category minimum, no forks/merges/skips/day-wrap, and exact reciprocal
native Connection fields. Fresh-only existing-Connection refusal is intentional.
After removing only added Connections, all earlier TT graph/alias data must be
unchanged. After removing generated stations/type changes, original network and
opaque header must be recoverable. Independent upstream readers do not import
business generators and also check the old all-pass TT restoration baseline.

Pipeline order is semantic validation and pure in-memory generation → fresh
native Connection records → actual decoded-count assertions → optional generic
run path/hash/speed-name/window binding → shared fd-secure atomic publisher.
The original run binder is not treated as a terminal semantic oracle. It binds
exact final seven archive bytes; its .run validator is narrow and named, never
a blanket typedstream bypass. Empty output directory creation and verification
remain in the same transaction. Every source, including Connection/run templates,
is rechecked. Existing-target fast rejection follows no symlinks and cannot
replace the final no-replace commit gate.

All results are STATIC. Native movement, stopping, actual delay, state/reservation
transfer, physical fleet count, initial activation, terminal shutdown, braking,
conflict/deadlock handling and complete runtime preferences are unverified. A
planned final parked tail is not automatically a deadlock. Do not launch EXE or
prepare Wine under the current task's paused-runtime instruction.

Large terminal requests should be written to a UTF-8 JSON request file, then
`python -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_generate_current_operating_archives --args-file /absolute/path/request.json`.
Do not place the complete 144-Course JSON in one `--json` shell argument: operating
systems impose per-argument size limits. The supported file input uses the same
JSON input handling and strict profile validation; it is not an alternate semantic path.
