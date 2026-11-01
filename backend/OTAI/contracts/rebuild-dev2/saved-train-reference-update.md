# Bounded Train identity and reverse Course references

The new preview tool changes exactly one Train16 name (group 0) and all Course11 train-name references (group 3) in the complete selected multi-document project. It does not rename Courses, Engines, Stations, files or paths. There are no file writes or exports. Native simulation and GUI dirty/menu changes are outside this data operation.

## Original-function evidence, freshly inspected

- `0x6bb318` OTTrain.setTrainName assigns its saved name; `0x6c2dbc` encodes trainName first.
- `0x42b384` OTController.trainNameChangedFrom:to: forwards the change to CourseController.
- `0x45ef40` CourseController iterates its Course list and calls setTrainName on every exact string match.
- `0x455f6c` Course.setTrainName assigns the name and a runtime change flag; `0x456b6c` encodes the name after course ID, entering speed and itinerary list. Runtime flags are not invented in the saved stream.

These are decompiled function bodies with verified Objective-C metadata, not original vendor source. Their hashes are in the adjacent verification report; the vendor material is not packaged.

## Boundaries and safety invariants

The wrapper requires complete actual inventory, exact hashes, a single selected .run and 2–100 infrastructure documents (the existing multi-document domain), and passing existing operating preflight before and after. Extra unbound files are rejected; this is not a global rename over unrelated projects.

The core checks all archive graph objects and incoming references, including dictionary keys and inline typed containers. Every occurrence of the old name must be the selected Train identity or a Course train-name field; unclassified identical names, including unrelated description text and C-string/inline representations, are rejected rather than guessed. This conservative refusal is a tool boundary, **not an OpenTrack restriction**. Aliased strings shared only by recognized fields retain their sharing. New/old names are distinct printable ASCII names, capped at 200 characters; collisions and unbound Course train references are refused.

Fresh archive decode verifies updated references; reversing only the intended changed fields must restore the original graph fingerprint. The positive synthetic rename/reverse-rename test also restores exact original bytes. The generated operating-project test validates complete preflight and proves source files unchanged. No native application load or simulation result is claimed.

## Coverage dimensions

Related requirements: M5.1, M5.1.2, M6.1, M6.1.1, A04, A05, A06. Read: bounded identity/reference discovery in the operation. Generate: not provided by this tool. Modify: supported for the stated Train16/Course11 closed domain, preview only. Export: not enabled. These partial statuses do not close entire requirements.
