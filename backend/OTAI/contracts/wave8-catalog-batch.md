# Current catalog batch contract

Baseline: frozen wave7. Wave8 integrates the previously isolated current-only purebytes module without reviving legacy Project, graph, migrations or draft validator. Wave6/wave7 are unmodified.

## Entry

`catalog_batch.apply_batch(blobs, operations) -> (six_output_blobs, report)`.
`blobs` is exactly six immutable bytes: `depot,trains,courses,dest,stations,timetable`. Operations is a list of 1..100 flat dictionaries, maximum 10,000 total selected entities/rows. All parameters are strict and unknown/null values fail. Inputs are immutable; no output is returned on any early or late error. Source paths and expected SHA are intentionally not part of the purebytes layer.

- `{'kind':'update_engines','names':[exact names], 'cw_value':1.25, 'understands_radio':True}`. At least one field. cw finite numeric 0..100, bool prohibited; readback is native IEEE float32 rounding (e.g. 0.1), not decimal exactness. Radio strict bool. Names unique/nonempty. **Original batch API, not native C setter equivalence:** `setVehicleCwValue:` takes int32 and casts to float, whereas the audited batch directly writes a float. Archive flag bit 4 represents radio. No mass/force/speed/curve fields are exposed; associated guards are not bypassed because those operations cannot be requested.
- `{'kind':'update_courses','course_ids':[exact ids], 'acceleration_percent':90, 'delayed_acceleration_percent':85, 'comment':'text'}`. At least one field. Percentages strict int 50..100. Native C setters clamp to 50..100; this narrower API **rejects**, rather than clamps, out-of-domain inputs. They are acceleration and delayed acceleration, **not braking**. Comment retains original model printable ASCII, <=240 characters. Unspecified fields remain None and do not inherit active defaults.
- `{'kind':'shift_timetable_rows','course_ids':[exact ids], 'seconds':60, 'include_actual':False}`. Shifts planned arrival/departure for all existing rows of selected Courses. Signed int32 delta; signed int32 resulting absolute seconds; normalized day -366..366. Negative shifts allowed within domain. Nil and `HH:MM:SS` remain undefined, not midnight; undefined nonzero day is rejected. Midnight uses divmod day normalization. Actual fields are unchanged: `include_actual` may be omitted or false; **true is explicitly unsupported by this original planned-only method**. No interval propagation or run-window modification.

No rename/delete/create/reorder/binding changes, simulation caches or native-validity claims. No docs/corridors are loaded; unexpected context property access fails. Dest catalog references are real but infrastructure documents and their geometric connectivity are unvalidated.

## Genuine reuse and constructor adaptation

Original `OperationalData.update_courses` and six `TimetableOperations` methods remain AST-identical static source definitions, with small current-only context, strict arguments and validated native string/time helpers. Engine select/update planned-copy/replacement/diff is reused; update has one declared adaptation: deepcopy -> certified shallow node/group clone, preserving all untouched descendants and cross-owner references. Engine scalar/flag prefix and record projection are narrowed to the two exposed fields. No runtime exec/compile or permissive module stubs.

`verify_reuse.py` compares static ASTs and 48 source hashes. `source-fingerprints.json` includes original Python, certified codec/accessors/atomic publisher, decompiler C evidence. Decompiled C is evidence, not recovered original source. Two Course C sources are extracted from formal baseline `resources/function-bank.zip` into `evidence/`.

Old `TypedValue(b'*', bytes)` is not accepted silently: `codec_adapters.cstring_value(bytes)` explicitly constructs `CString(SharedString(bytes))`, with strict NUL-free bytes validation and encode/readback test. None of these three slices constructs systems/diagrams, so the adapter is not injected into unreachable operations and unsupported factories are not exposed.

## Validation and graph preservation

Strict current shape/class/inheritance accessors; actual Engine->Train->Course, Course->Itinerary, Timetable owner/station, contiguous index/last-index, interval existence/station/cycle, Connection current6/owner/target/station checks. Shifted schedules require chronological planned times and saved dwell compliance. No unbound connection publication shortcut.

Every graph is traversed through certified `reference_inventory`, including all supported inline arrays/structs/groups, rather than only the first occurrence. Shared selected entities, root reentry and mutable Course-array aliases fail. Unchanged shared descendants may remain shared. A full deterministic graph/alias signature masks only selected slots; radio masking preserves every non-radio flag bit. Before/after and fresh-load signatures must match. Changed field values are separately fresh-load verified. Three unmodified catalogs retain exact input bytes. Other graph nodes and cross-references within edited catalogs retain exact structural identity topology and saved values (not byte-for-byte reserialization identity).

## Filesystem integration

The wave8 wrapper uses the existing `CourseBundles.publish_bundle`, not write a second atomic implementation: expected SHA and complete source preimages, fresh target under authorized OTProjects/OTAI/workspaces, staged strict decode, pre/post source rechecks, no-replace rename, source/symlink guards and cleanup before commit. `run_verification.py` demonstrates this exact layer using SHA-identical BJTU copies within this task's private OTProjects. A rerun intentionally refuses an existing output directory; select a fresh authorized target to rerun publication.

Publication is **catalog increment**, not a complete relocated or validated Project. Infrastructure/run/corridors are not loaded or modified. The wave8 wrapper registers this bounded operation. No GUI/native application acceptance is claimed.

## Wave8 integration addendum

The pure modules are now package-local under current_archive/catalog_batch_reuse,
and catalog_batch_tools.py exposes the bounded six-catalog transaction. The
original isolated helper had a bug allowing undefined planned time with nonzero
day despite the contract. The current helper explicitly checks strict day type,
range and zero undefined day before returning None; regression tests cover both
planned slots and nil/sentinel values. This is an explicit helper adaptation,
not a change to the six AST-preserved original timetable methods. No claim of
full Project validation or native simulation follows from the endpoint.
