# Current archive primitives: C domain / API guard / tested domain

All actions edit real current typedstream archive bytes. Default preview writes
nothing. Explicit fresh target plus preview_only=false publishes one file through
the existing fd-secure no-replace transaction. All input hashes (including Engine
catalog, run and other documents) are rechecked before and after publication.
A post-publication error has commit_completed=true: inspect the named target/hash;
do not overwrite, blindly retry, or claim rollback. Source archives never change.

## Timetable
Native string-copy setters do not parse clock text. Strict API accepts 00:00:00
through 23:59:59 or literal HH:MM:SS sentinel; raw permits valid Unicode or nil,
no embedded NUL, maximum 1 MiB UTF-8. Four day setters accept signed int32 without
native clamps; API rejects bool/coercion. Explicit actual_* keys only. These are
single-row primitives, not interval/controller propagation. Noncanonical unbound
interval offsets refuse because native decode would normalize unrelated fields.

## Formation
Native setPosInTrain writes signed int32 and does not reorder. engine_reference_index
is a zero-based array selector, never the position value. Native add appends and
its default is Engine-record count + Trailer-group count + 1. API contiguous policy
requires complete unique 1..N; explicit native policy preserves arbitrary signed
positions. No derived physical fields are recalculated. Remove shifts both Engine
and Trailer groups using position greater-than, not ordinal. Conservative shared
record/container guards are API policy, not native C preconditions.

## Path
Route append and Path flatten use native add/rebuild/persist semantics, but API
rejects self/overlap/cycles, cross-document continuations, unresolved identities,
ambiguous ownership and supplied Itinerary dependencies. Native original methods
do not contain all these guards. Persist one first Route plus complete saved infos;
fresh resolution checks the full ordered chain. No nested Path or simulated native
runtime. Project run paths must be canonical same-project ASCII records; supplied
keys are exact document filename stems. Directory inventory and all encountered
external labels are verified within the selected project; a caller true flag alone
cannot permit missing documents. Omitted outside-project archives are not claimed
known. Use a distinct output project/location if retaining prior derived archives
would conflict with the intentionally conservative inventory rule.

## Evidence
`artifacts/wave3/transport-verification.json` records actual production stdio writes
and Skill CLI write plus independent official reader checks. Derived formation and
local-Path fixtures are explicitly labeled; original fixtures remain unchanged.
Standalone module evidence further tests C boundaries and whole-graph invariants.
Neither original application execution nor simulation is performed or claimed.

Run parser provenance: supported ASCII key#value# subset is evidenced by the already supplied tests/fixtures/bjtu/run.template and prior archive.parse_run. Test test.run is derived by replacing template placeholders; it is not claimed to be a production-authored original run. Actual filesystem inventory plus run/supplied-list matching and external-reference closure establish the selected boundary. Unknown list formats and unresolved labels refuse.
