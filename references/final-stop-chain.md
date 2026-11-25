# Explicit final-stop area chain

Use `opentrack_preview_final_stop_chain` only for a single-document, forward, single journey whose **last** station is an explicitly modeled stop. This separate domain does not change pass-only defaults.

A stopping area is not a new invented archive object. It binds the ordinary entry End pair (station type 1), the reference/exit End pair (type 2), the same StationModel, a real directed track Edge and its exit signal. Supply entry, exit, edge key, actual length in metres, direction and exit signal name. The area must be unbranched under the current finite reader, and the actual single Engine length (rounded up to whole metres) must fit. Both exit halves require existing explicit topology: never add a fake continuation track to make validation pass.

The ordinary entry does not create another timetable visit. The origin and any intermediate stations pass; exactly the final visit has `stop=true`. Requests contain absolute planned seconds, not measured arrival data. Arrival equals departure, dwell is zero, actual timestamps remain empty placeholders and actual day offsets are zero. This models a terminal stop declaration, not waiting and subsequent departure, reverse stopping, turnround or train-set circulation.

Reuse the explicit six donor sources, vehicle specification, ordered speed types and Windows run namespace from the operating-chain contract. Station sequence, selected approach, exit signal, length, Engine binding, timetable key/order/day/flags and all eight member references must agree. Merely setting a timetable stop flag without the physical saved-data area is rejected.

Preview is the default. Set top-level `preview_only=false` with a fresh `target_directory` on Windows x64 local NTFS to publish the eight members and the empty output directory. The run execution root and document path must match that target. The published receipt verifies saved bytes and bindings. Native motion, stopping and physical circulation require separate evidence. Use the actual stop location, direction, area length, signal and course arrival plan for the selected layout.
