# Bounded English three-station recipe

Paired candidate: `0.33.1-zeroaccept1`, Python 3.13.x. This recipe is a linear
three-station, one-train forward journey: originate, pass the middle, stop at the
last station. Use one `.opentrack` file per station and six common catalogs.
It is not an arbitrary railway design or certification of every registered tool.
The underlying 2–12 station input bound is a data-layer range; this native
acceptance case has three stations.

Native actions below may be performed by the agent or by the user with the
agent's guidance. If desktop control is unavailable or unreliable, use
[user-guided operation](user-guided-operation.md): the agent prepares and checks
the data, then guides small native steps and evaluates the returned evidence.

1. Select six authorized, exact-SHA donor resources: header, native shapes,
   Depot, Train, Course and Timetable templates. A new graph does not remove the
   need for native format resources and explicitly accepted vehicle physics.
   Preserve donor bytes; never copy an old completed railway as the new design.
2. Declare three new station IDs/names, new Engine/Category/Train/Course/Path/
   Itinerary names, planned visits, a same-day window and an explicit fresh
   target. Use printable English/ASCII for every new native name and path. New
   Engine/Category output names are checked before donor reads. Existing template
   names remain exact opaque lookup identities. Use real JSON booleans.
3. Call `opentrack_initialize_station_documents_project` with
   `preview_only=true`. Use the exact [station-document schema](station-documents-project.md).
   Check three document paths, ten candidate members, one station per file,
   connectors, the continuous Path/Itinerary, vehicle length and final-only stop.
   A preview is not a saved project.
4. Keep the same declaration, bind every execution/document path to the actual
   new target, and set `preview_only=false`. Confirm a committed publication
   receipt and independent saved-byte readback of all ten members. Then use
   multi-document inspect and preflight with a complete actual inventory.
   Save and preparation tools do not start OpenTrack.
5. When native operation is requested, operate directly or guide the user to
   open Preferences in original English
   OpenTrack 1.7, Import that exact `.run`, and confirm all six catalog paths:
   `DestInfoFile`, `DepotFile`, `TrainFile`, `CourseFile`, `StationFile` and
   `TimetableFile`. Confirm the three infrastructure paths too. Merely opening
   three drawings does not replace an older active station or vehicle catalog.
6. Complete the native list refresh **before Start**: use the original
   **Open** command and then **Cancel**, then open **Itineraries (Ctrl+5)**.
   In the tested case this triggers the original controller's
   `updateWhenInvisible:1` aggregation. Confirm `ZF_TRIP`, length `3200`, active
   Paths `1/1` and Routes `2`. Move an overlapping panel if necessary to read
   it. This is an original UI refresh; it does not change Train data or require
   an injected bridge. Check the actual station identities Alpha/Bravo/Charlie
   in the Station Inspector, not a stale list.
7. Save the three documents, close/reopen the project and repeat the six-catalog
   and Itinerary checks for the reloaded project. In the accepted case all three
   real station double-clicks updated the original Inspector without the guard.
   Use ASCII for any text entered in the original app.
8. Preserve input hashes and native outputs before running or saving. Separately
   verify departure, passage, crossing both file boundaries, terminal zero speed,
   one stop, Course completion and simulation-window completion. Save/reload and
   a run after saving are additional checks. Record the actual Delay Scenario.
   Do not treat a configured end time or successful process exit alone as proof
   of every completion step.

Use a UTF-8 request file through the paired bridge:

```text
python -B <SKILL>/scripts/ot.py --root <DATA_ROOT> call opentrack_initialize_station_documents_project --args-file REQUEST.json
```

The accepted declaration used `ZF_A/Alpha`, `ZF_B/Bravo`, `ZF_C/Charlie`,
`half_link_length_m=300`, Course `ZF1001`, Train `ZF_TRAIN_1`, Path `ZF_MAIN` and
Itinerary `ZF_TRIP`. Reference-point distances are 0 / 1,600 / 3,200 m; planned
visits are 08:01 / 08:04 / 08:07, with only the last marked stop. Its window is
08:00–08:12 with step `0.2`. Two fixed 500 m approaches per station and the
selected proxy vehicle physics are part of this finite profile.

This **bounded native case passed**: initial CLI/MCP publication and independent
ten-member comparison, all three GUI documents loaded, original Save/reload,
Alpha/Bravo/Charlie double-click updates, and the refreshed GUI simulation through
the 08:12 end window. Independent save review found only root frame/view/visible
rectangle changes, preserving all 23 models per document and Route/Path/Itinerary
semantics. The optional guard was not loaded.

Keep the attempts separate. The first stock batch run produced **46** files and
used Delay Scenario 1. GUI run 2 produced **43** files and one Origin warning
because the live Itinerary list used a temporary fallback. That failed warning
check is retained. After the native Open → Cancel / Ctrl+5 refresh, GUI run 3
produced **43** new files with **zero WARNING/ERROR**, both boundary crossings and
the same physical results. The ten saved inputs remained unchanged through that
run; all 72 protected originals matched their hashes. No Train edit was used to
remove the warning. The three-file output-count difference is the batch run's
additional global timetable exports, not three missing GUI-run outputs.

The final GUI Current Time and End of Simulation at 08:12, with seven green
message rows, were observed in original CUA image returns and separately reviewed
visually. The native disk files have no durable End event. The ordinary GUI process
remained alive, so no exit code is used as GUI completion evidence; no PNG was
fabricated. This certifies the stated three-station case, not every tool or every
2–12 station input, arbitrary editing, fleets or calibrated vehicle physics.

| Event | Declared plan | First native observation |
|---|---|---|
| ZF_A departure | 08:01:00 | 08:01:00 |
| ZF_B passage | 08:04:00 | 08:02:32 |
| ZF_C arrival | 08:07:00 | 08:03:58 |

The terminal arrived early and remained stopped; the planned Course end was
08:07:00. This verifies the bounded journey and stop, not exact timetable
adherence or zero-delay operation.

Native simulation can write actual timetable clocks and native catalog state.
Use before/after snapshots and distinguish raw serializer sharing from semantic
changes. A post-run project may correctly fail fresh-initializer checks that
require unset actual results. Do not rewrite live results merely to satisfy those
fresh-generation assertions. Private donors, generated native projects and the
commercial executable are not redistributable Skill contents.
