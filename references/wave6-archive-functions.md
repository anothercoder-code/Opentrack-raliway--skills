# Wave6 current stock fields, Engine curves and Train cloning

Use current archive bytes, exact names and actual source SHA-256 values. These
operations generate saved information; they do not run a simulation or launch OpenTrack. A local agent may invoke the supported handlers within current task and full-software authorization. Discover the actual public schemas before calling.

## Read and edit raw existing fields

1. Call `opentrack_inspect_current_stock_fields(source_path, kind, name, fields)`.
   `kind` is exactly `OTTrain`, `OTEngine` or `OTTrainCategory`; `fields` is a
   nonempty list of distinct allowlisted identifiers. Inspect the returned hash.
2. Call `opentrack_edit_current_stock_fields(source:{path,sha256}, kind, name,
   changes:{field:value,...})`. Default `preview_only:true` saves nothing.
3. Review every requested field and its old/new raw value. Repeat with
   `preview_only:false` and a distinct fresh `target_path` to publish a copy.
4. Inspect that saved path with the same getters and compare the output hash.

Each edit batch targets **one class and one named object**, atomically. Do not
split a requested same-object batch into independent file writes. Unknown fields,
cross-class keys, empty changes and invalid values reject the whole operation.

| Current class | Explicit fields |
|---|---|
| Train16 (10) | `trainType`, `avgDeceleration`, `maxDrawbarForce_kN`, `decelerationUsedFormula`, `brakedWeightPercentage`, `decelerationFunctionParameterC1`, `decelerationFunctionParameterC2`, `brakingDelayType`, `startingRollingResistanceOffsetSpeed_kmh`, `startingRollingResistanceFactor_Nt` |
| Engine2 (2) | `resistFactor`, `adhesion` |
| Category19 (5) | `dispatchingType`, `timingStationsType`, `initialDelayDistributionFunction`, `trackNameCreationType`, `delayAddType` |

`trainType`, `decelerationUsedFormula`, `brakingDelayType`, `adhesion` and all five
Category fields are raw signed-int32 codes. The remaining fields are finite
binary32 values on write. Bool, strings, implicit coercion and overflow are not
numeric input. Do not translate raw codes into unproven business labels, infer
physical units from suffixes, or promise physical validity from serializability.
The three correctedDeceleration/min/max fields are deliberately **not exposed**.

Existing nonfinite values remain readable: strict JSON uses native-bit tags
rather than bare NaN/Infinity. Such tags are reports, **not writable values**.
Untouched native bits, including nonfinite values, are preserved. A successful
finite replacement does not establish native NaN setter behavior.

## Replace or append an existing Engine curve

Call `opentrack_edit_current_engine_curve` with expected-hash `source`, exact
`engine_name`, zero-based existing `diagram_index`, `mode:"replace"` or `"append"`,
and **exactly one** of text `content` or structured `points`. Preview first;
commit requires `preview_only:false` and a fresh `target_path`.

Structured rows are `[speed, force, saved_type]`: exact int32, nonnegative speed,
saved_type 1 or 2. Text follows the audited ASCII Z/V parser, including numeric
prefix conversion and H affecting the next source row; text H is not a saved type.
Review ignored/incomplete text lines, conversion and duplicate diagnostics.

Negative force goes to braking; zero/positive goes to traction. First speed wins
within each array; append keeps existing winners. Arrays sort by speed. Empty
replacement is supported; later insertion without an existing point template is
refused. This edits an existing Engine/diagram, not a new diagram constructor.

The reviewed aggregate function updates only Engine speedMax, forceMax and
forceMin across **all** diagrams. Braking speeds do not contribute to speedMax.
Engine powerMax and diagram axes/adhesion/color/supply/name/loss data stay unchanged.
No interpolation, guessed power formula, UI autoscaling or simulation cache is
created. Shared mutable ownership corridors and unsupported point variants reject.

## Create a new Train from the same formation

`opentrack_clone_current_train` requires:
- `source:{path,sha256}` for a current trains archive;
- `project_run:{path,sha256}` for the actual project `.run`;
- `depot:{path,sha256}` for the Engine catalog;
- exact existing `template_name` and fresh unique `new_name`.

The supplied archives must match the run's unique **TrainFile** and **DepotFile**
bindings. `EngineFile` is not the key in the provided BJTU run. Do not treat matching
names or directories as proof of same-project membership. Every Engine name in
the template must exist in the supplied depot and its Category name must exist
in the same TrainList. Inspect all three dependency hashes, preview, then save
only to a fresh target. Source run/depot/trains stay unchanged.

This is **same-formation template composition**, not original `copyWithZone:` or
`init` equivalence. No replacement, fallback template, different composition,
new Engine, Category creation, physical recomputation or old-version promotion.
All Train scalars inherit unchanged; only the new Train name differs. Owned arrays,
EngineRefs, deceleration points and trailers are independently cloned. Existing
aliases between the original Trains remain unchanged. Category is a name reference,
not an external entity to deep-copy. Root collection count increases by one;
no unobserved index/cache field is fabricated.

For a later edit requiring run membership, use a legitimate run binding to that
saved copy. Saving the new trains file does not rewrite the original run or
relocate a complete project.

## Publication, evidence and limits

The three write endpoints share the standard `Next.finish` preview/fresh-target
publication boundary: expected hashes, bounded paths, no overwrite, dependency
rechecks, saved-byte verification and fresh reload. A postcommit failure may report
`commit_completed:true`; inspect the exact target before retrying.

Original decompiled C evidence, API safety subset and empirical tests are separate
claims. Tests use real provided BJTU current archives plus explicitly identified
boundary fixtures and upstream python-typedstream as an independent reader, not
the OpenTrack application. Preserve C hashes and original provenance/license files.
Do not turn 17 scalar pairs or four endpoints into whole-feature/176-item completion.
See `contracts/wave6-scalar-archive.md` for field locations and source-function IDs.
