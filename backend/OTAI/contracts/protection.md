# Original Shuntings, Overlaps and Route protection

Baseline: stock English OpenTrack 1.7, original EXE SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
Evidence is the original manual 4.1.2/4.1.5/4.2 and stock coder/lookup methods.
No native selector is executed.

`OTEndModel` group 16 contains `OTShuntingList`, whose inherited array contains
**OTPath wrappers**. Each automatic Path has exactly one `OTShunting` in group
0, the same name in group 1, its own nonnegative ID/start-End pair in group 2,
description in group 3, and one matching `OTArrayInfo` in group 4. The embedded
Shunting retains `[-1,-1]` as its body ID pair; its info repeats that pair and
name. The original `S:YPS_[262]-YPS_03` wrapper has Path ID 0/start 262, ten End
references, and Shunting speed 40 km/h. Frozen `topoOst.opentrack` anchors this
mapping. Names with stock brackets/parentheses must bind exactly.

`OTShunting v0` inherits `OTSecurityArray` and appends one float speed in km/h
(group 10 with parent v5, group 11 with parent v6). The dummy-Shunting flag is
transient and is not encoded. `OTShunting.encodeWithCoder:` is at `0x5c90cc`.
The existing audited parent-v5-to-v6 migration preserves the subclass tail.
The bundled sanitized shape includes this upgraded class, with all source
network references removed.

The same Shunting record can serve as an Overlap. Original
`OTShuntingList.getOverlapWithName:` (`0x5c9700`) delegates to
`getShuntingWithName:`; `getOverlapAtIndex:` (`0x5c9718`) unwraps the Path's
first object. A Route binds an Overlap using security group 7 (name) and group
9 (start End ID). The generator requires an exact unique Shunting at the Route
terminal End. With a supported one-boundary Route continuation, the reference
is written on the terminal document's companion Route. Overlap release time
is the Shunting's security release-time field. No separate invented Overlap
class or stored role flag is introduced.

Route release groups contain **End objects**, not OTElement objects. With
parent v6, group 12 holds the release-boundary array followed by slow-zone
start/end End references. Parent v5 uses group 11. Original `group`
(`0x5a5f68`) stores the first/last boundaries; `ungroup` (`0x5a5f04`) stores all
Ends. Original `setStartZoneAtIndex:` / `setEndZoneAtIndex:` (`0x5a5e0c` /
`0x5a5e8c`) store selected End objects. Explicit API boundaries must follow the
directed Route and include its global start/end. Continued Routes partition
these references by document and retain each local first End. Zone endpoints
must be ordered Ends on a local Route; continued-zone behavior is not audited.

Creation and partial updates operate only on drafts. Omitted update fields
remain unchanged; explicit null resets the selected boundary/zone/Overlap
field. These semantics also survive batch expansion and editor undo/redo.
Validation checks references and directed geometry; it does not simulate
interlocking, sensor release or actual shunting/Overlap dispatch.

The offline graph reader traces automatic Shunting Paths and caps reported
Edge speed limits at the stored Shunting speed. This is a data limit, not an
estimated running time. Edge splitting preserves the movement chain; deletion
reviews Shunting, dependent Overlap Route, Path, Itinerary and Course closure.
Removing a Signal preserves a Shunting that only depends on the retained
vertices/Edges. API snapshot undo is independent of stock keyboard Undo.

Current limits: one-document Shuntings, local slow-speed zones, and at most one
Route document continuation. Cross-document Shunting persistence, recursive
Route continuation and complete native lifecycle/dispatch parity are unverified.
