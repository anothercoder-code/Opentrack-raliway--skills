# Original OpenTrack train diagrams

**案例与合同边界：**本文涉及的站数、股道数、网格或走廊是现成辅助入口和验收案例的范围，不是所有复杂设计的固定规定。其他设计先按[需求组织设计](complex-design-workflow.md)，再选择符合实际合同的实现路径。

**Prerequisite:** first complete [full original-software authorization](software-authorization.md). User task permission or a passing original save guard is not confirmation of a valid full software licence. No native-data work or GUI-guided workaround before confirmation.

First resolve what “image” means. A station schematic, a chart drawn from CSV,
an OpenTrack screenshot and an original Train Diagram EPS/TIFF are different
artifacts. When the user requests the software's running diagram, obtain actual
native trajectories and use the original renderer/exporter. An AI-generated
image or a custom curve redraw does not satisfy that request.

`scripts/native_diagram.py` prepares bounded files and reviewable jobs. **It
never starts OpenTrack or injects a DLL.** It supports this release's actual
nine-station grid and five complete H2 through courses, not arbitrary networks,
partial turning-course projections, occupation stairways, conflicts or PDF.
These are the helper's input limits, not the software's definition of a running
diagram or a global design restriction. For another project or
Corridor, use supported original selection/export controls or a separately
verified adapter; do not change the H2 helper's guards to pretend it fits.
All source/project/donor paths are explicit and relative to the authorized root;
the same English printable-ASCII requirement applies inside the original app.
The only native executable identity supported by the source bridge is SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Do not change addresses/version labels to accommodate another executable.

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
provided the actual Corridor is the main window. Blank inspectors without a
selected document are not proof of corrupt simulation data. Do not keep blindly
clicking a floating control that loses focus; refresh the surface or switch to
the already authorized guided/native-function route.

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
