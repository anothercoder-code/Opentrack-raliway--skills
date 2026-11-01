# Original timetable editing and text exchange

Target: original stock English OpenTrack 1.7; EXE SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
The local manual 6.2/6.3 and original controller, record and exporter instruction
windows establish the operation scope. No original program/UI/method is executed.

## Row commands

Use `GenerateOperations.timetable_operations`, ordered after definitions, Course
updates/lifecycle and rolling-stock operations. Stage/editor accept each `kind` directly. Each
operation's zero-based indices refer to the result of preceding operations.
Select exact `rows: [{course_id,index}]` or nonempty `course_ids`, never both.

`create_timetable_skeletons` uses existing Course IDs and the first Itinerary
to derive station rows with current Category defaults and undefined times.
Read [automatic creation](timetable-creation.md) before using it; the row selectors
below apply to edits of existing rows.

- `update_timetable_rows`: only supplied attributes change. Null arrival/departure
  clears to `HH:MM:SS` and day zero; omit other fields to preserve them. Empty
  optional text clears it; connections `[]` explicitly replaces the whole list.
- `insert_timetable_rows`: supply station/time attributes and `before_index`;
  null appends. Existing records, actual fields and connections remain.
- `delete_timetable_rows`: reindex rows/maxIndex and rebuild `CourseID#index`
  dictionary keys. A vanished target station's incoming connections reject by
  default; explicit `reference_policy: detach` removes them. Remaining visits to
  the same station retain connections. Course definitions are preserved.
- `shift_timetable_rows`: shift defined planned times with day carry/borrow.
  Overlapping family selections shift each physical row once; actual fields and
  stored interval offsets remain.
- `set_timetable_interval`: set exact Course references/optional stored offsets
  without retiming. Null detaches to `0` and clears the stored offset to zero,
  matching current `OTTimetable.initWithCoder:` (0x67af18). Selecting the reference
  Course itself makes it a root and also clears its offset, even when a shared
  offset argument is supplied. Only rows with a real reference preserve an omitted
  offset. Raw diagnostic reads may show nonzero encoded offsets on detached
  historical inputs, but the native decoder resets those to zero. Cycles are rejected.
- `edit_timetable_connections`: old-index partial updates/deletions, append or
  clear/append; preserves omitted fields. Location is exit/entry/dispo. Saved
  `time_reference_type` is a raw integer, distinct from location. Min/max wait,
  join/split and stored dispatching distance are separately editable. Native
  transient dispatching state is not an archive flag.
- `reset_timetable_actual`: original resetActual (0x67adec) clears actual strings
  and their two day offsets only.
- `copy_actual_to_planned`: explicitly copy defined saved actual times/days.
  Native `validActualData` is transient and absent from the original coder; this
  data command does not recreate or certify that live validity flag.
- `sync_timetable`: remove rows without Course definitions. Explicit detach can
  remove their incoming connections and reset orphan interval references.

Original `deleteRowWithTimetable:` (0x6880b0), insertion/addition controllers,
interval binding methods (0x693c78/0x693d38/0x693df8), field controllers and record
setters are recorded in `artifacts/research/timetable-editing-layouts.txt`.
Writers upgrade audited Timetable v7/v8 records to v9 and Connections v0-v5 to
v6 once per selected catalog, reporting migrations. Untouched catalogs remain.

## Interval propagation

`propagate_interval` controls planned times, station, track, dwell, stop/timing
flags and mass; `propagate_delays` separately controls mean delay/distribution.
Both are explicit API options; no global native UI preference is read or changed.
Connections are replaced only on explicitly selected rows, not automatically
renumbered through a train family.

The original field controllers match the same station and row index among:
direct dependents of the edited Course, siblings sharing its interval reference,
and that reference Course itself when its row has no own interval reference. This is direct saved-reference behavior, not
an invented recursive/transitive family. Defined-to-defined time edits propagate
the time delta. Clearing propagates undefined time. Newly defining a time uses
stored reference offsets (subtract source offset for root/siblings). Conflicting
selected origins fail rather than overwrite each other. Fractional offsets that
would create a subsecond saved time in that last case remain explicitly unsupported;
the saved HH:MM:SS interface does not guess a native rounding rule.

Generic calendar edits retain their declared data-operation semantics; full
native cache and undefined-time arithmetic quirks of every field controller
remain unverified. Native sequential interval copies use the separately reviewed
float32 clearing/skipping rules in the interval-Course contract.

Station edits always update owned connection station names.
`rebind_station_connections` optionally updates incoming targets when the old
station no longer has a remaining visit and there is one exact new destination;
ambiguous moved visits fail. Otherwise callers can edit connections explicitly
within the same batch. Final reference/chronology checks remain mandatory.

## Original text formats

The 1.7 exporter (`OTOutputController.exportTimetableWithExchangableFlag:`,
0x541830) and Windows importer (0x69aa98) use two tab-separated blocks, with
`// Connections:` between them. Original PE literals at 0x792461 and 0x7925b0
independently establish the 16/8-column headers. The manual/release appendix
describes the older 14/7 layout, also supported. The intermediate 15-column
layout is not guessed.

Current row order:
`courseID, intervalCourseID, timeToIntervalReference, stationIndex, stationSign,
trackName, arrTimeDayOffset, arrTime, depTimeDayOffset, depTime, useDepTime,
dwell, stopAtStation, meanDelay, Distribution, deltaMass`.
Legacy rows omit trackName and deltaMass.

Current connection order:
`courseID, connCourseID, stationIndex, connStationSign, connTimeType,
connChangeTime, connMaxChangeTime, connectionType`.
Legacy connections omit connTimeType.

Text `connectionType` is join=1, split=2, entry=16, dispo=32. Saved group 4 uses
join=1, split=2, entry=4, dispo=8. These namespaces are not interchangeable.
Original setConnectionInfo: (0x711340) discards legacy text bits 4/8; the parser
does likewise. Ambiguous simultaneous entry/dispo and unsupported codes reject.

`opentrack_export_timetable` writes a fresh, hashed artifact in the workspace,
with source digest and per-field representability warnings. Formats are current
`opentrack_17`, legacy `opentrack_16`, and mapped `json`. Native text omits actual
times and dispatching distance; legacy additionally omits track/mass/time type.
JSON is a mapped record export, not an exact replacement for native archives or
their object sharing. Embedded separators/non-ASCII fail native text export.
Generation also emits a current-format timetable file with its CSV; a format
failure is returned explicitly, not hidden behind a supposed successful export.

## Import semantics

`import_timetable_text` accepts inline `content` or a project-relative/absolute
`file_path` inside the existing project/data/workspace read bases. Bytes are
snapshotted and hashed; the resulting reviewed draft is independent of later
edits to that text file. It is input provenance, not a writable source catalog.
Use file input for large data, especially through the Windows CLI bridge.

Existing-data policies: `reject`, full selected-Course `replace`, or row-key
`merge`. Merge preserves saved actual fields, unlisted connections and fields
absent from the chosen format. Native connection identity is target Course plus
target station; duplicate matches fail. New data must have unique, contiguous
indices in the resulting Course. All referenced stations/Courses are checked.

Missing Course definitions require explicit per-Course `templates`, a
`default_template_id`, or `create_unbound_courses: true`. Templates copy exact
existing formations/Itineraries. Unbound records match the original concept of
an empty Course but retain binding/Itinerary validation errors in their draft;
no vehicle or path is guessed and they cannot be published as valid ready data.

Sequential original interval creation and explicit connection-property
propagation are covered in [interval Courses](interval-courses.md). The former
renumbers copied connection targets; whole-row replacement and text import do
not automatically apply that numbering rule.

Budgets are API limits: 1000 operations and requested Course definitions, 10000
requested timetable row targets/connections per draft; exchange input 2 MB,
4095 characters per original Windows input line. Selected-Course export is not
native simulation acceptance. Original proprietary XML has a separate
[XML operation](timetable-xml.md). RailML timetable/GModel/FBS/Protim/SimuVII and
remaining native timetable functions are not implemented by this text operation.
