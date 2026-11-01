# Saved-data information exchange and connection records

Discover the current edition/profile schemas; the historical 33-tool profile count is not the present registry size. This selected text/record tool group accepts inline structured inputs without reading or changing a native archive. The handlers do not launch an executable or control a desktop. That function boundary does not prohibit a separately authorized local agent or original-software workflow.

## Original timetable text

`opentrack_decode_timetable_text` accepts `content` and optional
`preserve_source`. Pass its `document` to `opentrack_encode_timetable_text`.
Edit typed row fields between these calls. Current 1.7 uses 16/8 TSV columns;
legacy 1.6 uses 14/7. An unchanged document preserves source bytes, including BOM,
comments and CRLF. Edits/format changes use canonical compatible columns and
report losses. ASCII fields, byte/row/buffer limits and unknown fields are
validated. This is not a native saved Timetable or RailML import.

## Z/V curves

`opentrack_parse_engine_curve_text` accepts `content`, returns a typed `diagram`
and ordered source rows. `opentrack_render_engine_curve_text` accepts `diagram`,
optional `engine_name` and `diagram_index`. Original atoi quirks, next-row H flag,
force-sign split and first-speed-wins ordering are explicit; inspect every loss
warning. Do not infer a complete Engine, native exporter comment byte identity,
traction feasibility or native saved diagram verification from these operations.

## Connection/turnround JSON records

1. Construct the schema's explicit state with rows, courses, formations, categories.
2. Call `opentrack_inspect_connection_records` to validate and obtain `version`.
3. Pass that same `state` and `expected_version` plus commands to
   `opentrack_apply_connection_records`. Review all `diff` and `actions`, not only
   the bounded preview. Retain the returned state/version/undo token.
4. In the **same running stdio/HTTP service**, use
   `opentrack_undo_connection_records` with that exact resulting state/version.
   Tokens are single-use and kept only in server memory. A restarted server or a
   separate CLI invocation cannot use them. JSON state may be saved by the client;
   this is not native persistence or native Undo.

Version hashes bind the caller-supplied JSON snapshot, not a server-owned project.
Apply is a pure data transformation: replaying old input may create another branch;
there is no project lock or durable optimistic-concurrency claim. Undo rejects a
mismatched state/version, invented token and token reuse. Target-0 placeholders
remain pending data, never valid native dispatch. Helpers preserve audited
counterpart/default-field semantics but do not schedule rolling stock or verify
runtime feasibility. The low-level save/load helper is not a filesystem MCP tool.

## Errors, test evidence and native boundary

Schema errors use INVALID_ARGUMENTS; domain errors retain their specific codes.
Production stdio tests cover successful calls and rejected malformed inputs;
CLI bridge returns exit 2 on tool failure. Existing archive APIs still fail with
NATIVE_DEPENDENCY_MISSING without typedstream_writer; do not bypass a denied
source download to obtain it. Read capabilities before native operations.

Detailed contracts ship in the companion MCP package under OTAI/contracts:
`timetable-text-document.md`, `engine-curve-pure.md`, `connection-records-pure.md`.
The 176-item coverage table retains unsupported/partial entries. These tools
establish only documented information-exchange subscopes, not a complete clone.
