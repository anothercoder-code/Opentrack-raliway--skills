# Current Timetable row setters — integration candidate, not in batch2

Historical pure-module extraction from frozen batch2. The function manipulates archive bytes and does not invoke GUI/native simulation or upload data. Its old integration status is not the current wrapper status or a prohibition on authorized local-agent work; see [contract scope](README.md).

```python
from timetable_setters import patch_archive
new_bytes, diff = patch_archive(source_bytes, 'G1046', 0,
    {'arrival': '23:59:59', 'arrival_day_offset': -1,
     'departure': '00:00:01', 'departure_day_offset': 2})
```

Caller publishes bytes under authorized project paths with expected-source SHA and atomic transaction. This function itself never writes or mutates input bytes. It selects an existing `CourseID#index`; creates no row or template and changes no identity/reference/connection.

## Native function versus API guard

The recovered C string setters copy an Objective-C object; they **do not parse** times or derive days. Default `time_mode='strict'` accepts exact 24-hour clock text or `HH:MM:SS`; this is an API policy, not native behavior. `time_mode='raw'` accepts arbitrary valid Unicode (including empty) or nil, guarded at 1 MiB UTF-8 and no embedded NUL. No time normalization is performed. Nil is not conflated with the undefined text sentinel.

Each four day setter copies a signed int32 without clamps. All negative values and int32 extrema supported. Setting a day alone is allowed even if associated time is undefined, because the original C allows it. Actual strings/days require explicit `actual_*` keys; planned edits never change actual data. Planned cache invalidation exists only in native runtime, not serialized; no cache is invented.

Unbound interval references nil/`0`/`-1`/empty with nonzero offsets are rejected, not silently preserved as native-reload-equivalent and not silently repaired in an unrelated setter. Native `0x67af18` normalizes those offsets to zero; the caller must repair that separate domain explicitly. Bound offsets and all references remain unchanged.

## Verification

`python tests/test_timetable_setters.py -v` from this folder, or execute by path from workspace. Tests resolve immutable source `opentrack-wave2/OTAI/tests/fixtures/bjtu/OTData/empty.timetable` (74 rows). Every successful case is freshly decoded by both independent codec and official pytypedstream 0.1.0 test-only reader. A protected graph/alias signature skips only explicit target slots and verifies all remaining objects, fields, encodings and sharing topology across re-encoding. Shared row ownership rejects; replacing a shared NSString creates a new NSString and leaves its other uses untouched.

`evidence/real-archive-diffs.json` records source/output hashes and explicit field diffs; three output archives are actual source-derived samples, including variable-length strings and cross-day edits. `contracts/timetable-setters.json` records exact C zip members, hashes, mappings and domain claims. Official structural reader acceptance is **not native application execution**.

## Integration

Copy `timetable_setters.py` to `opentrack_ai/current_archive/timetable_setters.py` (imports already absolute). Connect through the existing project path/SHA/atomic-save guard. Do not replace higher-level controller interval propagation semantics with these single-row primitive setters. Tests and evidence remain a standalone integration bundle; no shared MCP registration was changed.
