# Portable paired installation

This is the maintained distribution dated 2026-11-26. It uses paired backend
protocol **0.33.1-zeroaccept1-v4**, Python **3.13.x**, and the pinned
dependencies in the packaged `backend/OTAI/requirements.txt`.
This archive is named `opentrack-network-rail` and is the only maintained
OpenTrack railway Skill distribution.

## Install a release ZIP

The Skill's frontmatter name and discovery directory are both
`opentrack-network-rail`. A source checkout may keep a development directory
name such as `railnet-studio-advanced-hakimi`, but the installed directory must
be named `opentrack-network-rail`.

In PowerShell, use an explicit destination. `$env:CODEX_HOME` normally defaults
to `$HOME\.codex`.

```powershell
$release = 'D:\Downloads\opentrack-network-rail-release.zip'
$sidecar = "$release.sha256"
$expectedLine = (Get-Content -LiteralPath $sidecar -TotalCount 1).Trim()
$expected = ($expectedLine -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $release -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "Release SHA-256 mismatch" }

$extract = Join-Path $env:TEMP 'opentrack-network-rail-extract'
New-Item -ItemType Directory -Path $extract | Out-Null
Expand-Archive -LiteralPath $release -DestinationPath $extract

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$skills = Join-Path $codexHome 'skills'
New-Item -ItemType Directory -Path $skills -Force | Out-Null
$target = Join-Path $skills 'opentrack-network-rail'
if (Test-Path -LiteralPath $target) {
  $rollback = "$target.before-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
  Move-Item -LiteralPath $target -Destination $rollback
}
Move-Item -LiteralPath (Join-Path $extract 'opentrack-network-rail') -Destination $target
```

After extraction and installation, restart Codex so Skill discovery rereads the
directory. Keep the rollback directory until the installed package has been
smoke-tested. Do not copy development caches, `.git`, `__pycache__`, `.pyc`,
EXE or DLL files into the installed directory.

For a source checkout that has already been validated for release, use
`scripts/package_release.py` to create the clean ZIP with its manifest and SHA
sidecar, then install from that ZIP. Avoid maintaining a separate
direct-source installation.

Remove superseded OpenTrack Skill directories from the active discovery paths
after the rollback check so only this distribution handles railway tasks.
Installation and profile discovery are not proof of native acceptance.

The standalone CLI uses `backend/OTAI` and its own paired backend.
`OTAI_ROOT`, if explicitly set, is the parent containing `OTAI/server.py`;
`OTAI_DATA_ROOT` is the authorized data root. Individual profile CLIs may take
`--root`; inspect their actual `--help`. There is no fallback to another installed
backend when versions, layouts, profiles or authorization capabilities do not match.

The maintained server exposes four profiles: `ai`, `generation`,
`simulation-evidence` and `all`. Start with the discovered `ai` profile for
semantic composition. It intentionally exposes a small set of inspection tools,
the five semantic operations, the hash-bound reviewed-writer publication
gateway and the pure reality-station plan validator.
Switch to `generation` or `all` only for a specific reviewed implementation
tool that the plan names. Profile discovery does not execute a plan.

The original English railway OpenTrack **1.7**, proprietary native templates and
vehicle data must be supplied separately with permission. This distribution does not ship
the original commercial EXE, OpenStep runtime, private donor archives, current
user preferences, screenshots or raw private project evidence. Own helper source
or a native bridge is not a replacement simulator and must preserve original
license checks and the selected original edition's behavior. No Skill command
starts a native helper just by being read.

Before a new project, inspect and hash actual donor resources, declare the true
execution root and native document paths, and use the selected profile's complete
input contract. New native names, labels, paths and entered values use printable
English ASCII. A fresh publisher requires a new target; existing projects use
reviewed in-place updates. Moving an extracted project does not automatically
rewrite its internal fixed-root bindings.

The optional Inspector guard retains source and static/offline evidence;
`runtime_verified=false`. Precompiled binaries are not supplied. Its installed
files do not establish that the original
process loaded it. Native diagram export is a distinct, bounded original-runtime
workflow with its own fingerprint, ABI, main-thread and saving-edition guards;
read [native running diagrams](native-running-diagram.md) before any invocation.
After the software-authorization prerequisite has been met, if other dependencies
or native resources are absent, finish only the inspection/preparation whose own
inputs are available and state the exact missing prerequisite. Before software
authorization, restrict work to the allowed metadata/help or Skill maintenance. Do not fake
hashes, silently use old local installations or relabel preview output as a saved
project. Workflow routing starts in [SKILL.md](../SKILL.md).

## 软件授权

安装 Skill 不授予 OpenTrack 许可。开始任何铁路业务前，先按[完整版软件授权](software-authorization.md)确认并记录用户的有效完整授权；没有确认不能继续生成、读改工程、仿真、导出或指导同等操作。
