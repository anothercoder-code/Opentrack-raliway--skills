# Current Shunting and Overlap data contract

New implementation dated 2026-10-29, not a byte recovery of the missing historical module. OpenTrack retains all dynamic execution responsibilities.

The supported input is one current Document4 graph with closed local End7/Edge3 relations. A Shunting list contains an automatic Path0 whose sole body is Shunting0 → SecurityArray6 → OrgArray2 → MutableArray0. The automatic Path carries the allocated owner ID; its body and OTArrayInfo use IDs -1/-1. A code-0 OTSigInd points back to the body. No new fictional Overlap class or role flag exists: Route group 7 stores the Shunting name and group 9 its start End ID.

Evidence checked read-only from the restored original function bank: Shunting initializer 0x5c8a04, encoder 0x5c90cc, decoder 0x5c907c, SecurityArray initializer 0x5bcf88, encoder 0x5c2c3c, getOverlap 0x5c20b4, getOverlapWithName/start 0x5c213c, ShuntingList getOverlapWithName 0x5c9700. Existing v11 `contracts/protection.md` and data implementation supply the validated automatic-Path shape. No original binary was executed.

Operations: inspect; create a bounded simple directed local End chain; bind a Route-end Overlap; unbind it; delete an unreferenced Shunting. Creation advances highestGivenRspID. Deletion never rewinds it. Body default security values are explicit, speed and release/reservation times caller-supplied. Create performs a reload and inverse graph check. Bind writes only the two native reference fields and checks reload. Delete rejects dependent Overlap/name/Path references and preserves high water. Cross-document Shunting, recursive Overlap, arbitrary legacy class migration, occupied-entry policies, rename/update and dynamic feasibility are outside this module's declared domain.

`opentrack_preview_current_shunting` takes SHA-bound `source`, `operation`, `spec`, and `preview_only`. `preview_only=false` is rejected before source reads. Outputs are hashes and receipts; no files are published. `opentrack_preview_spatial_shunting` uses seven explicit donors and the recovered finite three-station split core, which creates complete native data in memory and verifies a shared same-direction suffix. It does not generate a Shunting route or prove physical train placement. Its example request is newly assembled from v11 fixture donors in `tests/rebuild_spatial_fixture.py`.

The ordinary regression suite tests record roundtrip, binding/unbinding, dependent deletion rejection, high-water preservation, invalid numeric parameters and source immutability. This is data-function verification, not the independent publisher security gate, original software loading, or one-day simulation acceptance.

## dev1 extension

The original Document4 editing scope above remains bounded. `inspect_inventory` additionally reads known Document3/4 original layouts without permitting their mutation. `bind_overlap` accepts the opt-in `selection_policy="same_document_explicit"` for current supported local nonterminal Shunting, with default `route_terminal` unchanged. Cross-document and recursive behavior is not enabled. See `contracts/rebuild-dev1/shunting-cross-document-and-overlap.md` for the contract and evidence.
