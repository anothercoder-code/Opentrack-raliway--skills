# Original rolling-stock maintenance

The stock English 1.7 executable and original saved records are the contract.
These operations edit isolated native archives. They do not invoke controllers,
launch OpenTrack, reproduce runtime caches or provide native simulation acceptance.

## Typed batch and persistence

`rolling_stock_operations` in `opentrack_generate_operations` is an ordered list
after definitions, Course lifecycle and timetable operations. The same tagged
operations are accepted by `opentrack_stage_changes` and the persistent editor.

| Kind | Selection | Behavior |
|---|---|---|
| `update_engines` | exact `names` | supplied Engine attributes; optional single-diagram curve edit |
| `update_formations` | exact `names` | supplied Train attributes, consist lists or braking data |
| `update_categories` | exact `names` | supplied priority/delay/performance attributes |
| `rename_engines`, `rename_formations`, `rename_categories` | `renames: [{name,new_name}]` | simultaneous identity changes and exact typed reference rebinding |
| `delete_engines`, `delete_formations`, `delete_categories` | exact `names` | dependency rejection, explicit replacement or explicit cascade |

Names retain the existing printable ASCII API boundary. Duplicate sources or
destinations, unknown records and collisions with an unselected name are errors.
Swaps are simultaneous. Descriptions and unrelated strings are not replaced.
An atomic batch supports 1000 definition/edit operations and 10000 rolling-stock
edit targets, including cascade selections. Course deletion keeps its separate
shared Course target budget. Failed staging does not change source files or
advance editor history.

## Partial fields

Fields and their individual bounds are reused from EngineSpec, FormationSpec
and CategorySpec. At least one update field is required. Omission preserves the
field; explicit null is rejected. Creation defaults are never applied as edits.
Cross-field checks use the resulting values, including adhesion/total mass,
driven/total axles, minimum/maximum force and category delay thresholds.

Scalar Engine edits preserve all saved diagrams, power, voltages, efficiency,
braking points and color. An explicit `traction_points` or `nominal_power_kw`
edit requires at most one existing diagram; it changes its force points,
axis bounds, description and derived power while retaining independent diagram
data. It rejects multi-diagram curve replacement rather than guessing which
voltage system to replace. A requested power proxy is explicitly uncalibrated.
Changed force must cover the preserved points, and the combined diagram extent
must cover a changed Engine speed; individual supply diagrams may be slower.
Whole diagram lists and selected diagram creation/editing/loss input are covered
by the later [Engine diagrams](engine-diagrams.md) contract.

Scalar formation edits preserve consist and braking formula/table. Supplied
`engines` or `trailers` replaces that list; the other list and its positions are
preserved. Automatic positions use free 1-based positions around preserved and
explicit units. Conflicts and shrinkage requiring omitted units to move are
errors. Exact Engines must exist. Supplied category names must already exist.
New trailers use the audited native v3 migration, as in formation creation.
Explicit braking data selects table formula 0 and writes native negative
deceleration. A preserved table must cover a changed consist.

Category edits preserve unknown flag bits, colors, omitted distributions and
later native fields. Supplied tables retain ordering, probability and enabled
distribution checks. Native layouts missing a requested scalar are rejected.
None of these commands automatically adjusts timetables or claims calibration;
distance, speed and consist changes still require operational review.

## Identity/reference contract

| Identity | Native definition | References maintained |
|---|---|---|
| Engine | OTEngine group 1 | OTTrainEngine group 0, preserving positions/count |
| Formation | OTTrain group 0 | OTCourse group 3 |
| Train Category | OTTrainCategory group 1 | OTTrain group 3; diagram hidden category names |

Original OTTrainList.renameCategoryWithName:to: (0x6d883c) calls
changeTrainCategoryNamesFrom:to: (0x6d8938), which rebinds Train category names.
OTTrainController.trainNameChangedFrom:to: (0x6d2da8) delegates the notification.
Train Category and Conflict Category arrays are independent namespaces. Conflict
Category names/colors/types are not Train-category references.

The corridor decoder reads hidden names into ivar 0x34 for versions >10
(0x4445f7..0x44464d); it is group 23 in saved v11-v13, whose lengths are
24/25/26 groups. Versions <=10 have no saved hidden list. Rename keeps list order
and does not reorder the category array or signal rules. Explicit replacement on
deletion maps hidden membership to the survivor and collapses duplicate names;
cascade deletion removes that membership.

## Deletion

Default `reference_policy: reject` reports dependencies. An explicit
`replacement` must exist in the same namespace and survive deletion. It rebinds
Engine references, Course train names or Train category names, preserving
dependent records and timetable rows. `replacement` and `cascade` are mutually
exclusive.

Explicit `reference_policy: cascade` deletes dependent formations and their
Courses/timetables through the audited Course lifecycle detach operation,
including interval, connection, Incident and diagram cleanup. The complete
dependency tree is retained in the change artifact. At least one Train Category
must remain, matching the original controller's minimum-category check.

Coasting rules use the category's zero-based array index: the original
OTSimCourse.handlePassedSignalsOfEndArray:head:handlePowerSignals: passes
indexOfTrainCategoryWithName: directly to coastingAtIndex: at 0x63c580..0x63c5a1.
Performance Cat. Signal has original type 50 (isPerformanceCategorySignal,
0x5d0e64); its performance array is category-specific. The corresponding ordinary
Performance Signal type 43 is distinct and its global data is preserved.
OTInspector.tableView:objectValueForTableColumn:row: passes the category table's
row index directly to performanceAtIndex: at 0x50b188..0x50b1aa after testing
isPerformanceCategorySignal.
Signal v8-v11 performance/coasting arrays are groups 14/15; v10-v11 append a
further group without shifting them. Deletion removes the selected category
indexes and retains surviving rule objects/order. Missing tail entries remain
missing, matching native indexed accessor defaults. Arrays exceeding the selected
category list and unaudited layouts are rejected. Renaming leaves indexes intact.

## Evidence and output

`OTAI/artifacts/research/stock-maintenance-layouts.txt` contains bounded original instruction
windows and explicit reference observations. The frozen original Schweiz.trains
anchors separate category namespaces. Existing original operational goldens
anchor scalar records. Regressions check retained data, references, errors,
native round trips, batch ordering and editor undo; they do not certify native
runtime behavior.

Generation emits full `rolling-stock-changes.json` and a compact response preview.
Nested long arrays are reduced to counted previews; full curves, dependencies
and cascade details remain in the artifact and draft manifest.
