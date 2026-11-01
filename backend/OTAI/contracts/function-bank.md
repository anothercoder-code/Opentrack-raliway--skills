# Original-build function evidence

The function bank targets stock English OpenTrack 1.7, executable SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
It contains actual Ghidra 12.2 C decompiler output. This is generated pseudocode,
not recovered original source, a callable native API, or semantic parity.

The validated full-image scan discovers 369 classes, 100 categories and 13,064
Objective-C methods. Ghidra also discovers code functions without such metadata.
The bank descriptor and quality report record successful/failed exports, rather
than assuming every discovered function decompiled. External import declarations
and non-executable COFF labels are excluded from code export.

`opentrack_read_function` works in both MCP profiles. An empty query or metadata
filter returns a paginated inventory. An exact address, or exact selector with
enough class/category/kind filters to select one entry, returns C lines. Offsets
are zero-based; returned line numbers are one-based. Limit is 1..300 lines or
inventory items. An exact missing/ambiguous selection fails. A recorded export
failure cannot be presented as working pseudocode.

The portable resource is `function-bank.zip` plus a SHA-256 descriptor. The
reader verifies the ZIP, index, point-selected C file and code hash manifest.
It never extracts files, starts OpenTrack, invokes selectors or writes process
memory. Original executable/runtime files are not included in that resource.

Before using a function as implementation evidence:

1. Resolve its class/selector and read the function, including relevant callees.
2. Check control-flow warnings, receiver identity, scalar/floating-point returns,
   aggregate ABI and variadic arguments. Generic `objc_msgSend` prototypes can
   omit real arguments. A successful decompiler call alone does not settle these.
3. Record the bank ID, entry and file digest. The reviewed Engine overlay refines
   native runtime imports and unambiguous selector/format call-site signatures.
   Unresolved call sites and complex signatures remain explicit.
4. Repair missing types/arguments/call relationships through original metadata
   and regenerate the C before implementation. Do not return to instruction-level
   analysis unless the user explicitly requests it. Leave unresolved details
   unverified, then verify saved representations against independent fixtures.
5. Verify the typed operation, persistence and real MCP transport separately.

`OTUndo/tools/verify_decompilation.py` audits local exports. The merged bank
records which pass supplied each function and preserves overlay provenance.
`OTAI/build_function_bank.py` builds a fresh immutable evidence folder and a
portable ZIP. No count in these artifacts marks the full 176-item Agent goal
complete. Framework DLL method metadata remains a separate evidence scope.

## Function-first reading, v0.17.1

The rolling-stock/controller overlay exports 1,016 focused functions. Call-site
receiver types need separate review even when selector spelling matches:
`OTPlotPoint.getX/getY` return float, whereas `OTDPoint.getX/getY` return int.
The XML end-element handler creates both types. Its intermediate point setters
take floats and its saved curve point setters take ints. The audited individual
call sites, with source metadata, are in `focused-call-signatures.json` inside
the bank. Do not use a class-wide XML-point signature override.

Exact reads return `referenced_string_literals` for their current C page and
`string_annotations_available`. Each annotation includes the DAT address,
original C line numbers, value, byte count, encoding and original-byte digest.
Extraction accepts only backed non-executable PE bytes with a bounded classic
12-byte object layout, zero ISA, exact length, trailing NUL and strict UTF-8.
These are layout candidates, not proven runtime object types. Unsupported data
stays unresolved. C bytes and their verified hashes remain unchanged.

The reader checks the annotation digest and build before returning values. It
uses only the bundled data; no executable or process is needed for MCP reads.
`OTAI/build_function_review.py` produces seven annotated reading copies and an
index guide from verified inputs. These comment-only copies are separately
hashed and explicitly labelled as reading copies, not recovered source.

This release improves function evidence and its reading workflow. It does not
add a RailML business operation or change generation behavior. A successful C
export, a string annotation and a readable function remain different from an
implemented, persisted and tested native-feature equivalent.
