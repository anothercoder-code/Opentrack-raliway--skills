# Guiding the user through original OpenTrack

先完成[原版完整版软件授权确认](software-authorization.md)。未确认时不开展业务操作，也不把用户引导当成绕过工具授权检查的替代入口。

Use this mode when the agent cannot reliably control the desktop, lacks computer
tools, or the user wants to perform the native operations. The agent remains
responsible for engineering inputs, project preparation, diagnosis and result
interpretation. The user performs the mouse/keyboard steps. This mode needs no
computer-use plugin and does not require the user to write native archive data.

Respect the user's selected operator. If they request direct agent operation,
check the callable desktop tools and their startup errors before proposing a
handoff. Installation or an enabled setting does not establish a working tool.
If the user declines doing the clicks, do not keep repeating simulator steps.
Preserve the live OpenTrack session while repairing the connection; if a client
reload requires their help, explain that specific action and retain the pending
visual checkpoint. Do not restart or reimport the railway project as a remedy
for an unavailable desktop-control tool.

Read the selected project's data contract and, for the bounded three-station
case, the [zero-start recipe](zero-start-three-station.md). That recipe records a
past native result; following it is not evidence that the current project ran.

## Prepare a concrete handoff

For a new project, select a currently active initializer/profile, inspect its
required sources, prepare its preview, publish to the authorized fresh target
and read back the saved members. Eight registered legacy geometry writers are
quarantined; an unavailable desktop or dependency does not make the old
create/editor/stage/generate/publish pipeline an alternative. Check BLOCKED
status and the [current interface index](archive-interface-index.md) before
preparing a concrete handoff. For an existing
project, inspect and edit the current files at their declared paths when the
selected operation supports it; retain its document names and catalog bindings.
Do not regenerate, relocate or repeatedly import a working project for every
small correction. A backend publisher that requires a fresh target still has
that contract; do not bypass it to overwrite an existing destination.
Keep one station per document.
Give the user the actual `.run` path, execution root, document names, six catalog
paths and expected Itinerary/Course names. Count the actual manifest: the
three-station single-scenario profile has ten inputs (three documents, six
catalogs and one run); the normal/fault yard profile has seventeen (three
documents, two sets of six catalogs and two runs). Do not hand over only
an unsaved JSON request or candidate receipt and call it a usable project.

Bind expected counts, station signs, connections, Itinerary length, active Paths
and Routes, simulation window and output path to this project's inspected data.
Use `ZF_TRIP / 3200 / Paths 1/1 / Routes 2` only for the accepted ZF example.
Explain that its fixed-root project must retain the declared execution path;
moving a ZIP elsewhere does not relocate internal bindings automatically.

If an active supported entrypoint is blocked by a setup problem, provide its
exact setup/CLI command with real authorized paths and ask for its output.
Diagnose it before proceeding. `LEGACY_GEOMETRY_DISABLED` is intentional
quarantine, not a missing-dependency error: do not tell the user that installing
a parser, changing backend paths or using an old direct call clears it.
Do not invent files, successful publication or a supported filesystem. Do not
delegate byte editing, donor identity selection or schema construction to a
beginner merely because the agent cannot use the GUI.

## Advance from the user's current state

Give one short action or a small group of adjacent actions, normally one to
three. Include the expected visible result and the specific feedback needed.
Wait at consequential checkpoints such as import, save/reload and simulation;
do not request approval after every harmless click. If the current window or menu
is unknown, ask which window/title/control is visible before giving coordinates.
Use menu labels and named controls rather than screen coordinates. When feedback
differs from the expected state, resolve that discrepancy before the dependent
step. Continue independent backend checks while waiting when useful.

If the user stops computer use, including with the physical Esc stop, stop GUI
actions immediately. A status question or request to inspect files does not
resume desktop operation. Continue the authorized offline work or explanations;
resume computer use only when the user clearly asks to continue it.

Explanations can be Chinese or the user's language. Every value typed into the
original app must be printable English/ASCII, including new names and execution
paths. Copy paths from the actual project, not a placeholder. Never instruct the
user to type Chinese into native fields or rename opaque existing template keys.

Example for a project whose files the agent has actually prepared:

> 操作：在原版 OpenTrack 的 Info → Preferences 中点击 Import，选择我给出的
> `.run` 完整路径。此步完成后先停在 Preferences。
>
> 预期：六个目录项都指向该工程的 `OTData/chain.*`，三份图形档按工程打开。
>
> 反馈：发回显示的目录路径；如果菜单不同，告诉我当前菜单文字。若方便提供
> 截图，我会按实际界面继续指导。核对后关闭 Preferences，再进行下一步。

Substitute the real verified path in an actual instruction. Do not send the
whole acceptance checklist as an undifferentiated batch of clicks.

## Window and modal state

An empty Windows process `MainWindowTitle` is not proof that this application
has no visible windows. In one stock session it remained empty while the user
could see the Simulation panel paused at 09:04:15. Use the actual window/panel
observation; do not restart a confirmed live session from the empty title alone.

For direct computer operation, retaining the first scratch document/window and
its tool binding through the session reduced focus trouble in one observed
workflow. This is an empirical precaution, not a guaranteed fix for modal
ownership or the Inspector lifetime problem. Do not create another scratch
window and assume it repairs a session whose first binding has been closed.

A native dialog missing from `listWindows` can still be active. Activating a
secondary drawing window before pasting has sent a filename/path into the
canvas instead of the dialog. Do not repeatedly try Tab, Enter, shortcuts or
paste against guessed focus. Only send text when the current editable control
and recipient are actually established. If the user accepts a guided handoff, give one precise action on the visible
dialog and wait for the resulting state. If they have declined doing the clicks,
preserve the session and explain the smallest necessary control-connection
recovery instead of repeatedly assigning that dialog step.

After the first misdirected input, stop GUI input and preserve the disk state.
If it is established that a particular document contains only the agent's
accidental, unsaved input, guide closing that document and choosing **Don't Save**
on its known prompt. Do not save the accidental canvas text, blindly discard
unknown dirty documents, force-kill the old session, or treat the lack of a
tool-selectable dialog as proof that its prompt has disappeared.

## Native checkpoints

1. **Import and bindings.** Import the exact `.run` when initially loading a
   project or intentionally switching its operating settings. For a correctly
   bound existing project, continue editing in place rather than importing again.
   Verify `DestInfoFile`, `DepotFile`, `TrainFile`, `CourseFile`, `StationFile`,
   `TimetableFile`, the infrastructure paths and output directory in the **live
   Preferences**. The `.run` or a saved Preferences file alone does not prove
   those active values. Record displayed paths or inspect a provided screenshot;
   use saved Preferences as additional evidence when available. Opening drawings
   alone does not switch operating catalogs. Close Preferences after the values
   have been checked, before issuing document or simulation commands.
   Distinguish unchanged catalogs from catalogs whose bytes were replaced at
   those same paths. A correct path is not evidence that their contents reloaded;
   the native same-path importer can skip catalog reading. Before replacing
   catalog bytes, unload their controllers as well as the affected drawings.
   If independent cache unloading cannot be established, normally end the
   controlled native session first, resolving its actual dirty prompts, then
   replace the files and restart. Exiting the old session after replacement can
   write its stale catalogs over the new bytes. After loading, verify actual
   Itinerary/Train/Course/station content, not only path strings.
2. **Verify the active list before Start.** Compare the actual Itinerary name,
   length, active Paths and Routes with this project's prepared expectations.
   For the tested ZF three-station workflow, original Document → Open → Cancel,
   then Tools → Itineraries (Ctrl+5), refreshed the list. Use that source-backed
   workaround when the matching stale-list symptom is present; it is not a
   mandatory click sequence when the current contents are already correct. If an unresponsive or unaddressable dialog
   blocked direct operation, first guide the user to cancel it and identify the
   resulting window. Do not keep sending keystrokes to a guessed window.
3. **Save and reload.** For a modified document, guide Document → Save, confirm
   its modified marker clears, then inspect the actual persisted archive and
   semantics. Ctrl+S on a clean document can perform no write; an unchanged
   title, timestamp or hash in that case is not a passed native-save test.
   If a save probe is needed, an optional source-reviewed original Inspector
   **Set** action can mark a document dirty while setting a supported field to
   its current value. First establish the real selected model, document and
   exact value, and verify that this field's native handler calls document dirty.
   Use the original UI without injection; do not invent a business-data edit to
   force saving. Read back after Save and establish that business fields and
   references did not change. Source evidence for a handler is not runtime proof
   that the action selected or saved the intended object.
   For a reload, close the Station Inspector before closing its selected
   document, then genuinely close and open that document at the same path.
   Opening a file that is already open can only focus its in-memory window;
   Revert on a clean document may not read newer disk bytes. Neither establishes
   a fresh load. Recheck identities and bindings after the actual reopen; import
   again only if operating settings need to be reapplied. Read
   [Inspector safety](inspector-safety.md) for the selected revision's limits.
   Distinguish Save of a published file from Untitled → Save As; the latter has
   not been certified by the bounded ZF acceptance.
4. **Station properties.** In the bounded accepted case, guide one station
   double-click at a time. Compare displayed Station name/sign with the expected
   station in that document. A stale previous selection is not a pass. If a
   crash or stale panel occurs, stop native interaction, retain the exact file,
   action and error details, and return to backend inspection. Do not tell the
   user that the optional guard is loaded merely because it was installed.
5. **Simulation.** Preserve existing output before rerunning; confirm the active
   Course, Start/Stop, step, Delay Scenario and output path. Guide Simulation →
   Start. Ask for the actual Messages text and final Current/End state, with a
   screenshot when available. Diagnose any warning from its exact wording.
   In the recorded ZF case, `Train not starting at Origin of Itinerary` was
   resolved by list refresh with unchanged Train data. For a new case, inspect
   the actual warning branch, active Itinerary and origin/vehicle bindings;
   do not assume the same cause or edit Train positions just to hide it.
6. **Results.** Inspect fresh output files with the backend when accessible.
   Independently check departure, intermediate passage, cross-file continuity,
   terminal zero speed, Course completion and simulation-window completion.
   A green screen, a configured Stop time or an output count alone is insufficient.
   Do not promise 43 files for other output settings or projects.

When original command-line simulation is appropriate, read the script-execution
section of [native contracts](native-contracts.md). It gives the actual argv,
valid-run breakpoint behavior, catalog writebacks and input/output binding
requirements. This can complete an authorized original-engine run when desktop
control is unavailable. CLI simulation does not prove GUI Save, reload-by-click,
lamp rendering or Inspector acceptance, and is not a way to resume stopped
native work implicitly. Keep any historical [native acceptance](native-acceptance.md)
result separate from this current run.

## Report what is actually known

Keep a short checkpoint record: project identity/input hashes, action, expected
state, received evidence and unresolved items. Identify evidence explicitly:

- **User-reported native observation:** the user's description; not independently
  visible to the agent. A bare "done" does not establish every numeric result.
- **Agent-reviewed user screenshot:** only the controls and text actually visible;
  it does not prove disk persistence or a physical train stop by itself.
- **Agent-checked saved data/output:** fresh files and their parsed values; they
  do not replace an unrecorded GUI completion event.
- **Agent-operated native check:** use this label only for controls the agent
  actually operated and results it observed in the current run.

If output or screenshots are unavailable, deliver the engineering work and state
the remaining native checks as pending or user-reported. Keep helping the user
collect the next useful observation; never relabel a guided attempt as a past
agent-run acceptance or reuse historical ZF results as current evidence.
