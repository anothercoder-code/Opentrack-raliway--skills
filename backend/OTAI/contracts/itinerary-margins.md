# Original Itinerary safety-margin data controls

Version 0.30 implements the finite-float32 saved-data behavior of the original
Itinerary Misc panel and its model. It does not execute native train control,
GUI selection, modal dialogs or dirty notifications.

`itineraries[].safety_margins` generates an initial profile in the same dependency
batch as Paths, Itineraries, Courses and timetables. Each row contains signed
`position_m` and `safety_margin_m`. Initial rows are normalized to float32 and
sorted as an original text import. The native record is OTSafetyMargin v0,
NSObject v0, one `ff` group; OTDest group 5 holds OTSafetyMarginArray v0.

Use `network_operations: [{kind: edit_itinerary_margins, name, edits: [...]}]`.
Stage and persistent editor accept the same command.

| Edit action | Original behavior |
|---|---|
| `add` | No selected indices: append an independent copy of the last row, or constructor defaults `(0,0)` when empty. Explicit `selected_indices`: insert after the greatest selected row and inherit that preceding row. |
| `insert` | Direct model operation at `index` in `[0,count]`, requiring a nonempty profile. Inherit the preceding row, or row 0 when inserting at 0. |
| `update` | Select current zero-based `index`. A margin value change preserves array order; a position change sorts immediately. Both fields compose margin edit then position edit on the same selected object. Return its resulting indices, including repeated references. |
| `delete` | Delete unique selected `indices` in descending order. Empty selection is a no-op. |
| `clear` | Composition of Select All/Delete; remove all rows from the existing array. |
| `sort` | Original model position comparison and Foundation merge ordering. |
| `import_text` | Snapshot inline `content` or an allowed `file_path`; replace the entire profile, parse accepted rows and sort. No append/merge interpretation. |

Indices refer to the current array after earlier edits. All values are stored as
float32; duplicate positions and negative margins are preserved. Bounds, schema
and input errors abort the draft before any source files change. Per Itinerary:
10,000 rows; per command: 1,000 edits; per draft: 10,000 margin edits.

## Sorting and lookup fidelity

Original Foundation `sortUsingSelector:` calls `sortUsingFunction:context:` and
the exported `_NSMergeSort` at 0x32011208. Equal keys interleave left then right
during a merge, so Python stable sorting produces different duplicate-row order.
The already-ordered shortcut is selected by the **top-level count > 63** and
propagated through recursion. Base cases for 2 and 3 items retain the original
comparison branches. The independent Python projection preserves these rules.

`opentrack_get_itinerary_margins` returns bounded row pages, original indices,
duplicate/unsorted diagnostics and optional `distances_m` queries (up to 200).
It never sorts implicitly. Original lookup walks saved order: first exact match;
otherwise the preceding row before the first greater position; before the first
row or for an empty profile it returns zero. Beyond the final row it returns the
last margin. Thus an exact duplicate position can use a different row from a
point immediately after it. Query arguments are also rounded to float32.

Catalog `include_itinerary_details` returns at most 20 margin rows with a full
count and truncation flag. Use the dedicated paged reader for large profiles.

## Shared native references

An archive may reference one row more than once or share a row, margin wrapper
or embedded array across loaded Itineraries. Edits preserve these identities:
changing a shared row affects each owner; replacing the selected array's
contents affects every owner of that array. Editing then removing a row in one
batch still updates other arrays retaining it. Add/insert allocate fresh rows;
Itinerary duplication copies each row occurrence independently, as the original
copy loop does. Import allocates fresh rows in the existing array.

Read pages expose each row's first `reference_index` and a bounded shared-profile
preview. Full network diffs record alias groups and affected shared profiles;
compact responses bound those lists. Mapped JSON includes batch-local wrapper,
array and row reference IDs, plus shared loaded owners outside the export.

## Original text exchange

`opentrack_export_itinerary_margins(names, format)` exports one or more exact
loaded Itineraries as `native_text` or lossless mapped `json`. It writes fresh
artifacts, hashes, ownership and a complete manifest. Source archives survive.

Text uses `position<TAB>margin`, two decimal places and comment headers. Original
MSVCRT half rounding is away from zero; conversion uses 17 significant decimal
digits before filling wide fixed-format fields. The exporter emulates this for
stored finite float32 values, including negative zero and large values. Headers
identify OTAI and do not impersonate original file timestamps.

The importer skips spaces before its first-character test and accepts a row only
when that first character is a digit. Leading tabs, signs or decimal points are
not admitted by that gate. It replaces commas with dots, splits **tabs only**,
requires at least two fields, consumes numeric prefixes as NSString.floatValue,
uses zero for invalid numeric fields, ignores extra fields and retains duplicate
positions before the native sort. No eligible rows means an empty replacement.
Nonfinite/overflow values, embedded control bytes and unsupported buffer-length
cases are explicit errors; they are not silently clipped or split.

Native text can lose precision, skip signed-position rows on reimport, change
row order when the importer sorts and discard repeated-row identity. For each
selected profile sharing a wrapper, array or row with another loaded Itinerary,
`cross_itinerary_shared_references_not_represented` lists those owners in
`shared_profiles`, whether inside or outside the selection, including empty
shared containers. Text cannot describe or reconstruct these relationships;
this warning does not mean import detaches an existing shared array (it does not).
Independent profiles with equal values do not trigger this warning. Full
warnings are saved in the manifest. Mapped JSON preserves all finite saved
values, order and selected profiles' reference relationships. Maximum text input is
2 MB, supported line length is 1,022 characters, and one export has at most
100,000 rows. A file is snapshotted before parsing; unlike the native dialog's
clear-before-fopen path, a read failure cannot destroy the source or a draft.

## Evidence

`artifacts/research/itinerary-margins-v030.json` pins the original binary,
35-function application pass, 226 recovered call sites, explicit remaining UI
signature sites, eight Foundation dependency functions and callback type repair.
`artifacts/research/foundation-sort-v030.c` is the typed generated core C.

Frozen `tests/fixtures/itinerary-margins` contains independent evidence: a real
NSArchiver archive from OTSource's OTSafetyMargin model, 76 installed Foundation
identity-permutation cases covering 47,676 rows, 264 x86 MSVCRT formatting bit
cases and NSString numeric conversions. The sort probe uses existing NSNumber
comparison on finite float32 keys; the comparison signs match the reviewed
margin comparator. It does not execute original OpenTrack methods. Runtime,
Source inputs and probe fingerprints distinguish these evidence levels.

Relevant originals: OTDestInspector Misc add/delete, cell edit, text import/export;
OTSafetyMargin init/copy/getters/setters/compare/coders; OTSafetyMarginArray
add/insert/delete/sort/lookup; and OTDest's safety-margin forwarding method.
Native application simulation, runtime preparation and full original-function
Agent parity remain unverified. This component does not complete the 176-item goal.
