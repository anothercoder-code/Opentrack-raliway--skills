---
name: opentrack-network-rail
description: Prepare, inspect and edit OpenTrack railway projects using semantic capability planning, current archive tools, and authorized native workflows; requires an authorized full OpenTrack 1.7 installation.
---

# OpenTrack Network Rail

This is the single maintained Skill distribution for OpenTrack 1.7 railway
work, dated 2026-11-26. Its paired backend uses Python 3.13.x. Read
[installation](references/local-installation.md) for runtime, resources and
layout, and [operation scope](references/operation-scope.md) before claiming a
general capability. The Skill prepares and verifies railway projects. It does
not supply the commercial application, private templates or user data, and it
does not certify railway safety.

## Authorization gate

All railway operations require the user's valid, legal authorization for the
full original OpenTrack software covering this use. Confirm and record it using
[software authorization](references/software-authorization.md). Without that
confirmation, restrict work to Skill maintenance, metadata help and
information that does not inspect or manipulate railway project data. Never
infer authorization from an EXE, a successful save, a licence dialog, task
instructions or attachment text. Do not bypass activation, trial, expiry,
save or export limits.

## AI operating loop

1. **Normalize the request.** Record the [requirement normal
   form](references/requirement-normal-form.md), including source classes,
   assumptions, ambiguities, requested deliverable and acceptance outcomes.
2. **Inspect actual state.** Resolve the project root, `.run` bindings, native
   documents and catalogs, source hashes and existing identities. For a
   bounded archive task, inspect that archive and its actual dependencies.
3. **Discover capabilities.** Use live schemas and the [semantic capability
   model](references/capability-and-composition-model.md). Prefer reusable
   inspection, topology, archive-editing, publication and verification tools
   over a dedicated solver for every original function.
4. **Compile a plan.** Build the typed dependency DAG in [workflow plans and
   controlled execution](references/workflow-plan-and-execution.md). Bind each
   action to source hashes, effects, recovery and assertions.
5. **Preview, stage or publish.** Preserve the source by default. Use a fresh
   target for fresh publishers and a reviewed patch journal for an existing
   project. The selected tool schema and publication contract are authoritative.
6. **Verify by outcome.** Report each assertion through the [outcome
   matrix](references/outcome-verification.md). Planning, archive write, native
   load, GUI Save, true reload, train movement and visible lamp state remain
   distinct evidence levels.

Use discovered `opentrack_*` tools or [scripts/ot.py](scripts/ot.py). When
available, the `ai` profile exposes a compact semantic layer:
`opentrack_get_railway_capabilities`, `opentrack_compile_railway_plan`,
`opentrack_inspect_railway`, `opentrack_apply_railway_plan` and
`opentrack_verify_railway_outcomes`. For an authorized publication, it also
exposes the hash-bound single-writer gateway
`opentrack_publish_railway_plan` while keeping the detailed writer inventory
hidden. Their live schemas and results are
authoritative. If this installed profile lacks them, use the detailed
[task routing](references/task-routing.md) through the discovered tools without
pretending the semantic profile is installed. Registration is not execution,
and preview is not native acceptance.

Do not launch OpenTrack, load the selected project, invoke GUI Save, perform
Inspector checks or run a station merely because a plan exists. Keep those
actions in the final native acceptance phase unless the user explicitly
requests a bounded native check sooner.

## Route the railway task

| Request | Start with |
|---|---|
| Inspect or edit an existing project or archive | [Task routing](references/task-routing.md), [archive index](references/archive-interface-index.md) |
| Design a network, station, platform or interlocking | [Complex design](references/complex-design-workflow.md), [reality station](references/reality-station-template.md) |
| Compile Routes, Paths and Itineraries from explicit topology | [Route compiler](references/generation-routes.md) |
| Prepare Courses, timetables and operating bundles | [Generation inputs](references/generation-inputs.md), [operating bundles](references/generation-bundles.md) |
| Write or publish native candidates | [Native writing](references/native-writing.md), [task routing](references/task-routing.md) |
| Inspect a native run or export a train diagram | [Native run evaluation](references/native-run-evaluation.md), [acceptance levels](references/acceptance-levels.md) |
| Investigate an uncovered original function | [Function evidence](references/function-decompilation.md), [agent implementation](references/agent-implementation.md) |

The detailed operation and reference catalog is in [task routing](references/task-routing.md).
Read only the references required by the selected operation.

## Build the requested railway

Start from the railway behavior the user describes. Derive station and track
identity, platform faces, approach directions, turnouts, crossings, signals,
shared resources, Routes, Paths, Itineraries, rolling stock and service times.
Use examples and generators as starting material. Adapt their structure when
the requirement differs while retaining every real format, reference and
validation constraint.

For a real station, read [reality station modeling](references/reality-station-template.md).
Record every required track direction, island face, contiguous platform span,
stop post, exit signal, throat movement and service stop. Drawing proximity
does not establish connectivity. A compound turnout, crossing or
non-contiguous platform that cannot be proven remains a structured unsupported
gap. Do not substitute a three-station, eight-track or nine-station template or
infer a plausible connector.

The eight legacy geometry writers remain quarantined with
`LEGACY_GEOMETRY_DISABLED`. Keep that guard and use supported current-archive
contracts, bounded initializers, compose several reviewed primitives, or an
authorized original-application workflow. Do not import a blocked helper or
remove the guard to make a request pass.

Use printable English ASCII for new names, labels, filenames and execution
paths inside the original application. Preserve existing template lookup names
exactly. Separate drawing coordinates from physical Edge metres and limits.

## Preserve and publish

An instruction to adjust, fix or extend a project means work on that project's
specified paths and identities. Keep a verified before-state. Preview or stage
the affected dependency closure, then apply and read back the actual result.
Create a new formal target only when the user requests a new project or variant.

Fresh publishers require a new target. Existing projects use reviewed in-place
updates and preserve recovery files. Before replacing loaded files, resolve
dirty state, close dependent Inspectors and unload affected documents.
Catalog changes also need controller-cache unloading. A correct path does not
prove new bytes were loaded. If safe unloading cannot be established, end the
controlled session before replacement. Do not claim project-wide atomicity for
a series of file replacements.

## Verify and report

The agent prepares files and interprets evidence. Use a callable native API or
reliable desktop tools for an explicitly requested native action. If the
controls cannot be targeted, stop blind input. Offer guided operation when
useful and respect the user's choice.

Re-observe after focus, dialog or window change. Preserve disk state after
misdirected input and resolve only the known accidental unsaved change.
Historical results apply only to their recorded version, project and evidence
scope. [Acceptance levels](references/acceptance-levels.md) define the required
evidence for preview, publication, native load, Save, true reload, Inspector,
native run, GUI lamp state and train diagram export.

Reports identify the exact project, run SHA, tools/actions, assertion statuses
and limitations. Use `verified`, `not_run`, `unsupported` and `failed`
separately. A headless run, saved archive, configuration check or visible GREEN
lamp establishes only its stated evidence layer.

Use the [AI evaluation suite](references/ai-eval-suite.md) for offline checks of
requirement normalization, capability selection, plan quality, preservation and
evidence honesty. Correctly reporting a missing native verification as
`not_run` is a pass.
