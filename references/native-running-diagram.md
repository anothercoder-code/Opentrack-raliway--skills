# Original OpenTrack train diagrams

**案例与合同边界：**本文涉及的站数、股道数、网格或走廊是现成辅助入口和验收案例的范围，不是完整版所有复杂设计的固定规定。其他设计先按[需求组织设计](complex-design-workflow.md)，再选择符合实际合同的实现路径。

**Prerequisite:** first complete [full original-software authorization](software-authorization.md). User task permission or a passing original save guard is not confirmation of a valid full software licence. No native-data work or GUI-guided workaround before confirmation.

First resolve what “image” means. A station schematic, a chart drawn from CSV,
an OpenTrack screenshot and an original Train Diagram EPS/TIFF are different
artifacts. When the user requests the software's running diagram, obtain actual
native trajectories and use the original renderer/exporter. An AI-generated
image or a custom curve redraw does not satisfy that request.

`scripts/native_diagram.py` prepares whole-network capture jobs and writes offline
native Corridor candidates from original events. The historical nine-station
H2 workflow remains available for its accepted export case.
All source/project/donor paths are explicit and relative to the authorized root;
the same English printable-ASCII requirement applies inside the original app.
The only native executable identity supported by the source bridge is SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Do not change addresses/version labels to accommodate another executable.

## Capture another project and select a corridor

1. With `prepare-network-capture`, pass `--root`, `--request`, and a fresh
   `--job-dir`. The request has `project_directory`, `run_file`, `files`
   (exact relative source member names mapped to SHA-256, including the .run),
   and `donor` (relative `path` and `sha256`). Use a selected .run closure
   without existing diagram declarations. The disposable relocated project
   enables recorder, protocol and distance/time outputs and binds the empty
   `OTDocuments/ActualNetwork.otsimnet`. Other simulation controls retain their
   source values.
2. Run the original on the new project's .run and recheck fresh work output
   and actual collector. The new collector uses the original executable's
   recorded position and topology data. An empty seed is not an actual capture.
3. Run `inspect-network --root <root> --collector <relative-path>
   --collector-sha256 <sha> --course <reference-course>` to find station End
   IDs and check whether observed adjacent events uniquely identify its physical
   alignment. The course is optional.
4. Run `project-corridor --root <root> --request <relative-json>
   --job-dir <fresh-dir>` to write a Corridor candidate. The request supplies
   hashed `collector` and `donor` objects, `distance_traces` (Course ID mapped
   to hashed native .st1 path), and `spec` as below. Either declare explicit
   `edges` with `edge_id` and `from_end` in corridor order, or resolve
   `course_id` from independently retained native position events.

```json
{
  "paths": [{"course_id": "H2E1"}, {"course_id": "H2W1", "reverse": true}],
  "stations": [
    {"station": "J21", "end_id": "1292"},
    {"station": "J22", "end_id": "1712"},
    {"station": "J23", "end_id": "2132"}
  ],
  "courses": ["H2E1", "H2W1", "TURN_NW"],
  "maximum_st1_delta_residual_m": 2.0
}
```

An alternative physical path must list its Edges in the primary axis direction
and may use an integer `start_m` to join part of the axis. Use `reverse: true`
to orient a reference Course that ran in the opposite direction. Native Edges supply
the metre lengths. Shared End coordinates and directional aliases must agree.
When a train leaves the declared alignment, save only its actual on-alignment
segments; a later return starts a separate line. This applies independently to
either travel direction. Check each retained point's relative distance against
the interpolated independent native .st1 trace. Flag residuals without moving
events. The generated receipt and point provenance expose segment boundaries,
original event indices, nearest position anchors and the residual.

### Route occupation and route-braking layers

Add `occupation_traces` to the projection request to verify and encode the original
route-occupation layer. Each Course maps to `reservation` and `release` objects
with `path` and `sha256` for its native `.step1` and `.step2` files. The tools
require the same written native scenario as the Course's `.st1`. They compare the
collector reservation and release End IDs, clocks and projected metres with both
the actual route travelled and the corroborating native stair transitions. They
encode intervals with the same two spatial endpoints supported by both banks in a
shared chronological order. The receipt includes interval boundaries, native
indices and unmatched records. These are the reserve/release times represented by
the original Route Occupation layer. Actual rail occupation start/end in monitoring
files is a separate output.

Add `conflict_messages`, a `path` and `sha256` object for the same run's
`OT_Messages.txt`, to encode route-braking conflict markers. The current codec
requires collector type 4, one original Braking for Route warning on the same
Course and clock second, and one retained actual movement segment at that instant.
Tag-dependent conflict identifiers require the original tag, which the network
collector omits. Same-second duplicate keys and events beyond the retained
physical segment are reported separately.

The current file contract uses OpenTrack 1.7's captured
`OTSimDocument2` up to 20 MiB and the verified `OTCorridorDocument11` donor with
16-bit topology distance markers, up to 32,767 m per corridor. A generated
12 km corridor opened in the Windows OpenTrack 1.7.6 GUI and rendered five
train traces (including two partial turns), gray occupation bands and four
yellow route-braking markers. The original GUI exported that same view as
EPS and TIFF. Tag-dependent conflicts and other new cases still require their
own acceptance.

## Display and edit the planned timetable in the original application

`prepare-planned-corridor` creates a fresh, relocatable project for a native
planned Corridor view. OpenTrack builds the planned line from the active
Course and Timetable catalogs and the Corridor's ordered Station signs. The
archived position, reservation and conflict data continue to supply the actual
layers. `show_actual` can hide those layers in the prepared view.

```powershell
python scripts/native_diagram.py prepare-planned-corridor --root D:/RailWork --request OTAI/workspaces/planned-request.json --job-dir OTAI/workspaces/planned-corridor
```

The request includes the `project_directory`, selected `run_file`, `files`
map of exact source-closure member paths to SHA-256, and a `corridor` with
`path` and `sha256` for an existing `.otsimcor` v11 or v13. Select enabled
`courses` to include in the clock/Station readback, each with at least two
timed Corridor Station signs and explicit absolute planned clocks. The original
viewer uses the project's active catalog and its own category filters.

Optional `timetable_edits` maps exact `CourseID#index` keys for the selected
Courses' existing Corridor entries to `arrival`, `departure` and their named
`*_day_offset` fields. The new project preserves stored actual clock fields.
For example, `{"RDG09#1":{"departure":"10:25:45"}}` changes the copy of the
P9 planned departure. `planned_time_format` accepts `none`, `mm` and `mm:ss`.
The job receipt lists the saved clocks, original Station positions, hashes and
the selected closure preflight. The source `.run` should have no existing
diagram declarations. Existing relative interval-backed rows require another
authoring workflow.

In original OpenTrack, choose `Info → Preferences → Import` and select
the job's `project/<run-file>`. Choose to open listed documents. Bring
`Planned Corridor.otsimcor` to the front and verify `Planned Timetable` and
`Actual Timetable` under the `Tools → Train Diagram` inspector. Inspect the
planned layer before starting a new simulation. To edit with the original
GUI, click the planned line to select a Course and drag its time point along
the time axis. Confirm the new value in `Tools → Timetable`, save the timetable
bank in the fresh project and reopen it with the same `.run` for readback.

The original application displayed the Reading P9 planned departure at
10:25:45 together with the archived actual trajectory. Dragging the planned
departure handle set it to 10:25:55. The original Timetable panel read back the
new value and Save DB persisted it. A separate original simulation that
reopened the saved timetable departed Reading at 10:25:55 after a 175-second
stop, and reached the terminal at 4,225 m.

## Batch export original running diagram files

OpenTrack 1.7 script mode writes native graphical timetables as
`<drawing>.<scenario>.otsimcor`. Use `prepare-diagram-batch` to create a fresh
simulation project from the selected run and up to 24 Corridor definitions.
It retains each definition's Station coordinates and native topology lookup,
clears the movement banks and enables original `Output Train Diagram`.

```powershell
python scripts/native_diagram.py prepare-diagram-batch --root D:/RailWork --request OTAI/workspaces/diagram-batch-request.json --job-dir OTAI/workspaces/diagram-batch
python scripts/ot.py --root D:/RailWork --profile simulation-evidence call opentrack_simulation_control --args-file D:/RailWork/OTAI/workspaces/diagram-batch/run-request.json
```

The preparation request supplies `project_directory`, selected `run_file`, its
exact `files` path-to-SHA map, `scenarios`, simulation `expectations` and `drawings`.
Each drawing has a unique `name`, a SHA-bound native `source` `.otsimcor` with a
populated topology lookup and expected `courses`. An optional `time_window_s`
sets the native display window in absolute simulation seconds. Use a source
run without other diagram declarations. The original archival files keep the
run's movement records even when a drawing displays a narrower time window.

Check the [native simulation job status](native-simulation-jobs.md). Once the
selected scenarios pass, publish their original archives into a fresh directory.
`--include-occupation` adds the original `.occ` and `OT_OccStatistics.txt` files
when present.

```powershell
python scripts/native_diagram.py publish-diagram-batch --root D:/RailWork --batch-dir OTAI/workspaces/diagram-batch --job-dir OTAI/workspaces/diagram-delivery --include-occupation
```

The publisher verifies the original run, frozen drawing inputs and output hashes.
It checks the expected Course, Station positions, saved time window and movement
points in each archive. `original-exports.json` records the reservation and
release point counts, Station events and the relative-distance residual compared
with the independent `.st1` files.

In the Reading P9 acceptance, original scenarios 0 and 17 each wrote one full
and one P9 detail `.otsimcor`. Each archive includes 1,309 RDG09 movement points
across 4,225 m and Station events confirming a 120-second stop. The maximum
`.st1` relative-distance residual was 0.178 m. Each scenario also produced two
original `.occ` files and one original `OT_OccStatistics.txt`.

To obtain EPS or TIFF, open the native `.otsimcor` and use the original
Save Picture commands described below.

## Collect actual whole-network traces

The `.otsimnet` collector is distinct from the selected `.otsimcor` Corridor
display. `Output Train Diagram#1#` alone does not create a usable evaluation
document. The source-backed collector must be bound by `Train Diagram Document`.
The external v11 display donor used for its empty dictionary/date shapes is SHA
`6276294079eaca391576effe3ad67b3ebe5e181330ea3ef9736ec45250315e81`.
Only its empty container shapes are used; training curves are never copied.

```powershell
python scripts/native_diagram.py prepare-capture --root D:/RailWork --project OTProjects/MyGrid --donor "OTProjects/Training/OTDocuments/Corridor Station A - Station G.otsimcor" --job-dir OTAI/workspaces/diagram-capture
```

Preparation creates an empty `Grid3x3.otsimnet`, a separate `capture.run`, an
isolated output directory and backups/hashes of all 16 inputs. The seed has
seven independent empty dictionaries and the good-adhesion/no-delay/performance-1
metadata selected for this fixed grid capture profile. Those experiment settings
are not defaults for every project: a different capture workflow must preserve
or explicitly declare its own adhesion, delay and performance assumptions. There are no invented trajectories. It does not rewrite the
formal run file or global Preferences.

Before an authorized native run, resolve the current session and dirty state;
do not replace files while stale objects/controllers remain loaded. Verify the
stock executable hash. The original scripted invocation is:

```powershell
& 'D:/RailWork/OpenTrack.app/OpenTrack.exe' -scriptinit '-runfile=D:/RailWork/OTAI/workspaces/diagram-capture/capture.run'
```

Run the original process using an appropriate hidden startup setting when doing
background script work. It can write actual timetable values back to the formal
catalog: freeze that writeback and the fresh outputs before restoring the clean
plan from the prepared backups. Never discard unknown user modifications or
restore blindly over files modified after the controlled run. A zero exit code
is insufficient: check actual new files, complete current Course IDs, station
topology, time window, terminal stops and classified warnings. Require the
collector to contain the expected current Course/station identities, not just
nonzero size. For this bundled grid profile those expectations are 33 Courses
and nine stations; other projects must derive their own inventory and counts.

The verified source case's native-written collector contains 100137 actual
events, 1699 reservations and 1270 releases. The new portable preparation is
offline-checked; every new capture still needs its own original run acceptance.

## Project the actual H2 Corridor

Use the grid candidate receipt (plans/proofs/traces/execution_root), the actual
native collector hash, the same external display donor and fresh native `.st1`
outputs. H2 is J21—J22—J23 at 0/6000/12000 m. The five complete services are
H2E1, H2E2, H2W1, H2W2 and H2E1_FOLLOW.

```powershell
python scripts/native_diagram.py project-h2 --root D:/RailWork --project OTProjects/MyGrid --recipe OTAI/workspaces/grid-candidate.json --collector OTAI/workspaces/diagram-capture/Grid3x3.otsimnet --collector-sha256 <actual-64-hex-sha256> --donor "OTProjects/Training/OTDocuments/Corridor Station A - Station G.otsimcor" --capture-output OTAI/workspaces/diagram-capture/capture-output --job-dir OTAI/workspaces/H2-corridor
```

This preserves real `posEndID/posNextEndID/posFactor/time` events, resolves their
actual route and native Edge metres, compares every projected point with native
`.st1` output, and writes point provenance plus residuals. Preserve additional
node-crossing events between sampled output rows; do not delete or move them to
force equality. The accepted source case used 15055 actual points. Its ordinary
nearest-sample maximum residual was 0.300132 m; ten additional node events had
nearest-row residual up to 1.9 m; linear-interpolation maximum was 0.390776 m.
Do not claim the failed 0.061 m equality gate passed or claim its native cause is
fully known. The new helper shortens only the display comment to fit the page.

For this legacy-donor-derived, offline H2 candidate, retain root v11 with 24
groups and controller v1 with four dictionaries; do not relabel these to current
v13 without the additional fields.
g5 is simData, g19 is the now-empty single-track array; the native decoder creates
v1's empty timetableDict. Use offline `overwriteData=0`, display flags `0x8508`,
and remove that donor's training events/conflicts/occupation/single-track data.
This cleanup is not an instruction to delete actual single-track, conflict or
occupation layers from other Corridors. Neither this candidate nor a codec
roundtrip alone proves native decoding or rendering.

## Original EPS/TIFF export

Use ordinary native controls when they work reliably. `Document → Save To` and
Train Diagram `Operations → Save Picture` reach the same original function,
provided the actual Corridor is the main window. In the validated Windows
workflow, choose EPS or TIFF under `Save To → Options`, close Options, then
save to a separate output directory. The file type dropdown may continue to
show Documents while OpenTrack appends the format suffix to the file name.
The 12 km corridor EPS identified OpenTrack as creator and contained all
three stations, both turn labels and the route-braking legend. The original
TIFF decoded to 522 × 734 pixels. Use the tool's options panel and verify the
written file signature after saving.

For the user's explicit native-function request, prepare a narrowly scoped job:

```powershell
python scripts/native_diagram.py prepare-export --root D:/RailWork --exe OpenTrack.app/OpenTrack.exe --corridor OTAI/workspaces/H2-corridor/H2_Actual.otsimcor --job-dir OTAI/workspaces/H2-native-export
```

This generates C source, exact EXE/input path and SHA guards, five course-point
counts and an x86 `build.cmd`. Use an x86 MSVC developer prompt with the Windows
SDK, or supply existing `--vcvars`, `--sdk-root` and `--sdk-version` explicitly.
No compiler, SDK, original runtime, binary, donor or licence material is bundled.
Review/compile the generated sources before execution. Then, within authorized
native work:

```powershell
& './launch-owned.exe' --check
& './launch-owned.exe' --run-native-export
```

The launcher refuses an existing original process and never attaches to an
ambient PID. Only its newly created stock child can load the isolated extension.
The bridge temporarily observes named AppKit/Foundation message imports, invokes
Objective-C on the actual host window thread, and restores dispatch entries on
completion/failure. This is a runtime extension, not an untouched-process claim.
It does not synthesize mouse/keyboard input, patch original disk binaries,
replace business methods or expose arbitrary addresses as a public operation.

The fixed call chain preserves `NSApp.delegate versionAllowsSaving` before load
and export; false stops. Full `OTCorridorDocument initWithFile:` must return the
real unarchived document with NIB/controllers/views; use that return object,
not the allocated dummy. Verify exact docFileName, three stations, five native
event counts and signed-int `corridorLength=12000` (`i8@0:4`, not float). Export
the whole `OTCorridorDocView` using original `saveTo:using:` with the original
`dataForEPS`/`dataForTIFF` selector and char BOOL return. These are the same
original implementations reached by the EPS/TIFF wrappers. PDF has no supported
Windows write branch in this binary.

The original case waited about 40 seconds for a native pump event, then wrote
EPS 441892 bytes and TIFF 1532786 bytes with both native returns 1. A launcher
timeout leaves its child open: inspect that PID, trace and actual files before
retrying; never launch another copy blindly or kill an unrelated session.
Automatic readiness is not universal proof against startup/modal dialogs.

Accept export only after checking native return values, file magic, EPS Creator
and labels/bounding box, TIFF dimensions, actual visible curves and disk hashes.
PNG conversion from original TIFF or EPS rasterization is allowed; label it a
conversion, not a redraw. The accepted case rendered 522×734 with three station
axes/time axis/five labelled traces; its upper-right comment clipped slightly,
while the main graph was complete. This release's parameterized export job
compiled offline but was not executed again during packaging. Do not transfer
that past native success to a newly prepared job without its own runtime proof.
