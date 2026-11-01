# Function recovery before implementation

The user's development workflow is: repair original function types, arguments
and call relationships first; read the resulting functions and callees; then
implement the Agent operation. Instruction-level inspection is not an automatic
fallback. Use it only when the user explicitly requests that analysis.

This is a local development interface, with no old API compatibility gate.
It still targets original stock English OpenTrack 1.7 and preserves the complete
176-item Agent objective. A C recovery pass does not complete a business feature.

## v0.26 recovery evidence

`artifacts/research/function-types-v026.json` pins the current bank, original
binary, all 76 regenerated function hashes, script/metadata inputs and the owned
Ghidra process's successful exit. There were zero export failures; 14 C files
changed. The original executable was not run or changed.

Original Foundation/AppKit metadata declares the reviewed range argument as
`{?=II}`: two unsigned 32-bit fields. For only `substringWithRange:`,
`deleteCharactersInRange:` and `replaceCharactersInRange:withString:`, the
refiner represents this argument as explicit location/length words. Method
argument counts are checked before expansion. Other composites/arrays and
aggregate returns remain excluded. This restores 13 recorded call sites.
Signature agreement among classes does not establish the dynamic receiver class.

The regenerated XML time helper now exposes all replacement arguments. Both
comma and dot are replaced with the colon literal before splitting. Station
longitude/latitude and validity functions now show explicit double values;
the timetable key comparison shows its real getter/compare arguments. These
are concrete C readability improvements, separately checked through the real
MCP function reader. They do not prove complete native runtime semantics.

A second selector-resolution experiment produced identical C for all 76
functions and did not increase recovered sites. Its artifacts are retained,
and the source was restored to the verified first-pass hash.

## Remaining gates

The focused pass still records 37 unresolved call sites. Shared reset/setter
dispatch can retain invalid inferred stack temporaries. `rangeOfString:`
aggregate returns and all low-level numeric conversions are not certified by
the argument-only repair. Raw C stays machine-generated pseudocode, not
recovered source. Never replace missing information with invented parameter
types or claim all functions are ready for implementation.

`opentrack_read_function` serves the hash-checked C and review notes; line limits
and string annotations are unchanged. Readable examples are in
`artifacts/function-reading/function-types-v026.md`. The function bank still
contains 13534 C files; counts are not semantic completion. No new RailML
timetable importer/exporter, native parser acceptance or simulator is added.
