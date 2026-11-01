"""Explicit fail-closed quarantine, independent of optional legacy dependencies.
The current_archive APIs do not import or call this legacy Project pipeline.
"""
from .errors import APIError
CODE='LEGACY_GEOMETRY_DISABLED'
REASON=('Legacy whole-project geometry writes are quarantined pending saved-field audit. '
        'The old worksheet show_grid mapping conflicts with a protected Document flag, '
        'and old document factories assigned an unverified group18 identifier. '
        'No protected field is edited or repaired; use bounded current_archive tools.')
BLOCKED_TOOLS=frozenset({'opentrack_create_project','opentrack_generate_operations',
    'opentrack_stage_changes','opentrack_start_editor','opentrack_edit_editor',
    'opentrack_publish_draft','opentrack_apply_draft','opentrack_create_demo_line'})
def reject(*args,**kwargs):
    raise APIError(CODE,REASON,{'status':'blocked','independent_of_missing_dependencies':True,
        'legacy_draft_publication_allowed':False,'current_archive_tools_affected':False})
