# Native graphic alignment

Current API: `0.33.1-zeroaccept1`. The two integers in
`OTGraphicModel.loc.align` are alignment codes, not pixel dimensions.
New graphic placements use these exact keys. This example is a Station placement:

```json
{"x":130,"y":50,"angle":0,"alignment_x":0,"alignment_y":0}
```

The reviewed general generation subset is `(0,0)`, `(1,0)`, `(2,0)`, `(0,3)`,
`(0,4)`. The new Station profile retains `(0,0)`. A **new Signal must instead
match its actual owner End's alignment**: horizontal Ends use `(1,0)` or
`(2,0)`; vertical Ends use `(0,4)` or `(0,3)`. Read the selected End's actual
fields rather than guessing from a signal name or its apparent screen position.
For example, only when that End stores `(1,0)`, its Signal placement can be:

```json
{"x":130,"y":50,"angle":0,"alignment_x":1,"alignment_y":0}
```

The Signal input schema rejects `(0,0)`; the common factory also rejects any
alignment that differs from the selected End, including the opposite direction.
It does not silently replace an old request's `(0,0)` with a guessed direction.
Station's native mouse handler directly initializes `(0,0)`; the native Signal
handler reads the End View alignment before initialization. Directional
End/Connector locations retain their supported orientation values. Mixed
nonzero axes are outside this bounded creation contract; this is not a claim
that every original graphic type or native alignment combination is supported.

Legacy `width` or `height` keys in a graphic placement are rejected with a
migration error. They have no compatibility alias and are never converted from
pixel sizes into native alignment values. Inspect the intended native placement,
keep the Station profile separate from the Signal's actual End direction, update
the request and preview it again. A historical Signal request that used `(0,0)`
must be corrected from its owner End; it is not a valid new-Signal default.
Actual page/canvas dimensions and other genuine size fields are separate.

Common factories and public schemas use the same validation. Internal one- and
multi-document generators, terminal-area profiles, finite topology and new Signal
routes use the explicit contract. Existing-archive inspection/configuration and
faithful cloning preserve the source field values; they must not silently
normalize an old Signal's alignment. Preserving such a source value is distinct
from passing the new-Signal direction check.

After generation, reload the actual bytes and compare every new Signal's groups
4/5 with its actual owner End, alongside model identities, station/end references,
connectors and Path/Itinerary binding. Static direction checks do not establish
native icon visibility, three-aspect operation, train separation or failure safety.
This data check is separate from the original Inspector's selected-object lifetime
failure; see [Inspector safety](inspector-safety.md).

When a loaded drawing has Signal models but no visible lamps, first inspect the
actual Signal/End orientation, display flags and fresh-load state. A saved model
count or `show_icon=true` does not prove the original View drew the lamp. Correct
the source-backed defect in the current project; do not make another project or
guess alignment/visibility bits from screen position. A drawing adjustment and
the saved physical track length are separate changes.

The winmulti1 journey events remain historical runtime observations, followed by
a station double-click crash. Staticfix1 did not start or operate OpenTrack;
fixed alignment bytes and an installed guard do not establish GUI editing safety.
