# Wave7 saved-data scope

Baseline: frozen wave6 Library MCP v5, SHA256
ca6b34bd61c44107682abe6287770f8f13da327aa590bcfbde62346430c5b893.

## Edge scalar operations

Existing current OTDocument4 / Edge3 selected by unique global modelID. Length
is signed int32 metres, radius finite binary32 metres, gradient finite binary32
per mille. Typed keys length_m/radius_m/gradient_per_mille map exactly to candidate
length_m/radius_raw/gradient_raw, no conversion. Units use current C/manual,
nonzero gradient corroboration is read-only legacy-container evidence, not a
migration gate. Negative/zero values reflect setter domain, not useful geometry.
Original float setters permit bit patterns the finite API refuses. Existing
unselected NaN payloads/negative zero and End/Route references are preserved.

## Named distributions, not Category tables

Named OTDistribution1 is CourseList3 group3. Only function code1 is business
editable (piecewise linear). Category code0 negative exponential/code1 linear is
separate. A name such as Uniform 30-50 is not a distribution enum.

Replace/edit/insert/delete interval row and explicit-template new/copy are bounded
API operations. New requires existing named template, explicit OTDistribution:1,
unique ASCII name and all rows; no-template empty library creation is rejected.
No init defaults are guessed, and composition is not original init/copy completion.

policy is mandatory: native_setter allows finite floats outside table-domain
bounds and reports invalid guard; piecewise_linear_guard requires nonnegative,
ordered nonoverlap and total100 within explicitly computed binary32 tolerance.
No normalization, sampling or runtime validity is claimed. Unselected raw payloads
are retained and nonfinite values are strict JSON null/classification/bits.

Real04 named fixtures have CourseList3 internal markers15/16 and Incident9/10.
Those unrelated records are opaque-preserved, not migrated; only named current
schema is edited. This is NOT whole-file current-format certification. Shared
mutable owners and object/container cycles are rejected before copy-on-write.

## Read-only references

Exact run bytes/SHA bind supplied courses/timetable actual paths in one named
project. Timetable9 distributionName and Incident12 three fields are audited;
unknown consumer versions, missing catalogs or closure remain explicit boundaries.
No arbitrary equal strings are treated as references. Rename and whole-distribution
delete remain blocked. A read-only dependency receipt is not write authorization.

## Five run keys

Start Day Offset, Start Time, Stop Day Offset, Stop Time and Step are exact ASCII
strings; Step is physical simulation seconds, not Time Ratio. Native C domain,
stricter API canonical syntax/day/float safety guards and tests are separate.
All non-selected bytes (paths, comments, document lists, other keys) stay exact.
The .run bytes are NOT typedstream: separate exact parser/fresh validation uses
the unchanged fd-secure publisher through an optional validation callback.
Five-key editing does not execute, configure a full runnable project or validate a
simulation. No paths are edited and no multi-file publication is implied.

## Publication and evidence

Every write requires source SHA; default preview performs source recheck and
fresh private decode/parse without publication. Explicit fresh target uses shared
atomic no-replace transaction, same input pre/post checks and committed-error
receipt. Never retry a commit_completed error by overwriting the target.

Source hashes/decompiled C/fixtures are under artifacts/wave7-evidence. “Original
C” denotes audited Ghidra decompiler output, not recovered vendor source. Independent
pytypedstream reader verification is not OpenTrack application reload. GUI, old
compatibility, native engine, unknown selector dispatch, all 176-requirement completion and
multisource write closure are not claimed.
