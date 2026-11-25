"""Export a cross-worksheet platform to one correctly measured fresh RailML track."""

from pathlib import Path

import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag, railml_tree
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyCrossDocumentPlatform, ExportCrossDocumentPlatform
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_railml_cross_document_platform import fixture


def apply_and_export_args(tmp_path, direction, *, middle=False):
    service, request, folder = fixture(tmp_path, direction, middle=middle)
    stage = folder / 'Output'
    receipt = service.cross_document_platform(ApplyCrossDocumentPlatform(**request, preview_only=False))

    def ref(path):
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(path.read_bytes())}

    args = {'documents': [ref(stage / Path(source['path']).name) for source in request['documents']],
            'stations_catalog': ref(stage / 'Project.stations'), 'track': request['track'],
            'station': {**request['station'], 'station_sign': 'P', 'ocp_id': 'O'},
            'target_path': (folder/'Roundtrip.railml').relative_to(tmp_path).as_posix()}
    return service, request, args, folder, ref, receipt


@pytest.mark.parametrize('direction', ('up', 'down'))
def test_cross_document_export_is_a_single_track_and_reimports_both_native_members(tmp_path, direction):
    service, request, args, folder, ref, applied = apply_and_export_args(tmp_path, direction)
    preview = service.export_cross_document_platform(ExportCrossDocumentPlatform(**args))
    assert not (tmp_path/args['target_path']).exists()
    exported = service.export_cross_document_platform(ExportCrossDocumentPlatform(**args, preview_only=False))
    assert exported['saved'] and exported['post_commit_verified'] and preview['output_sha256'] == exported['output_sha256']
    assert exported['output_inventory']['track_count'] == 1
    assert exported['output_inventory']['total_track_length_m'] == 450
    assert exported['output_inventory']['reciprocal_connection_pairs'] == 0
    assert exported['engineering']['native_cross_document_connector_pairs'][0]['embedded_position_m'] == 290
    assert exported['source_facility']['reciprocal_connectors'] == applied['reciprocal_connectors']
    assert exported['reimport']['native_layout_verified']
    assert exported['reimport']['catalog_byte_identical']
    assert exported['reimport']['worksheet_bytes_match'] == {'Left': True, 'Right': True}
    assert exported['reimport']['worksheet_seed_sha256'] == {
        Path(source['path']).stem: source['sha256'] for source in request['documents']}
    xml = tmp_path / args['target_path']
    root = railml_tree(xml.read_bytes())
    [ocp] = root.iter(tag('ocp'))
    [platform] = root.iter(tag('platformEdge'))
    [stop] = root.iter(tag('stopPost'))
    assert (ocp.get('id'), ocp.get('code')) == ('O', 'P')
    assert (platform.get('pos'), platform.get('length'), platform.get('dir')) == (
        ('50' if direction == 'up' else '350'), '300', direction)
    assert stop.get('pos') == ('350' if direction == 'up' else '50')
    assert stop.find(tag('signalRef')).get('ref') == 'SI'
    if direction == 'up':
        # Active public reimport from the source worksheet baselines.
        request.update(railml=ref(xml), target_directory=(folder/'Reimported').relative_to(tmp_path).as_posix())
        receipt = service.cross_document_platform(ApplyCrossDocumentPlatform(**request, preview_only=False))
        assert receipt['members'] == applied['members']


def test_cross_document_export_preserves_layout_when_original_graphic_id_is_not_next(tmp_path):
    service, _, args, folder, ref, applied = apply_and_export_args(tmp_path, 'up')
    path = folder/'Output/Left.opentrack'
    root, version = writer.load_next_compatible(path.read_bytes())
    _, byid = route_factory.document(root)
    byid[applied['local_station_model_ids']['Left']].contents[0].value += 40
    changed = folder/'Changed'
    changed.mkdir()
    candidate = changed/'Left.opentrack'
    candidate.write_bytes(writer.dump_verified(root, version))
    args['documents'][0] = ref(candidate)
    args['speed_profiles'] = [{'native_train_type': '0', 'etcs_train_category': 3}]
    receipt = service.export_cross_document_platform(ExportCrossDocumentPlatform(**args, preview_only=False))
    assert receipt['reimport']['native_layout_verified']
    assert receipt['reimport']['worksheet_bytes_match'] == {'Left': False, 'Right': True}
    root = railml_tree((tmp_path/args['target_path']).read_bytes())
    assert {entry.get('etcsTrainCategory') for entry in root.iter(tag('speedChange'))} == {'3'}


@pytest.mark.parametrize(('fault', 'error'), [
    ('duplicate_id', 'facility ID is duplicated'),
    ('incomplete_edge_trace', 'cover each physical native Edge'),
    ('wrong_direction', 'no platform approach'),
])
def test_cross_document_platform_export_rejects_ambiguous_or_incomplete_mappings(tmp_path, fault, error):
    service, _, args, _, _, _ = apply_and_export_args(tmp_path, 'up')
    if fault == 'duplicate_id':
        args['station']['ocp_id'] = args['track']['track_id']
    if fault == 'incomplete_edge_trace':
        args['track']['edges'].pop(0)
    if fault == 'wrong_direction':
        args['station']['direction'] = 'down'
    with pytest.raises(APIError, match=error):
        service.export_cross_document_platform(ExportCrossDocumentPlatform(**args, preview_only=False))
    assert not (tmp_path/args['target_path']).exists()


@pytest.mark.parametrize('direction', ('up', 'down'))
def test_three_worksheet_export_recovers_both_connectors_and_the_same_native_platform(tmp_path, direction):
    service, _, args, _, _, imported = apply_and_export_args(tmp_path, direction, middle=True)
    result = service.export_cross_document_platform(ExportCrossDocumentPlatform(**args, preview_only=False))
    connectors = imported['reciprocal_connector_pairs']
    assert result['source_facility']['reciprocal_connector_pairs'] == connectors
    assert [[end[0] for end in row] for row in connectors] == (
        [['Left', 'Middle'], ['Middle', 'Right']] if direction == 'up' else [['Right', 'Middle'], ['Middle', 'Left']])
    assert imported['area_length_m'] == 380 and len(imported['area_edges']) == 4
    assert [row['embedded_position_m'] for row in result['engineering']['native_cross_document_connector_pairs']] == [290, 370]
    assert result['output_inventory']['total_track_length_m'] == 530
    assert result['reimport']['worksheet_bytes_match'] == {'Left': True, 'Middle': True, 'Right': True}
