# Saved-data preflight reconstruction

This is new implementation, not a byte-exact restoration of the missing historical prepare module. OpenTrack remains responsible for signal state transitions, interlocking, dispatching and train dynamics.

## Public contract

`prepare_contract.preflight.check(run_blob, bound_reader)` consumes immutable run bytes and a caller-supplied exact-inventory byte reader. It returns `passed_static_subset`, structured `errors`, `unestablished`, per-dependency hashes and finite check results. The module itself opens no user project paths, writes no sources and launches no process. The outer project wrapper owns source hash/race rechecks and complete project inventory binding.

The supported current-format operating profile requires six catalogs, 1..100 documents, an explicit ordered speed-type list, an output path and an increasing run window. It checks train/category/engine, course/train/itinerary, edge speed-index and timetable references using the retained current-archive contract. A successful data preflight does not establish native loading or a completed simulation.

In dev1, known Diagram13 self-path and Station references, ordered Document Set groups, and Incident names bound to CourseList events are checked statically. Incident values are event names, not paths. Unknown layouts or unbound references are rejected. These checks do not establish diagram rendering, automatic group activation, or event triggering. See docs/rebuild-dev1-auxiliary-preflight.md for the original-function evidence. Optional run parameters other than explicit timing are recognized/preserved, not certified for full original-runtime semantics. Cross-document graph continuity is checked by the outer `MultiDocumentTools.project` layer, not claimed by this standalone catalog preflight.

## Source evidence

The recovered 01 function-bank files were read statically: `005784c8` uses whole-line `strstr` and clears the train-type array on the first TrainType entry; `006bcc70` reports missing engines but may still set the preparation flag. Therefore the Skill rejects ambiguous run fields, requires explicit speed mappings and checks engine bindings instead of treating a preparation flag as proof. The codec and `run_bundle.verify_archive_bindings` are retained project implementation contracts. No original program was run.

## Fresh verification

`python3 -m unittest discover -s tests -p test_rebuild_preflight_contract.py -v`: 15 tests passed. The actual retained v11 operating bundle passes the finite data profile: 144 courses, 6 trains, 12 stations, 720 planned timetable rows, 1 infrastructure document and 92 edges. Missing dependencies, references, speed names and invalid timing are rejected. All input bytes remain unchanged. No native-runtime or original compatibility result is claimed.
