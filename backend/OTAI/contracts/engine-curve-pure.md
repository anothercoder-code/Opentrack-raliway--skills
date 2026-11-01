# Pure Z/V exchange — second-wave integration contract

## Requirement scope and unchanged acceptance

`OTAI/replica/requirements.json`: M5.2.2 Tractive Effort/Speed Diagram,
M5.2.6 Z/V Diagram Window, G01 Engine records/traction curves, A03 import/export.
This increment implements only inline text ↔ typed point data. These parent rows
remain **partial**, not completed. Original acceptance still requires callable real
Agent transport and relevant persistence/native compatibility. Neither a parsed
JSON object nor a compatible text file is a loaded Engine archive.

## Files and integration

Overlay `opentrack_ai/engine_curve_exchange.py` onto the baseline; review
`artifacts/engine-curve-minimal.patch`. Add `engine_curve_tools.py`.
Existing `errors.py` is unchanged and included only for isolated package testing.
Do NOT overlay this isolated empty `__init__.py` onto the production package.

Inside Registry.__init__, before constructing tools:

    from .engine_curve_tools import tool_definitions as curve_text_tools
    definitions.extend(curve_text_tools())

Add both tool names to `generation` profile:
- `opentrack_parse_engine_curve_text`
- `opentrack_render_engine_curve_text`

Both definitions use the Registry's standard four-tuple, default read-only flags,
and strict Pydantic schemas. See `artifacts/tool-schemas.json`. There are no paths,
project IDs, network callbacks, filesystem outputs, or user-controlled imports.
No typedstream/native archive modules load for these tools.

## Native text semantics retained

Evidence: existing audited source-layout functions and literals, named and hashed
in `artifacts/baseline-evidence-sha256.json`; no new original source was downloaded.
First physical line is the caption and can also be data. Only ASCII digits after
leading SP pass the numeric gate; leading TAB, plus/minus are skipped. Tokens
split on SP/TAB. Commas become decimal points; atoi-like signed numeric prefixes
truncate and invalid force becomes zero. Only exact third-token `H` marks type 2
on the NEXT parsed source row; incomplete/ignored rows do not consume the marker.
Shift happens before sign split (negative braking, otherwise traction), duplicate
removal (first speed per destination wins), and sorting. Source-order rows and
canonical diagram are both returned so data loss is not concealed.

Export visits traction then braking and writes H from the next point's type.
ASCII, NUL/control-character, signed-int32, 1022-character physical-line, 2 MB,
and 100000-source-point boundaries remain enforced. Render now also rejects
invalid FIRST point types, floats, bools and out-of-int32 point values (previously
first types could evade validation and floats could silently normalize). Text
atoi behavior is unchanged; typed JSON strictness is a distinct boundary.
Surrogate Unicode now returns a structured ASCII error instead of escaping as
an unhandled encoding exception.

## Output/loss rules

Parse returns source rows, canonical diagram, SHA256/raw byte count, native
parser details and warnings for skipped rows, duplicate/sorted points, atoi
conversion, invalid force, and unrecognized extra tokens. It does not create
full saved Engine defaults, choose supply assignments, or change metadata.

Render returns inline ASCII CRLF bytes (as JSON string), SHA256, byte count and
loss warnings. The output header deliberately says **Produced by OTAI**: it is
compatible point text, not byte-identical original OpenTrack header/date/path.
A complete export/reimport comparison catches cross-curve collisions in addition
to omitted supply/color/adhesion/scales/visibility/loss fields, first-type changes,
zero-braking reclassification and numeric/space-trimmed captions.
Inputs are never mutated. Existing archive import/apply remains lazy and is still
blocked in this environment by missing typedstream_writer; no claim otherwise.

## Verification and limitations

Run `python -B -m unittest discover -s tests -v` in this isolated directory.
Tests include strict schemas and handler invocation, missing-writer import probe,
exact compatible export bytes, reviewed original golden point VALUES, H carry,
atoi quirks, sign/duplicate/sort losses, int32/ASCII/buffer failures and mutation
checks. `tests/fixtures/compatible-golden.txt` is a manually pinned compatible
export expectation, NOT a native application export. Original fixture archive
hash is recorded as provenance only: no new decode/load test has run here.

Actual Registry/profile/CLI/stdio integration belongs to the integration worker;
standalone handler tests do not count as real MCP transport. Native Engine load,
archive apply/save/undo, native view/event execution, broader formats and full
M5/G01/A03 acceptance remain outside this increment and remain open.

## Unified wave-2 delivery

Production registration is now in OTAI/opentrack_ai/registry.py (generation and all profiles).
Use the unified packaged tests from README; prior standalone worker paths above describe development evidence, not a required external checkout.
Install dependencies from OTAI/requirements-server-tested.txt. Real production stdio/CLI and historical schemas are exercised by OTAI/tests/test_exchange_wave_stdio.py.
