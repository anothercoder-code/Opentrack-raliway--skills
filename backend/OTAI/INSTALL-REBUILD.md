# Install the paired backend

Install the enclosing `opentrack-rail` Skill folder, including `SKILL.md`,
`scripts/` and `backend/OTAI`. This source layout is not the commercial application
or a replacement simulator. Read [installation](../../references/local-installation.md) and
[software authorization](../../references/software-authorization.md). Installing
this package grants no OpenTrack licence.

Use Python **3.13.x** with the pinned `requirements.txt` dependencies in the same
interpreter. Replace placeholders with actual authorized paths:

```text
python -X utf8 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> tools
python -X utf8 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_capabilities --json "{}"
python -X utf8 -B <SKILL>/backend/OTAI/server.py --root <DATA_ROOT> stdio
```

`--root`/`OTAI_DATA_ROOT` select business data. `OTAI_ROOT` is an explicit backend
parent override. Required contracts, capability checks and authorization are
not unlocked by `--profile all`, installing old dependencies or switching to a
broader backend. Use `scripts/license_authorization.py --help` for the current
confirmation-record commands; never create a statement without the user's words.

Use the discovered tool schema and availability status for each task. Convenience
generators and tested layouts are examples, not global railway-design rules.

## Registered tools and availability

Registration is not an availability or native-acceptance claim. The legacy
whole-project geometry pipeline remains quarantined with
`LEGACY_GEOMETRY_DISABLED`; authorization or compatibility flags do not remove
that protection. Do not call an internal function or another backend to bypass
a public restriction. Current typed file operations and fresh initializers have
their own source, schema, filesystem and save prerequisites.

Read/publication support is host- and operation-specific. Use reported filesystem
capabilities. Windows operations rely on the reviewed x64 fixed-local-NTFS
implementation; that does not enable every other publisher on Windows. Preserve
SHA, path, no-follow, no-replace and post-commit reconciliation rules.

A saved=false preview is not a published file. Existing-project edits use a
supported current-file/original Save path and do not repeatedly create new projects.
Original loading, saving, true reload, simulation and drawing need their own
current evidence; historical scenarios do not certify new inputs. See
[acceptance](../../references/acceptance-levels.md). Optional source components do not establish
that the original app loaded them, and no helper is automatically started by installation.
