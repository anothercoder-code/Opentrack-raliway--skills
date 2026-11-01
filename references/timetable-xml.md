# Original timetable XML exchange

Use `opentrack_export_timetable` with `format:"opentrack_xml"` for original
proprietary XML. This is separate from rolling-stock RailML and does not yet
implement RailML timetable import/export. Inspect the full export manifest for
omitted fields and original importer quirks. XML is not a lossless database backup.

```json
{
  "project":"<project>",
  "timetable_operations":[{
    "kind":"import_timetable_xml",
    "file_path":"<exported XML path>",
    "existing":"replace"
  }]
}
```

Use exactly one `file_path` or `content`. Reject is the default for existing
timetables. Replace recreates imported Courses' rows; other Courses remain.
`clear_existing_timetables:true` explicitly clears the whole timetable, including
with `<timetable/>`; Course definitions remain. Editor undo can restore it.
New IDs require exact Course `templates` or `default_template_id` with the right
formation and direction. `create_unbound_courses:true` creates invalid drafts
for later binding. Import writes appear in generation counts and full diffs.

Native connection attributes are read from dictionary keys, not XML text order.
Conflicting `connectionPlace=home/station` plus `connectionTimeType` rejects by
default. Choose `connection_attribute_order:"time_type_then_place"` to retain
the place or `"place_then_time_type"` to apply the original time-type location
reset. The result warns that Foundation dictionary order is not reproduced.
Do not reorder XML attributes expecting this to select the behavior.

Export omits actual times by default because native validity is unpersisted.
Explicit `saved_actual:"as_valid"` exports saved actual strings as valid=yes and
reports the assumption. Import retains original actual-string carry, actual-day
assignment to planned days, seconds arrival/departure asymmetry and connection
meet/dispo quirks. Review warnings before using the draft operationally.

Import snapshots UTF-8 bytes, resolves no DTD/external resource and rejects entity
declarations. Current ASCII name/text contracts and shared batch limits apply.
Review validation, `timetable_changes_json` and export manifest, then publish a
fresh valid project. Packaged `OTAI/contracts/timetable-xml.md` contains exact
function evidence and remaining parity limits. No native GUI or simulation runs.
