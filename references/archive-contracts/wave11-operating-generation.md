# Fresh network and planned operating archives

`opentrack_generate_current_operating_archives` extends the explicit network
specification with paired type2 StationVertex pass references, fresh vehicle definitions,
Courses and Timetables. It runs through one transaction, not a chain of
partially published edits. It does not launch original OpenTrack or user-local Codex. Server-side Python generation and tests are separate.

## Inputs and deliberate boundaries

All nine source paths must remain under the authorized `OTProjects` or
`OTAI/workspaces` roots, are read with no-follow directory descriptors, and
carry exact SHA-256 preconditions. The run source is used for its ordered
TrainType mapping, not copied as a runnable configuration with old paths.
The header's licence and registration fields are preserved unchanged; this
neither grants a licence nor certifies that a runtime is installed.

The infrastructure, movement identities, Station models/catalog, Engine and
Category names, Train definitions, Courses and planned rows are new. Vehicle
physics and conflict definitions come from an explicitly named current type
template with two explicit acceptance booleans; these are not calibrated new
rolling-stock models or independent physical fleet instances. The initial
vehicle domain requires a single Engine and no trailers.

Stations use reciprocal paired End7 type2 reference vertices with the same
actual StationModel on both halves, not platform or stopping-region geometry. Timetable records are pass-only, arrival equals
departure, dwell is zero, actual results are unset. Repeated station names are
preserved with unique station indices, including subsequent laps.

Choose exactly one of:

- A fully explicit ordered Course/visit plan.
- A finite schedule with one assignment per new Train definition, periods,
  start/window, period interval and phase, plus explicit free-flow multiplier
  and per-leg planning slack. Each leg follows actual Route/Edge occurrences.

The speed type is a native name, such as `Reihe R`, not Edge key `0`. The
source run's ordered list maps that name to the numeric Edge speed-table key.
Each visit interval must exceed the necessary free-flow lower bound based on
actual length, direction-specific limit and Engine maximum speed. This is not
a motion simulation: acceleration, curvature and conflicting reservations
may require more time. Satisfaction of that bound does not prove feasibility.
The generated schedule rejects overlap of consecutive planned services using
the same Train definition, but does not prove physical vehicle circulation.

## Output and safety

Without a run binding, outputs are one Document and six catalog files. The
catalog prefix is explicit and names are collision checked case-insensitively.
Preview is default and does not create any target. Save requires a fresh
output directory. All member bytes are prepared and read back before the
single atomic no-replace directory publication; every source is checked
before and after publication. An error after commit explicitly reports
`commit_completed`; inspect the target instead of retrying as an overwrite.

The manifest states the exact tested scope. `native_simulation_executed`,
`complete_project_validated`, physical fleet circulation and platform support
remain false. A generated 24-hour plan is not a completed 24-hour simulation.

## Example and verification

The packaged `verification/wave11/build_grid_operating.py` reproduces the
three-horizontal/three-vertical teaching case in a fresh root from the bundled
private fixtures. It creates six Train definitions, 144 Courses and 720
planned pass records, with separate H1/H2/H3/V1/V2/V3 itineraries. Input physics
are proxy type values, not railway engineering certification.

The portable independent reader uses upstream pytypedstream in a new process,
reconstructs actual movement/station order, checks speed lower bounds and
actual-result emptiness, and restores the before-station graph for comparison.
MCP stdio and the separate Skill CLI are also tested, including preview,
saving, duplicate-target rejection and immutable sources.

## Optional execution-root run binding

`run_configuration` is optional and must name the intended execution-side
absolute root and `windows` or `posix` path style. That path is not inferred
from the cloud staging location, `%PROJECT%` is never emitted, and relative
native path expansion is not assumed. This does not verify that the chosen
execution root or an OpenTrack runtime actually exists.

The generated minimal `.run` binds all six catalog roles, the infrastructure
Document, the ordered TrainType mapping and the explicit start/stop/Step.
It does not inherit unrelated physics/options from the input run template:
that template supplies the speed-type mapping only. Other application/global
defaults are not isolated or validated, so `complete_runtime_configuration`
remains false. No API call, application launch or native run occurs.

A fresh empty output directory is created inside the same atomic bundle.
Only the exact `.run` member uses its explicit text/hash/path validator; every
other member still receives typedstream decoding. Directory identity is checked
with directory descriptors, including after commit. The manifest lists expected
empty directories; a postcommit error retains the published files and reports
both expected files and directories. Existing targets are never overwritten.

The example's `C:/OpenTrackProjects/TeachingGrid` is a declared teaching path,
not an observed server installation. Supply the real authorized server root
when creating a bundle for an actual runtime. A POSIX path contract does not
imply official Linux engine support.

## Geographic semantics correction

See [paired StationVertex contract](wave11-station-vertex-generation.md) for exact
Inspector/setter/consumer semantics, ambiguity guards and the wave10 erratum.
Type1 associations can be valid native station-area members, but are outside this
point-only generated profile. Timing Station flags alone do not make an End
geographically recognizable. Counts describe recognized planned references, not
observed native passing events; actual simulation remains unexecuted.
