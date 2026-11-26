# Requirement normal form

Use this contract after the software-authorization gate and before selecting
tools. It turns a railway request into facts that a compiler and verifier can
check. Keep the user's words, source observations, design decisions, assumptions
and unresolved facts separate. A fluent plan does not promote one category into
another.

## Required record

```yaml
objective: <what must exist or operate>
deliverable: information | preview | staged_change | fresh_project | existing_project_patch
scope:
  project: <actual project or explicit new target>
  run_file: <actual selected run, or null>
  documents: [<affected worksheets>]
  catalogs: [<affected native catalogs>]
identity:
  source_paths_and_sha256: []
  preserve: [<existing names, paths, identities and services>]
sources:
  - id: <stable id>
    kind: user_statement | native_observation | official_reference | assumption
    locator: <path, URL, query or conversation statement>
    retrieved_on: <date or null>
    supports: [<field or fact>]
site:
  station: {name: <name>, code: <code>}
  tracks: []
  platform_faces: []
  platform_spans: []
  throats: []
  movements: []
operation:
  formations: []
  services: []
  stops: []
  turnarounds: []
constraints: []
assumptions: []
ambiguities: []
acceptance: []
```

Use native units and exact identifiers. For a station, record track direction,
platform face, usable stopping range, stop post, exit signal, ordered native
Edges and throat connectivity separately. Graphic proximity is not connectivity.
For a service, record formation, ordered visits, arrival and departure clocks,
explicit day offsets, dwell and downstream continuation.

## Fact admission

Each material fact must have a source or an explicit assumption. Mark a value as
unresolved when the available evidence conflicts or does not establish it. Ask
one grouped question only when the missing fact changes topology, safety,
publication scope or service meaning. Prefer inspecting the selected project
over asking the user to repeat native identifiers.

Do not insert a plausible platform, turnout, signal, vehicle or time merely to
make a template validate. A design assumption that affects acceptance must say
so in `assumptions` and must be rechecked in the outcome matrix.

## Handoff

Pass this record to capability selection and plan compilation. The plan may add
derived fields, but it must retain source IDs and assumptions. A tool response
is a new observation, not permission to overwrite the original requirement.
