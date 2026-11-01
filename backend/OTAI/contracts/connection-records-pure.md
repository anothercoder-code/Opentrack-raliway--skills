# JSON connection command layer

## Delivered scope

Nine actions: `insert`, indexed `delete`, `turnround_to`, `turnround_from`,
`add_start`, `add_end`, `join_at_station`, `split_at_station`, `split_at_end`.
This is structured record editing, not GUI automation, archive writing, dispatch,
coupling, circulation planning, or feasibility assessment. All 176 requirement
statuses remain immutable; this adds evidence only to a bounded sub-scope.

Input `state` has format `opentrack-connection-records-v1`, integer `revision`,
`rows`, `courses`, `formations`, `categories`, optional `metadata`. Rows use the
existing native-record connection field names. Optional row metadata preserves
unrelated timetable data; it is opaque, not interpreted. Full JSON Schema is
exported in `schemas.json`, and validation executes before commands. Exact
identity is `(course_id,index)`; rows are selected by index order, not input
array order. Duplicate row or catalog identities are rejected rather than guessed.

`expected_version` is SHA256 of canonical full state, including revision and
unrelated metadata. A successful batch returns an independent new state,
monotonically increased revision, full row before/after diff, all sequential
actions, first-ten preview, creation/deletion counts, and an undo receipt.
Errors never mutate input. No-op batches still advance revision to prevent
version reuse. 1–1000 commands per batch, at most 2 allocations per command;
no nested operations or family propagation are claimed.

The host hook returns opaque undo tokens and retains full snapshots server-side;
wrong-state, stale and reused tokens fail. Undo restores complete prior content
with a new revision, not an old version. Tokens are scoped to one live service
instance and are not durable across service restart. Core `undo` receipts are
trusted in-process values, not an authentication mechanism or an MCP input.

`save_state` uses fsynced temporary JSON + atomic replace, `load_state` validates
and rejects duplicate JSON keys. Filesystem paths are trusted host-only helpers,
not MCP arguments. JSON save/load does not demonstrate typedstream persistence.

## Reviewed behavior retained

- Insert reuses the first target-ID match. Omitted target creates `"0"` draft.
  A placeholder is not a validated connection and must not be published as valid.
- Delete removes only the current zero-based slot on selected row. Batch indices
  are sequential; no automatic reciprocal or interval-family deletion.
- Category default follows exact Course→formation→Category references. Missing
  Category resolves native 420 seconds. Finite float32, modulo 86400, truncation;
  negative means `HH:MM:SS`; overflowing/nonfinite values fail atomically.
- Turnround-to selects last owner row; target start match gives primary split
  and plain reciprocal start with nil max; otherwise first matching station
  gives join/join. From selects first owner row and plain primary, split
  reciprocal at target end or first matching station. Each owner gets its own
  Category default only when allocating.
- Existing primary resets station/location/join/split but preserves wait/type/
  distance. Existing reciprocal only ORs the requested join/split flag and
  otherwise preserves fields. Shell allocation before reciprocal lookup
  preserves two-record self-turnround behavior.
- Start helper's raw nil max is represented by logical `HH:MM:SS` plus
  `maximum_wait_is_nil:true`; other new records omit nil marker.
- Station helpers choose first matching visit even for later repeated selection.

## Evidence and requirement mapping

Reviewed inherited files (read-only frozen baseline):
`OTAI/opentrack_ai/connection_commands.py`, `OTAI/opentrack_ai/native_records.py`,
`OTAI/opentrack_ai/models.py`, `OTAI/contracts/connection-commands.md`,
`OTAI/tests/test_connection_commands.py`,
`OTAI/artifacts/research/connection-commands-v023.json`.
Original C addresses/hashes and original audit limitations remain in the last
file; this work does not assert a fresh full C or binary review. No 02-source
403 route was retried or bypassed. No native application/binary was executed.

M6.3 / M6.3.1 / M6.3.3 / M6.3.4 / M6.3.6: JSON record command and persistence
sub-scope only; original full item acceptance remains partial. R17.30 has no
specific release-note semantics in the available evidence: **not implemented or
verified as a complete release-note feature** merely from these commands.

Tests port explicit expected cases from inherited golden tests and add JSON
persistence, strict schema, version guard, error atomicity, registration hook,
server undo and duplicate-key rejection. They do not prove native compatibility.
Real MCP transport is the separate integration owner's gate, not claimed by the
standalone hook unit test.

## Version and transport boundaries

`opentrack_inspect_connection_records(state)` returns the canonical version, row/
connection counts and structural-validation scope so Agents need not compute hashes.
Apply is a pure transformation of caller-supplied state; there is no authoritative
project lock and resubmitting old state is permitted as a separate branch. Only
undo is single-use and tied to the exact output state. Do not claim apply replay
protection or cross-client concurrency control. Reserved owner rejection matches
the audited code: insert and compound turnround only, not standalone helpers.
CLI one-shot invocations cannot share undo tokens: undo requires the same live
Registry instance (e.g. same stdio/HTTP service lifetime). JSON state files are
durable; undo tokens are not.

## Integration

Copy `connection_records.py` and `connection_record_tools.py` into host package.
Call `connection_record_tools.tool_definitions(APIError)` **once per Registry**;
register each returned `(name, description, model, handler)` tuple using existing
host conventions. Model-like classes provide `model_json_schema`,
`model_validate`, `model_dump`; strict schema errors become `INVALID_ARGUMENTS`.
Retain handlers across requests so undo state persists. No shared registry file
is changed here. Dependency: jsonschema (already available in this server).

## Unified wave-2 delivery

Production registration is now in OTAI/opentrack_ai/registry.py (generation and all profiles).
Use the unified packaged tests from README; prior standalone worker paths above describe development evidence, not a required external checkout.
Install dependencies from OTAI/requirements-server-tested.txt. Real production stdio/CLI and historical schemas are exercised by OTAI/tests/test_exchange_wave_stdio.py.
