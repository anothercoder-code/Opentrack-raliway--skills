# Known-layout Shunting scalar updates

`opentrack_edit_current_shunting` edits a SHA-bound native worksheet. Select the saved automatic Path by its `name`, `array_id` and `start_id` from `opentrack_preview_current_shunting` with operation `inspect_inventory`. Supply a nonempty subset of `speed_kmh`, `release_time_s` or `reservation_time_s`.

```json
{
  "source": {
    "path": "OTProjects/MyProject/OTDocuments/Station.opentrack",
    "sha256": "<actual source SHA-256>"
  },
  "shunting": {"name": "S", "array_id": 9, "start_id": 540},
  "changes": {"speed_kmh": 32.5, "release_time_s": 15, "reservation_time_s": 2},
  "preview_only": false,
  "target_path": "OTProjects/MyProject/OTDocuments/Station-edited.opentrack"
}
```

Omit `preview_only` to preview. Saving requires a fresh target and uses the shared atomic no-replace save, source rechecks and disk reload. The existing `opentrack_preview_current_shunting` operation `update_parameters` accepts the same `shunting` and `changes` inside `spec` and remains read-only.

Known Document3/4, End6/7, Shunting0/SecurityArray5/6 layouts may be read and updated in this independent scalar domain. Automatic Path owner and exact identity, its sole body and saved reference, local node ownership and a known code-0 indication are required. Body IDs are not normalized: a body ID pair differing from the owner is retained when its saved ArrayInfo agrees. Nonlocal continuation, extra incoming aliases and unknown layouts fail closed. Three of the five original04 local records have an existing indication pointer to another embedded Shunting; the scalar edit preserves it without repairing or certifying its operational meaning. Body incoming count must equal one owning Path reference plus its existing self-indication count; additional references are rejected. Existing geometry is preserved, not certified as physically or operationally valid.

Speed is finite positive binary32 no greater than 1000 km/h. Release and reservation times are nonnegative int32 seconds. The codec checks updated values after fresh decoding and verifies that restoring the three old scalars reproduces the canonical original bytes. The edit covers existing local records and their three documented scalar fields. The fresh worksheet can be reviewed before rebinding it in an OpenTrack project.

## Evidence provenance

The restored dev1 inventory/core establish exact layout slots: SecurityArray group5 slots2/3; Shunting speed group11 for SecurityArray6, group10 for SecurityArray5. Prior retained engineering evidence identifies original setters at 0x5c8ba8 (speed), 0x5bda08 (release), 0x5bd9ec (reservation), with encoding at 0x5c90cc / 0x5c2c3c. After authorized input restoration, all five decompiled functions were reread in this round. The setters assign exactly one field; SecurityArray encoder explicitly emits releaseTime and reserveTime as the third/fourth integers, and Shunting encoder appends its speed after the superclass encoding. These are static decompiler observations, not execution. Verification includes synthetic known-layout fixtures and edits to all five original04 local records, with fresh decoding, scalar restore, graph equality and original bytes untouched; it is not a native-application compatibility result.

## Coverage

M4.2, M4.2.2, A04, A05: read = bounded known-layout inspection; generate = unchanged existing current-only domain; modify = three bounded scalars on exact local known layouts with fresh decode and inverse-graph proof; export = unavailable in this tool. No whole requirement is promoted to complete from these tests.
