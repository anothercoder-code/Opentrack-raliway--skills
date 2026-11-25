import pytest

from opentrack_ai.current_archive.graphic_alignment import make_signal_placement
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, position, project_from, transform
from opentrack_ai.current_archive.tools import sha

from test_saved_multi_document_reroute import chain


def _operation(project, end_id):
    end = project.model(('A', end_id))
    return {'action': 'create_main_signal', 'end_id': end_id, 'signal_name': 'A Additional Exit',
            'main_role': 'exit', 'placement': make_signal_placement(end, *position(end)),
            'sight_m': 500, 'delay_s': 0, 'show_symbol': True, 'show_icon': True}


def test_add_main_signal_with_continued_native_routes(chain):
    documents, paths, catalog, _ = chain
    original = project_from(documents, paths, catalog)
    hashes = {key: sha(value) for key, value in documents.items()}
    output, receipt = transform(documents, paths, catalog, 'A', _operation(original, 4))
    assert set(output) == {'A'} and receipt['nonselected_graph_verified']
    fresh = project_from({**documents, **output}, paths, catalog)
    native_id = max(original.byid['A']) + 1
    signal = fresh.model(('A', native_id))
    assert receipt['signal_id'] == native_id and fresh.model(('A', 4)).contents[11].value is signal
    assert signal.contents[8].values == [1, 4, 2]
    assert _movement_manifest(original) == _movement_manifest(fresh)
    assert {key: sha(value) for key, value in documents.items()} == hashes
    with pytest.raises(ValueError, match='used by a saved movement'):
        transform(documents, paths, catalog, 'A', _operation(original, 12))
