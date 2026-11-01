# Historical synthetic three-station demo constructor

**Current release status:** `opentrack_create_demo_line` is registered for an
explicit `LEGACY_GEOMETRY_DISABLED` rejection; its old whole-project writer is
quarantined. The remaining text records that constructor's historical template,
physics and output contract, not a ready current creation path. Do not bypass
the guard or treat the demo's names, station count or speeds as general design
requirements. Choose a matching current initializer/profile or original workflow.

`opentrack_create_demo_line` is a template-based constructor within this Skill/API. It currently requires the audited BJTU1/BJTU2/BJTU3 source and BJN/JNW/NJN station namespace. It does not create arbitrary new interlocking topology or start OpenTrack.

## Call

```powershell
py -3.13 -B D:/opentrack/OTAI/server.py call opentrack_create_demo_line --args-file D:/opentrack/OTAI/examples/nanjing-shanghai-400.json
```

The default model is Nanjing South (NJN) – Suzhou North (SZB) – Shanghai Hongqiao (SHH), using **synthetic** 200 km and 100 km sections. Native names and RTF label text are ASCII for the legacy runtime; the instructions/CSV/metadata include Chinese display names. Station name collisions are resolved in one string-identity pass, so old BJN→new NJN does not subsequently turn into SHH. Connector document names and Route/Path/Itinerary references are updated together.

An existing target is rejected with `PROJECT_EXISTS`; choose a fresh project_name for another variant. No apply flag or application exit is required to create a fresh independent project. It never changes BJTU, global preferences or root OTTemp catalogs.

## Speed and service configuration

- `maximum_speed_kmh`: default 400; `station_speed_kmh`: default 160.
- A separate `DEMO_EMU_400` vehicle and Engine are cloned. The force envelope is `min(max_force, nominal_kW * 3.6 / kmh)` with explicit points through 400; brake points also cover the complete range.
- Default engineering proxy: 472 t, 209 m from the source, nominal 16 MW, 320 kN envelope. This is not manufacturer data or a validated adhesion/traction model.
- Default 8 departures each direction, first 06:00, reverse offset 5 minutes, requested interval 40 minutes and middle dwell 3 minutes. Resource checks may increase the actual interval.
- Only the four existing principal interstation Edges absorb distance changes. Every defined Path, including alternatives and reverse paths, must retain the selected section totals. No vertex/signal is added.
- Saved numerical Step is 0.1 s and playback ratio 30:1. Verify the actual Simulation controls separately when the user runs the application.

## Verification and limits

`opentrack_check_demo_plan` reads the selected native inputs afresh. It checks service/vehicle/itinerary binding, three-stop order, timetable offsets, requested minimum headway, initial body, route resource overlap, all Path distances and diagram distance/time consistency.

The estimator adapts the existing OTUndo Strahl proxy: 25 m integration, stored force curve capped by nominal power, 0.7 m/s² braking, 15% running allowance, rounded station times, 180 s advance reservation and release/gap margins. It includes the 209 m body behind the starting signal. It does not invoke native dispatch, adhesion or resistance methods; it cannot certify actual speed, collision freedom, terminal clearance or capacity. The speed CSV contains kinematic estimates and padded planning times, not native outputs.

The project contains a unique versioned six-catalog bundle, three renamed infrastructure documents, three native corridors, `.run`, `timetable.csv`, speed profile CSVs, `demo-plan.json` and Chinese loading instructions. `opentrack-project.json` selects its default run. Keep the report's source digest and `native_simulation_verified:false` intact when describing evidence.
