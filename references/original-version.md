# Original OpenTrack compatibility

The baseline is the **original stock English OpenTrack railway application,
version 1.7**. It is not the Chinese localization/enhancement launcher.

| Item | Original baseline |
|---|---|
| Native executable | `OpenTrack.app/OpenTrack.exe` |
| Audited SHA-256 | `f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104` |
| UI sources | `OpenTrack.app/Resources/English.lproj` and the original manual/release notes |
| Native formats | Original `.opentrack`, `.run`, `.depot`, `.trains`, `.courses`, `.stations`, `.dest`, `.timetable`, `.otsimcor` |
| Native framework imports | Original AppKit, Foundation and NeXT runtime; no hook DLL is required |
| Excluded baseline extensions | `OpenTrack-zh.exe`, `otundo-launch.exe`, `undohook.dll`, translated controls, IME/keyboard/focus patches |

The two launchers can coexist on disk. Do not uninstall, delete or alter either
one to adapt a Skill. Select the original executable if a native run is later
authorized. The paired saved-data backend itself does not start OpenTrack or operate its UI.
The Skill can coordinate separately authorized original GUI, script-run and
bounded native-export workflows; keep those evidence layers separate.
For another original build, revalidate its archive contracts/offsets; a different
hash is an unknown build, not proof that it is a Chinese edition.

## Original UI instructions

Use original labels such as `Tools`, `Engines`, `Trains`, `Itineraries`,
`Courses/Services`, `Timetable`, `Simulation`, `Info > Preferences`, `Step` and
`Start`. Verify exact wording in the selected version's original resources or
manual when needed. Chinese explanations may follow these labels, but must not
replace them with assumed translated menu text.

Do not assume stock Ctrl+Z/Ctrl+Y, Delete/focus fixes, wheel/drag enhancements or
Chinese input from the injected build. The API's `opentrack_start_editor` and
undo/redo history operate on isolated disk snapshots and are independent of
native keyboard commands. File repairs and new projects use the original
archive format, not an enhancement-specific save format.

## Evidence and acceptance

`OTUndo/tools` and `OTUndo/out` contain offline schema readers, writers, class
metadata, assembly snippets and historical investigations. The directory name
does not mean its DLL/launcher is needed. Prefer the original executable,
English NIBs, original stock sample archives and manual as the product contract.
Keep handwritten enhancement C and its function inventory separate from the
original feature/MCP inventory.

Use `opentrack_capabilities.target_baseline` to check the selected file, stock
fingerprint and visible framework overrides. The file check does not establish
native loading, successful simulation or absence of injected modules in an
already-running process. A stock-runtime claim requires evidence for that actual
process; without it, report runtime acceptance as unverified.

Do not normalize or translate valid stock data merely because the Skill's
explanation is Chinese. Apply a text/schema repair only for a demonstrated
defect within the requested scope, preserving reference names unless a complete
rename is explicitly intended. Generated Chinese descriptions that fail the
legacy cString conversion are a specific historical case, not a requirement to
rewrite all original data.

## Original saved-record versions

The stock application's own sample infrastructure uses `OTSecurityArray v5`,
while 1.7 writes v6. A v6 reservation-point group precedes Route flags and
release/zone references, so the old and current group indices differ. The
interface reads both versions. New Route generation converts all loaded v5
descendants in its isolated draft, including Shuntings that share the parent,
and reports `serialization_migrations.OTSecurityArray`. This is a native-format
compatibility conversion, with defaults verified in the original decoder;
it does not depend on the Chinese edition. Other versions are rejected for
this operation until their layouts are audited. Input files remain unchanged.

Course record v0–v11 layouts are also audited against the original decoder;
the selected container remains `OTCourseList v3`. The English menu's actual
spacing tags are Discrete=0, Moving=2, Moving (CBTC)=3. See
[Course controls](course-controls.md) for defaults, partial editing and legacy
mode preservation. The frozen NIB is test evidence, not a runtime dependency.

Course lifecycle uses the original 1.7 reserved-ID rules and audited timetable,
Incident and diagram reference layouts. Original Reset Itineraries prunes
unavailable names; the API uses selected documents for availability. It does not
reset persisted Course properties or call a live controller. See
[Course lifecycle](course-lifecycle.md).
