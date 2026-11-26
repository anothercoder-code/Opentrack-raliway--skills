# Semantic capabilities and composition

The Skill's subject is the railway requirement. The AI selects capabilities,
then uses discovered tools to implement them. Raw tool names are implementation
details and may change with the paired backend.

## Capability record

Every candidate capability needs:

- `capability_id` and the railway intent it satisfies;
- required object types and source SHA bindings;
- prerequisites and dependent capabilities;
- ordered implementation tool families;
- read, preview, stage or publish effect;
- software-authorization and host prerequisites;
- supported evidence level and known exclusions.

Registration is not readiness. Check the live schema, availability, BLOCKED
description, quarantine status and actual resource prerequisites. Do not count
the eight legacy geometry writers as usable construction tools.

## Composition rules

Reuse general capabilities such as inspection, topology resolution, reference
compilation, typed archive editing, publication and verification. A template is
an input or example, not a universal semantic model. Do not request a dedicated
solver for every original function.

Split a task at real dependency and safety boundaries:

1. establish project and source identity;
2. resolve existing objects before inventing new ones;
3. construct or retain the directed infrastructure;
4. bind stations, platform faces and facilities;
5. define Route, Path and Itinerary movement;
6. bind formations, Courses and timetables;
7. prepare a runnable candidate;
8. verify assertions by evidence layer.

When no supported primitive can establish a compound turnout, non-contiguous
platform, crossing or other required safety relationship, return a structured
unsupported result. Do not infer connectivity from drawing adjacency, reuse an
unrelated fixed template, or claim a blocked writer as a fallback.

## Semantic profile

When available, the `ai` profile exposes a small set of entry points:

- `opentrack_get_railway_capabilities`
- `opentrack_compile_railway_plan`
- `opentrack_inspect_railway`
- `opentrack_apply_railway_plan`
- `opentrack_verify_railway_outcomes`

The same profile exposes `opentrack_validate_reality_station_plan` for the
station-specific evidence contract. It validates source provenance, tracks,
island faces, exact Edge-End spans, stops and signals, directed throat links,
shared resources, train fit, day-crossing dwell and downstream continuation
before selecting writers.

Use them for requirement/capability discovery, plan compilation, inspection,
controlled execution boundaries and outcome aggregation. Their live schemas
and results remain authoritative. A planning or preview result is not a saved
project, and neither is native simulation evidence.
