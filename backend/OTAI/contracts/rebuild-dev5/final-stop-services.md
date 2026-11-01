# Finite single-journey final-stop service catalogs

`generate_final_stop_services(inputs, *, area_specs, course_template_id, timetable_template_key, document_name, plan, speed_type='Reihe R')` accepts eight immutable byte sources: courses_template, timetable_template, trains, depot, stations, document, dest, run_template. It returns only generated courses/timetable bytes and a static receipt, not files or native runtime results.

Plan contains 1–100 independent Course definitions, each with exactly course_id/train/itinerary/visits. Visits have exactly station_sign/absolute_seconds/stop; stop is a strict boolean. Each selected itinerary has 2–100 unique station occurrences, no intermediate or origin stop, and only the last stop=true. Arrival equals departure and dwell is zero. This is not an intermediate dwell, subsequent departure, turnround or fleet circulation model. Multiple Courses do not imply multiple physical vehicles or conflict-free use of an area.

This module does not call the pass-only generator and toggle its flags. It independently constructs planned Course/Timetable records with the existing low-level factories. Existing five-visit terminal-domain guards are unchanged.

## Required real saved-data associations

Area reader validates known Document4 station/End/Edge/signal geometry and exact supplied area specs. Station catalog signs, names and timing marks must agree. The actual selected itinerary is traced through saved Path/Route references; type1 ordinary entry contributes no extra station occurrence, type2 reference does. The last occurrence must use the selected area entry immediately before its exact exit/reference End; merely sharing a station name is insufficient.

A single Engine at position 1 and no trailers is required. Engine maximum speed and length come from the real depot object, not a declared count or supplied train length. `ceil(length)` must fit the actual stopping-area edge. The Category stopAtEveryStation bit is rejected because it contradicts an explicit only-final-stop plan. Per-segment planned time must meet the necessary edge-limit/Engine-speed bound; acceleration, braking, conflicts and physical feasibility remain unproved.

## Construction and independent readback

Templates are explicit and connection-free. Temporary exemplar records are removed from both output catalogs. Fresh decode validates exact Course/Train/Itinerary names, dictionary Course#index keys, station order, index/maxIndex, planned clock/day, flags 2 for pass and 3 for final stop, dwell zero, empty connection arrays, and actual-time HH:MM:SS/day0 reset. No input bytes change. Run-window binding belongs to the outer whole-project composer.

Coverage: M2.1.3/M2.1.4/M6.1/M6.2/G05/G06/A05 are bounded generation/readback only, not complete requirements. No modify-in-place, export, original execution or actual stopping observation is claimed. The original software owns dynamics.
