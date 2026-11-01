# Audited native contracts

The machine-readable source of truth is `opentrack_get_schema`, with evidence IDs readable through `opentrack_read_evidence`. The audited OpenTrack.exe SHA-256 is `f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104`. Unknown builds require revalidation before editing or using runtime offsets.

This is the original stock English `OpenTrack.app/OpenTrack.exe`, not
`OpenTrack-zh.exe`. Localization/injection DLLs are not required. See
[original-version compatibility](original-version.md).

## Catalog failures

- `OTCourseList` archive v3 stores subclass incident/distribution arrays before inherited `embeddedArray`. Actual Courses are in `contents[4]`; `contents[1]` is the incident array. The repair only moves a nonempty all-Course misplaced array when the actual Course array and other auxiliary arrays are empty.
- `OTTrainList.contents[3]` is the vehicle list. `OTTrain.contents[2].values[1]` is the Engine-reference array; its entries refer to Engine names.
- `.depot` is the top-level Engine array. Simulation lookup compares exact Engine names, including the inherited vehicle name.
- `.stations` is a mutable dictionary keyed by station sign, containing `OTStation` values. An array with correct station values still fails native `allKeys`. That failure previously interrupted later Engine initialization even while Tools → Engines independently displayed the depot.
- `.timetable` keys are `courseID#index`. Rows also carry Course ID, index, last index, station sign, arrival and departure. Cloning a Course requires changing both keys and embedded row IDs.

## Encoding and field interpretation

- NeXT reads byte-string length tags as signed. The old literal `AA` became −86; 170 bytes must use positive `81 AA 00`. Use the audited writer and native-compatible reader; Python-only unsigned decoding is insufficient. Reencoding is allowed only if the permissive parser can still reconstruct the archive.
- This Foundation build's `NSString.cString` raises `NSCharacterConversionException` for specific generated Chinese descriptions. Normalize only known affected descriptive fields when repairing that demonstrated defect. Do not rewrite valid original data merely to match the language of the Skill, or transliterate reference keys without a complete rename operation.
- Runtime ivars are **byte offsets in objects**; archive schemas are **positions in encoded groups**. They are not interchangeable.
- `OTSignalModel.contents[8]` contains type/type/location side; `contents[9]` contains display type/sight/flags/release speed. The location side is not the display system or stopping reference.
- `OTSecurityArray.contents[5]` contains distances, times, cross-document index and dirty flag. Interpret each unit from verified semantics; 400 is not automatically 400 seconds.

## Physical and operational semantics

- Local graphic IDs repeat across documents. An attached signal is a separate object.
- Connector pairs and related half-vertices determine directional continuity; drawing proximity does not establish connectivity.
- Ordinary Routes have main-signal boundaries. Paths concatenate Routes, Itineraries concatenate Paths, and a Course selects a vehicle and itinerary.
- A new train's body extends behind the starting signal. Reserve the actual starting/approach track and any applicable platform resource until its tail clears. The first forward Route may omit this resource.
- Physical speed, numerical Step in seconds and playback Time Ratio are separate. `v_max × Step` versus shortest Edge is screening, not a convergence/collision proof.
- Class metadata and disassembly are evidence. Finding a selector is not authorization to invoke it. Optional legacy selectors need an existence check in any separately authorized native integration.

## Original script execution without desktop control

The audited original EXE accepts `-scriptinit` and one argument of the form
`-runfile=<absolute ASCII path>`. Use an argv list, with the executable's own
directory as cwd and its existing NeXT runtime environment. This starts the
original AppKit application and simulation engine; it can still open dialogs.
It does not require injection or a replacement simulator. In the tested Windows
installation the existing `NEXT_ROOT` and executable PATH were sufficient;
do not change global environment variables as part of a run.

Before launching, establish that no unresolved OpenTrack session remains,
verify the EXE identity above, and independently verify the exact run file,
all referenced documents/catalogs and output directory. An invalid or absent
`-runfile` can fall back to Recent documents rather than fail closed. Preserve
old outputs and capture exact input hashes before Start. Do not run concurrent
instances against the same catalogs or terminate an unrelated existing session.

With a valid run file, its six catalog bindings, OutputPath, Delay Scenario and
simulation controls are read by the native startup path. `-scriptinit` initializes
outputs, refreshes Itineraries, starts simulation and requests termination on
both normal End and Stop. Exit code zero alone therefore does not certify a
completed journey or window. `-script` is a continuation mode with different
header/scenario behavior; do not substitute it casually. An omitted delay
argument defaults to scenario1 before run-file precedence, not scenario None.

The script mode preserves a valid run's breakpoint. A break between Start and
Stop can pause indefinitely. For an explicitly unattended run, either generate
it with a breakpoint before Start, or record a narrowly reviewed temporary
change of that one control. In the tested 09:00..09:20 case, `Break Time#00:00:00#`
does not pause because the original breakpoint condition also requires
`startTime <= breakTime`. Retain before/actual-run hashes and restore the original
setting only after the owned process exits, checking it has not changed again.
Bind result verification to the actual run input, not its restored version.

Native exit can serialize destination, station, train and timetable catalogs;
actual timetable results can change. Preserve and attribute these changes from
fields and references, instead of rolling them back automatically or calling
every byte difference harmless. Script mode also synchronizes selected native
user defaults. Record relevant settings before and after a controlled run.

Inspect fresh protocol, Messages, Course statistics, station events, speed and
occupation outputs for the exact selected inputs. Preserve native warning
severities and diagnose each category. A GUI pause can spread producer timestamps
without making the outputs stale; any larger accepted cohort span needs an
explicit run-specific reason and the original before-run baseline. Physical
distance/time outputs have their own precision: clock strings truncate seconds,
statistics numeric seconds use zero decimal formatting, and logged kilometre
distances use four decimals. Verify these representations against fine-time
samples and recovered implementation evidence before choosing a tolerance.

This mode proves only what the actual original-engine results establish. It
does not certify GUI Save As, visible dynamic lamp colours or Inspector editing.
When those remain necessary and desktop tools are unavailable, guide one small
user action on the already prepared current project; do not ask for repeated
imports or describe an unobserved screen as agent-operated evidence.

In one later visible startup, the stock app exited before showing a window with
`FREED(id): message release sent to freed object`. Its actual dump located a
`Save Special` menu/NSMenuCell destruction chain in `awakeFromNib`, before the
simulation timer; the same saved catalogs subsequently loaded and ran with other
startup settings. That failure is separate from the Station Inspector lifetime
issue. Diagnose the failing stage and stack before changing archive data. A
successful alternate launch does not establish that the original menu bug is
fixed, and a live process alone does not establish a user-visible window.
