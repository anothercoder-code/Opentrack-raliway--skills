# Install the paired source backend

Use the enclosing **opentrack-rail** folder as the Skill installation. It contains
`SKILL.md`, `scripts/` and this `backend/OTAI` directory. It is an intact source
layout, not a verified standalone wheel and not the commercial application.

Read [the Skill installation guide](../../references/local-installation.md)
and [software authorization](../../references/software-authorization.md). The
maintained distribution requires the valid full original-software entitlement
confirmed by the user before business operations. Installing this package grants no licence.

## Runtime and paths

Use Python **3.13.x** and this directory's `requirements.txt`. The following are
command forms; replace every placeholder with an actual authorized path:

```text
python -X utf8 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> tools
python -X utf8 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_capabilities --json "{}"
python -X utf8 -B <SKILL>/backend/OTAI/server.py --root <DATA_ROOT> --profile generation stdio
```

There is no nested `backend/OTAI/skills/opentrack-rail` folder to install or run.
The paired bridge finds its bundled backend. `OTAI_ROOT` is an explicit backend
parent override; `--root` or `OTAI_DATA_ROOT` is the business-data root. A missing
mandatory runtime or authorization contract must fail, not switch to an older backend.
Use `scripts/license_authorization.py --help` for the actual confirmation-record
commands; never create a user confirmation without the user's explicit statement.

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

## Available operations

The maintained edition exposes the implemented tool set; its convenience
generators and tested examples do not define all permitted railway designs.
Compose those tools around the user's operating requirements. Each original
function does not need its own one-to-one solver.

Discover the selected profile's tools and read the actual schema. A shared raw
contract does not make a tool public in every profile. Registration counts are
neither original-feature completion nor GUI acceptance. Business calls in CLI,
MCP and HTTP share scope and authorization checks.

Reads and publication are host/operation-specific. Use the reported filesystem
capabilities; current supported Windows archive operations require the reviewed
native x64 fixed-local-NTFS implementation. This does not turn the retained
Linux incremental catalog publisher into a Windows writer. Do not weaken source
SHA, path, no-follow, no-replace or post-commit reconciliation rules.

Fresh project creation validates execution and document bindings against its
actual target and re-reads committed bytes. Existing-project changes use their
own supported update/original Save path; a fresh-only initializer cannot overwrite
an existing project. Preview bytes or `saved=false` are not delivered files.

Native execution belongs to the original software. Agent-operated or user-guided
loading, saving, reloading and simulation must be separately authorized and
evidenced for the current project. Historical Open→Cancel/Ctrl+5 actions, ZF
names, 3.2km, 08:12 and output counts describe that case, not new-project inputs.
See [acceptance scope](../../references/acceptance-levels.md).

The optional Inspector guard is source-only and lacks
native runtime acceptance. This package does not install/start a guard or replace
the original EXE. Tests needing private fixtures and old static/dev reports
remain historical evidence; missing fixtures do not prove every current operation
is blocked, and an old test pass does not certify a new operation.
