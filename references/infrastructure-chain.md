# Single-document infrastructure chain

Use `opentrack_preview_infrastructure_chain` to build explicit topology, main signals, Routes, Paths and Itineraries for one document. Preview is the default. Set `preview_only=false` and supply a fresh `target_directory` on Windows x64 local NTFS to publish one verified directory.

## Required inputs

- Existing authorized `header` and `shapes` donor files with exact inspected SHA256. New railway objects are generated; a header/type donor is not proof the resulting railway is operational.
- `document_name` and its authoritative `document_path`. For publication the path must equal the actual target's absolute path plus `/OTDocuments/<document_name>.opentrack`.
- `network` with explicit vertices, sides and edges. A crossing on the screen does not imply connectivity.
- Explicit main signal attributes and their vertex/side. Only the supported fixed raw main-signal profile is generated.
- `routes` with ordered directed End references, release grouping and reserve-previous setting. Do not infer these from station names or geometry. Internal main signals require the route to be split rather than ignored.
- Named `paths` selecting ordered new Route names, and named `itineraries` selecting ordered new Path names. Both must be continuous and simple; no implicit repeated/circular movements.
- Optional `stations` point bindings. Point stations are not stopping areas, platforms or depot operating functions.

The schema forbids extra multi-document/Connector fields. Do not remove them or silently substitute a simpler plan to make a request pass. Choose the separate finite-topology preview for connectivity-only multi-document work; do not claim its result already has routing or traffic.

## Inspect the result

The three members are one document, the Station catalog and the DestInfo catalog. The report includes generated IDs, directed itinerary end keys and reference checks. A successful publication sets `saved=true` after disk readback and preserves both source files. This operation supplies infrastructure only. Vehicle catalogs, timetable, run configuration and native operation require a separate workflow.
