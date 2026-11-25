> Historical development/audit snapshot. The stage/version in this filename
> scopes "current", "remaining", cloud/platform blockers, integration status and
> test results below. Read the [current backend entrypoint](../README.md) and
> enclosing Skill before treating a statement as current capability or permission.
> Preserve actual function/input contracts; do not turn an old no-GUI/cloud-only
> task boundary into a general ban on authorized local work. A currently applicable
> approval rejection still governs that exact action and cannot be bypassed.

# Auxiliary run bindings: dev1

This adds read-only data validation, not a simulation engine. Native dynamic behavior remains OpenTrack's responsibility.

## What changed

- `Train Diagram Document` bindings load explicit bytes, check `OTCorridorDocument` version 13 and its known encoder groups, verify stored `docFileName` against the selected run path, and resolve `OTCorridorStation` version 0 station signs against the selected Station catalog. Persisted plot-result data and display behavior are not certified.
- `Document Set Name` and subsequent `Document Set Document` lines form ordered groups. Multiple named groups are allowed, members must be selected infrastructure or diagram documents, and empty/orphan/duplicate groups or members are refused. The ordinary script-run reader does **not** apply document-set groups. These are exported-preferences metadata and do not substitute for explicit infrastructure/diagram declarations.
- `Incident#name#` selects events by exact name in `CourseList.incidentArray`. It is **not a filename** and causes no extra file read. Missing or ambiguous names and duplicate selections are refused. Stored Use flags remain unchanged. The native script runner clears Use then enables matching names; this checker does not perform that runtime action.
- `MultiDocumentTools.load_project` now uses the explicit auxiliary parser and validates named-event binding instead of incorrectly resolving event names as paths. The old fresh-generation run parser remains unchanged.

## Evidence

Original decompiled function evidence inspected: `0041c0a8` script-run parser, `00436b54` script runner, `0046f35c` event-name lookup, `0041c2b0` exported-preference group handling, `00432fd4` group writer, `004446f0` corridor document encoder, and `00453e68` corridor station encoder. These are static decompiler observations, not original source or native execution results.

The authorized original04 BJTU-demo.run references 13 selected files including itself: six catalogs, three infrastructure documents, three diagrams and the run. All three diagram path/station bindings and its document-set group passed the new auxiliary checks. The overall finite operating preflight still rejects this original model because planned timetable fields contain noncanonical placeholder times. No original data was changed to hide that failure.

## Verification and limits

`test_rebuild_auxiliary_preflight.py`: 15 tests passed, including the original13-file selection, synthetic bounded diagrams, valid and missing event names, grouped document sets, immutable input hashes, and multi-document inventory routing. Synthetic diagrams exercise the data checker only; they are not asserted to be native-loadable fixtures.

The event check proves exact name ownership and the known Incident12 layout. It does not certify every type-specific target, trigger, sampling or dynamic outcome. Unsupported class versions still fail closed. Original application loading remains a separate compatibility check.
