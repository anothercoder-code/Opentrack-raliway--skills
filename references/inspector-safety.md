# Original Inspector selected-object lifetime

First satisfy [full original-software authorization](software-authorization.md).
This reference records a recovered failure mode and an optional source project;
it is not a requirement to inject a guard for every drawing or simulation task.

## Failure and historical component

The original 1.7 Station Inspector can redraw its table before refreshing an
unretained `selectedGraphicModel`. A retained crash dump recorded `graphicView`
sent to a freed object after closing paths left the selection stale. Correcting
graphic alignment does not prove that lifecycle problem is repaired. A nil test
after messaging a stale pointer is insufficient.

The earlier English-only guard was designed to invalidate selection before
potentially reentrant display/update callbacks and before owning document, view
or model destruction. It must not retain an already stale pointer or assume
that retaining a model keeps its associated view/document safe. Exact EXE,
Objective-C method/ivar ABI and hook identities are part of that component's
contract, not rules for arbitrary OpenTrack extensions.

## Current distribution and use boundary

The current package retains source under `native-inspector-guard/`;
its earlier prebuilt EXE/DLL have been removed. The old local
`D:/opentrack/OTInspectorGuard` artifact path is historical provenance, not a
fallback installation or an executable command for another user's machine.
No Skill CLI or MCP operation automatically starts/injects this guard, and
normal original/localization launchers do not automatically load it.

Before any future use, confirm that the selected source/build actually exists,
review its current fingerprints and licensing prerequisites, and establish an
explicitly authorized invocation path. Do not assume that an old standalone
launcher participates in the current attestation gate. The historical design
used a fresh owned child and `WH_GETMESSAGE` on its own thread, with no attach/PID
mode; that description does not certify a newly compiled or old external binary.

The guard has static/offline evidence only. Compilation, mocked lifecycle or
reentrancy checks, source installation and PE checks are not original-runtime
acceptance: `runtime_verified=false`. If runtime verification is requested,
use a disposable project copy and cover the affected double-click, selection,
closing/deletion, panel and post-simulation paths with actual native evidence.
Its recovered UI-thread scope is not arbitrary cross-thread safety.

The former empty-selection/dummy-panel sequence remains a diagnostic candidate,
not a proven safe workaround: displaying one panel can redraw older panels before
a later pointer clear. Do not present it as the fix or force it into every task.
For current-project replacement, close affected Inspectors and genuinely unload
the old model/catalog objects as documented in
[station layout](station-document-layout.md); preserve unrelated dirty work.
