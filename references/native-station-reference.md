# Relocating a saved station reference

Use `opentrack_relocate_native_station_reference` when an existing
Station Vertex must move along the same station track and booked physical
stops must remain in place. Supply the complete SHA-bound `source_project`
inventory, `document`, `station_id`, and the directional `from_end_id` and
`to_end_id`. Both paired vertices must already belong to the selected
StationModel. Supply a `witness_itinerary` that visits both Ends exactly once,
the `expected_edge_ids` in its travel order, and `expected_shift_m`. The
signed shift is negative when the new reference precedes the old one.

The tool writes the native station-reference type on both halves and verifies
the Routes, Paths and Itineraries from fresh archive bytes. For booked
Course options it checks the new directed station occurrence against the
original timetable index and track. On a separate reference with no attached
signal, the operating planner follows the station area to its one directed
exit signal and resolves the ordinary head marker on that approach if present.
The actual stopping marker, location and fit must remain consistent for a booked
stop to pass the edit. Planned times, existing signal positions and stock
remain available in the original archives.

`unassigned_changed_itineraries` lists definitions without a Course binding
that require a review of the new Station occurrence or endpoint before use.

## Rebind a booked origin or terminal

When the old reference End is an Itinerary endpoint, submit
`endpoint_rebindings` for each affected Course Itinerary. Each entry names
the saved `itinerary` and gives its complete ordered `replacement_routes`
using `document`, `name`, `array_id`, and `start_id`. Choose existing
main-signal Route boundaries. The revised route may cut or extend the
station prefix or suffix. It must retain the whole common directed section.
The tool reuses exact existing Paths where possible, preserves the original
Routes and shared Paths, and updates the saved Itinerary and its `.dest` row.

For each enabled Course using an edited endpoint, `endpoint_course_reviews`
records its old and new directed origins and terminals, route lengths, and
terminal train-head positions. The tool reads the actual consist and timetable
to resolve stopping points. It compares unaffected physical stops by Edge and
local offset, so a changed origin can move output chainage while preserving the
same physical stop. The current contract covers Courses with one Itinerary.
Independent moving-block and CBTC Courses can use the same saved geometry
review. Linked vehicle transfers use fixed-block spacing.

A saved interval family can use a common rebound Itinerary. Review every
enabled Course using that Itinerary. A follower may itself be a reference
for another Course. The edit requires one root and an acyclic family,
checks that every member has the same ordered Stations, and verifies each
row's absolute clock against its immediate reference. The original
reference IDs, offsets and timetable bytes are retained. Endpoint moves
preserve existing timetables. The interval generation operation still uses
the native convention of reusing the template's existing reference.

For a saved fixed-formation turnround, use `endpoint_link_reviews` to name
every directed Connection6 pair in the affected chain. Each entry gives
`from_course`, `to_course`, and `movement` as `continue` or `reverse`.
The edit checks the reciprocal terminal and origin records, their order,
the native station sign, the identical ordered train formation, and the
successor's saved minimum wait. It resolves the departure from the predecessor's
saved arrival Route and verifies the resulting End against the successor's
first Route. The `.courses` and `.timetable` archives are retained byte for byte.
Supply the complete reviewed chain even when the edit moves only one link.

For a chain with formation changes away from the edited reference, list every
saved split and join in `endpoint_formation_reviews`. Name `kind`,
`main_course`, `other_course`, `station_sign`, and the `main_visit_index`.
The review derives the actual formation lengths at each visit, checks the
ordered remaining stock against any terminal successor, and verifies the
original event berth and occupied-entry permissions.

For an interior same-direction split at the relocated main signal, add
`split_berth_relocation` to that split's review. In both `expected_head`
and `replacement_head`, give `document`, `end_id`, `signal_id`, `edge_id`,
`edge_offset_m`, ordered `platform_edge_ids` and `available_length_m`.
The writer checks the contiguous directed approach, derives the arrival and
retained tail positions, and verifies that the dispatch uses the parent's
exact departure Route and the child's zero-offset origin. Other events on
the chain retain their saved berths.

For a same-direction physical join at the relocated main signal, use
`join_berth_relocation` with the same head and platform fields. The receiving
and supplying Courses must share one exact incoming Route. The writer computes
the supplying train's contact point from the receiving train's actual rear.
The occupied-entry settings, entrance signal and safety elements at the contact
remain bound to the same native objects.

An existing split or join on a platform longer than its final Edge can also be
retained during a later edit at a different station. Review the same saved
event. The writer compares the directed platform, head and tail positions,
connected Routes and protection on both archive versions. Track chainage can
change with an earlier origin move while the event remains in the same place.

For an Itinerary that has distance-based safety margins, explicitly set
`map_itinerary_safety_margins: true` on that `endpoint_rebindings` entry.
The profile on retained track follows the change in origin chainage. A
trimmed origin inherits the former active margin at the cut, including the
original order of duplicate rows at that exact point. An extended prefix
uses the native zero default before the first mapped row. An extended suffix
inherits the last margin. Mapping requires finite, sorted rows inside the
old route and every native margin object to have a single owner. The report
contains both row sets and the old and new chainages of the common span.

Use the saved geometry action `create_main_signal` to prepare a free
directional End in a connected project. Fetch a separate reviewed Route if
the chosen station boundary needs a new approach or departure segment.
In the Reading case, an exact 500 m station prefix was added for the new origin
and a separate 500 m suffix was added for the new terminal. Both candidates were
then saved through the same endpoint rebind action.

Use `main_signal_relocation` with `signal_id` and `direction` when a saved
main signal and the paired reference must move together along one exact
adjacent Edge in the same station. In this mode the writer derives the
affected Route and Path bindings from the original archives. Supply the same
witness and Course reviews. The transaction verifies the new signal owner,
the directed station occurrences and the full Destination catalog.

Preview is the default. Provide a fresh `target_directory` and set
`preview_only: false` to publish the full selected-run closure with rebound
paths. For subsequent acceptance, compare both the new station reference and
the observed stop and onward run in original OpenTrack. A queue entry can
optionally request `endpoint_signals` with the Course and both native main
signal IDs. It checks the frozen origin and terminal End, then verifies the
signal identities and chainages in the bound original `.sigpos`. The runtime
Course expectations verify arrival and the terminal head position separately.
For a connected chain, use `endpoint_links` in the queue request and include
terminal expectations for all participating Courses. Original-run checks bind
both trains' signal, timetable and movement files with the native message log.
They check arrival, successor activation at zero chainage, stationary time, and
departure, and reject an itinerary fallback during activation.
