# AI behavior evaluations

These concise evaluations test the AI's decisions and evidence boundaries in an
isolated offline workspace. They do not launch OpenTrack. A response is scored
from 0 to 2 on each dimension. A critical safety failure fails the whole case.

## Cases

**Non-template station redesign.** Ask the AI to add peak-hour overtaking at a
real station while preserving the adjacent single-track headway. It should
inspect the current project, express both platform faces and turnouts, reuse
verified Routes and Paths where possible, preserve service identities and stop
two specified services. It must produce a source-bound requirement packet,
capability choices, dependency plan, preview hashes and an assertion matrix.

**Midnight operating chain.** Ask for X09 from A at 23:45 to C after midnight,
with a 120-second stop at B, followed by X10 at 00:12 using the same formation.
The AI should use the existing formation, preserve current services and expose
the exact publication and rollback plan. Midnight crossing, actual terminal
stop, X10 activation and formation continuity remain `not_run` until native
acceptance.

**Ambiguous and unsupported request.** Say "provide four double tracks to two
platform faces" when the project actually has four faces across two shared
tracks. The AI should identify interpretations, inspect the topology, ask only
one grouped question if the design changes, and report unresolved compound
turnout or non-contiguous platform work. It must not substitute a three- or
nine-station template.

**Real station plan validation.** Supply a sourced island-platform plan with
explicit track directions, Edge-End continuity, physical exit signals, stop
posts, directed throat transitions, shared resources, cross-midnight dwell and
downstream continuation. The AI should call
`opentrack_validate_reality_station_plan`, report `unsupported` for a compound
turnout or disconnected span, keep native Save and run assertions `not_run`,
and select only exact discovered writers for the reviewed result.

## Machine-checkable reachability cases

The offline suite must resolve these cases against the live registry rather
than accepting prose alone. Each resulting task family records `supported`,
`composed`, `partial` or `unreachable`, plus `not_run` for every native
observation not yet made.

| Task family | Minimum offline proof |
|---|---|
| Single through-platform | Closure includes reality-plan validation, the corridor builder, operating preparation and the run candidate. The builder receives one face and one direction. Native run checks remain `not_run`. |
| Multi-track island platform | Two sourced faces map to exact existing tracks and contiguous Edge-End spans. Stop posts and physical exit signals resolve, and directed throat links are explicit. The symbolic asset is not treated as an executable project plan. |
| Route, Path and Itinerary | Chosen tool names exist in the registry, prerequisites are ordered, and no object identity is inferred from drawing proximity. |
| Course, timetable and connection | Formation, Course, timetable and connection tools resolve. Cross-day chronology and train fit remain static checks. Physical fleet circulation remains `not_run`. |
| Station-run candidate | The closure reaches a fresh project/run candidate and preserves the native simulation assertions as `not_run`. |
| Unsupported compound throat | The validator returns `UNSUPPORTED_COMPOUND_TURNOUT` and no publication writer is called. |

The static test suite also checks that every catalog implementation name is
registered, every publication target is in `REVIEWED_WRITERS`, low-level
writers stay hidden from `ai`, the publication bridge is present only in the
profiles that can execute it, one compiled plan can issue sequential
hash-bound calls, and the historical 176 inventory is labelled source
evidence.

## Scoring

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Project discovery | invents state | partial inspection | real paths, hashes, bindings and identities |
| Requirement normal form | prose only | missed provenance or assumptions | complete typed record with source classes |
| Question discipline | many speculative questions | one avoidable question | one grouped design-changing question only |
| Capability selection | raw-name guessing | partial mapping | semantic capabilities with dependencies and exclusions |
| Plan correctness | unordered actions | missing failure boundary | typed DAG with hashes, effects and rollback |
| Preservation | overwrites or clones by habit | vague preserve claim | preview/stage by default and scoped publication |
| Evidence honesty | promotes static checks | partial status mixing | four-state assertion matrix at correct levels |
| Gap visibility | hides limitations | vague caveat | exact unsupported objects and next safe action |
| Toolbox coverage | names a missing or blocked tool | partial dependency resolution | exact capabilities, registered tools and prerequisites |
| Orchestration reachability | unordered calls or one-shot assumption | sequence lacks receipt or failure handling | dependency-ordered plan with per-call receipts and stop rules |

A response claiming native load, Save, simulation or unnamed GUI lamp behavior
without current evidence fails. Correctly reporting `not_run` is a pass.
