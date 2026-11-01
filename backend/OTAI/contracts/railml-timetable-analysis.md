# RailML 2.2 timetable analysis

`opentrack_inspect_railml_timetable` is a read-only Agent preparation tool for
original stock English OpenTrack 1.7. It does not yet import/export RailML
timetables. Proprietary OpenTrack XML remains a separate implemented exchange.

## Function-first evidence

The portable bank remains `bank-v024-timetable-xml`, original binary SHA-256
`f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`.
`artifacts/research/railml-timetable-analysis-v025.json` pins 23 reviewed original
C files by address and SHA. This phase made no new decompilation bank pass.

| Original function | Address | Applied scope |
|---|---|---|
| `importRailMLTimetable_V220:` | `0x69f7fc` | Analyze before main import; explicit original scope selection |
| `xmlStartElementRailMLAnalyze_V220:` | `0x6a1e24` | Station/formation/train lookup inventory |
| `xmlStartElementRailMLAnalyze_V220:key:value:` | `0x6a1ff0` | Station name priorities, formation name, train number, type/scope |
| `xmlEndElementRailMLAnalyze_V220:` | `0x6a2288` | Native lookup inputs; UI choice ordering remains unimplemented |
| `replaceInternationalCharacters:` | `0x41c96c` | ASCII station projection only; Unicode conversion remains unverified |
| Main RailML attributes/end callbacks | `0x6a5a44`, `0x6a6c1c` | Evidence for part/connection diagnostics, not an implemented importer |

Raw C has unresolved dynamic-call, aggregate and shared-stack arguments.
The bank is machine-generated pseudocode, not recovered original source.
Schema validation and original application/parser acceptance were not run.

## Input and output

Supply `project` and exactly one of `content`/`file_path`. Files use the existing
project/data/workspace read scope and UTF-8 with optional BOM. The returned
SHA hashes inspected bytes. No artifacts, drafts or archive writes are made.
Selected project hashes are compared again after analysis.

The root must declare `version="2.2"` and use either no namespace or
`http://www.railml.org/schemas/2013`. Foreign/unknown extension subtrees cannot
impersonate timetable records. Prefix normalization is independent and reports
unverified native parity. DTDs/external resources are never read; declared
entities reject. No XSD validity is implied.

`section` chooses `summary`, `stations`, `formations`, `train_parts`, `trains`,
`train_groups`, `rows`, `times`, `references`, or `diagnostics`. Details use
`limit` (1–200) and `offset`; follow `next_offset` while `has_more`. Counts and
diagnostic counts always describe the whole input. Raw time strings and day
attributes are observed, not converted or validated as native times.

`train_type` filters the trains page. `scope` filters the times page. These
filters are independent, exact and diagnostic: null means all, empty matches
missing/empty attributes. Time items retain `scope_attribute_present` to show
that distinction. `selection_inventory` lists observed types/scopes and does
not reproduce the native menu's nil/empty distinctions, order or Cartesian
type/scope expansion. Other pages are unfiltered.

Limits: 2 MB UTF-8, 50000 elements, depth 64, 64 attributes per element, 4096
characters per attribute, 10000 records per section/diagnostic list. Each
type/scope inventory has at most 64 distinct values, each at most 80 characters.
Excess rejects with a typed error; details are not silently truncated.

## Original quirks and independent diagnostics

- The original reads **`abbrevation`**, not `abbreviation`. A nonempty value
  outranks `code`, which outranks `name`. Empty superior values plus nonempty
  `name` remain dictionary-order ambiguous; station projection is null and a
  diagnostic is emitted. XML source attribute order does not resolve it.
- Non-ASCII station candidates are retained raw with null native projection.
  Exact project matches describe saved catalog names, not runtime binding.
- Duplicate IDs, missing/ambiguous references, empty mappings, and parts
  declared after their train references are distinct diagnostics. Duplicate
  IDs are not silently selected for candidate assembly.
- Reused trainParts warn about the native importer's shared-row alias risk.
  Candidate row counts merge equal resolved boundary stations and report
  mismatched parts that the native command skips. These are static candidates,
  explicitly not native import results. No rows are assembled or mutated.
- Native connection `trainPartRef` lookup uses the train-ID lookup dictionary;
  a real part ID alone may therefore fail. The diagnostic is independent of
  source attribute ordering or trainRef/partRef conflict resolution.
- A calculated-scope import writes planned timetable fields in the original
  main callback. Observing that scope does not certify actual-time validity.

Comprehensive RailML import/export, native type/scope selection, temporal conversions,
Course creation, formation selection options, interval-group writes and exact
callback ordering remain incomplete. They must not be marked as implemented
because this preparation tool exists. No replacement simulation loop is added.
