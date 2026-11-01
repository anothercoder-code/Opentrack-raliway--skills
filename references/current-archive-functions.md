# Current archive workflow and exact action scopes

Discover schemas each time a package changes. `generation` now includes the
current archive inspectors, function reader and guarded mutation tools. Every
source is a real file under configured `OTProjects` or `OTAI/workspaces`; filenames
in examples are illustrative, not permission to access a different computer.

## One-file mutations

Inspect a catalog for its exact `id` and `source_sha256`, or list saved route
objects for name plus signed IDs. Use `opentrack_patch_current_engine` for speed,
or `opentrack_transform_current_archive` with one typed `operation`:

| action | actual saved-data scope |
|---|---|
| patch_train | maximum_acceleration_mps2, braking_delay_s, braking_release_speed_kmh; finite binary32 setter domain, no invented physical feasibility constraint |
| patch_category | default_connection_time_s; departure_process_time_s (original finite negative clamp, preserve signed zero); departure_process_starts_at_departure_time (inverse saved integer) |
| clone_engine | explicit current template, fresh name, independent copied mutable graph; inherit unspecified fields, not native copyWithZone equivalence |
| set_description | exact OTRoute / OTPath / OTDest object; new NSString avoids mutating shared aliases; empty string clears |
| create_local_path | explicit existing local Route chain/name/expected fresh ID, no continuation; allocate highestGivenRspID+1 and write counter, save first Route plus ordered infos; historical ID reuse refused |

`preview_only` defaults to true. For save pass a fresh `target_path` and false.
The source hash is mandatory. The server writes a complete archive, atomically
publishes without replacement and decodes the actual target again. Existing and
symlink targets are not overwritten/followed. No automatic overwrite retry.
Review `change_report` and output SHA, then call the inspector on the target.
An `ARCHIVE_COMMITTED_POSTCHECK_FAILED` error with `commit_completed=true` means
the file was published before a later check failed; inspect its path/hash, do not
claim rollback or blindly retry. Published files are not deleted by error cleanup.

## Course + timetable catalog bundle

`opentrack_generate_current_course` needs five source catalog path/hash pairs:
courses, trains, dest, stations, timetable; plus an actual external Engine catalog
path/hash for Train reference validation. They must be in the same catalog folder.
Provide explicit `template_id`, fresh `course_id`, Train/Itinerary names and rows.
Each row selects an existing `template_key` and explicit station/planned times/day
offsets. Undefined time is null with zero day offset; at least one planned time
is required. Connection-bearing templates and replacement of existing rows are
unsupported. Actual-result strings reset; each new row gets its own empty
connection array. Unset interval references normalize offset zero as in the
original decoder. Omitted optional fields inherit the reviewed current template.

Preview reports count deltas, file hashes and dependency manifest. Save requires
an explicit fresh `target_directory`. Five archives plus manifest are staged,
flushed and decoded; all six inputs are hash-rechecked before one Linux
`renameat2(RENAME_NOREPLACE)` directory commit. Unsupported atomic API/filesystem
fails closed. If `BUNDLE_COMMITTED_POSTCHECK_FAILED` is returned with
`commit_completed=true`, the whole directory was already published but a later
check failed; inspect its hashes rather than claiming rollback or retrying an
overwrite. This is **not a complete relocated Project**: no .run file, external
Engine archive or infrastructure document is included or automatically rebased.
Null document hashes mean not loaded—not validated. Retain the manifest and use
an explicit subsequent integration step to put these catalogs into a full Project.

## Evidence and domains

Companion MCP contracts:
- `contracts/current-archive-engine-speed.md`: Engine setter/getters/coder,
  integer km/h unit proof and API safety-domain distinction.
- `contracts/current-stock-functions.md`: six setter addresses/types/normalization,
  signed-zero behavior and explicit-template clone.
- `contracts/current-path-functions.md`: description functions and bounded Path
  composition, object/array ownership, local ID/name restrictions.
- `contracts/current-course-factories.md`: explicit Course11/Timetable9 composition,
  every supplied/inherited field, time/reference checks and unsupported cases.

Runtime code uses a new independent serializer. The original function bank is
hash verified. Fresh files were independently read by the official reader in
server tests. No original GUI/runtime launch is needed for these archive-function
gates; no such launch or actual traffic correctness is claimed.
