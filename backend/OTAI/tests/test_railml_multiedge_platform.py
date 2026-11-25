"""Roundtrip a single physical RailML platform across multiple native Edges."""

import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyFacilities, ExportFacilities, InfrastructureRailMLTools
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document
from test_railml_facilities import XML
from test_railml_facility_export import find


def fixture(tmp_path, *, direction='up', mode='plain'):
    spec = generate.spec()
    spec['vertices'] = [generate.vertex(key, x * 60) for x, key in enumerate('ABMCD')]
    prototype = spec['edges'][0]
    segments = [('A', 'B', 120, 'West'), ('B', 'M', 240, 'Platform track'),
                ('M', 'C', 60, 'Platform track'), ('C', 'D', 350, 'East')]
    if mode == 'branch':
        spec['vertices'].append({**generate.vertex('Z', 150), 'y': 70})
        segments.append(('M', 'Z', 75, 'Branch'))
    spec['edges'] = [{**prototype, 'key': start + stop, 'from': [start, 1], 'to': [stop, 0],
                      'length_m': length, 'track_name': name} for start, stop, length, name in segments]
    blob, labels = schematic_document(spec, [])
    _, models = route_factory.document(writer.load_next_compatible(blob)[0])
    ids = {row.contents[9].values[1]: gid for gid, row in models.items() if writer.kind(row) == 'OTEdgeModel'}
    xml = XML
    if direction == 'down':
        xml = xml.replace(b' id="P" pos="125"', b' id="P" pos="425"').replace(b' id="C" pos="425"', b' id="C" pos="125"')
        xml = xml.replace(b'pos="425" dir="up"', b'pos="125" dir="down"').replace(b'dir="up"', b'dir="down"')
    signal_ids = ['S']
    if mode == 'signal':
        xml = xml.replace(b'</signals>', b'<signal id="INNER" name="Inner" pos="365" dir="up" '
                          b'type="main" function="exit" sight="300"/></signals>')
        signal_ids.append('INNER')
    if mode == 'inside':
        xml = xml.replace(b'id="P" pos="125" length="300"', b'id="P" pos="126" length="299"')

    work = tmp_path / 'OTAI/workspaces/railml-platform'
    work.mkdir(parents=True)

    def source(name, raw):
        path = work / name
        path.write_bytes(raw)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}

    request = {
        'railml': source('Platform.railml', xml), 'worksheet': source('Track.opentrack', blob),
        'tracks': [{'track_id': 'T', 'edges': [{'edge_id': ids[240], 'start_end_id': labels['B'][1]},
                                              {'edge_id': ids[60], 'start_end_id': labels['M'][1]}]}],
        'signals': [{'signal_id': sig} for sig in signal_ids],
        'stations': [{'cross_section_id': 'C', 'platform_edge_id': 'P', 'exit_signal_id': 'S',
                      'stop_post_id': 'SP', 'direction': direction}],
        'target_directory': (work / 'Native').relative_to(tmp_path).as_posix(),
    }
    return InfrastructureRailMLTools(tmp_path), request, work, source, labels, ids


def published(tmp_path, direction='up'):
    service, request, work, source, labels, edges = fixture(tmp_path, direction=direction)
    applied = service.facilities(ApplyFacilities(**request, preview_only=False))
    target = work / 'Native'
    sheet = (target / 'Track.opentrack').read_bytes()
    station = applied['source_station_cross_sections']['C']
    export = {
        'template_railml': request['railml'], 'worksheet': source('Populated.opentrack', sheet),
        'stations_catalog': source('Populated.stations', (target / 'FacilityCatalog.stations').read_bytes()),
        'tracks': request['tracks'], 'signals': [{'signal_id': 'S', 'track_id': 'T', 'direction': direction,
                                                 'end_id': station['reference_end_id']}],
        'stations': [{**request['stations'][0], 'station_sign': 'CTR', 'track_id': 'T', 'ocp_id': 'O'}],
        'target_path': (work / 'RoundTrip.railml').relative_to(tmp_path).as_posix(),
    }
    return service, applied, export, source, labels, edges, sheet


@pytest.mark.parametrize('direction', ('up', 'down'))
def test_reversible_ordered_platform_keeps_exact_stopping_edge_and_member_pairs(tmp_path, direction):
    service, applied, export, _, labels, edges, sheet = published(tmp_path, direction)
    row = applied['source_station_cross_sections']['C']
    approach = ('B', 'M', 'C') if direction == 'up' else ('C', 'M', 'B')
    lengths = (240, 60) if direction == 'up' else (60, 240)
    half = int(direction == 'down')
    assert row['ordinary_end_ids'] == [labels[name][half] for name in approach[:-1]]
    assert row['stopping_edge_id'] == row['area_edge_id'] == edges[lengths[-1]]
    assert row['area_edge_ids'] == [edges[length] for length in lengths]
    assert row['reference_end_id'] == labels[approach[-1]][half]
    assert row['length_m'] == 300 and applied['station_readback']['multi_edge_platform_count'] == 1
    _, by_id = route_factory.document(writer.load_next_compatible(sheet)[0])
    st = by_id[row['reference_end_id']].contents[12].value
    for name, kind in zip(approach, (1, 1, 2)):
        for end in labels[name]:
            assert by_id[end].contents[12].value is st
            assert by_id[end].contents[20].value == kind
    assert by_id[row['reference_end_id']].contents[11].value is by_id[applied['source_signals']['S']['model_id']]
    check = service.export_facilities(ExportFacilities(**export, preview_only=False))
    assert check['reimport']['byte_identical_worksheet']
    assert check['source_station_cross_sections']['C']['area_edge_ids'] == row['area_edge_ids']
    data = (tmp_path / export['target_path']).read_bytes()
    assert find(data, 'platformEdge', 'P').get('length') == '300'
    assert find(data, 'stopPost', 'SP').get('pos') == ('425' if direction == 'up' else '125')


@pytest.mark.parametrize(('mode', 'error'), [
    ('inside', 'complete contiguous native Edges'),
    ('branch', 'unbranched at each native boundary'),
    ('signal', 'Additional signals inside the platform'),
])
def test_platform_rejects_ambiguous_extent_and_stop_before_publication(tmp_path, mode, error):
    service, request, work, *_ = fixture(tmp_path, mode=mode)
    with pytest.raises(APIError, match=error):
        service.facilities(ApplyFacilities(**request, preview_only=False))
    assert not (work / 'Native').exists()


def test_export_rejects_a_gap_in_existing_station_membership(tmp_path):
    service, _, export, source, labels, _, sheet = published(tmp_path)
    root, version = writer.load_next_compatible(sheet)
    _, by_id = route_factory.document(root)
    for key in labels['M']:
        by_id[key].contents[12].value = None
    export['worksheet'] = source('Broken.opentrack', writer.dump_verified(root, version))
    with pytest.raises(APIError, match='must follow every complete RailML-mapped Edge'):
        service.export_facilities(ExportFacilities(**export, preview_only=False))
    assert not (tmp_path / export['target_path']).exists()
