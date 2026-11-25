# Export original RailML 2.2 timetable data

```json
{
  "timetable":{"path":"<project>/OTData/service.timetable","sha256":"<64 hex digits>"},
  "courses":{"path":"<project>/OTData/service.courses","sha256":"<64 hex digits>"},
  "stations":{"path":"<project>/OTData/service.stations","sha256":"<64 hex digits>"},
  "trains":{"path":"<project>/OTData/service.trains","sha256":"<64 hex digits>"},
  "depot":{"path":"<project>/OTData/service.depot","sha256":"<64 hex digits>"},
  "course_ids":["G9001","G9002"],
  "preview_only":false,
  "target_path":"<fresh path>/service.railml",
  "railml":{
    "dataset_name":"Example",
    "planned":true,
    "published":true,
    "only_active":true,
    "existing_stations_only":true,
    "connection_ocp_reference":"station"
  }
}
```

Use `opentrack_export_native_railml_220_timetable` with the current archive codec.
The timetable, Course, Station and Train files belong in the same saved catalog
directory. Supply the matching Depot for formation dimensions. The output is
published to the selected fresh path with source and saved output hashes.
All Stations and formation summaries are included. `course_ids` selects which
saved timetable Courses are exchanged. You can save the scheduled clocks and
connections back into a fresh timetable through the mapped import tool.
[Mapped RailML timetable import](native-writing.md#railml-22-时刻表)

All time choices false still emits scheduled times. Published copies planned
strings. Calculated saved strings require both `railml.calculated:true` and
`saved_actual:"as_valid"`; this is an explicit assumption about unavailable
runtime validity. Default omission can leave calculated-only output without times.

Optional `station_filter` supports `uppercase`, `replace_first`, `first_string`,
`replace_last`, `last_string`. Replacement counts use current length, zero
inserts/appends, and original trailing-space removal retains the first character.
Existence filtering uses the source signs. Review ID collisions and empty signs.

By default, `railml.connection_ocp_reference: "original"` reproduces the original
cross-station writer's trainPart ID in the OCP field and reports a warning.
Use `"station"` to emit the target Station's actual OCP ID for a mapped
cross-station round trip. The target Station must exist in the saved catalog.
Select all target Courses needed for the round trip, and check warnings for
unresolved references, negative day omissions and nil maximum waits.
Formation dimensions are exported as summaries. Course itineraries, control
settings, and complete vehicle definitions stay in their original catalogs.
Unprepared stock metrics assume zero transient delta mass, with exact integer
dimensions below 2^24.

The CLI validates the published XML structure and connection count on readback.
Full XSD and original software import are separate acceptance checks.
[Official RailML 2.2 timetable schema](https://www.railml.org/files/download/schemas/2013/railML-2.2/documentation_xs3p/timetable.xsd.html)
[Original OpenTrack function and export contract](../backend/OTAI/contracts/timetable-railml-export.md)
