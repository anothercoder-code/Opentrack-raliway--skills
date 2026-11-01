# Original Course controls and saved versions

Baseline: stock English OpenTrack 1.7, EXE SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Primary evidence: original English CourseController NIB, native coder/controller
instruction windows, manual 6.1.2, and frozen stock `IC4000`. No UI/method runs.

## Mode codes and times

`OTCourseController.handleEditCourse` (`0x467128`) reads `selectedItem.tag`
before `setResRelType:`. Actual English NIB tags are:

| Label | spacing_mode | Native group 8 |
|---|---|---|
| Discrete | discrete | 0 |
| Moving | moving | 2 |
| Moving (CBTC) | moving_cbtc | 3 |

These are tags, not menu positions. NSActionCell's getter (`0x340a8ff4`) reads
`_tag`; its coder (`0x340a9b40`) writes that field in the NIB's `i:` group. The
frozen NIB SHA-256 is
`1806cccebcf1e756210045e7ce99f9b1fb9af6ccb6bc11458e2f437cdbe74096`.
Unknown saved codes, including 1, return unchanged as `spacing_mode_code` with
`spacing_mode: null`; unrelated edits preserve them.

Group 12 stores two floats: Course **additional** reservation/release seconds.
The manual adds each to the corresponding Route time. They are separate from
dwell and Step. New Courses/patterns default to discrete and zero additional
seconds, as in the native constructor. Entry speed converts public km/h to
native m/s. The reserved second float in group 7 remains unchanged.

## Preference order

Group 2 stores ordered Itinerary names; priority 1 is the first name. The
priority-column setter (`0x46d430`) subtracts 1 before calling
`changeDestNameAtIndex:toIndex:` (`0x455a74`). That method removes/inserts the
name and clamps an excessive destination index to the last entry. There is no
invented per-name priority scalar. `itinerary_preferences` derives actual ranks.
Bulk `itinerary_move` uses an exact name and 1-based position with that clamp;
`itineraries` replaces the complete ordered list.

## Decoder defaults

Original `initWithCoder:` (`0x4567d8`) supplies missing fields:

| Saved version | Groups | Field introduced and absent default |
|---|---:|---|
| 0 | 5 | ID, entry speed, Itinerary array, Train, speed type |
| 1 | 6 | Enabled integer, true |
| 2–3 | 7 | Acceleration percentage, 100 |
| 4 | 8 | Output offset/reserved float, 0/0 |
| 5 | 9 | Spacing mode, 0 |
| 6 | 10 | Delayed acceleration, normal acceleration |
| 7 | 11 | Description, empty string |
| 8 | 12 | Comment, empty string |
| 9 | 13 | Additional reserve/release floats, 0/0 |
| 10 | 14 | Display train number, empty string |
| 11 | 15 | Kind, empty string |

Enabled means a positive integer. A nil legacy Itinerary array becomes an
empty mutable array during migration, matching the decoder. Reading applies
defaults without mutating input. Writes upgrade all Course records in the
selected catalog together to v11; existing typed groups, aliases and reserved
values remain. Counts are reported. Unknown versions/encodings fail preflight.
Old-version tests are synthetic decoder branch cases; the independent native
Course golden is v11. The catalog container remains `OTCourseList v3`.

## Editing and limits

`course_updates` selects exact unique `course_ids`. Only supplied attributes
change, with optional `invert_enabled` or `itinerary_move`. Use an empty string
to clear optional text; null is rejected. References are checked before writing.
IDs and timetable keys are not renamed. Timetable/depot/formation data remain.
The manifest and `course-updates.json` retain full per-Course diffs; ordinary
responses use bounded previews. CSV adds mode/code and additional timing fields.

Generation and Stage share a 1000-operation API budget before pattern expansion;
the v0.10 generation-only 200-operation restriction was unnecessarily narrow.
A draft accepts up to 10000 requested Course update targets. These are interface
budgets, not native catalog-capacity claims. Real MCP/package tests cover data
operations; moving-block dispatch and actual timings remain unverified.
