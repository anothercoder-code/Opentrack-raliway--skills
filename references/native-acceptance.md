# Native acceptance of 0.31.0-winrelease1

The 2026-10-29 Windows acceptance used the original English OpenTrack 1.7,
an explicitly generated empty topology, the `single_document_final_stop`
profile, and an actual eight-member publication. It is a finite acceptance
case, not certification of all 176 functions or calibrated railway dynamics.

## Recorded workflow for this finite case

Use current schemas when adapting this procedure. The station count, six-resource
profile and observed UI refresh below belong to winrelease1; they do not select
the design or required clicks for every future project.

1. Use input planning and six authorized native format templates. Supply explicit
   new vertices, edges, stations, signal directions, Routes, Paths, Itinerary,
   vehicle inheritance and timetable. Empty topology means no inherited track;
   it does not remove the format and physical-template requirements.
2. Preview `opentrack_initialize_project`. Review candidate structure, references,
   unsupported operations and physical inheritance. Bind the run execution root
   and document path to the intended fresh target directory.
3. Publish using that tool, `preview_only=false` and the exact target. Read the
   actual saved members and verify their returned SHA-256 values. A preview's
   `saved=false` candidate receipt remains distinct from the publication receipt.
4. In original OpenTrack, load the saved `.run` and its `.opentrack` document.
   Confirm all six active databases, topology title, used Courses, output path,
   start/stop time and step. Open **Tools > Itineraries (Ctrl+5)** and confirm the
   expected Itinerary is listed before starting the first simulation after import.
5. Run in the native Simulation panel. Inspect Messages and actual `.tt`, `.vt`,
   Course statistics and protocol. Confirm departure, passage, physical terminal
   stopping, Course completion and Simulation window completion separately.
   Preserve input hashes and dated output snapshots.

## Observed result and first-import warning

The new ReleaseLine case had five vertices, four edges, three stations, three
main signals, two Routes, one Path, one Itinerary and one Course REL1001.
Native results: departure 06:01:00, intermediate passage 06:02:50, terminal
arrival 06:04:34; the last two speed records were zero, with one station stop,
zero route brakings and zero signal stops. The GUI reached 06:12:00 and displayed
End of Simulation. All eight published input hashes remained unchanged.

The first run displayed `Train not starting at Origin of Itinerary`. Original
`OTSim.go` emits this warning when it cannot find the local Itinerary in its
global inspector list and successfully constructs a temporary one from external
DestInfo. In this recorded case the remedy required no train-length or coordinate edit.
Opening the original Itineraries Inspector and rerunning the **unchanged** saved
project removed the warning. The exact reason the first import failed to collect
the embedded Itinerary remains unproven. Retain the observation as a diagnostic
option, not a mandatory refresh or a universal explanation of later warnings. If a fresh case still warns, investigate actual identities and native
inspector state instead of adding arbitrary track or suppressing the warning.

The original text Messages file omitted the final End of Simulation event in
both runs; GUI evidence records that event separately. The protocol also lists
the empty Untitled document created at application launch. Only REL1001 and the
published ReleaseLine topology contributed to the accepted journey.

The source-tree evidence is under `integrations/winrelease1-20261029/evidence`
on the acceptance machine. The public package includes instructions and code,
not the six private donor files or the proprietary OpenTrack executable.
