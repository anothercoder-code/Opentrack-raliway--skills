# Windows local archive operations

Use the paired backend and Python 3.13.x. Read `opentrack_capabilities` before
choosing file operations: tool discovery, filesystem support, publication support
and native OpenTrack acceptance are separate capabilities.

Desktop control is optional. If the agent cannot reliably operate OpenTrack,
continue backend preparation and use [user-guided operation](user-guided-operation.md)
for the native loading, saving, Inspector and simulation checks. Give concrete
paths and expected results, then evaluate the user's feedback step by step.

Select the workflow for the current requirement; a Windows host does not select
a particular station count or railway layout. For custom designs, start with
[requirement-led design](complex-design-workflow.md). The following ZF facts are
historical evidence for the [three-station recipe](zero-start-three-station.md),
not a mandatory Windows startup sequence or the expected identities of another
project. That case passed Save/reload and three true Station double-clicks.
Its original Open → Cancel / Ctrl+5 refresh confirmed
ZF_TRIP / 3200 / Paths 1/1 / Routes 2 before Start; other projects must use their
own inspected names, lengths and route counts. The unrefreshed GUI run's
Origin warning is preserved as a failed attempt; the refreshed third GUI run
produced 43 files with zero WARNING/ERROR, unchanged ten inputs and a physical
final stop. CUA terminal observation plus separate visual review establish GUI
08:12 End; disk output and a still-live process alone do not establish that time.

## Backend selection

The standalone Skill locates `backend/OTAI` automatically. The co-packaged bridge
locates its matching `OTAI/server.py`. An explicit `OTAI_ROOT` overrides that
selection and must point to the directory **containing** `OTAI`, not to `OTAI`
itself. `OTAI_DATA_ROOT` identifies the project data root. Incorrect or empty
configuration must produce a clear error; it must not silently invoke an older
backend at `D:/opentrack`.

Run the bridge with the interpreter that holds the paired dependencies. Prefer
the installation's local launcher when one is provided. For a complex request,
write UTF-8 JSON and pass `--args-file` instead of constructing a shell argument.

## Verified Windows read scope

`0.33.1-zeroaccept1` retains the native **Windows x64, fixed local NTFS** reader behind
`ArchiveTools.secure_bytes`. Source paths remain relative to the selected data
root, below `OTProjects/` or `OTAI/workspaces/`. The reader is bounded to 20 MiB
per archive. Network/UNC paths, removable drives and other filesystems are outside
this implementation's support contract.

Each path component, including the configured root's ancestors, is opened relative
to a retained parent handle. Reparse points and multi-link files are rejected;
ordinary pathname reads are not used as a fallback. The reader checks volume/file
identity, normalized handle paths and metadata before/after content reading, and
denies conflicting data-writer and rename/delete sharing. ADS and device-like path
components are rejected before opening.

The API foundation is Microsoft's [NtCreateFile contract](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile)
for relative directory handles and sharing, [GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)
for actual handle paths, and [GetVolumeInformationByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew)
for filesystem identification. These contracts support the implementation design;
they do not certify every Windows environment or every OpenTrack feature.

Use the host's reported operation-specific capabilities. Fresh single-file copy
saves and the new `opentrack_initialize_project` whole-project publisher use
Windows handle operations. Existing Linux-only incremental catalog bundle
publishers remain separate and do not gain Windows support from this change.
`opentrack_initialize_station_documents_project` also uses the same reviewed
native publisher for N station documents, six catalogs and one run member.

Winmulti1 adds retained-handle complete project enumeration for
`MultiDocumentTools.inventory_names`, so multi-document inspect/derive and the
existing A/B or line-chain previews no longer require the POSIX `parent_fd` on
Windows. The walker retains each directory/file handle, rejects reparses and
multi-link files, checks full inventories and native identities twice, and checks
parent metadata around the scan. Default bounds are 2000 files, depth 16 and
256 MiB total; individual file reads remain bounded to 20 MiB. Complete source
SHA inventories include existing result files, even when they are not selected
as run dependencies. Do not pass an old input-only inventory after simulation
has added output files.

The POSIX `parent_fd` primitive itself remains unavailable on Windows. Other
tools that still call it do not acquire support from this inventory adapter.
Unsupported operations must return explicit errors rather than retrying through
an unprotected filesystem path.

Version `0.31.0-static5` rejected Windows archive reads with
`UNSUPPORTED_SECURE_FILESYSTEM`; its bridge and pure-memory tests passed. That
historical test does not establish the new Windows implementation's acceptance.
The winread1 local acceptance read a real Engine catalog through CLI and MCP,
previewed its maximum speed from 350 to 321 km/h without saving, and rejected
wrong source hashes and out-of-scope inputs. A real six-resource initialization
preview returned eight members matching the independently invoked core. Input
hashes stayed unchanged and the stdio session closed. This establishes the tested
read/preview paths; it does not establish delivered project files or native
OpenTrack execution.

The installation's verification report records exact inputs, source hashes,
code version and native acceptance results. Keep the new revision's results
separate from historical POSIX tests and the older 0.30 simulation sample.

## Saving and native verification

For an existing-project adjustment, keep its current execution root and update
the affected members in place through an operation that actually supports it.
Use [station document layout](station-document-layout.md) for the replacement
closure and native-cache handling. Do not publish another named project merely
because its tracks, signals or diagram spacing need correction.

Only a tool whose current schema permits saving can publish. A fresh-only
publisher requires an explicit fresh target and preserves existing destinations;
it does not provide an in-place overwrite primitive. Do not weaken its guards or
silently fall back to an unsupported filesystem operation. Use a reviewed local
replacement or original native Save for the authorized current-project update;
if those are unavailable, explain that concrete missing step. New project publication uses
`opentrack_initialize_station_documents_project` for the supported one-station-per-
document chain, or `opentrack_initialize_project` for its retained single-document
profiles, with `preview_only=false` and `target_directory`.
The execution root and every document path must equal that actual target. Preserve
the nested `OTDocuments/` and `OTData/` members; never flatten the project.

Windows writes stage owned files/directories under retained directory handles,
flush file contents, atomically rename without replacement, then read actual
saved bytes and revalidate the run/document/catalog bindings. Source hashes are
checked around the transaction. A post-commit error explicitly reports
`commit_completed=true`; inspect that target before deciding on a retry. Do not
report rollback or delete a committed target merely because verification failed.
If `PUBLICATION_COMMIT_OUTCOME_UNCERTAIN` reports `commit_attempted=true` and
`commit_completed=null`, preserve both the possible final target and staging
name, inspect their actual identities/content, and reconcile before retrying.
An uncertain commit is not a known rollback. `FlushFileBuffers` verifies file
content flushing; directory-entry survival after a power loss is not certified.

The old preview tools and pure cores remain unsaved. A new tool's unsaved
`candidate_receipt` describes construction; its separate `publication` receipt
describes successful disk delivery. Neither substitutes for native simulation.

After any successful save, independently inspect the persisted bytes and bindings.
For a requested OpenTrack run, confirm the actual imported catalog paths and
enabled Course set, then capture native events, curves and statistics. A normal
simulation end is not proof of physical terminal stopping or multi-train safety.
Check the actual Itinerary contents before a run. For this original 1.7 build,
Tools > Itineraries (Ctrl+5) is one way to inspect them. Use a refresh only when
the active list/content needs it; do not repeat Open → Cancel or reimport a
correctly bound project merely to reproduce a sample sequence. Opening the
Itineraries panel removed a first-import temporary-Itinerary warning in the
historical winrelease1 single-document final-stop case. See
[historical native acceptance](native-acceptance.md) for that observed result and
the remaining limits of its diagnosis. The winmulti1 multi-document project's
loading, boundary crossings and complete journey require their own native evidence.
Read [station document project](station-documents-project.md) for the current
data and publication contract and the historically observed winmulti1 three-document
case: original Messages record REL1001 in REL_A at 06:01:00, REL_B at 06:02:50
and REL_C at 06:04:34; final speed was zero and the GUI ended at 06:12:00 without
warnings. A later station double-click crashed in the original Inspector. The
journey observations are historical evidence, not GUI editing safety or current
revision acceptance. No OpenTrack execution occurred in the staticfix1 work.

New graphic placement inputs use explicit `alignment_x/alignment_y`; legacy
placement `width/height` is rejected. The five reviewed generation pairs and
source-preservation boundary are documented in [graphic alignment](graphic-alignment.md).
The optional English-only [Inspector guard source](inspector-safety.md) addresses
selected-object lifetime separately. The current distribution is source-only;
it does not include a prebuilt guard EXE/DLL or route to an old installation.
The historical launcher design used strict PE checks and a fresh owned child,
not an old PID, but it has no current original-runtime acceptance. Any future
build/invocation needs the software-authorization prerequisite and its own
reviewed runtime checks; `runtime_verified=false`.

For the stock1.7 reader, importing the same catalog path can skip a catalog
reload. Opening an already-open document can only focus its existing object,
and Revert on a clean document may not read changed disk bytes. Actually unload
and reopen affected documents/catalogs when they changed; changing the project
folder name is not a cache-refresh mechanism. Close a selected object's Inspector
before unloading it. Retain and diagnose dirty edits rather than overwriting them.
Closing drawings alone does not unload shared catalog controllers. When their
bytes change, unload those controllers too or normally exit the controlled
session before replacement, then restart and verify actual catalog contents.
An old session can write its cached catalogs during exit and undo a premature
on-disk replacement.

Check six catalog bindings and OutputPath in the live Preferences, then close
Preferences before issuing drawing or simulation commands. The native importer
persists catalog setters before setting OutputPath, whose setter does not
immediately write Preferences; a saved Preferences file can therefore lag the
active output directory. Resolve this using live controls and the actual run
protocol, without treating either old disk text or a successful import click as
proof of all active settings. For modal focus and clean-Save limitations, read
[user-guided operation](user-guided-operation.md).
