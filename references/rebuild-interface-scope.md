# Rebuilt saved-data interfaces

This development assembly combines the intact v11 package with selected recovered
source modules and explicitly new integration code. It is not a byte-identical
recovery of an unpublished historical candidate.

## Selecting a workflow

For this user's multi-station projects, prefer one station per topology document;
read [station document layout](station-document-layout.md) before generation.
On Windows, retained-handle complete inventory enumeration now supports the
existing multi-document inspect/derive, A/B and line-chain preview workflows.
`opentrack_preview_finite_explicit_topology` remains a point-station/track/connector
preview. Use [station document initialization](station-documents-project.md) and
`opentrack_initialize_station_documents_project` to preview or publish a bounded
forward final-stop operating chain, one station per document and N+7 members.

Discover exact schemas and availability using `ot.py tools`; BLOCKED descriptions
and `LEGACY_GEOMETRY_DISABLED` take precedence over old interface examples.
Eight registered legacy create/editor/stage/generate/publish writers are
quarantined pending saved-field audit, not available after a dependency install.
Current-archive contracts and supported bounded initializers remain separate.
The same registry powers its CLI and MCP tools. Explicit standalone profile
CLIs are distinct entrypoints, not hidden matching MCP commands. Pass a UTF-8
request file for large JSON using `--args-file`.

- Multi-document: inspect exact project inventories, validate connector closure,
  preview new Path/Itinerary objects or a bounded A/B topology.
- New operating station chain: preview or publish N single-station documents,
  six common catalogs and one `.run`; then separately perform native acceptance.
- Legacy grid-decomposition preview: the particular 25-document/eight-template
  preview described by its own schema, with geometrically separated crossings
  rather than interchange junctions. It is not the definition of a railway
  grid design, nor the later turning-yard profile. For a current custom network,
  begin with [requirement-led design](complex-design-workflow.md) and select the
  matching actually discovered interfaces; the [nine-station example](grid-station-yard.md)
  is another convenience profile, not a global replacement rule.
- Operational data: preview bounded mixed consists, multi-station timetables,
  reciprocal shunting connections and spatial splitting from explicit templates.
- Signals/protection: inspect and preview verified stored fields and associations.
- Incidents/sets: preserve native shared-object membership and bound target records.
- Preflight/run review: validate a stated subset of run-file/catalog references;
  native runtime success is never inferred from static validation.
- Results: parse supported result formats as supplied data, without inferring that
  a current simulation produced them.

## Persistence boundary

The older multi-document and other preview tools described here reject
`preview_only=false`. Hashes and counts in their receipts describe in-memory
candidate bytes, not delivered files. The separate winrelease1
`opentrack_initialize_project` publisher saves a bounded **single-document**
eight-member project on Windows x64 local NTFS. The winmulti1
`opentrack_initialize_station_documents_project` is a separate N+7 publisher for
the documented one-station-per-document forward final-stop chain. Neither a
publisher nor a connector/static-path validation certifies native boundary
crossings or complete simulated operation.
Separate native acceptance has now passed for the winmulti1 three-document
REL_A/REL_B/REL_C forward journey, with original per-document departure/pass/
arrival events and a physical final stop. See the bounded result in
[station document project](station-documents-project.md); other interfaces and
the full 176 requirements do not inherit that completion status.

## Completion evidence

Use the current tool schemas, explicit source SHA bindings and fresh-data test
receipts. Do not reuse historical test counts as tests of this rebuilt assembly.
A schema listing only proves discovery. A core round-trip proves the tested data
case, not every native parameter combination. Original 176 requirements retain
their identity; a separate implementation matrix describes bounded interfaces.

## Coverage metadata without legacy archive dependencies

Use `opentrack_get_function_coverage` with `scope="packaged"` and one of
`section="summary"`, `"saved_data"`, `"interfaces"`, or `"requirements"`.
The default auto source uses the packaged summary when no legacy audit exists.
Rows support pagination and explicit filters. Retained v11 saved-function evidence
is labelled historical; reading it does not re-certify that behavior in this build.

`scope="legacy"` and native/python/enhancement sections still require their real
fingerprinted audit files. Missing legacy reports are reported as unavailable;
they are never replaced with guessed native counts. Read tools do not regenerate
reports. Build-time revision refresh is an explicit maintainer operation.

## Additional dev1 data domains

`opentrack_preview_finite_explicit_itinerary` admits a finite ordered list of simple
Path references, including repeats only when every boundary is continuous. It
neither changes default Project validation nor generates an infinite operating loop.

`opentrack_preview_current_shunting` supports `inspect_inventory` for known original
layouts. Reported `editable=false` does not authorize migration or edits. Binding
Overlap defaults to `route_terminal`; `same_document_explicit` must be selected
explicitly and still requires a uniquely resolved local Shunting and no conservative
re-entry conflict. No cross-document or recursive Overlap capability is inferred.

Run review treats Incident records as event names. Auxiliary diagram and set checks
are static saved-reference checks. A document set in exported preferences is not
proof that the script runner activated it.

## dev2 explicit data operations

- `opentrack_preview_finite_explicit_topology`: explicit bounded documents, double vertices, edges, point stations, paired connectors. No routes or operational traffic; geometric crossing is not connectivity.
- `opentrack_preview_rename_train_references`: complete single-run selected inventory; rename one Train16 and every exact Course11 reverse reference. Unknown same-name uses or extra unbound files are refused. No export.
- `opentrack_preview_current_shunting` action `update_parameters`: supported existing local layouts; only speed and two timing scalars. No guessed ID repair, geometry changes, cross-document or recursive behavior.
- `opentrack_get_function_coverage` with `section="requirements", operation="read|generate|modify|export"` filters the corresponding operation's status rather than old whole-requirement status. Missing assessment is not unsupported; tests of bounded examples do not establish full original feature parity.
