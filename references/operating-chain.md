# Single-document pass operating chain

Use `opentrack_preview_operating_chain` for explicit infrastructure, vehicle definitions, Courses, planned timetable rows and a bound `.run`. The eight members are one document, six catalogs and one run. The default previews them in memory. Set top-level `preview_only=false` with a fresh `target_directory` on Windows x64 local NTFS to publish the project and empty output directory.

## Explicit inputs, not inferred operation

- `infrastructure` is the full single-document infrastructure-chain request. Provide point stations at both itinerary ends and every planned visit. A previous example containing only middle station B cannot be silently supplemented with A/C.
- Provide SHA-bound Depot/Train/Course/Timetable donors and exact template identifiers. Header/shapes donors remain in the nested infrastructure request.
- `vehicles` uses an explicitly chosen single Engine and no trailers. Physical curves/category definitions are inherited only when explicitly accepted. `maximum_acceleration_mps2` is m/s², `braking_delay_s` seconds, and `braking_release_speed_kmh` km/h. This does not recalibrate a train or create a physical fleet circulation plan.
- `train_types` is ordered. `speed_type` selects its name, whose index must exist on every edge, including an unused branch. Do not reorder names or drop a branch to pass validation.
- `plan` explicitly names Course, Train, Itinerary and ordered visits. Each visit supplies `station_sign` and integer `absolute_seconds` from day 0; 86400 means next-day midnight. No separate arrival/departure, dwell, stop or turnround fields are supported.
- `run_configuration` must explicitly use Windows path style. The infrastructure document path must equal the normalized execution root plus `/OTDocuments/<document_name>.opentrack`. For publication the execution root must match the actual target directory.

## Semantics and rejection

This domain is **pass-only**: arrival equals departure, dwell is zero and stop flags remain unset. Planned station order must equal the generated itinerary's station sequence. Times must increase, satisfy the existing edge-limit/vehicle-vmax lower bound, and lie inside the explicit run window. The lower bound ignores acceleration and conflicts: passing it is not a feasible dispatch plan or measured travel time.

Reject a missing endpoint station, unknown train/itinerary, mismatched native root, missing speed index, invalid ordering/window or stop request. Do not repair the user's plan implicitly. The former fields belong to separate explicit modeling decisions; stop/turnround requires a separately proven domain.

The preview returns `saved=false`. A successful publication returns `saved=true` and a separate readback receipt for the eight members and run bindings. Native simulation and physical fleet circulation require their own evidence.
