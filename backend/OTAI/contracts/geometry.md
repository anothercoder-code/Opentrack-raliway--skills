# Geometry contracts for the independent editor

These contracts describe the audited OpenTrack 1.7 archive. They do not establish
complete native editor or simulation equivalence. The executable fingerprint is
recorded by `opentrack_capabilities` and the source manifest.

The primary behavioral source is `OTUndo/out/manual-e16-text.txt`, sections
3.3--3.6. In a DVG a movement alternates related half-vertices and Edges; two
switch branches on the same half cannot be traversed directly into one another.
Drawing coordinates and kilometre reference points do not determine Edge length.

`OTGraphicModel.encodeWithCoder:` at `0x4dcb30` writes ID, angle, x, y, x/y
alignment and label in archive groups 0--6. Its runtime ivars have different
offsets. A horizontal pair uses x alignment 1 and 2 at a common drawing position.

`OTEndModel.encodeWithCoder:` at `0x4c7910` writes these fields after its
superclass:

| Group | Field | Static encoding evidence |
|---|---|---|
| 7 | OTElement object | `0x4c7953`, runtime offset `0x34` |
| 8 | related half ID | `0x4c7978`--`0x4c7999`, derived runtime offset `0x74` |
| 9, 10, 11 | first Edge, second Edge, Signal | `0x4c79b4`--`0x4c79dc` |
| 12, 13, 14 | Station, instrument, kilometre point | `0x4c79f7`--`0x4c7a51` |
| 15, 16, 17, 18 | Route/Shunting/Path lists and name | `0x4c7a79`--`0x4c7ad3` |
| 19 | highest Route/Shunting/Path ID | `0x4c7adb`, runtime offset `0x50` |
| 20 | stationEndType | `0x4c7af0`, runtime offset `0x70` |
| 21 | switch time, seconds | `0x4c7b08`, runtime offset `0x4c` |
| 22 | default switch leg is second | `0x4c7b27`--`0x4c7b44`, runtime byte `0x48` |
| 23 | insulated joint, axle counter | `0x4c7b49`--`0x4c7b5d`, runtime bytes `0x49/0x4a` |

`OTEdgeModel.encodeWithCoder:` at `0x4bd5e0` writes endpoints in groups 7/8.
The `iiffii` group 9 contains track type, integer length, radius, gradient,
loop type and dLinkType (`0x4bd62a`--`0x4bd64e`). Group 10 holds contact-wire and
tunnel cross sections. Group 11 bit 0 is equalSpeed and bit 1 is rackRail
(`0x4bd679`--`0x4bd6a0`). Groups 13/14 are outgoing/incoming exclusion links,
15/16 are speed keys/dictionary, 17/18 power/propulsion references, and 19/20
track/line names. Reversing an Edge swaps endpoints and directional speeds and
negates the gradient; its physical connectivity and length stay the same.
Path tracing selects speed group 1 for movement from endpoint 1 to 2 and group
2 for the reverse. Each traced Edge exposes its direction and per-train-type
limits. The legacy scalar `limit_kmh` is the minimum of those directional
train-type limits, a conservative screen rather than selection of a particular
Course's train type.

Safety membership is represented by each End's Element reference and the
Element's End array. Edges incident on the same half belong to the same safety
component. Related halves do not by themselves unite their safety components.
Manual Merge Elements can intentionally unite disconnected components. Reset
Elements explicitly recomputes the selected groups' default Edge components.

Splitting preserves total integer length, directional speeds, grade/radius,
existing Route identity/Path references and the old exclusive safety section.
Reset Elements is available to create separate default components afterward.
This preservation policy has not been shown equivalent to all native split
cases. Direct exclusion-linked Edge splitting is rejected until redistribution
has a verified contract.

Signal construction currently covers metric main/combined and audited
ETCS-main numeric types. It does not yet implement every distant, shunting,
halt-board, aspect-system, balise or dispatch property. A connector half has no
Edge or Signal; its related half must also have no Signal. Links are reciprocal
document names plus local IDs, rather than cross-file object pointers.

Deletion reports dependent Routes, Paths, Itineraries and Courses. By default
it rejects a used graphic. Explicit cascade removes these definitions and the
affected Courses/timetable rows only in a new draft. It preserves originals and
does not claim complete arbitrary connection/instrument dependency support.

Editor undo/redo selects immutable validated archive snapshots. Revisions are
optimistic concurrency tokens, including undo/redo transitions. A filesystem
lock serializes commits across processes; an edit after undo cuts the visible
redo branch while old draft snapshots remain recoverable.
