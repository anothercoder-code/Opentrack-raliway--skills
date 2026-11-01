# Read functions before implementing commands

Use `opentrack_read_function` before investigating a missing/uncertain command.
When installed beside the selected backend under `OTAI/resources`, the verified
function bank provides original-build Ghidra C pseudocode and a paginated index;
the reader never starts OpenTrack. This Skill distribution contains the reader
and contracts but does not include `function-bank.json`/its archive. The packaged
reader reports `FUNCTION_BANK_UNAVAILABLE` if that separate resource is absent.
Do not assume tool registration means its optional evidence payload is installed,
or silently select another installation. Business investigation still requires
[full software authorization](software-authorization.md).

```json
{"class_name":"OTEngineController","selector":"engineZVImportPressed:","limit":100}
```

Use `offset` for the next page. Search by `query` or class without a selector to
list candidates, then resolve one exact entry. Categories and class/instance
methods are distinct. An address can select an unowned C function:

```json
{"address":"0x4cdea0","limit":100}
```

Record bank ID, entry and SHA-256. Inspect warnings, actual receiver types,
integer/floating-point results, variadic formats and aggregate returns. Some
Objective-C call sites still have generic types; generated C can omit arguments.
Read callees before deriving rules. If parameters, receiver types or call
relationships are missing, repair metadata/prototypes and regenerate the C
before implementing the operation. During implementation do not return to
assembly unless the user explicitly requests instruction-level analysis.
Unresolved details stay unverified; a cleaner-looking function is not proof of
its semantics. Verify the saved layout with native fixtures at the stated scope.

The reader returns `referenced_string_literals` for the current C page. These
hash-checked annotations resolve bounded classic constant-string layout
candidates, including XML field names left as `DAT_...` by Ghidra. Their `lines`
use the original 1-based C line numbers; pagination uses a 0-based `offset`.
The C bytes are unchanged. A string annotation does not prove a receiver's class,
and unrecognized constants remain unresolved. With the verified bank installed, querying its functions needs neither the
original EXE nor a running application process. This technical independence does
not remove the software-authorization prerequisite or provide the missing bank.

For example, `OTTrainController` / `xmlStartElement:key:value:` exposes original
rolling-stock XML attribute handling. Read `xmlStartElement:`, `xmlEndElement:`
and the Engine/Train model callees before deriving import behavior. Seeing these
functions does not mean RailML import/export has been implemented as an Agent
operation. Do not switch back to broad assembly browsing or guess types merely
to make pseudocode look cleaner.

The frozen original-build bank inventory described by this historical recovery
record has 369 classes, 100 categories and 13,064 methods. Actual exported/failed counts are in `OTAI/resources/function-bank.json`
and quality-report.json inside the ZIP. Do not substitute metadata counts or a
readable function for a typed operation, persistence test or real transport test.
No function count proves original source recovery or complete Agent parity.

The historical v0.26 recovery pass regenerated 76 functions and restores 13 range-argument call sites
from original `{?=II}` metadata. This repairs only those argument words, not
aggregate returns or all receiver identities. Shared reset/setter calls remain
unresolved and are explicitly noted by the reader. Read the packaged
`OTAI/contracts/function-types.md` before treating these functions as ready for
business implementation. That recovery pass itself added no RailML timetable
importer/exporter; this is not a statement that later releases have no export.
See [current RailML timetable export](railml-timetable-export.md) for its actual
implemented scope, and retain the separate importer gap.
