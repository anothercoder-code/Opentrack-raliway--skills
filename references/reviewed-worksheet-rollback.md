# Reviewed worksheet application and rollback

The advanced CLI and MCP can apply a saved geometry increment to one existing native worksheet and restore its exact previous bytes. Use this workflow with the original OpenTrack application closed. The tools check the Windows process list and acquire the same local mutex as skill-owned original runs. They operate on ordinary files on fixed local NTFS volumes.

1. Use `opentrack_edit_saved_geometry` with a fresh output directory to generate the geometry increment. Review its original and replacement hashes with `opentrack_prepare_reviewed_movement_application`. Keep that output separate from the project.
2. Start the tool service with `--allow-apply`. Call `opentrack_apply_reviewed_worksheet` with the exact `project_run` and `bundle_manifest` path/SHA pairs, a fresh `recovery_directory` outside the project and bundle, and `consent: "apply_reviewed_worksheet"`. A named `OTProjects/<project>` or `OTAI/workspaces/<project>` project can qualify. Editor history snapshots are immutable.
3. Retain the returned `journal.path` and `journal.sha256` with the journal's `before.opentrack` and `after.opentrack`. Compare the returned worksheet hash with the approved replacement.
4. To undo the file operation, call `opentrack_rollback_reviewed_worksheet` with that exact journal path/SHA pair as `transaction`, another fresh `recovery_directory`, and `consent: "restore_reviewed_worksheet"` while OpenTrack is closed. The tool checks the installed file identity and bytes and all other run-bound project files. A normal restoration installs a new file identity with the exact original content.

Example CLI prefix

```powershell
py -3.13 -X utf8 scripts/ot.py --root D:/opentrack --profile all --allow-apply call opentrack_apply_reviewed_worksheet --args-file request.json
```

Each successful normal operation publishes a recovery journal with both native images before moving the first held file. Two separately atomic same-parent renames clear and fill the original name. Another process can briefly see a vacant name. A competing occupant causes the tool to stop without overwriting it. If the first rename has happened and the name is still vacant, the rollback tool can recover the verified original sibling and preserve its file identity using the existing journal. If the name is occupied and an interrupted sibling remains, the tool preserves all files for review. Power-loss durability of directory entries has not been verified.

The workflow verifies the complete run-bound worksheet set and native catalogue paths. Only one worksheet may change. Multi-file geometry increments, catalogue changes, alternate data streams, and worksheet files with distinct inherited owner/group/access metadata fall outside this scope. The original application's running session, in-memory Undo and autosave history remain separate from this workflow. Legacy `opentrack_apply_draft` remains quarantined.
