# Generic protocol-text evidence adapter

This contract describes `opentrack_ai.simulation_evidence`, not every native
simulation or result workflow in the enclosing Skill. It is a conservative
text-evidence adapter; its blocked control and unknown per-train fields are
properties of this adapter, not a claim that authorized original execution or
other separately audited result readers are unavailable.

## Current public entrypoint and operation scope

The current main Registry already integrates this module. Use the packaged
entrypoint, replacing placeholders with real paths:

```text
python -X utf8 -B <SKILL>/backend/OTAI/server.py --root <DATA_ROOT> --profile simulation-evidence tools
python -X utf8 -B <SKILL>/backend/OTAI/server.py --root <DATA_ROOT> --profile simulation-evidence stdio
```

The old `simulation_evidence_server.py` and integration-patch command referred
to a historical standalone snapshot; that launcher/patch is not the entrypoint
of this package. Use the common Registry's capability and
[full-software authorization](../../../references/software-authorization.md)
checks; do not construct a separate wrapper to bypass those gates.

| Tool | Actual behavior in this adapter |
|---|---|
| `opentrack_simulation_capabilities` | Reports this generic adapter's control/result limitations, not an inventory of every installed workflow |
| `opentrack_simulation_control` | The registered start/status/stop request returns `state:blocked`, `executed:false`, `job_id:null`; performs no process action |
| `opentrack_inspect_simulation_evidence` | Bounded reads of selected existing run/protocol/messages; consistency is not proof of a successful train journey |

The actual `tools` output and [operation scope](../../../references/operation-scope.md)
are authoritative. A definition in a shared module is not proof that an action
is usable. Business calls require the scoped user attestation.
`ok:true` means the selected request was handled, not that simulation ran.

## Format and exact evidence boundary

The adapter reads the existing protocol-text convention used by `Service.logs`:

- `.run`: `key#value#` output/catalog/window/Step parameters;
- selected `OT_Protocol.*.txt`: six catalog paths, Simulation Time/Step and the
  `Used Courses:` section terminated by `Occupations:`;
- selected output directory's `OT_Messages.txt`: exact standalone end/cancel markers.

It requires an explicit protocol path instead of newest mtime. It compares
required Course IDs, duplicate/extra/missing IDs, header/catalog path text,
window and Step, and hashes files actually read. These hashes identify bytes;
they do not bind the files or catalog contents to one original invocation.
`protocol_consistent_with_selected_run` is text consistency only.

`expected_course_ids` are caller requirements, not observations. The old 288-ID
full-day scenario was one example, not a fixed train-count requirement. The
current model accepts 1–10000 unique, nonempty exact IDs; preserve that actual
schema bound. It creates a row for each required ID but does not derive per-train
departure, terminal arrival, cancellation or interruption from `Used Courses`.
Those fields remain null when this parser lacks evidence. `Occupations:` is a
section heading, not proof of terminal arrival or complete resource release.

The parser exposes end/cancel marker observations. Marker absence does not prove
zero incidents, and an end marker alone does not prove every train completed.
Nonzero configured day offsets prevent its legacy single-day consistency flag;
clock text alone cannot establish a full 24-hour duration. This generic adapter
retains `goal_complete:false` and `native_simulation_verified:false`.

## Execution and integration boundaries

This module does not inspect main archive dependencies, own a native job or
provide an audited start/stop controller. Do not turn an unperformed dependency
check into a statement that the current whole server cannot import, or that no
original engine has ever run. Its own no-process behavior remains unchanged.
Separately authorized original-app workflows or audited result readers may use
their own interfaces; the specific project and outputs still need their own evidence.
Read [current acceptance scope](../../../references/acceptance-levels.md) rather than
transferring one parser's blockers to every workflow.

Historical synthetic parser/transport tests used no original software. They
support the tested parser/error behavior only. They do not certify the source
of arbitrary user files, physical arrival, full-day operation, conflict freedom
or native control. No substitute terminal CSV/JSON convention is invented here.
