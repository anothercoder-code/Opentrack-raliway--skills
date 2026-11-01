# Legacy batch-generation contract — current native writer quarantined

**Current release status:** `opentrack_generate_operations` and its old
stage/editor/publish/apply pipeline are blocked by `LEGACY_GEOMETRY_DISABLED`,
independently of parser availability. The field and batch descriptions below are
historical contract/reference material, not instructions to call a current native
writer. Do not remove the guard or call internal legacy methods as a workaround.

Information-only `opentrack_prepare_operations` and graph compilation remain
separate scopes. Current native tasks must use a matching `current_archive`
operation/initializer, supported standalone profile, or authorized original-app
workflow. Inspect the exact contract; these are not aliases promising every old
batch command. Native implementation gaps must be reported explicitly.

This reference covers actual native archive operations when the required parser
and dependencies are available. A structured information-only bundle is a
separate deliverable: it must not be described as this native draft workflow.
For prose intake, units and dependency-failure recovery, read
[input planning](generation-inputs.md). Native simulation is not required for
an information-generation deliverable.

Use `--profile generation` for focused native MCP tools. Use `all` for advanced
geometry, binary/evidence and repair tools. The exact published input schema is
authoritative; obtain it from MCP discovery or `tools`. This workflow does not
start the native application, create a replacement GUI or run a simulator.

Use ordered `network_operations` for Itinerary edit/copy/rename/delete, Add,
Path replacement and library reset; see [Itinerary controls](itinerary-controls.md).

## One dependency batch

Use ordered `timetable_operations` for first-Itinerary station skeleton creation, existing row changes, interval families,
connections and original text import. `opentrack_export_timetable` exports a
selected existing timetable without rewriting a project. Read
[timetable editing](timetable-editing.md) for formats and reference behavior.

For repeating an existing Course with its full saved timetable and connections,
use `create_interval_courses`; [interval Courses](interval-courses.md) covers
sequential copies, connection renumbering and property propagation. Prefer
`patterns` when supplying a new stop/offset pattern instead of copying one.

For Course renames/deletion or unavailable Itinerary cleanup, add the ordered
`course_lifecycle` list after definitions/partial edits. Read
[Course lifecycle](course-lifecycle.md) for simultaneous rename/reference rules,
explicit dependency detachment and full diff exports.

1. Inspect the selected project/run, catalogs, available Paths and station signs.
   An Engine name, formation name, Course ID and Itinerary name are different
   identifiers. Preserve spelling/case exactly. Native graphic identity includes
   document, class and local ID; Signal IDs differ from attached vertex IDs.
2. If needed, search topology with `opentrack_search_network`. Route definitions
   use the returned directed `nodes`; Paths use Route selectors; Itineraries use
   continuous named Paths. Do not guess connectivity from drawing proximity.
3. Submit one `opentrack_generate_operations` batch. Omit unused arrays. The
   dependency order is `stations`, `engines`, `categories`, `formations`, `shuntings`, `routes`, `route_protection_updates`, `paths`,
   `itineraries`, `courses`, `patterns`, `timetables`, `course_updates`. Definitions earlier in the
   batch can be referenced by later records. `rolling_stock_imports` run after
   Engine/Category definitions and before formations, Routes and Courses; read
   [stock XML](rolling-stock-xml.md) for native defaults and collision choices.
   Next run `course_lifecycle`, `rolling_stock_operations`, then
   `timetable_operations`, preserving order within each list. Category/formation
   edits therefore affect subsequent `create_timetable_skeletons` defaults.
   One batch writes one draft project;
   the original files remain unchanged.
4. Read `generation_summary`, changes, validation errors/warnings and CSV preview.
   Sample resulting Courses with `opentrack_get_service` to confirm the full
   Course → Train → Engine and Course → Itinerary → Path → Route chains.
5. Publish using `opentrack_publish_draft` with the returned `draft_id` and a fresh
   `project_name`. A separate project does not require closing a running original
   OpenTrack. Existing-project application uses the separate advanced apply
   guard and requires the original application closed.

Finish when the requested native records, checks and exports are delivered.
Do not turn an information-generation task into repeated simulation trials.

For station-row derivation, use `create_timetable_skeletons` with exact existing
Course IDs; saved rows need `replace_existing:true`. It reads the first
Itinerary, station vertices/halt/exit candidates and current Category defaults.
Times remain `HH:MM:SS`. Fill times in subsequent ordered row operations or a
later draft. Generation warnings do not certify static preparation; read
[timetable editing](timetable-editing.md) for the creation boundary.

## Engines and formations

For Category priority, distribution tables or detailed Engine/Train parameters,
read [rolling stock](rolling-stock.md). Category `dispatching_priority` is a
real native field: 1 is higher than 2. It is separate from Course acceleration.
Catalog `kind: categories` and service `category_details` expose the exact
formation binding. `include_curves: true` on catalog/service requests includes
Engine tractive-effort points; leave it false for compact normal queries.

`engines` require a unique ASCII `name`, integer `mass_t`, `length_m`,
`maximum_speed_kmh`, `maximum_force_kn`, and exactly one curve source:

- `traction_points`: increasing integer `speed_kmh` / `force_kn` pairs, beginning
  at zero and covering the declared maximum; force cannot exceed its limit.
- `nominal_power_kw`: generates a full-range constant-power engineering proxy.
  Explicitly label it uncalibrated. Do not describe it as a real measured curve.

Optional `template_name` chooses an exact existing record. Otherwise a verified
class shape or existing catalog record supplies unspecified native fields.
`adhesion_mass_t` cannot exceed total mass; driven axles cannot exceed all axles.

`formations` require `name` and `engines: [{engine_name, count, positions?}]`.
Optional `trailers` records specify `name`, integer `mass_t`, `length_m`,
`maximum_speed_kmh`, `count`, optional `positions`, rotating mass/axles,
`number_of_items` and power-loss data. Counts expand physical records; positions
are unique slots in the complete 1…N consist. Omitted positions use free slots.
`number_of_items` is a resistance parameter and never multiplies mass/length.
Generated Trailer records use original 1.7 class v3. Input
`braking_deceleration_mps2` is positive; native deceleration values are negative.
The generator preserves/creates the named Train category and its wrapper arrays.
Several Courses may reference the same formation definition; this alone is not
a rolling-stock circulation or collision guarantee.

## Routes, Paths and Itineraries

`routes` use `name` and directed `nodes: [{document, end_id}]`. Ordinary Routes
start/end at main Signals and may not skip an intermediate main Signal. The
current native persistence supports local Routes or one document boundary.
Supply `signal_aspects` when no verified original defaults exist. Security and
release fields use the exact typed schema; no native interlocking parity claim
follows from writing the Route.

Supported original controls include `reserve_with_previous`,
`discrete_for_moving_block`, `slow_speed_only_for_head`, occupied-entry flags,
`occupied_entry_speed_kmh` / `occupied_entry_wait_s`, approach-zone length/speed
and optional reservation/release-point flags. Read the network reference for
their exact scope. `description` is accepted on Routes, Paths and Itineraries.
Generated Routes clear inherited overlap references by default. To create
Shuntings/Overlaps, release boundaries, local slow-speed-zone endpoints, or to
batch partial edits, read [protection](protection.md). Original printable ASCII
names, including brackets/parentheses, are preserved exactly.
Inspect `serialization_migrations` for the audited v5 security-parent upgrade.

`paths` use `name` and `routes: [{document, start_id, name}]` (or `route_id`).
`itineraries` use `name` and `paths: [exact_path_name, ...]`. Disconnected chains
are rejected. The draft and publication rebase Itinerary document references.
Read resulting descriptions and references with `opentrack_list_routes`,
`opentrack_list_paths`, and `opentrack_list_catalog` with `kind: itineraries`.

## Courses and repeated patterns

An explicit `courses` item needs `course_id`, exact `train`, `itineraries`,
`speed_type` and at least two `stops`. `speed_type` is the original Course string
from the chosen project/preferences, such as `Reihe R` in the bundled fixture;
do not confuse it with an Edge speed-table integer key or guess it for another
installation. `enabled`, `acceleration_percent`, `delayed_acceleration_percent`,
`entering_speed_kmh`, `output_offset_m`, `train_number`, `course_type`, description
and comment can be specified. Missing Train or Itinerary bindings are rejected.
The native normal/delayed acceleration defaults are 100%; entry speed is
converted to native m/s. Display train number and Kind are separate strings.
For native spacing tags, additional reserve/release seconds, ordered Itinerary
preferences and bulk partial edits, read [Course controls](course-controls.md).
The v0.6 name `priority` was incorrect and is now rejected with a migration
message; it must not silently change physical acceleration. Existing archives
are not automatically repaired. Review any old use and regenerate explicitly.

Each stop supplies `station_sign`, `arrival` and/or `departure` as `HH:MM:SS`,
explicit `arrival_day_offset` / `departure_day_offset` (default zero), optional
`dwell_s`, `track_id`, `stop_at_station` and `timing_station`. First stop
requires departure, last stop requires arrival. Times must be chronological and
scheduled dwell at planned stops must meet `dwell_s`. Unknown station signs are rejected. Missing
endpoint times use the original `HH:MM:SS` placeholder. Keys become
`CourseID#0`…`CourseID#N`, with synchronized row indices/last indices. Original
Course IDs with internal spaces, such as `RE 5830`, are supported. Track ID is
native group 18; group 2 is an interval Course reference. Do not interchange
them. An empty track ID is the native automatic/unspecified default.

Stops also support `mean_delay_s`, `distribution_name`, `delta_mass_t`,
`interval_reference_course_id`, `interval_offset_s` and `connections`. A
connection supplies exact `target_course_id`, optional `target_station_sign`
(defaults to the current station), `minimum_wait_s`, optional `maximum_wait_s`,
`entry_connection`, `join` and `split`. Targets may be later in the same batch;
preflight checks them before writing. These are native data records, not proof
of feasible transfers or successful runtime coupling. Dispo/dispatch connection
generation remains unsupported.

`patterns` avoid per-Course Agent calls. Supply `id_prefix`, `first_number`,
`number_step`, `count`, `first_departure`, `interval_s`, `train`, `itineraries`,
`speed_type` and offset stops. `arrival_offset_s` / `departure_offset_s` are
seconds from each departure; first `departure_offset_s` must be 0.
`first_departure_day_offset` selects the first date. Clock strings and dates
carry across midnight automatically from offsets; the tool does not guess a
midnight crossing from explicit descending same-day times. Two patterns
can express the two directions. Station flags and Course acceleration/type are
preserved. `keep_interval_reference: true` links later services to the first
Course, with per-row offsets. The tool does not infer a real timetable or a safe
dispatch interval.

`timetables` replaces the complete stop list of an existing Course. Existing
unrelated Course rows are preserved. Entity replacement otherwise requires
explicit `replace_existing: true`; fresh names are the default.

Limits: at most 1000 generated Courses, 10000 requested timetable rows and 10000
connections per batch; at most 64 powered and 1024 total consist records;
day offsets -366…366. Full circulation, automatic connection planning and native
dispatch/coupling execution are not implemented. CSV preview contains day
offsets and track IDs, and **all resulting project rows**, including
preserved source services, and is UTF-8 with BOM for spreadsheet compatibility.

When generation introduces current fields, audited old Trailer/Timetable/
Connection records are upgraded together **inside the draft**, with defaults
from the original decoder. The result's `serialization_migrations` reports
counts; unsupported legacy layouts are rejected. Original files are preserved.
The v0.6 track-ID/interval-field assignment was corrected in v0.7.

Advanced `simulation` input edits accept `start_day_offset` and
`stop_day_offset`, save the original `.run` day keys, and update corridor time
windows. This does not launch a simulator. Existing `shift_timetable` and
`clone_course` carry scheduled times across dates; cloning rebases connection
owner IDs. Exact parameter schemas remain authoritative.

## Validation and delivery

Generation always uses `validation_scope: generation`: native schema, text,
object references, Train/Engine/Itinerary bindings and timetable chronology
remain integrity checks. Saved Step, departure-window and initial-body
preparation limitations are warnings for this data task. `preparation` validation
retains stricter static startup screening. Neither scope establishes actual
capacity, collision freedom or successful native simulation.

The source example `OTAI/examples/generate-operations.json` generates a labelled
400 km/h proxy and 16 bidirectional services using known BJTU Paths. Replace
names/times with those verified in the actual target project. `generation_summary`
counts requested generated/updated records, not all preserved project records.

The standalone MCP archive contains offline Python helpers and sanitized native
class shapes; no native EXE/DLL or localization runtime is included. Set
`OTAI_ROOT` to its extracted folder and optionally `OTAI_DATA_ROOT` to a separate
OpenTrack data root. Selected offline creation/generation operations do not technically require an
installed native EXE. This describes dependencies, not the public capability scope or
an exemption from confirmed full software authorization. Advanced evidence/runtime tools can require the original installation.
Use an ASCII data-root path for original `.run` path encoding; the Python code
and installed Skill may live elsewhere.
