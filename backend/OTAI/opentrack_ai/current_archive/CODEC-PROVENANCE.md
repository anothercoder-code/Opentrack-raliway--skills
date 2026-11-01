# Independent current-archive graph codec

This is a **new independent implementation**, not the missing/protected original
OpenTrack writer and not recovered source. No GUI, simulation, JSON transport,
local user computer, or blocked Drive source is used. Runtime: Python standard
library only. `typedstream_writer.py` is a compatibility filename, not a provenance
claim; integration should use `current_archive.writer`.

## What has actually passed

Run from the workspace root:

```sh
PYTHONPATH=opentrack-native-writer:opentrack-archive-research/vendor \
  python opentrack-native-writer/verify.py
```

Seven test methods pass, including:

* 21 existing archive fixtures: independent decode → editable graph → fresh encode;
  compare every official pytypedstream reader event, including reference type/index,
  class version, encoding, integer/float/string, array and struct. Both archives also
  decode with the official high-level generic unarchiver. Reencoding is idempotent.
* Current OTTrain16 / OTTrainCategory19 / OTTimetable9 in native-shapes:
  12 actual edits (each class: scalar, longer UTF-8 string, reference reuse,
  newly allocated NSString). Outputs are real binary archives in `evidence/`.
  Scalar and string edits change exactly one independent-reader event. Reused aliases
  are checked with Python `is` after both own and official generic decoding.
* Explicit synthetic **wire boundary only** cases: cyclic object graph, same object
  repeated, equal-but-distinct shared-string tokens, distinct C strings sharing one
  token, negative zero, signaling/quiet NaN payloads, infinities, both byte orders,
  length boundaries 127/128/32767/32768, invalid references/types/ranges.

JSON reports are evidence summaries, not the archive format. `real-roundtrips.json`
contains source/output SHA-256 and sizes. BJTU empty.trains grows from 1678 to 2134
bytes because compact integer float representations are rewritten as IEEE payloads;
its full independent-reader event stream remains identical. Other fixtures may be
byte-identical because their wire representation is already canonical, not because
source bytes were reused. Archive objects never retain the input blob.

## Graph and API

`decode(bytes, strict_lengths=False) -> Archive`; `encode(Archive) -> bytes`.
Archive groups retain exact encodings and explicit shared-string token identities.
Generic objects hold `.clazz` and `.contents`; each group has `.encodings`, `.values`
and single-value `.value`. Class objects hold `.name/.version/.superclass`.
All Foundation objects remain generic: no partial known-class interpretation.

There are two independent identity namespaces:

1. shared-string `SharedString` tokens (equal bytes do NOT coalesce identities);
2. object/class/C-string references, assigned in traversal order before nested
   content. Reserving object IDs before classes/content preserves cycles.

`WireFloat(float)` retains only that scalar's original IEEE bits to preserve signaling
NaNs and negative zero; changed arithmetic values are normal float and freshly packed.
Integer compression is canonical, not byte-preserving. Unchanged type/field group
order is retained. Unknown groups are not dropped or assigned guessed field names.

Minimal adapter API: `load`, `load_next_compatible`, `dump`, `dump_verified`,
`fingerprint`, `objects`, `kind`, `string`, `elements`, `set_elements`, `ar.TypedValue`,
`ar.TypedGroup`, `ar.GenericArchivedObject(clazz,None,contents)`, `ar.Class`, `ar.Array`.
Non-None known superclass objects are rejected. This API is **not** proof that the
whole existing Project/server works; missing schemas/graph module are separate work.

## Explicit boundaries / fail closed

* Only typedstream v4; unsupported type encodings, invalid references or type mismatch,
  invalid bool, incompatible struct/array shape, unsupported 64-bit integer wire values,
  and superclass cycles fail. No unknown field-layout inference or migration.
* `q/Q` use the known 32-bit typedstream integer wire representation; values requiring
  more than 32 bits are rejected. Inputs are capped at 20 MiB. This is not a hardened
  hostile-input parser: recursive depth and total object count have no custom budget.
* String helpers recognize only observed NSString `+` layout; array helper recognizes
  only observed count + object-group layout. A UTF-8 helper cannot establish application
  charset policy. The core preserves uninterpreted bytes.
* `load_next_compatible` applies **conservative signed-length encoding checks**, not an
  actual OpenTrack native reader. `dump_verified` means same-core structural validation,
  NOT native application validation. The independent reader is used by `verify.py`.
* Native OpenTrack application acceptance, schema semantics, runtime-tail filtering,
  business constraints, production atomic file writes, and simulation correctness are
  **not established**. This core emits bytes and never writes a user project.
* Duplicate class names with different versions are preserved, not declared application
  safe. Current-class layout validation belongs to audited schema adapters.

## Sources

Wire format/API reference: dgelessus/python-typedstream 0.1.0, official PyPI package
already installed by the sibling research task at `opentrack-archive-research/vendor`.
Specifically public `typedstream/stream.py` event/format documentation and
`typedstream/archiving.py` reference allocation/graph API. No upstream source is copied
or bundled here. Upstream is LGPL-3.0-or-later; if someone separately redistributes that
reader they must preserve its COPYRIGHT and COPYING/COPYING.LESSER notices.

OpenTrack schema evidence is separate: legal current fixture archives and
`OTAI/artifacts/wave2-audit/current-archive-function-field-map.json`. This core writes
existing typed groups, not guessed `encodeWithCoder` ivar layouts.
