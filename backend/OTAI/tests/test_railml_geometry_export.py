"""Export native directed tracks, switch slots, and reciprocal worksheet connectors."""

import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag, railml_tree
from opentrack_ai.current_archive.infrastructure_railml_tools import ExportFacilities, ExportGeometry, InfrastructureRailMLTools
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document
from test_railml_facility_export import export_fixture, find


def trace(track_id, *edges):
    return {'track_id': track_id, 'edges': [{'edge_id': edge, 'start_end_id': start} for edge, start in edges]}


def place(tmp_path, name, blob, traces):
    directory = tmp_path / 'OTAI/workspaces/geometry'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(blob)
    return {'path': target.relative_to(tmp_path).as_posix(), 'sha256': sha(blob), 'tracks': traces}


def physical(blob):
    _, byid = route_factory.document(writer.load_next_compatible(blob)[0])
    return [(key, edge) for key, edge in byid.items() if writer.kind(edge) == 'OTEdgeModel']


def test_fresh_railml_preserves_directional_engineering_and_exact_copy_contract(tmp_path):
    spec = generate.spec()
    edge = spec['edges'][0]
    edge.update(radius_m=600.5, gradient_per_mille=-7.25, equal_speed=False,
                speeds=[dict(train_type='0', speed12_kmh=110, speed21_kmh=90),
                        dict(train_type='1', speed12_kmh=125, speed21_kmh=115)])
    sheet, ids = schematic_document(spec, [])
    [(edge_id, _)] = physical(sheet)
    source = place(tmp_path, 'Line.opentrack', sheet, [trace('T', (edge_id, ids['right'][0]))])
    service = InfrastructureRailMLTools(tmp_path)
    target = 'OTAI/workspaces/geometry/Reverse.railml'
    args = ExportGeometry(documents=[source], target_path=target)
    preview = service.export_geometry(args)
    assert not (tmp_path / target).exists()
    report = service.export_geometry(args.model_copy(update={'preview_only': False}))
    out = (tmp_path / target).read_bytes()
    assert sha(out) == preview['output_sha256'] == report['output_sha256']
    assert report['saved'] and report['post_commit_verified']
    assert report['omitted_native_fields']['unselected_speed_categories']['sample'] == ['1']
    assert report['output_inventory']['total_track_length_m'] == 1000
    root = railml_tree(out)
    assert [(o.get('dir'), o.get('pos'), o.get('vMax')) for o in root.iter(tag('speedChange'))] == [
        ('up', '0', '90'), ('down', '1000', '110')]
    groups = {group.get('id'): group.find(tag('speeds', 'speed'))
              for group in root.iter(tag('infraAttributes'))}
    for change in root.iter(tag('speedChange')):
        profile = groups[change.get('profileRef')]
        assert profile.attrib == {'etcsTrainCategory': '0', 'vMax': change.get('vMax')}
    assert next(root.iter(tag('gradientChange'))).get('slope') == '7.25'
    assert next(root.iter(tag('radiusChange'))).get('radius') == '-600.5'
    assert (tmp_path / source['path']).read_bytes() == sheet


def test_turnout_uses_first_slot_trunk_and_rejects_wrong_mapping(tmp_path):
    spec = generate.spec()
    spec['vertices'] += [generate.vertex('main', 430), {**generate.vertex('branch', 430), 'y': 120}]
    lead = spec['edges'][0]
    spec['edges'] += [
        {**lead, 'key': 'main', 'from': ['right', 1], 'to': ['main', 0]},
        {**lead, 'key': 'branch', 'from': ['right', 1], 'to': ['branch', 0], 'track_name': 'branch'},
    ]
    sheet, ids = schematic_document(spec, [])
    edges = {record.contents[8].value.contents[0].value: edge_id for edge_id, record in physical(sheet)}
    lead_id, main_id, branch_id = (edges[ids[key][0]] for key in ('right', 'main', 'branch'))
    maps = [trace('Main', (lead_id, ids['left'][1]), (main_id, ids['right'][1])),
            trace('Branch', (branch_id, ids['right'][1]))]
    src = place(tmp_path, 'Jct.opentrack', sheet, maps)
    service = InfrastructureRailMLTools(tmp_path)
    report = service.export_geometry(ExportGeometry(documents=[src]))
    assert report['native_turnout_count'] == 1
    assert report['output_inventory']['reciprocal_connection_pairs'] == 1
    assert report['output_inventory']['unmatched_connection_count'] == 0
    reversed_branch = trace('Branch', (branch_id, ids['branch'][0]))
    with pytest.raises(APIError, match='away from the native facing junction'):
        service.export_geometry(ExportGeometry(documents=[{**src, 'tracks': [maps[0], reversed_branch]}]))
    with pytest.raises(APIError, match='cover each physical native Edge'):
        service.export_geometry(ExportGeometry(documents=[{**src, 'tracks': [maps[0]]}]))


def test_cross_document_connectors_export_once_with_exact_references(tmp_path):
    a, a_ids = schematic_document(generate.spec(), [('left', 0), ('left', 1)])
    b, b_ids = schematic_document(generate.spec(), [('right', 0), ('right', 1)])
    pair, _, _ = generate.make_pair({'A': a, 'B': b}, {'A': 'A.opentrack', 'B': 'B.opentrack'})
    a_edge = physical(pair['A'])[0][0]
    b_edge = physical(pair['B'])[0][0]
    a_source = place(tmp_path, 'A.opentrack', pair['A'], [trace('East', (a_edge, a_ids['left'][1]))])
    b_source = place(tmp_path, 'B.opentrack', pair['B'], [trace('West', (b_edge, b_ids['left'][1]))])
    service = InfrastructureRailMLTools(tmp_path)
    report = service.export_geometry(ExportGeometry(documents=[a_source, b_source]))
    assert report['native_cross_document_connector_pairs'] == [
        {'first': {'document': 'A', 'end_id': a_ids['right'][0], 'connector_id': a_ids['right'][1], 'track_id': 'East'},
         'second': {'document': 'B', 'end_id': b_ids['left'][1], 'connector_id': b_ids['left'][0], 'track_id': 'West'}}]
    assert report['output_inventory']['reciprocal_connection_pairs'] == 1
    assert report['translated_document_coordinates'] == {'A': (0.0, 0.0), 'B': (200.0, 0.0)}
    assert not report['preserves_native_document_boundaries']
    with pytest.raises(APIError, match='Missing connector document'):
        service.export_geometry(ExportGeometry(documents=[a_source]))


def test_fresh_facility_exchange_builds_geometry_and_roundtrips_exact_stop(tmp_path):
    service, payload, _, ids = export_fixture(tmp_path)
    del payload['template_railml']
    sheet = (tmp_path / payload['worksheet']['path']).read_bytes()
    by_length = {edge.contents[9].values[1]: ident for ident, edge in physical(sheet)}
    payload['tracks'] += [trace('West', (by_length[120], ids['A'][1])),
                          trace('East', (by_length[350], ids['C'][1]))]
    result = service.export_facilities(ExportFacilities(**payload, preview_only=False))
    out = (tmp_path / payload['target_path']).read_bytes()
    assert result['reimport']['byte_identical_worksheet']
    assert not result['geometry_template_preserved']
    assert result['fresh_geometry']['native_edge_count'] == 3
    assert result['verified_direct_native_connection_count'] == 2
    assert find(out, 'platformEdge', 'P').get('length') == '300'
    assert find(out, 'stopPost', 'SP').get('pos') == '300'
