# Export original RailML 2.2 timetable data

```json
{
  "project":"<project>",
  "format":"railml_2_2",
  "course_ids":["G9001","G9002"],
  "railml":{
    "dataset_name":"Example",
    "planned":true,
    "published":true,
    "only_active":true,
    "existing_stations_only":true
  }
}
```

Use `opentrack_export_timetable`. Review hashes, emitted counts, skipped Courses
and the complete `manifest`. All saved Stations and formation summaries are
included, as in the original writer. Only timetable Courses are selected.
No input archive is modified. RailML timetable import remains incomplete.

All time choices false still emits scheduled times. Published copies planned
strings. Calculated saved strings require both `railml.calculated:true` and
`saved_actual:"as_valid"`; this is an explicit assumption about unavailable
runtime validity. Default omission can leave calculated-only output without times.

Optional `station_filter` supports `uppercase`, `replace_first`, `first_string`,
`replace_last`, `last_string`. Replacement counts use current length, zero
inserts/appends, and original trailing-space removal retains the first character.
Existence filtering uses the source signs. Review ID collisions and empty signs.

The original cross-station connection bug writes an OCP ref using a trainPart ID;
the file preserves this behavior and warns. Other missing/wrong-type references,
negative day omissions, nil maximum wait, and data loss appear in the manifest.
This format stores summaries rather than full vehicle/Itinerary/control data.
Unprepared stock metrics assume zero transient delta mass, with exact integer
dimensions below 2^24; unsupported wide precision rejects instead of guessing.

Use `opentrack_inspect_railml_timetable` on the returned file for paged field and
reference review. This verifies the independent XML representation, not XSD or
original native parser acceptance. See `OTAI/contracts/timetable-railml-export.md`
in the package for exact function evidence, bounds and remaining parity limits.
