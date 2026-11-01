# Original proprietary timetable XML

`opentrack_export_timetable(format="opentrack_xml")` writes a fresh original
proprietary XML artifact. `import_timetable_xml` in generation, Stage or editor
imports that format from exactly one inline `content` or snapshotted `file_path`.
RailML timetable XML remains a separate unimplemented format. Current Course IDs
and editable native text fields retain their published ASCII/length contracts.

## Schema and import choices

The native document is `<timetable><course><courseID>…</courseID>…</course></timetable>`.
Each Course has optional `referenceCourse`/`referenceTime` and ordered
`timetableEntry` records with station, track, planned/actual arrival/departure,
wait, delay/distribution, delta load and nested connections. Original callback
names, formats and field rules were read from functions before implementation.
Row indices are assigned sequentially within each Course. Duplicate Course
containers and inconsistent/misnested containers reject rather than simulate
interactive replacement prompts. Unknown element names report warnings.

`existing` is `reject` or explicit `replace` for the imported Courses' timetable
rows. Replace recreates their saved row/connection fields, including resets of
unrepresented fields; it is not a partial merge. Omitted Courses are preserved.
`clear_existing_timetables:true` is the original Remove All choice, expressed
explicitly: it clears the complete timetable before storing imported rows while
retaining Course definitions. `<timetable/>` is accepted only with this choice.
Persistent editor undo restores the full prior native table.

XML contains timetable information rather than complete formation/Itinerary
bindings. Existing Course definitions are preserved. New IDs need explicit
`templates` or `default_template_id`. `create_unbound_courses:true` instead
creates reviewable invalid definitions for later binding. No formation or
direction is guessed. Shared draft budgets include imported definitions, rows,
connections and cleared rows of non-imported Courses. Generation summary counts
include timetable-import writes, not merely net growth.

## Reviewed native behavior

- A Course reset clears Course/reference fields; a row reset preserves Course,
  reference and offset, resets ordinary row fields and connections, and resets
  actual day offsets. Actual strings survive both resets and can carry between
  rows or Courses. Imported carry is reported; no runtime validity is inferred.
- A `referenceTime` format attribute before a first entry is ignored by the
  original attribute handler. Its text therefore uses the default float parser.
- `stopInformation` recognizes yes/y/1; departure `useDepartureTime` recognizes
  yes/1. Attribute values are case-insensitive where the native handler applies
  lowercase conversion. XML element/attribute names remain case-sensitive.
- Planned `valid=no/0` skips its time assignment. Actual time text is accepted
  only with `type=actual` and `valid=yes/1`; it does not establish native actual
  validity. A dayOffset on an actual element still writes the **planned** day
  field, while the saved actual day remains zero. Warnings expose this quirk.
- Float fields use finite float32 and original numeric-prefix parsing. Seconds
  for planned arrival use the native modulo/truncation formatter and retain the
  assigned day; seconds for planned departure recalculate its day. Actual seconds
  and connection seconds use the formatter without recalculating actual days.
  Negative seconds format to `HH:MM:SS`; wait/delay seconds use integer prefixes.
- New connections reset minimum and maximum wait to `HH:MM:SS`, then receive
  owner/target stations and supplied fields. A connection stationID sets both
  station names. `meet` sets join alone in this importer; `split` and `join` set
  their respective flag. Turnround/normal leave both clear.
- `connectionPlace=home` means entry, `station` means dispo, and `exit` means exit.
  The native export spelling `dispo` is not recognized by that importer.
  `connectionTimeType` resets location to exit and maps departure to 1, all other
  values to 0.

**Native attribute enumeration is not XML source order.** Expat callback
`0x40114c` builds a dictionary; `OTXmlParser.startElement:withAttributes:` at
`0x6e4930` enumerates `allKeys`. Foundation bucket ordering is not yet replicated.
For a conflicting home/station place plus time-type attribute, the default
`connection_attribute_order:"require_unambiguous"` raises
`TIMETABLE_XML_ATTRIBUTE_ORDER`. Explicit `place_then_time_type` or
`time_type_then_place` applies that reviewed callback sequence and reports that
native dictionary ordering was not reproduced. Reordering XML text alone does
not select a policy. This is an explicit remaining parity limit.

## Export representability

Output uses original tags, positive dayOffset attributes, one-decimal reference
offsets, three-decimal nonzero delta loads, source stationID in connections and
original connection type/place/time-type spellings. Source indices must be
contiguous and consistent. Text is XML-escaped; unsafe control/surrogate values
reject. The external DTD reference is descriptive; no DTD is bundled or fetched,
and neither export nor import claims schema validation.

The native actual-validity flag is not serialized. Default `saved_actual:"omit"`
reports any defined actual strings it omits. Explicit `saved_actual:"as_valid"`
emits both saved actual fields in each row as valid=yes, including placeholders;
the report states this does not prove runtime validity. It is an explicit data
selection, not a runtime observation.

Full export warnings cover negative day loss, per-row interval differences,
decimal precision, differing connection target stations, raw time codes, dispatch
distance, raw nil maximum storage, meet/split loss and native place import quirks.
The response previews 20 warnings; the manifest retains all. Import warnings and
before/after changes are complete in `timetable_changes_json`, with bounded
response previews. XML is not a lossless native database backup.

Inputs are UTF-8 snapshots, up to 2 MB, 64 nesting levels and 10000 rows/connections
within shared draft limits. No external resource is resolved. Entity declarations,
unsupported roots, invalid current field values, out-of-range days, missing
bindings and ambiguous callbacks fail before source writes. The original
unmarked wait/delay strings must be finite numeric text for the current record
reader; malformed native raw strings are explicitly rejected. Marked seconds
and hh:mm:ss fields use the reviewed original conversions. The original
application is never started. Native GUI/parser acceptance, exact Foundation
dictionary ordering, all raw C types and full original-function parity remain
unverified.

Function hashes, 210-function focused-pass provenance and bounded checks of
ambiguous shared setter arguments are in
`OTAI/artifacts/research/timetable-xml-v024.json`. Some branch-dependent shared
stack arguments remain poorly represented in C despite the bounded signature
refinement. Their specific instruction checks are recorded rather than claiming
all pseudocode was repaired.
