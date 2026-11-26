# Paired OpenTrack saved-data backend

This is the backend source bundled with the maintained
**opentrack-network-rail** Skill,
protocol `0.33.1-zeroaccept1-v4`, Python **3.13.x**. The product entrypoint is
[the enclosing Skill](../../SKILL.md); [capability scope](../../references/scope-audit.md)
and actual tool discovery determine which public operations are available.

The maintained edition exposes the implemented tool set; its convenience
generators and tested examples do not define all permitted railway designs.
Compose those tools around the user's operating requirements. Each original
function does not need its own one-to-one solver.

## Registered does not mean an enabled writer

The current `all` profile registers the maintained interface set, including
**eight quarantined legacy writers**. The quarantine returns
`LEGACY_GEOMETRY_DISABLED` even with full-software authorization:

`opentrack_create_project`, `opentrack_generate_operations`,
`opentrack_stage_changes`, `opentrack_start_editor`, `opentrack_edit_editor`,
`opentrack_publish_draft`, `opentrack_apply_draft`, `opentrack_create_demo_line`

Their old blank-project/editor/draft/batch examples are not executable current
workflows. Do not invoke underlying legacy functions or change the guard to
resume that same pipeline. Bounded `current_archive` APIs are not affected by
this legacy quarantine, but each still needs its actual schema, host, source,
authorization and save prerequisites. Registration counts are not counts of
ready operations, and not every remaining tool is unconditionally runnable.

## Authorization and execution layers

Before railway business, require the user's explicit confirmation of a valid,
legitimate FULL original OpenTrack software entitlement covering the current
use, plus permission for the task/data. Follow [software authorization](../../references/software-authorization.md).
The backend fails closed on business calls without the scoped user attestation;
that record is not vendor activation verification. Do not infer entitlement
from an executable, a saved file or an original save-guard return value.

The backend's archive handlers inspect or construct native saved data; they do
not implement OpenTrack's dynamic engine and do not start its GUI themselves.
This handler boundary is not a prohibition on a separately authorized original
GUI/native workflow or user-guided operation. No original EXE, vendor runtime,
private donor archives or software licence material is included.

## Use the current paired entrypoints

Use `<SKILL>/scripts/ot.py` or `<SKILL>/backend/OTAI/server.py`, replacing the
placeholders with actual paths. The source package no longer contains a nested
`backend/OTAI/skills/opentrack-rail` installation. Read [installation](INSTALL-REBUILD.md).

The `--root` argument and `OTAI_DATA_ROOT` select the actual data root.
`OTAI_ROOT`, when set, names the parent containing the selected `OTAI/server.py`;
it does not select data. A mismatching backend version, profile or
authorization-gate contract must fail instead of falling back to another installation.

`tools` reports registered interfaces, not native-function completeness.
`opentrack_capabilities` reports current operation/host and authorization scope;
its unconfirmed response is metadata only. File IO/publication capabilities are
operation-specific, so a historical POSIX-only publisher does not make every
Windows operation unavailable, and one Windows publisher does not enable all writers.

The `ai` profile exposes the semantic requirement/capability/plan/outcome tools,
`opentrack_validate_reality_station_plan`, and a minimal inspection set. It does
not expose arbitrary archive mutation. The compiler emits a hash-bound
dependency plan and assertion matrix. Apply audits results from explicitly
selected reviewed tools and does not dispatch nested tools. Concrete writes
still use `generation` or `all` after their exact schemas and source bindings
have been inspected. Planning, preview and profile discovery are not native
acceptance.

## Data contracts and verification

Use the selected tool's complete schema. A linear initializer, a yard template
and a grid template have separate contracts; their station counts and geometry
are not overall design limits. Fresh publishers remain no-replace; existing
project edits keep the selected paths and follow an explicit current-file workflow.

New graphic placements use `alignment_x/alignment_y`, never width/height aliases.
New Stations may use `(0,0)`; new Signals must match their actual owner End and
must not use `(0,0)`. Existing faithful inspection/clones preserve source values.

[Current acceptance levels](../../references/acceptance-levels.md) separate generation,
publication, original loading, Save/reload, actual running and native export.
Case counts, names, distances, refresh actions and warning totals apply to the
recorded case. They are not requirements for a different project. All new native
names, paths and UI text use printable English/ASCII as required by this workflow.

[Contract scope](contracts/README.md) explains shared modules versus public tools.
[Maintenance history](REBUILD_STATUS.md) and `docs/` retain frozen development
records; their old candidate status or integration blockers are not current
product-wide restrictions. Check the current code/schema before reusing them.
