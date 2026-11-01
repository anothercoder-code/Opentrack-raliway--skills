# Original connection planning commands

`plan_timetable_connections` is a typed timetable operation in generation,
staging and persistent editor sessions. It implements saved-data behavior of
the original English `Ins. Connection`, `Ins. Turnround to`, `Ins. Turnround
from` and `Del. Connection` commands and their connection helpers. It neither
invokes native selectors nor runs coupling, dispatch or simulation.

## Selection and insertion

Each command supplies `row: {course_id, index}`. `insert` defaults to that
selected row. With `target_course_id` omitted it inserts the original unbound
target `"0"`; with an exact target it inserts a named connection. The first
connection with the same target ID is reused, regardless of its other fields.
Ordinary insertion/deletion is local even when the row belongs to an interval
family. Prior v0.22 notes listing automatic family insertion/deletion as a gap
were incorrect and are superseded by this reviewed behavior.

A new connection uses its owner's current Train Category
`default_connection_time_s`. The native formatter rounds to float32, reduces
modulo one day and truncates positive fractional seconds. A negative value
gives `HH:MM:SS`; no resolved Category gives the native `00:07:00` fallback.
Same-batch Category/formation edits apply before these commands. Source and
reciprocal connections use their own owners' defaults independently.

Insertion creates exit-location, non-join/non-split connections with equal
source and target station signs, time-reference type zero and zero dispatching
distance. Maximum wait is the native `HH:MM:SS` unlimited marker, except for
the start helper described below. It does not calculate feasible turnround
times or allocate rolling stock. Existing connections retain their wait,
distance and time-reference fields unless the command explicitly changes them.

Unbound placeholders are reviewable invalid drafts: validation reports
`CONNECTION_COURSE`, and valid publication remains blocked. Bind them using
indexed `edit_timetable_connections` updates before publication. Other missing
named target Courses fail during binding.

## Compound Turnround commands

`turnround_to` selects the owner's last row; `turnround_from` selects its first
row, irrespective of the requested row index. The target must have a timetable
visit at that effective station. Missing target tables/stations fail atomically.

| Command | Target visit | Primary connection | Reciprocal connection |
|---|---|---|---|
| `turnround_to` | Target starts at station | Split, exit | Plain connection at target start |
| `turnround_to` | Target starts elsewhere | Join, exit | Join at first matching station visit |
| `turnround_from` | Target ends at station | Plain, exit | Split at target end |
| `turnround_from` | Target ends elsewhere | Plain, exit | Split at first matching station visit |

The primary always receives the effective source/target station and exit
location; join/split flags are set as above. Its existing wait/max/type/distance
remain unchanged. The reciprocal helper reuses the first connection by target
ID; an existing join/split helper sets only its requested flag and does not
clear other flags, change station/location or reset its wait. This preserves
original controller behavior rather than silently repairing a prior record.
For a new primary, allocation precedes reciprocal lookup and owner/target
initialization follows it. Self-turnround therefore can create two records;
it is preserved as a data command, not certified as operationally sensible.

## Explicit helpers, deletion and nil storage

`add_start` and `add_end` select the owner's first/last row. `join_at_station`
and `split_at_station` select the first visit to the selected row's station,
including when the selected index is a later repeat visit. `split_at_end`
selects the last row. Helpers require an exact target ID; they can create
one-sided data, so use compound Turnround for the corresponding paired action.

A newly created start-helper connection retains a raw **nil** maximum-wait
object: the original helper does not set that field. Other helpers initialize
it to `HH:MM:SS`. Readback exposes logical `maximum_wait: "HH:MM:SS"` plus
`maximum_wait_is_nil: true` only for raw nil. Archive copying, unrelated edits,
interval copying, whole-property propagation and publication preserve nil.
Native timetable text cannot encode that object distinction; exports report
`nil_maximum_wait_storage` among their representability warnings.

`delete` requires a zero-based `connection_index` in the row's current array
and forbids a target ID. Indices are evaluated sequentially within a batch.
It removes exactly that entry and does not edit a reciprocal or interval row.
It can repair a reserved-owner or blank-station draft; insertion retains the
original valid-owner/nonempty-station requirements. Invalid indices fail.

## Evidence, bounds and acceptance

The portable bank and entry addresses/hashes are frozen in
`OTAI/artifacts/research/connection-commands-v023.json`, including initializer,
coder, first-match helpers, nil getters/setters, English NIB captions and the
bounded float-to-integer rounding check. C pseudocode was read first. These
reviewed rules do not establish every dynamic/aggregate type in the C output.

Each plan accepts up to 1000 commands. All nested plans share the draft's
10000 requested row targets and 10000 connection allocations; reciprocal row
targets also count. No-op commands consume row budget. Errors leave the source
unchanged. Responses preview the first ten actions; full sequential actions
and before/after row diffs are in `timetable_changes_json`. Allocation counts
describe writes rather than net growth after deletion. Persistent editor undo
restores the complete original native table, including nil objects.

Scoped regressions cover all four compound branches, placeholder binding,
independent Category defaults, repeated targets/stations, existing-field
preservation, self-reference ordering, local deletion, nested budgets, native
round trips, nil export warnings and undo. Real compact MCP and extracted
packages are separately exercised. Native GUI/cache validity, connection
execution, automatic circulation and complete original-function parity remain
unverified. No OpenTrack application is launched.
