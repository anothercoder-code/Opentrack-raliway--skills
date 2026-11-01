# Function coverage and native evidence

The interface is a bounded business/data adapter. Function metadata, static instruction reading, offline fields and actual native behavior are separate capabilities.

## Query a selected evidence source

First satisfy [software authorization](software-authorization.md). Use the current
paired Skill entrypoint and substitute actual paths; the acceptance machine's
D-drive installation is not a fallback backend.

```powershell
py -3.13 -B <installed-skill>/scripts/ot.py --root <actual-data-root> --profile all call opentrack_get_function_coverage --json '{"scope":"packaged","section":"summary"}'
py -3.13 -B <installed-skill>/scripts/ot.py --root <actual-data-root> --profile all call opentrack_get_function_coverage --json '{"scope":"legacy","section":"native","class_name":"OTEndModel","selector":"searchRoutes"}'
py -3.13 -B <installed-skill>/scripts/ot.py --root <actual-data-root> --profile all call opentrack_get_function_coverage --json '{"scope":"legacy","section":"python","query":"find_category"}'
```

The packaged source offers `summary`, `saved_data`, `interfaces` and `requirements`.
Legacy audit sections are `summary`, `native`, `python` and `enhancement`, and
require the actual fingerprinted audit resources. Rows are paginated. Native filters include `binary`, exact `class_name`, selector substring and `status`; helper sections support query/status. Filters on a summary or the wrong section are rejected.

Coverage records identify their source and evidence snapshot. Treat `COVERAGE_STALE`
as a freshness limitation, not permission to edit a hash or version label. The paired
`scripts/audit.py` reads a summary with `require_fresh:false`; its default
`scope=auto` selects a legacy summary when the configured data root has one,
otherwise the packaged summary. An explicit `--args-file` can select a source.
Read and retain the returned scope/freshness rather than calling either source
current solely because the command succeeded:

```powershell
py -3.13 -B <installed-skill>/scripts/audit.py --root <actual-data-root>
```

It does not write coverage artifacts, regenerate source metadata or call another
installation. Refreshing the complete source tree needs the actual maintenance tooling and
its real source/binary inputs. `require_fresh:false` permits explicitly historical
reading where the tool schema supports it; retain the reported freshness.
A corrupt report is not repaired by renaming it. Read operations do not implicitly
regenerate evidence or operate OpenTrack.

## Read function pseudocode first

Start with `opentrack_read_function`, resolving an exact original class/selector or entry. Follow [function evidence](function-decompilation.md). Its generated C and file hashes are static evidence, not native execution or complete source recovery. Repair unresolved receiver/types/arguments with original metadata and regenerate functions first. Instruction-level inspection below is available only when the user explicitly requests that analysis; it is not an automatic implementation fallback.

## Resolve and read a method

```json
{"binary":"appkit","class_name":"NSWindow","category":"NSWindowsExtensions","method_filter":"windowHandle"}
```

Use that with `opentrack_get_native_class`. Class and category lookups return their declared instance/class methods; they do not implicitly merge an inheritance hierarchy or execute the selectors. Wrong modules, missing classes, categories and methods return structured errors.

```json
{"binary":"opentrack","class_name":"OTCourseList","selector":"encodeWithCoder:","method_kind":"instance","max_bytes":512,"limit":40}
```

Use that with `opentrack_disassemble_method`. It resolves the metadata IMP in a fixed installed module, requires an executable PE32 section, reads at most 4096 bytes, and stops at the first return or a known boundary. Pagination applies to the captured window. Other branches can remain outside it; `complete_function:false` is intentional. No arbitrary address, remote process address, file path or native invocation is accepted.

## Interpret the result

| Evidence | Permitted conclusion |
|---|---|
| Class/selector/type/IMP metadata | A named method declaration is present in that binary |
| Hash-checked generated C function | A decompiler produced the recorded function body; types and semantics still need review |
| Bounded disassembly | These instructions were decoded at its static address |
| Archive representation support | Particular fields can be decoded/preserved, without native initialization side effects |
| Bounded offline subset | The stated subset is implemented under its declared limitations |
| Approximate planning model | That model produced the estimate, without native physics equivalence |
| Actual native run evidence | Only the tested input, departure/terminal/run behavior actually observed |

The historical coverage snapshot reports general native invocation as unexposed.
It does not describe every later standalone workflow: the current separate
[native diagram bridge](native-running-diagram.md) exposes only its reviewed,
fingerprint-bound export sequence. Do not interpret the old table as a ban on
that implemented workflow or as permission for arbitrary native execution. Category metadata and disassembly are read-only inspection capabilities, not simulation control. Read-only directional search and particular typed current-archive builders have
their own contracts. The registered legacy generic geometry/history pipeline,
including create/editor/stage/generate/publish writers, is quarantined; old
coverage rows do not make those writers usable. Check current BLOCKED status
rather than inferring availability from registration or historical reachability. Complete search/interlocking/editor equivalence, complete Signal/worksheet properties, full physics and per-train native acceptance remain gaps. See [network operations](network-operations.md) and [geometry editing](geometry-editing.md) for exact supported scopes.

The audit's semantic links are positive-only reviewed relations. Do not calculate a native completion percentage from metadata counts or assume every unmapped getter has no related catalog data. Keep named gaps visible when reporting a task as complete or partial.
