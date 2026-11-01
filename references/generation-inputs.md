# From requirements to a coherent generation batch

## Select resources for the chosen operation

Required resources belong to the selected operation, not to every new design.
The template-based project/chain/yard initializers require their explicit donor
roles and real SHA-256 bindings; other current_archive tools specify their own
source roles, while information-only preparation can use explicit caller assertions.
The legacy blank factory contains a packaged-shape implementation but is currently
quarantined with `LEGACY_GEOMETRY_DISABLED`; do not offer it as a working alternative.
Choose a currently supported contract rather than require six external donors
for every information or design task.
A missing installed EXE is a technical dependency distinction, not an exemption
from the required [full software authorization](software-authorization.md).

## Intake template (planning aid, not an MCP schema)

```yaml
deliverable: information | native_draft | isolated_project | existing_project_update
source: {project: known server path, run: selected run if ambiguous}
stock:
  engines: supplied measured data or explicitly approved engineering proxy
  formations: powered/trailer composition and positions
network:
  reuse: exact Route/Path/Itinerary names discovered in the selected project
  new: directed endpoints and verified topology; not drawing coordinates alone
service:
  directions: origin, ordered stops, destination and itinerary for each
  numbering: prefix, first number, step; avoid existing IDs
  departures: first clock + day offset, interval seconds, count or inclusive end
  stop_times: offsets from departure or explicit clock + day offsets
  speed_type: exact original Course string from selected project/preferences
outputs: requested JSON/CSV/native text/XML, preview scope and destination
mutation: source preserved by default; replacement/publication only in authorized scope
```

Do not send this planning template directly to a tool. Translate to the tool's discovered schema. Reuse supplied values; inspect catalogs before asking the user to remember native IDs. If only an information package is requested, unresolved physical topology may be reported as unresolved without pretending native connectivity has been checked.

Ask when a missing value changes the result materially: ambiguous source project, which of two same-looking names to use, measured versus proxy traction, whether an end time includes a last departure, an unspecified midnight crossing, or destructive replacement. For harmless choices such as a fresh draft label, select and state a default. Group necessary questions, not one question per record. A supplied “tomorrow 00:20” means an explicit next-day offset, not a decreasing same-day clock.

## Object meanings and units

| Concept | Meaning / required distinction |
|---|---|
| Engine | Powered vehicle definition, not a departure. `mass_t` tonnes; `length_m` metres; `maximum_speed_kmh` km/h; `maximum_force_kn` kN; power kW. Native schema may require integer values: do not silently round user measurements. |
| Formation / native Train | Ordered consist referencing Engines plus optional trailers. Counts expand physical items; positions are unique slots in 1…N. `number_of_items` is a resistance parameter, not a multiplier of length/mass. |
| Course | One scheduled service using a formation and one or more ordered preferred Itineraries. A display train number is not necessarily the unique Course ID. Shared formations do not prove feasible circulation. |
| Route → Path → Itinerary | Directed signal-bounded movement → ordered Route references → continuous named Paths. “路线” may mean any layer: infer from context, otherwise clarify only when it changes construction. |
| Pattern | Template expanded into Courses, not a saved physical train. Opposite directions normally require separate patterns and verified direction-specific infrastructure. |
| Times | `HH:MM:SS` plus explicit day offsets for individual stops; pattern offsets/intervals/dwell are seconds. Clock strings are not duration values. |
| Braking | Input `braking_deceleration_mps2` is positive m/s²; native stored signs differ. Do not pre-negate input. |

Use supplied traction points where available. `nominal_power_kw` is an **uncalibrated constant-power proxy**, not a measured traction curve. A requested maximum speed does not prove a real train can attain it. Never invent calibrated stock to avoid a question.

## Midnight batch example

After resolving `NIGHT_SET`, `I:A_B`, `A`, `B` and `Reihe R` against the selected project, this is an illustrative **pattern item**, not a complete tool request:

```json
{
  "id_prefix": "N",
  "first_number": 101,
  "number_step": 2,
  "count": 3,
  "first_departure": "23:50:00",
  "first_departure_day_offset": 0,
  "interval_s": 900,
  "train": "NIGHT_SET",
  "itineraries": ["I:A_B"],
  "speed_type": "Reihe R",
  "stops": [
    {"station_sign": "A", "departure_offset_s": 0},
    {"station_sign": "B", "arrival_offset_s": 1200}
  ]
}
```

The generator carries dates across midnight. For explicit `courses`/`timetables`, set `arrival_day_offset`/`departure_day_offset` instead; `23:50` then `00:10` on day zero is not a valid shortcut. Verify first/last expanded departures, at least one midnight row, unique IDs, total service/row counts and every binding. Avoid per-Course calls to produce this pattern.

## Recovery decisions

| Observed problem | Correct next step |
|---|---|
| Native server cannot import `typedstream` or another required module | Record the actual import error and which operations cannot execute. Preserve payload/structured preview. Discover an information-only path if installed; its checks are not archive round-trips. Do not silently change the authorized host/data root, bypass a denied download, or invent native receipts. Existing user authorization for a local workflow can be used; ask only when the proposed change exceeds or leaves that scope unclear. |
| Tool not discovered / unsupported field | Read current schema; map only semantically equivalent supported inputs. State unsupported requirements rather than hiding them in ignored text. |
| Unknown Engine, Train, station or Itinerary | Inspect selected catalogs and correct explicit references. Do not create a different same-looking name or silently pick a template. |
| Disconnected Routes/Paths or ambiguous document IDs | Inspect directed topology and document/class/local ID selectors. Keep unresolved topology explicit; coordinate proximity is not evidence. |
| Existing name collision | Fresh names by default. Replace only when authorized and preview affected dependents; never automatically retry with replacement enabled. |
| Chronology/dwell failure | Correct explicit dates or stop offsets from requirements; retain requested dwell. Do not reduce dwell just to pass validation. |
| Source digest changed | Re-read source and regenerate/review against current data. Do not bypass stale-draft checks. |
| Serialization version unsupported | Report class/version and blocker. Do not claim successful native migration or fall back to another project's unrelated archive. |
| Batch limit exceeded | Partition dependency-safe batches; verify receipt/project selected for the next batch and final aggregate uniqueness/counts. Information-only partitions do not create native draft receipts. |
| Export loss warnings | Deliver exact loss report with format choice; retain richer structured/native representation when requested. Do not call a lossy export full parity. |

A native retry should address the observed cause and preserve originals. Stop repeating unchanged failing calls. Continue independent supported generation, reporting the precise boundary. Requested simulation acceptance is a distinct authorized workstream, not a reason to withhold useful validated information.
