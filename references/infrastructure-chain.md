# Single-document infrastructure chain

Use `opentrack_preview_infrastructure_chain` when the request describes one explicit document and needs topology, main signals, Routes, Paths and Itineraries together. This is one in-memory transaction, not a sequence of temporary file saves.

## Required inputs

- Existing authorized `header` and `shapes` donor files with exact inspected SHA256. New railway objects are generated; a header/type donor is not proof the resulting railway is operational.
- `document_name` and an explicit authoritative `document_path`; their basename must match. This is a saved native reference, not a local output destination.
- `network` with explicit vertices, sides and edges. A crossing on the screen does not imply connectivity.
- Explicit main signal attributes and their vertex/side. Only the supported fixed raw main-signal profile is generated.
- `routes` with ordered directed End references, release grouping and reserve-previous setting. Do not infer these from station names or geometry. Internal main signals require the route to be split rather than ignored.
- Named `paths` selecting ordered new Route names, and named `itineraries` selecting ordered new Path names. Both must be continuous and simple; no implicit repeated/circular movements.
- Optional `stations` point bindings. Point stations are not stopping areas, platforms or depot operating functions.

The schema forbids extra multi-document/Connector fields. Do not remove them or silently substitute a simpler plan to make a request pass. Choose the separate finite-topology preview for connectivity-only multi-document work; do not claim its result already has routing or traffic.

## Inspect the result

The tool returns three candidate member hashes and sizes: one document, Station catalog and DestInfo catalog. Its report includes exact generated IDs, directed itinerary end keys, stage receipts and static reference checks. `saved=false` and `operating_ready=false` remain true limitations: candidate bytes are not exported, no run/vehicles/timetable are generated, and OpenTrack has not been executed.

A hash-only preview receipt is not an artifact to hand to the original application.
This preview API has no publication output. If the task needs saved files, select
a complete initializer/editor/publication workflow whose input and persistence
contracts actually cover the design. Do not feed this receipt to an unrelated
publisher or claim that another workflow has saved this preview.
