# Calling the interface

The installed skill's `scripts/ot.py` selects the matching packaged backend. An explicit `OTAI_ROOT` names the directory containing `OTAI/server.py`; it is not the project data root. Use `--root` or `OTAI_DATA_ROOT` for the authorized data root. Do not redirect to another installation merely because a historical example used it. MCP, REST and CLI share schemas and dispatch code. Prefer argument files for multiline JSON and Windows shell quoting. For new operational records, choose a currently supported typed current_archive entry and read its schema. The [legacy batch reference](generation.md) and clone example below describe quarantined writers, not ready current repair routes.

Use the [original stock English version](original-version.md). Check
`opentrack_capabilities.target_baseline`; the Chinese launcher and injected
enhancements are not prerequisites. UI labels below refer to the original
English menus, not localized captions.

```powershell
py -3.13 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> tools
py -3.13 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_inspect_project --args-file <REVIEWED_PROJECT_REQUEST.json>
py -3.13 -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_stage_changes --args-file <REVIEWED_CLONE_REQUEST.json>
```

## Missing service or Engine

1. Inspect selected catalog paths and counts.
2. Resolve Course, vehicle, Engine references and timetable.
3. Validate native root types/field positions. If station initialization fails, trace that before adding duplicate Engine records.
4. Check current-input output or an already authorized runtime read. A Tools window is not simulation loading proof.

## Historical clone-departure example

`opentrack_stage_changes` and `opentrack_apply_draft` below belong to the currently
quarantined legacy whole-project pipeline (`LEGACY_GEOMETRY_DISABLED`). The
example describes the former contract; do not run it as a current fix. For a new
Course or timetable change, select an actually supported current_archive operation
whose schema covers the requested effect, and verify its saved result. There is
no implied one-to-one replacement for the legacy clone-and-shift action.

## New departure — legacy contract only

Clone a valid Course to a unique ID and shift its timetable. Keep or explicitly choose existing vehicle/itinerary names. A structurally valid clone may conflict with another train; inspect route/platform resources and actual dispatch before calling it runnable.

```json
{
  "project": "OTProjects/BJTU",
  "label": "Draft G9001 departure",
  "changes": [
    {"kind": "clone_course", "template_id": "G1046", "new_id": "G9001", "seconds": 900}
  ]
}
```

The result contains `draft_id`, `source_digest`, changes and validation. Inspect `opentrack_get_draft`. If applying is authorized and OpenTrack is closed, call `opentrack_apply_draft` on an apply-enabled server with that exact digest. If source bytes changed, stage again.

## Results

- `ok: false`: stable error code and next action.
- `valid: true`: offline structural checks passed; native operation is not certified.
- `not_observed`: no selected native protocol; used courses is unknown.
- `stale_or_incomplete`: catalog paths do not establish this protocol belongs to the selected input.
- `protocol_completed` requires agreeing catalog paths, window, Step, enabled-course count and end message. It proves a matching protocol end, not completion of every train, collision freedom or capacity. This generic protocol matcher does not establish per-train completion. Use the selected scenario's native per-train/event/resource outputs and its applicable auditor; the yard/grid auditors are separate checks, not an upgrade of this matcher.
- Nonzero start/stop day offsets cannot currently be matched from protocol text. Such a run is never reported `protocol_completed` solely from matching clock strings.

The frozen evaluation fixture is `OTAI/tests/fixtures/bjtu`. Tests materialize isolated workspaces and never apply to the user's BJTU baseline or launch OpenTrack.
