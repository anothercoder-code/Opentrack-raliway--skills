"""RailML inverse Facility mapping honours native operating anchors and source identity."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag, railml_tree
from opentrack_ai.current_archive.infrastructure_railml_export import export_facilities
from opentrack_ai.current_archive.infrastructure_railml_facilities import apply_facilities, project_geometry
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyFacilities, ExportFacilities, ExportFacilitySignal
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError

from test_railml_facilities import XML, fixture


def export_fixture(tmp_path, xml=XML, direction='up'):
    tool, import_args, ids = fixture(tmp_path, xml)
    import_args['stations'][0]['direction'] = direction
    args = ApplyFacilities(**import_args)
    source = (tmp_path / args.worksheet.path).read_bytes()
    sheet, catalog, report = apply_facilities(xml, source, args.tracks, args.signals, args.stations)
    work = tmp_path / 'OTAI/workspaces/facilities'

    def put(name, raw):
        path = work / name
        path.write_bytes(raw)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}

    payload = {'template_railml': put('Template.xml', xml), 'worksheet': put('Populated.opentrack', sheet),
               'stations_catalog': put('Populated.stations', catalog), 'tracks': import_args['tracks'],
               'signals': [{'signal_id': 'S', 'track_id': 'T', 'direction': direction,
                            'end_id': report['source_signals']['S']['end_id']}],
               'stations': [{**import_args['stations'][0], 'track_id': 'T', 'ocp_id': 'O', 'station_sign': 'CTR'}],
               'target_path': (work / 'Export.railml').relative_to(tmp_path).as_posix()}
    return tool, payload, put, ids


def find(blob, kind, identity):
    return next(node for node in railml_tree(blob).iter(tag(kind)) if node.get('id') == identity)


@pytest.mark.parametrize('direction', ('up', 'down'))
def test_existing_ids_preserved_and_reconstructed_from_the_native_sheet(tmp_path, direction):
    xml = XML
    if direction == 'down':
        xml = (xml.replace(b' id="P" pos="125"', b' id="P" pos="425"')
               .replace(b' id="C" pos="425"', b' id="C" pos="125"')
               .replace(b'pos="425" dir="up"', b'pos="125" dir="down"').replace(b'dir="up"', b'dir="down"'))
    tool, payload, put, ids = export_fixture(tmp_path, xml, direction)
    other = b'<signal id="Unselected" pos="300" dir="up" type="distant"/>'
    template = xml.replace(b'</signals>', other + b'</signals>').replace(b'sight="450"', b'sight="77"')
    template = template.replace(b'name="Central"', b'name="Obsolete title"')
    payload['template_railml'] = put('Template.xml', template)
    result = tool.export_facilities(ExportFacilities(**payload, preview_only=False))
    out = tmp_path / payload['target_path']
    data = out.read_bytes()
    assert result['saved'] and result['post_commit_verified'] and sha(data) == result['output_sha256']
    assert result['geometry_template_preserved'] and result['reimport']['byte_identical_worksheet']
    assert len(result['unselected_native_signal_model_ids']) == 1
    assert find(data, 'signal', 'S').get('sight') == '450'
    assert find(data, 'signal', 'S').get('dir') == direction
    assert find(data, 'signal', 'Unselected').attrib == find(template, 'signal', 'Unselected').attrib
    assert find(data, 'platformEdge', 'P').get('side') == 'left'
    assert find(data, 'platformEdge', 'P').get('height') == '760'
    assert find(data, 'ocp', 'O').get('name') == 'Central'
    assert find(data, 'stopPost', 'SP').find(tag('signalRef')).get('ref') == 'S'
    assert result['source_station_cross_sections']['C']['reference_end_id'] == (
        ids['C'][0] if direction == 'up' else ids['B'][1])


def test_geometry_only_template_gets_new_facilities_and_retains_native_edges(tmp_path):
    tool, payload, put, _ = export_fixture(tmp_path)
    geometry, _ = project_geometry(XML)
    payload['template_railml'] = put('Geometry.xml', geometry)
    result = tool.export_facilities(ExportFacilities(**payload, preview_only=False))
    data = (tmp_path / payload['target_path']).read_bytes()
    assert result['reimport']['verified'] and result['reimport']['byte_identical_worksheet']
    assert find(data, 'trackBegin', 'T1').attrib == find(geometry, 'trackBegin', 'T1').attrib
    assert find(data, 'platformEdge', 'P').get('length') == '300'
    assert find(data, 'platformEdge', 'P').get('side') is None


@pytest.mark.parametrize(('attrs', 'native_profile', 'exported_type', 'function', 'virtual'), [
    ('type="main" function="home"', (1, 2), 'main', 'home', False),
    ('type="main" function="blocking" virtual="1"', (1, 3), 'main', 'blocking', True),
    ('type="combined" function="home"', (2, 2), 'combined', 'home', False),
    ('type="combined" function="blocking"', (2, 3), 'combined', 'blocking', False),
    ('type="distant"', (3, 1), 'distant', None, False),
    ('type="repeater"', (3, 1), 'distant', None, False),
    ('type="shunting"', (4, 1), 'shunting', None, False),
])
def test_signal_roles_and_virtual_setting_roundtrip_native_bytes(tmp_path, attrs, native_profile,
                                                        exported_type, function, virtual):
    extra = f'<signal id="Variant" pos="125" dir="up" {attrs} sight="750"/>'.encode()
    xml = XML.replace(b'</signals>', extra + b'</signals>')
    tool, inputs, ids = fixture(tmp_path, xml)
    inputs['signals'].append({'signal_id': 'Variant'})
    inputs['stations'] = []
    args = ApplyFacilities(**inputs)
    original = (tmp_path / args.worksheet.path).read_bytes()
    sheet, stations, saved = apply_facilities(xml, original, args.tracks, args.signals, args.stations)
    assert stations is None
    evidence = saved['source_signals']['Variant']
    end = native.document(sheet)[3][ids['B'][0]]
    signal = end.contents[11].value
    assert signal.contents[7].value is end
    assert signal.contents[8].values == [*native_profile, 2]
    assert signal.contents[9].values == [2, 750, 646 if virtual else 644, 0]
    assert evidence['type'] == exported_type and evidence['function'] == function
    assert evidence['virtual'] is virtual
    signal_args = [ExportFacilitySignal(signal_id=sid, track_id='T', direction=row['direction'], end_id=row['end_id'])
                   for sid, row in saved['source_signals'].items()]
    output, report = export_facilities(xml, sheet, None, args.tracks, signal_args, [])
    out = find(output, 'signal', 'Variant')
    assert (out.get('type'), out.get('function'), out.get('virtual')) == (
        exported_type, function, 'true' if virtual else 'false')
    assert report['reimport']['byte_identical_worksheet']


def test_combined_physical_exit_binds_platform_and_roundtrips(tmp_path):
    xml = XML.replace(b'type="main"', b'type="combined"')
    tool, payload, _, _ = export_fixture(tmp_path, xml)
    result = tool.export_facilities(ExportFacilities(**payload))
    assert result['source_signals']['S']['type'] == 'combined'
    assert result['source_station_cross_sections']['C']['length_m'] == 300
    assert result['reimport']['byte_identical_worksheet']


def test_export_refuses_unmapped_direction_and_target_identity_capture(tmp_path):
    tool, payload, _, _ = export_fixture(tmp_path)
    payload['signals'][0]['direction'] = 'down'
    with pytest.raises(APIError, match='Expected one mapped boundary'):
        tool.export_facilities(ExportFacilities(**payload, preview_only=False))
    payload['signals'][0].update(direction='up', signal_id='T1')
    payload['stations'][0]['exit_signal_id'] = 'T1'
    with pytest.raises(APIError, match='belongs to another path'):
        tool.export_facilities(ExportFacilities(**payload, preview_only=False))
    assert not (tmp_path / payload['target_path']).exists()


def test_custom_signal_behavior_is_refused_before_publication(tmp_path):
    tool, payload, put, _ = export_fixture(tmp_path)
    root, ver, _, byid = native.document((tmp_path / payload['worksheet']['path']).read_bytes())
    byid[payload['signals'][0]['end_id']].contents[11].value.contents[16].value = 2.0
    payload['worksheet'] = put('Custom.opentrack', writer.dump_verified(root, ver))
    with pytest.raises(APIError, match='differs from the reimportable RailML signal profile'):
        tool.export_facilities(ExportFacilities(**payload, preview_only=False))
    assert not (tmp_path / payload['target_path']).exists()


@pytest.mark.parametrize('connected_boundary', ('begin', 'end'))
def test_direct_track_links_match_actual_native_end_pairs(tmp_path, connected_boundary):
    tool, payload, put, ids = export_fixture(tmp_path)
    _, _, models, _ = native.document((tmp_path / payload['worksheet']['path']).read_bytes())
    west = next(model for model in models if writer.kind(model) == 'OTEdgeModel'
                and model.contents[9].values[1] == 120)
    payload['tracks'].append({'track_id': 'West', 'edges': [{'edge_id': west.contents[0].value, 'start_end_id': ids['A'][1]}]})
    peer_link = b'<connection id="westT" ref="Twest"/>'
    boundaries = [b'<openEnd id="WestOpenBegin"/>', b'<openEnd id="WestOpenEnd"/>']
    boundaries[connected_boundary == 'end'] = peer_link
    track = (b'<track id="West" name="West"><trackTopology><trackBegin id="WestBegin" pos="0">' + boundaries[0] +
             b'</trackBegin><trackEnd id="WestEnd" pos="120">' + boundaries[1] + b'</trackEnd></trackTopology></track>')
    template = XML.replace(b'</tracks>', track + b'</tracks>').replace(b'<openEnd id="L"/>', b'<connection id="Twest" ref="westT"/>')
    payload['template_railml'] = put('Linked.xml', template)
    if connected_boundary == 'end':
        assert tool.export_facilities(ExportFacilities(**payload))['verified_direct_native_connection_count'] == 1
    else:
        with pytest.raises(APIError, match='differs from the native reciprocal End connection'):
            tool.export_facilities(ExportFacilities(**payload, preview_only=False))
