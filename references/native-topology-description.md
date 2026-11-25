# Original topology descriptions

Use the local tool schema to select sources by path and SHA-256. Both commands
preview the file name, digest and count by default. On Windows x64 with NTFS,
set `preview_only: false` and provide a fresh `target_directory` to save and
read the file back. The exported UTF-8 text follows the original
`OT_topo_text` record layout and identifies OpenTrack Skill as its producer.

## Worksheet

Use `opentrack_export_native_worksheet_description` with one current
`.opentrack` in `worksheet`. The `.desc` lists model IDs and types in
worksheet archive order, Safety Element members, Edge endpoints, paired
vertices and external connectors. The export receipt lists any unfamiliar
graphic classes separately.

## Routes, Paths and Itineraries

Use `opentrack_export_native_movement_descriptions` with the source
`project_run` and all its `documents` keyed by exact filename stem. Use
`dest_catalog` to check the bound `.dest` against the saved worksheet
Itineraries. Select `itineraries`, `paths` and/or `routes` in `sections`.
The file suffix follows the original section order, for example
`.IR.desc` and `.IPR.desc`.

The export uses the existing saved movement graph, including continued
Routes and finite ordered Itineraries. `detailed_routes` includes reservation
and release values. `detailed_itinerary_profiles` adds kilometre positions,
directional grades, radii, speeds and signal labels. Speed columns follow
the run's TrainType order. Supply the bound `station_catalog` to show
station names alongside codes in the track profile.

These commands export descriptions for inspection and comparison. To move
editable objects between projects, use the applicable native archive
import or infrastructure exchange commands. Format coverage was validated
against the installed exporter logic and saved projects. The original
application's text export dialog remains to be compared.
