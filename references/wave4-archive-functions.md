# Current Engine / Category / Itinerary saved-data operations

These handlers work on explicitly authorized saved archives under the configured data root. They do not require GUI/native simulation, old-version conversion or guessed defaults. This handler scope does not prohibit a local agent or separately authorized original-application operation.

## Engine physics fields
`opentrack_edit_current_engine_physics` requires `source:{path,sha256}`, exact
`engine_name`, `changes`, and optional fresh `target_path`. `preview_only` defaults
true. Changes: `adhesion_load`, `force_max_kn`, `force_min_kn`, each exact signed
int32. Native setters allow negative values/extremes; physically meaningful values
are a separate question. Forces are saved kN; adhesion is raw native mass integer,
not a validated mass-unit conversion. Adhesion zero clears the **first** diagram's
display flag, unless nil/empty. Nonzero does not restore it. Shared mutated objects
or ownership corridor reject; no copy-on-write, total-load correction, curve or
cache recomputation. `diagram_side_effect` identifies the extra changed cell.

## Category dwell
Inspect `opentrack_inspect_current_category_dwell` with `source_path` and exact
`category_name`. Use returned SHA in `opentrack_edit_current_category_dwell`.
Seven changes: `stop_at_every_station_time_s`, `dwell_variation_early`,
`dwell_variation_delayed`, `dwell_variation_early_unit_code`,
`dwell_variation_delayed_unit_code`, `dwell_variation_early_delay_offset_s`,
`dwell_variation_delayed_delay_offset_s`. Omitted values stay untouched; explicit
null is invalid. Five floats round once to finite binary32; bool, NaN, infinity
and overflow reject. Existing nonfinite stored values are reported as explicit
JSON-safe labels with binary32 width and exact bits, not silently zero/null. They
may be preserved or replaced by an allowed finite setter input; no native NaN
setter semantics are claimed. Stop time clamps negatives to +0 but preserves -0. Direct
variations preserve signed values/-0. Early offset clamps to <= -1; delayed offset
to >= +1. Unit codes are signed int32; unknown codes remain raw and their label is
null, never guessed. Readback is actual saved value, not setter normalization.
Use `float32_bits_le` to verify negative zero (`00000080`). No random dwell,
effective schedule, dispatch or simulation state is generated.

## Itinerary template composition
`opentrack_create_current_itinerary` accepts exact current `project_run`, every
`documents:{name:{path,sha256}}`, associated `catalog:{path,sha256}`, explicit
`document_paths:{name:original_saved_catalog_filename}`, `owner_document`, `name`,
`template_name`, exactly one `path_refs:[{name,array_id,start_id}]`, and optional
`description`. The existing local Path must resolve to connected nonrepeating
local Routes. Template must be a named same-document current Itinerary with empty
margins and a matching catalog row. This is **not** native init/copy equivalence.
New Itinerary retains verified unnumbered IDs [-1,-1]; first Path identity is shared
with its existing owner and ordered path infos are stored in both outputs.

A caller completeness boolean is not evidence: run lists, actual project archive
inventory and external document references must all match. Explicit saved catalog
filename mapping is checked against all existing rows, not inferred from the host
filesystem. Every source hash is rechecked. Save requires `preview_only:false` and
fresh `target_directory` outside the input project. Both changed native archives
commit together as one no-replace directory with a manifest. This is an increment,
not a relocated project; sources and saved document paths remain unchanged. Do not
claim that the original project automatically uses these new files. A postcommit
error with `commit_completed:true` means inspect that target, never overwrite or
blindly retry assuming no files were written.

After save, inspect the new native files in a fresh process; compare hashes, exact
changed fields, object-reference identity and dual document/catalog consistency.
Independent upstream pytypedstream readback validates saved archive structure,
not an OpenTrack application/simulator run. Contracts separate original C domain,
conservative API guard domain and concretely tested instances.

## Local Path allocator correction
For `opentrack_transform_current_archive` action `create_local_path`, `array_id`
is now confirmation of `highestGivenRspID + 1`, not a freely chosen historical
unused ID. Native `0x4c7188` writes that same new ID back to the owning End's
counter. Preview reports before/after; int32 overflow or inconsistent high-water
state rejects. BJTU End19: 10003 -> new Path10004/counter10004. Existing saved
Path100 fixtures remain valid existing objects; they are not newly allocated.

To discover the expected fresh ID, make only a `preview_only:true` request. A wrong
expected ID returns structured `EXPECTED_FRESH_RSP_ID` with `expected_fresh_id`,
`highestGivenRspID` and the inspected `source_sha256`, explicitly no mutation. This
is a refusal, not a successful creation. Correct the expected ID, preview again,
and save only with the same expected source SHA to an explicit fresh target. If
the source changes, inspect/re-preview; do not guess an ID or bypass the hash lock.
