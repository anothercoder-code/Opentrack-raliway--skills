# Outcome verification matrix

Every requested outcome becomes an assertion. Report each assertion separately
using exactly one status:

- `verified`: the required action and evidence exist for the stated scope;
- `not_run`: the action or observation has not happened;
- `unsupported`: the available capability or evidence cannot establish it;
- `failed`: the action ran and contradicted the assertion.

Do not promote configuration to execution, file publication to native load,
native load to GUI Save, or Save to true unload/reload. Do not promote a visible
GREEN lamp to complete interlocking safety.

## Assertion record

```yaml
assertion_id: <stable id>
requirement: <requested behavior>
status: verified | not_run | unsupported | failed
evidence_level: <schema | archive_roundtrip | native_load | gui_save | true_reload | inspector | native_run | gui_observation | native_diagram>
evidence: []
  # path, sha256, tool/action, timestamp or run id, observed value
scope:
  project: <path>
  run_file: <path>
  documents: []
  services: []
limitations: []
```

Use existing verifiers where they match the assertion, including project schema
validation, topology tracing, Route/Path checks, RailML readback, station
candidate preflight, native outcome inspection and GUI observation records.
An aggregate "passed" is insufficient when the user asked about specific
platforms, directions, stops, crossings or departures.

For a real-station replica, include track and platform identity, every required
throat movement, stop-post/exit-signal binding, Course stop and dwell, vehicle
fit, downstream continuation and the planned native load/save/reload/run checks.
An unsupported compound turnout or disconnected platform span remains
`unsupported`, even if the enclosing project otherwise validates.
