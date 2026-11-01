# Single-command current network archive generation

`opentrack_generate_current_network_archives` is one composite pipeline. It creates
new paired Ends, Safety Elements, Edges, a bounded main-signal profile, new
movement Routes, simple local Paths, and finite multi-Path Itineraries. It saves
one `.opentrack` document and its `.dest` catalog together into a fresh directory.
This is **not** a complete Project, train configuration, timetable or simulation.
It does not restore the quarantined legacy Geometry/Project factories.

## Sources and origin

Four explicit SHA-256-bound source roles are required: `header_document`,
`shape_archive`, `template_document`, `template_dest_catalog`. The header and
template document may be the same physical source. All are securely read beneath
the authorized OTProjects / OTAI/workspaces root. Every distinct file is rechecked
before any publication and afterward. Templates do not need a runnable source
project: only the strictly validated current structures are consumed. The source type
blueprint is not certified as an operationally valid project; its discarded old
movement is not used as a runtime reference oracle.

The header source must be current Document4/internal17. Its three graph containers
are replaced in a private copy after strict schema and retained-reference checks.
All non-graph header state, including opaque licence/registration state, stays
unchanged. No licence is granted, removed, forged or expanded. This is a derived
empty shell, not a vendor-certified empty-project fixture. The native-shapes file
provides class/layout prototypes, not a native constructor or a source railway.
All generated End/Edge/Safety values and connections come from the explicit spec.

The Path/Dest templates provide only validated current shape and explicit empty
margin policy. Every movement, name, ID, owner and saved reference is replaced.
External source object reachability is rejected. After the first Dest is made,
subsequent new Dest objects use that newly generated empty-margin type template.
The original projects are never edited or published as if newly generated.

## Explicit spec and supported domain

- 1–1000 paired vertices, 0–2000 actual Edges. End references use stable
  `{vertex, side}` keys, never diagram coordinate intersection or a guessed ID.
- Each half-vertex accepts at most two Edges. End-related pairs, Edge backlinks and
  Safety memberships are validated. The bounded profile has detector flags false;
  raw track/loop/dlink codes are explicitly 1, not inferred business enum labels.
- Edge length is positive integer metres; signed radius metres and gradient per
  mille are explicit finite float32 values. Diagram position is not a physical
  alignment. A topology ring does not prove curve dynamics or operating safety.
- Explicit per-train-type directional speeds are integers 1–1000 km/h, not a
  recommendation. `equal_speed` must agree with the actual speed table.
- The one supported main/exit signal profile is type1/main4/location2/show2/
  dispatch7, with track-speed indication0. Sighting distance, delay and graphic
  placement options are explicit. Signal.end and End.signal are mutually bound;
  signal indications point to the End, route indications to the Route.
- New Routes traverse 2–1000 unique Ends via actual reciprocal paired Ends and
  actual Edges. Main signals bound the Route; no hidden intermediate main signal
  or connector is accepted. Native RSP allocation is highwater+1. Release group
  modes are `global` or `each_end`, with explicit reserve_previous.
- Each Path remains local and simple. Closed journeys are represented by finite
  ordered Path occurrences, not by disabling the per-Path cycle guard. Adjacent
  repetition of the same Path is rejected; separated repetition is retained.
- Every Route/Path/Itinerary name is unique in the generated document. References
  resolve only to objects generated in this invocation. The complete output
  document set is exactly this one newly generated document.
- A new catalog contains only the generated Dest rows; each row names the actual
  output `<document_name>.opentrack` and preserves every ordered Path occurrence.

See `tests/fixtures/wave9/ring-request.json` for a complete two-lap example excluding
source paths/hashes. Its 4x500m/radius0 values are instructional placeholders, not
geometrically or operationally certified railway design.

## Transaction and evidence

Preview is default and writes nothing. All stages execute on private in-memory
bytes first; late failures return no output files. Only once the entire pair
passes fresh decoding and reference checks does the existing fd-secure Linux
renameat2 no-replace publisher atomically commit the fresh directory. Sources and
existing targets are never overwritten. A postcommit failure is reported with
`commit_completed=true` and expected hashes; inspect rather than blindly retry.

Receipts distinguish per-stage construction, counts, source hashes, output hashes,
header preservation and archive verification. The tests additionally use fresh
upstream pytypedstream processes and actual MCP stdio / standalone Skill CLI.
These are archive-level checks, not OpenTrack execution. No station, engine, train,
Course, timetable, .run or 24-hour result is supplied by this pipeline.

## Three-by-three instructional example

`tests/fixtures/wave9/grid-request.json` uses the same pipeline, not a separate
unverified generator. Its nine horizontal/vertical crossings are separate nodes
with separate Safety Elements. Twelve perimeter wyes provide actual permitted
connections. Twelve main signals partition the six corridor circuits into twelve
simple Routes/Paths; six Itineraries each retain two finite laps. The actual
`.opentrack` and `.dest` outputs are included with source/output SHA receipts.
This does not include six train objects or a day timetable. Signal sighting,
release-group and reserve-previous values are declared teaching assumptions;
no headway, braking-distance or deadlock safety follows from archive validity.
