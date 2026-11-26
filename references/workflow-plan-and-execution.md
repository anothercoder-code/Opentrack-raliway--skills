# Workflow plans and controlled execution

A Plan IR is a dependency DAG, not a prose checklist. Each action binds typed
inputs, an actual source snapshot, the selected capability and the exact
discovered implementation tool or family. It also declares expected outputs,
side effects, rollback boundary and the assertions it contributes to.

## Plan requirements

```yaml
plan_id: <stable id>
requirement_sha256: <normal-form digest>
source_project: {path: <path>, member_sha256: {}}
mode: inspect | plan | preview | stage | publish
actions:
  - id: <dependency-safe id>
    capability_id: <semantic capability>
    tool: <discovered MCP tool>
    inputs: {}
    prerequisites: []
    expected_outputs: []
    side_effect: none | create | replace
    target_scope: []
    verification_assertions: []
journal: []
rollback:
  strategy: <fresh_target | reviewed_patch_journal | not_applicable>
```

## Execution boundary

Planning, inspection and verification default to no mutation. Preview may
create only isolated temporary artifacts. Publication requires a fresh explicit
target, reviewed plan digest, unchanged source hashes and the selected tool's
actual publishing contract. Existing-project patches preserve paths and require
a reviewed before/after journal.

Reuse the established publication, reviewed-application and native-writer
guards. Do not import backend internals, run arbitrary shell, bypass
`LEGACY_GEOMETRY_DISABLED`, or reinterpret a blocked tool as available.

After every action, re-read the produced bytes or native candidate and record
the actual hash. On failure, stop dependent actions, retain the original and
write the concrete error. A retry must address the cause and verify the source
snapshot again. Never resume from a speculative receipt.

## Native boundary

Opening the original application, loading the actual project, GUI Save,
unloading and true reload, Inspector checks, live train movement and station
observations are separate actions. Keep them in the final native acceptance
phase unless the user requests a bounded native task sooner. This Skill does
not launch OpenTrack as an implicit consequence of planning.
