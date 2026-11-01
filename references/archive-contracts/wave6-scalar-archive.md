# Wave6 current stock archive contract

This contract describes the bounded scalar, Engine-curve and Train-template
interfaces. Live registered schemas and integration test artifacts determine what
is callable/tested; documentation alone is not proof of endpoint completion.
Original C means authorized Ghidra decompilation, not recovered vendor source.

## Public interface and transaction boundary

| Tool | Required operation arguments | Result / mutation |
|---|---|---|
| `opentrack_inspect_current_stock_fields` | `source_path`, `kind`, `name`, distinct nonempty `fields` | Saved raw getter values and inspected source identity/hash; no write |
| `opentrack_edit_current_stock_fields` | `source:{path,sha256}`, `kind`, `name`, nonempty `changes` dictionary | One selected object's batch, no partial field publication |
| `opentrack_edit_current_engine_curve` | `source`, `engine_name`, existing `diagram_index`, exactly one `content`/`points`, `mode` replace/append | Selected existing diagram point change plus reviewed Engine extrema update |
| `opentrack_clone_current_train` | `source`, `project_run`, `depot` (each path+SHA), `template_name`, `new_name` | One additional same-formation Train in a fresh trains archive |

The three mutation endpoints default `preview_only=true`. Explicit commit uses
`preview_only=false` and a fresh `target_path`; the shared `Next.finish` boundary
owns permitted-path checks, source/dependency hash rechecks, no-replace atomic
publication and saved-byte fresh reload. Pure modules take immutable bytes and
return bytes/receipt; they do not independently provide filesystem atomicity.
Failures before publication cannot partially change source files. A postcommit
error with `commit_completed:true` is not a reason to blindly retry an overwrite.

No GUI, native executable, simulation, legacy graph fallback or migrations are
required. No user's local Codex invocation is authorized by this operation.

## Exact scalar allowlist and original-function mapping

Group/slot are zero-based current archive field locations. `i` is signed int32;
`f` is binary32. Setter/getter IDs are original function addresses.

| Class/version | Field | Group.slot/type | Setter | Getter |
|---|---|---|---|---|
| OTTrain16 | trainType | 1.0 i | 006bb378 | 006bb184 |
| OTTrain16 | avgDeceleration | 1.2 f | 006c13f4 | 006c1404 |
| OTTrain16 | maxDrawbarForce_kN | 14.0 f | 006c1478 | 006c142c |
| OTTrain16 | decelerationUsedFormula | 12.0 i | 006c167c | 006c1670 |
| OTTrain16 | brakedWeightPercentage | 12.1 f | 006c1744 | 006c1738 |
| OTTrain16 | decelerationFunctionParameterC1 | 13.0 f | 006c1760 | 006c1754 |
| OTTrain16 | decelerationFunctionParameterC2 | 13.1 f | 006c177c | 006c1770 |
| OTTrain16 | brakingDelayType | 17.0 i | 006c1d30 | 006c1d24 |
| OTTrain16 | startingRollingResistanceOffsetSpeed_kmh | 21.1 f | 006c15cc | 006c15c0 |
| OTTrain16 | startingRollingResistanceFactor_Nt | 21.2 f | 006c160c | 006c1600 |
| OTEngine2 | resistFactor | 4.0 f | 004cbd90 | 004cb444 |
| OTEngine2 | adhesion | 5.0 i | 004cbdd0 | 004cb478 |
| OTTrainCategory19 | dispatchingType | 11.0 i | 006c429c | 006c4290 |
| OTTrainCategory19 | timingStationsType | 16.0 i | 006c4458 | 006c444c |
| OTTrainCategory19 | initialDelayDistributionFunction | 9.0 i | 006c44e0 | 006c44d4 |
| OTTrainCategory19 | trackNameCreationType | 23.0 i | 006c4590 | 006c4584 |
| OTTrainCategory19 | delayAddType | 19.0 i | 006c48c0 | 006c48b4 |

Train coder: 006c2dbc. Engine coder: 004ccc54, including inherited Vehicle coder
006df470. Category coder: 006c513c. Category C DAT type pointers have not been
resolved to source literals; actual current fixture encodings corroborate layouts.
Original setters return void after assignment; getters return the stored scalar.
The archive wrapper's bytes/receipt are additional API output, not original return ABI.

### Original C domain versus safe API and tested points

- Native integer setters assign signed-int32 without business-enum validation.
  API accepts exact integers [-2147483648,2147483647], not bool, float or coercion.
- Native float setters assign binary32 without the API's finite restriction.
  API accepts finite exact numeric input representable after binary32 rounding;
  overflow/NaN/Infinity reject. Signed zero, subnormal rounding and underflow to
  zero are supported. No physical sign/range clamp is invented.
- Existing nonfinite archive values use strict-JSON native-bit tags on read and
  in before-values; the original bits are preserved. The tags cannot be written
  back as numeric inputs. Reading a signaling NaN does not prove native setter
  semantics or runtime acceptance for it.
- Tests cover real BJTU records, each pair, same-object batches, integer limits,
  finite float limits, signed zero, subnormals, rounding, malformed inputs,
  unsupported layouts, nested/shared references and late-failure isolation.
  These are representative tests, not exhaustive original-domain execution.

Raw identifiers are not interpreted as business labels. Units are not inferred
from member suffixes. The separate original adhesion-method switch is not proven
to receive the saved adhesion member, so its labels are not offered. The three
correctedDeceleration/min/max fields remain excluded pending coupling review.

Strict current classes, ancestry, encodings and exact unique names are required.
Shared selected mutable objects/root/parent corridors are rejected. Nonselected
fields and reference aliases remain unchanged, verified by restoring selected
values and comparing the complete original graph, plus independent reader tests.

## Engine curves: bounded composite, not full UI import

Current Engine2 / OTDDiagram3 / OTDPoint0 (`iii`) only. Structured points require
exact int32, nonnegative speed, saved types 1/2. Text input follows the audited
ASCII parser: numeric-prefix conversion, H on the next source row, split by force
sign, first-speed-wins deduplication and sorting. API overflow rejection is a guard,
not a claim about native NSString overflow behavior. Reports expose conversion,
ignored/incomplete rows and duplicate handling.

Negative force goes to braking, nonnegative to traction. Replace clears selected
arrays before population; append retains existing winners. Existing point template
and non-nil arrays are required; empty replacement is allowed, but insertion into
an already empty diagram without a template is refused. No new Engine/diagram.
Selected ownership corridor must be exclusive; no hidden alias splitting.

`004cc798 setMaxPowerAndSpeed` scans all diagrams and updates only Engine group7
speedMax, group6 forceMax and group17 forceMin, with zero-initialized extrema.
Braking speed does not set speedMax. Group8 powerMax stays unchanged. Despite the
selector's name, no power formula is invented. Point insert 004cb684 and the
aggregate update are explicitly composed, not equated with a complete GUI action.

OTDDiagram coder 00472db8 does not save runtime force/brake/efficiency lookup caches;
00472944 initializes runtime arrays separately. The API does not fabricate those
caches or UI autoscaling. Axes, color, adhesion, supply, loss and caption remain
unchanged. Module tests include real BJTU Re 460/diagram0, append/replace/empty,
int32 boundaries, multi-diagram extrema and independent-reader preservation.

## Train same-formation template factory

Current TrainList3 internal format17, explicit existing Train16 template and fresh
name only. Name is nonblank, control-free and <=200 UTF-8 bytes (API limit, not native
limit). Positions must be complete unique 1..N; 1..1024 records. No implicit template,
replacement, changed composition, Category creation, or derived-physics recalculation.

Integrator must bind the supplied trains/depot to the actual run's unique
**TrainFile / DepotFile** entries, not a guessed EngineFile key or directory match.
Hash-check run and both catalogs before/after preparation/publication. EngineRef names
resolve in the supplied Engine2 depot; Category name resolves in the same TrainList.
The bytes-only factory itself cannot establish project identity. A saved copy is
not automatically substituted in the source run; later operations requiring project
binding must use a legitimate run binding to the new copy.

Clone Train-owned mutable arrays, deceleration wrapper/points, EngineRefs and
trailers, retaining immutable name/reference semantics. Original aliases are
unchanged, including real BJTU's shared EngineRef across its two original Trains.
Category remains a name reference, not a deep-copied external Category entity.
All archived Train scalar groups inherit unchanged; only the requested name differs.

TrainList encoder 006d99d8 writes 0x11, Categories, conflict Categories, then
OTMutableArray embedded array (00528500); actual root g3 is the Train array.
Append updates its count and adds one object without resetting unknown state.
Name lookup 006d82fc linearly scans count/objectAtIndex; no archived index is invented.
Original `copyWithZone:` 006ba9c4 calls init and selected setters, copies brake/trailer
children but adds EngineRefs from an array. This factory intentionally isolates
EngineRefs and retains all archived scalars: **not original copy/init equivalence**.

Real BJTU tests append 2→3, write a copy and independently reload it, compare the
entire original graph/aliases after removing the new record, and mutate cloned
children to demonstrate isolation. A separate current native-shapes Trailer3 case
covers trailer isolation. Those are archive tests, not original application launch.

## Evidence, provenance and coverage

Retain original C and per-file SHA manifests, native fixture provenance and all
codec/test-oracle license files in the package. Runtime writer is the independent
stdlib codec; upstream python-typedstream 0.1.0 is the separately licensed test
oracle. Do not describe provided BJTU or sanitized native-shapes fixtures as newly
application-produced files. No denied provider acquisition or unknown binary is used.

17 scalar pairs, curve composition and template creation are bounded contributions.
Do not inflate frozen 1412-function/176-parent denominators or mark entire parents
complete from registration, codec round-trips or this document alone. Integration
and persisted MCP/Skill tests must supply their own evidence beyond module tests.
