# Generate a network from explicit specifications

Use `opentrack_generate_current_network_archives`, not the blocked legacy
`opentrack_create_project` / Geometry draft path. This one operation generates a
new current-format network document and itinerary catalog without reusing an old
railway movement. It is a partial archive bundle, not a simulation-ready Project.

1. Securely inspect four source roles and bind their exact SHA-256 values:
   header_document, shape_archive, template_document, template_dest_catalog.
   The same current document can supply header and type-template roles.
2. Give a complete explicit network spec, named main signals, real End-sequence
   Routes, Route-name Paths, and finite Path-name Itineraries. The MCP schema is
   authoritative. Coordinate crossings do not connect tracks. Keep actual Edge
   length/radius/gradient/speeds separate from diagram coordinates.
3. Use preview first. Review generated counts and each stage, especially repeated
   Path occurrences, real filename catalog references and the supported profile.
4. Save only to a fresh target directory. The document and catalog commit together;
   inputs and existing output directories are never overwritten. A postcommit
   error requires inspection, not an overwrite retry.
5. Confirm source hashes unchanged and independent archive readback. Never claim
   trains ran, a complete project exists or a one-day simulation passed.

The header's opaque licence/registration state is preserved, never forged or
expanded. Geometry is rebuilt from the spec; explicit current Path/Dest templates
supply validated shape only, not old movement objects. Detector-enabled topology,
connectors, arbitrary signal types, single-Path cycles and automatic train/station/
timetable/run generation remain outside this tool.

For a ring, split the finite journey into simple Paths and provide an occurrence
sequence such as P0,P1,P0,P1. Do not deduplicate it, set a single infinite-loop flag,
or fake a closing endpoint without an actual connecting Edge.

The full contract is packaged as `archive-contracts/wave9-network-generation.md`.
