# OpenTrack paired saved-data backend

The package entrypoint is [SKILL.md](../../SKILL.md); current capability boundaries
are in [operation scope](../../references/operation-scope.md). Backend protocol
`0.33.1-zeroaccept1` requires Python **3.13.x**. These compatibility values are
needed to select the actual executable interface and native data format.

Use the discovered tool schema and availability status for each task. Convenience
generators and tested layouts are examples, not global railway-design rules.

## Authorization and execution layers

Business operations require the user's explicit confirmation of a valid,
legitimate FULL original OpenTrack software entitlement covering the current
use, plus task/data permission. Follow [software authorization](../../references/software-authorization.md).
The local attestation is not vendor activation verification. Do not infer it
from possession of an executable, successful saving or an original save guard.

Saved-data handlers inspect or construct native OpenTrack files; they do not
reimplement its dynamic engine or automatically start its GUI. In code,
`archive` means a native saved-data format, not a collection of release history.
No original commercial EXE, runtime, private donor or licence material is included.

## Registered tools and availability

Registration is not an availability or native-acceptance claim. The legacy
whole-project geometry pipeline remains quarantined with
`LEGACY_GEOMETRY_DISABLED`; authorization or compatibility flags do not remove
that protection. Do not call an internal function or another backend to bypass
a public restriction. Current typed file operations and fresh initializers have
their own source, schema, filesystem and save prerequisites.

## Paths and contracts

Use `<SKILL>/scripts/ot.py` or `<SKILL>/backend/OTAI/server.py`. There is no nested
Skill under `backend/OTAI/skills` to install. Read [installation](INSTALL-REBUILD.md).
`--root` or `OTAI_DATA_ROOT` selects the real data root. `OTAI_ROOT`, if explicitly
set, is the parent containing `OTAI/server.py`; it is not a data-root alias.
Missing mandatory contracts or incompatible protocols must fail rather than
silently choosing another local installation.

The current schema governs inputs. Match dependencies to the actual operation;
do not require six project catalogs or six donors for a single-file inspection.
Fresh-only publishers do not overwrite existing projects. Current-project edits
preserve selected paths and require before-state, reviewed differences and disk readback.

New placements use `alignment_x/alignment_y`, never width/height aliases. Stations
may use `(0,0)`; new Signals must match the actual owner End and cannot use `(0,0)`.
Faithful existing-object inspection and cloning preserve their source values.

See [acceptance](../../references/acceptance-levels.md) for the distinct evidence required for
file publication, original loading, Save/reload and actual simulation. Case
names, counts, distances and refresh actions are not mandatory values elsewhere.
Use printable English/ASCII for new text, names and paths inside original OpenTrack.
