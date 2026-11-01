# Inspect a RailML 2.2 timetable

Use `opentrack_inspect_railml_timetable` before planning RailML timetable import.
It reads XML and selected project catalogs without writing a draft or starting
OpenTrack. RailML timetable export is available through [the export tool](railml-timetable-export.md); import is still incomplete. Proprietary
OpenTrack timetable XML and rolling-stock RailML are separate capabilities.

```json
{
  "project":"<project>",
  "file_path":"<RailML 2.2 UTF-8 XML>",
  "section":"summary"
}
```

Inspect `selection_inventory`, counts and `diagnostic_counts`, then request
`stations`, `formations`, `train_parts`, `trains`, `train_groups`, `rows`,
`times`, `references`, or `diagnostics`. Follow `next_offset` until `has_more`
is false. `train_type` filters only trains, `scope` only times; other pages and
global counts remain unfiltered. Null selects all; empty selects missing/empty
attributes. Raw time/day text is not converted or certified.

The original station attribute is misspelled `abbrevation`. Empty higher-priority
attributes plus a name can depend on native dictionary iteration; a null
projection means unresolved. Non-ASCII station conversion also remains
unverified. Compare exact saved station/formation/Course names before binding.
Review missing/duplicate references, parts declared after use, shared-part alias
risks, boundary mismatches and connection part-reference warnings. Static
candidate Course IDs/row counts are explicitly not native import results.

Input is bounded to 2 MB with paged details. DTD/external resources are not read
and entity declarations reject. Prefix normalization, schema/native parser
acceptance and native type/scope menu ordering are not certified. This tool
does not establish that a timetable is ready for native import or simulation.
The packaged `OTAI/contracts/railml-timetable-analysis.md` defines the full scope.
