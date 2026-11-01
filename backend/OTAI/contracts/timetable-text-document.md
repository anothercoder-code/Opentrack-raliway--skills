# Pure original timetable text / typed JSON

## Implemented scope

`opentrack_decode_timetable_text` accepts `DecodeTimetableText` and returns a
versioned, typed `ExchangeDocument`. `opentrack_encode_timetable_text` accepts
`EncodeTimetableText` and returns original-format content, format, byte count,
SHA-256, source-preservation flag and full representability warnings. Both are
filesystem-free information generation/conversion, not native archive import.
Rows can be authored directly from JSON (`course_id`, `index`, `station_sign`
required; existing TimetableStop defaults apply), edited, serialized and reloaded.
Connections reuse the actual existing ConnectionSpec, not a new invented format.

The core parser/renderer are extracted from the existing timetable_exchange.py,
with archive-only error/seconds imports removed. Their old signatures remain;
the supplied patch replaces the old definitions by reexports. No archive, native
record decoder, native program, network, source.zip or local computer is needed.
`models.py` and `errors.py` remain shared dependencies, plus existing Pydantic.

## Exact exchange grammar

Two TSV blocks, separated by `// Connections:`. Current rows have 16 columns and
connections 8; legacy rows 14 and connections 7. Existing HEADER17/HEADER16 and
CONNECTION17/CONNECTION16 remain authoritative. 15-column rows are rejected.
No CSV approximation. CRLF canonical output. Original PE-extracted header
constants are checked against their existing fixture manifest SHA-256.

Arrival/departure null maps to HH:MM:SS. Day offsets remain separate signed
integers (-366..366), preserving midnight crossings. Undefined time requires
zero day offset. Connection waits are integer seconds (0..86399), encoded as
clock strings; maximum null is HH:MM:SS. Actual times and archive-private fields
are not in this document schema and are rejected if supplied, not dropped.
Legacy output explicitly warns for omitted track/mass/time-reference fields.
Dispatching distance cannot be represented and is warned. Native connection
bits 4/8 are ignored by the audited existing parser and produce decode warnings.
Warnings do not claim native semantic equivalence for those bits.

## Preservation and validation

Unchanged typed rows + same source format reproduce provided source_text bytes
(UTF-8 BOM, comments, LF/CRLF, lexical numeric forms, trailing newline included).
Source is re-parsed and compared, not blindly trusted. Editing or changing format
uses the existing canonical writer; warning identifies loss of comments and
lexical formatting. Typed fields not edited remain equal after reparse, except
explicitly warned non-representable fields. This is not arbitrary textual patching.
`preserve_source=false` explicitly chooses canonical generation.

ASCII fields only; 2,000,000 UTF-8 input/output bytes; data lines <=4095 characters;
10000 rows and total connections; shared typed model max 100 connections per row.
Duplicate identities, negative indices, malformed column counts/booleans/time,
missing connection owners, mutually exclusive entry/dispo, invalid waits and
mixed timetable version rows fail. Index continuity, station existence,
course target availability and chronology beyond time/day typing are deliberately
project validation concerns, not asserted by standalone text conversion.
No source file is read or modified by these tools.

## Integration and transport

Copy opentrack_ai/timetable_text_{core,document}.py; apply
patches/timetable_exchange.patch from OTAI root. Register the two model/handler
pairs in the actual Registry and required profiles. `tool_definitions()` exposes
complete input JSON schemas; schema extra fields forbidden.

Standalone verification:
`python -B tests/test_exchange.py` from this package (bootstrap locates the
read-only frozen baseline). tests/stdio_server.py is a real MCP FastMCP stdio
adapter using the same typed document. It exercises initialize, tools/list,
valid decode/encode and invalid-record tool error. It is not the production
Registry; production tool discovery/profile/CLI checks are integration gates.
No dependency installation is needed.

## Evidence and limits

Tests cover original header hash/columns, authored byte-exact canonical golden,
source-byte round trips with BOM/LF/no-final-newline, cross-day and undefined
values, modification preservation, legacy losses, invalid columns/owner/flags,
ASCII/size/duplicate enforcement, ignored-bit warning, schema and real MCP.
The canonical example is independently authored from audited columns, NOT a
new native executable output capture. Existing original PE headers are the
native-origin golden evidence; no claim of fresh native execution is made.

Original requirement IDs M6.2, M6.2.1, M6.2.3, R17.28, A03: closes standalone
text generation/typed exchange implementation and independent text persistence
subscope; real standalone transport passed. Does not close all commands in
those rows. Native Windows importer/exporter execution, native project/catalog
apply, archive migration, undo and UI/live runtime fidelity remain unverified by
this work. No 176-row status is changed to complete.

## Unified wave-2 delivery

Production registration is now in OTAI/opentrack_ai/registry.py (generation and all profiles).
Use the unified packaged tests from README; prior standalone worker paths above describe development evidence, not a required external checkout.
Install dependencies from OTAI/requirements-server-tested.txt. Real production stdio/CLI and historical schemas are exercised by OTAI/tests/test_exchange_wave_stdio.py.
