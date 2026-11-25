# Rebind booked Courses to reviewed platform tracks

Use `opentrack_rebind_native_course_platforms` to move an existing Course
to a different saved Itinerary or change its ordered platform preferences.
Supply the complete SHA-bound `source_project` inventory and select each
Course by `course_id`, its `expected_itineraries`, and the new
`itineraries` in dispatch priority order.

For every changed primary platform occurrence include the timetable row
`index`, exact `station_sign`, and its directed `from_reference` and
`to_reference`, each as `[worksheet, End ID]`. Indices distinguish
repeated visits to one station. To move a booked row to a different Station
record, supply its `target_station_sign`. Both the native station catalog
and the candidate Itinerary must contain that station. Each option must
serve the resulting row sequence and pass the saved timing, direction,
stopping location and formation checks.

At a reviewed row, `track` defaults to `preserve_constraint`. This retains
an unrestricted row or translates an explicit track constraint to the
matching native track. Use `pin` to store the single physical track shared
by the new options. Use `unrestricted` where genuine alternate platform
options occupy distinct tracks. The first-row track comes from the native
departure edge. An arriving train uses its saved stop edge or station
approach. The Course retains its stock, dwell and timetable clocks.
Changing the station code updates the affected owner and target references
of existing Connection6 records, including incoming waits from other
Courses. The connection types, waits and Course IDs retain their values.
Move both ends of an interval-relative timing reference to the same new
station. A repeated target that could resolve to different station codes
requires review before the migration.

Move linked reversing or continuing terminal and origin Courses together
if their physical transfer point changes. The new pair must retain the
original same-direction or opposite-direction relationship.

For an existing join or split use `composition_events` with `kind`,
`main_course`, `other_course`, `station_sign` and the exact
`main_visit_index`. Supply `target_station_sign` on the event when its
station code changes. Include the whole saved formation sequence for the
participating Courses in timetable order. The tool reads both existing
Connection6 records and verifies the original and new working locations.
Every Itinerary option must pass the formation checks. A split may use
different directed platforms when each main Itinerary ends its arrival
Route and starts its departure Route at the actual stopping End. Supply a
child Itinerary originating at each such End. The original looks at the
main train's arriving Route before a fallback Route and chooses the first
child Itinerary starting at a matching End in its saved priority order.
Each arriving Route must expose just its own child origin, including
the actual related Ends across connectors. The tool checks the successive
train lengths against each receiver option's directed stopping edges,
including visits after a split or a join.

A join defaults to `occupied_entry: "use_target"`, using the target
arrival Route and signal's saved authorization. Use `"copy_previous"` to
copy the existing authorization and speed or waiting options to the new
arrival Route and its entry signal as part of the same native project save.
A continued Route and its receiving fragment are saved together.
The target approach cannot acquire a new setting for unselected booked
Courses. The original approaches must agree on the settings when using
`copy_previous`. The tool checks occupied entry for each supplying approach.

For a join with several platforms, include receiver and supplying
Itineraries for every directed platform, each at the actual stopping
reference. The supplying Course ends at the join. The receiver leaves
from that reference on its next Route. Each Course's platform approaches
must branch from a common directed junction, where the original can
change its route sequence to the preannounced platform. The tool checks
the order in which the native change list finds these Routes and refuses
an endpoint or actual-related End that also identifies another platform.
Itinerary preferences on the two Courses may differ. Confirm the actual
choice and physical coupling in the original run after publication.

The default preview returns physical track, stopping length, affected rows
and member hashes. Set `preview_only: false` and provide a fresh
`target_directory` to publish the selected native run and its dependencies.
Use original OpenTrack after publication to verify actual dispatch,
reservation, the stop and completion.
