"""Rebuild measured native files without any input worksheet edge or route map."""

import os
from xml.etree import ElementTree as ET

import pytest

from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag
from opentrack_ai.current_archive.itinerary_edit_tools import run_infrastructure_paths
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError
from opentrack_ai.registry import Registry
from opentrack_ai.service import Service

from test_empty_project import sources


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Fresh native project publication uses a real Windows root')


def track_xml(direction, fault=None):
    def node(parent, type_name, **attrs):
        return ET.SubElement(parent, tag(type_name), {key: str(value) for key, value in attrs.items()})

    root = ET.Element(tag('railml'), {'version': '2.2'})
    infra = node(root, 'infrastructure')
    track = node(node(infra, 'tracks'), 'track', id='main_track', name='Main')
    topology = node(track, 'trackTopology')
    node(node(topology, 'trackBegin', id='First', pos=0), 'openEnd', id='FirstOpen')
    node(node(topology, 'trackEnd', id='Last', pos=530), 'openEnd', id='LastOpen')
    origin, finish = (50, 430) if direction == 'up' else (430, 50)
    node(node(topology, 'crossSections'), 'crossSection', id='Reference', pos=finish, ocpRef='O')
    elements = node(track, 'trackElements')
    node(node(elements, 'platformEdges'), 'platformEdge', id='Platform', pos=origin, length=abs(finish - origin),
         dir=direction, ocpRef='O')
    speed = node(elements, 'speedChanges')
    for category, increase in ((3, 0), (5, 7)):
        for travel, position, base in (('up', 0, 85), ('up', 290, 110), ('down', 290, 55), ('down', 530, 88)):
            node(speed, 'speedChange', id=f'Speed{category}_{travel}{position}', dir=travel, pos=position,
                 vMax=base + increase, etcsTrainCategory=15 if fault == 'speed' and base == 85 else category)
    slopes, radii = node(elements, 'gradientChanges'), node(elements, 'radiusChanges')
    for index, (position, slope, radius) in enumerate(((0, '-0.125', 600), (290, '2.25', -800))):
        node(slopes, 'gradientChange', id=f'Slope{index}', pos=position, slope=slope)
        node(radii, 'radiusChange', id=f'Curve{index}', pos=position, radius=radius)
    ocs = node(track, 'ocsElements')
    signals = node(ocs, 'signals')
    node(signals, 'signal', id='Through', name='Through Block', pos=250 if fault == 'seam' else 325,
         type='main', function='blocking', sight=380, dir=direction)
    node(signals, 'signal', id='Exit', name='Platform Exit', pos=finish, type='main', function='exit', sight=340, dir=direction)
    stop = node(node(ocs, 'stopPosts'), 'stopPost', id='Stop', pos=finish, dir=direction, platformEdgeRef='Platform', ocpRef='O')
    node(stop, 'signalRef', ref='Exit')
    node(node(infra, 'operationControlPoints'), 'ocp', id='O', code='PLT', name='Measured Platform')
    node(node(node(infra, 'trackGroups'), 'line', id='Line', name='Test Corridor'), 'trackRef', ref='main_track')
    return ET.tostring(root)


def request_for(tmp_path, direction, fault=None):
    source = tmp_path / 'OTProjects/Reviewed'
    source.mkdir(parents=True)
    header, shapes = sources()

    def input_file(name, data):
        path = source / name
        path.write_bytes(data)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}

    destination = tmp_path / 'OTProjects/Rebuilt'
    request = {'railml': input_file('Corridor.railml', track_xml(direction, fault)),
               'header_document': input_file('SourceHeader.opentrack', header),
               'shapes': input_file('Classes.archive', shapes), 'track_id': 'main_track',
               'worksheets': [{'document': name, 'start_position_m': low, 'end_position_m': high}
                              for name, low, high in [('West', 0, 240 if fault == 'partition' else 250),
                                                      ('Middle', 250, 370), ('East', 370, 530)]],
               'station': {'cross_section_id': 'Reference', 'platform_edge_id': 'Platform', 'exit_signal_id': 'Exit',
                           'stop_post_id': 'Stop', 'direction': direction},
               'train_types': ['Fast', 'Slow'], 'speed_profiles': [
                   {'native_train_type': '0', 'etcs_train_category': 3}, {'native_train_type': '1', 'etcs_train_category': 5}],
               'execution_root': destination.as_posix(), 'target_directory': destination.relative_to(tmp_path).as_posix()}
    registry = Registry(Service(tmp_path, False, False), profile='all')
    tool = registry.tools['opentrack_rebuild_native_railml_corridor']
    return lambda args: tool.handler(tool.model.model_validate(args)), request, destination


@pytest.mark.parametrize('direction', ['up', 'down'])
def test_rebuild_saves_directed_station_reciprocal_connectors_and_engineering(tmp_path, direction):
    rebuild, args, target = request_for(tmp_path, direction)
    preview = rebuild(args)
    assert not target.exists() and not preview['saved']
    receipt = rebuild({**args, 'preview_only': False})
    assert receipt['saved'] and preview['member_sha256'] == receipt['member_sha256']
    assert receipt['engineering_readback_verified'] and not receipt['native_worksheet_geometry_copied']
    assert receipt['platform']['area_length_m'] == 380 and len(receipt['platform']['reciprocal_connector_pairs']) == 2
    assert receipt['platform']['reference_end'][0] == ('East' if direction == 'up' else 'West')
    assert len(receipt['through_routes']) == 1 and receipt['through_routes'][0]['reserve_previous']
    assert receipt['validation']['destination_count'] == receipt['validation']['course_count'] == receipt['validation']['train_count'] == 0
    before, after = receipt['engineering_segments'][1:3]
    assert (before['start_position_m'], before['end_position_m'], before['document']) == (50, 250, 'West')
    assert (after['start_position_m'], after['end_position_m'], after['document']) == (250, 290, 'Middle')
    assert before['directional_speeds_kmh'] == after['directional_speeds_kmh'] == {
        '0': {'up': 85, 'down': 55}, '1': {'up': 92, 'down': 62},
    }
    assert (before['gradient_per_mille'], before['radius_m']) == (-0.125, 600)
    changed = receipt['engineering_segments'][3]
    assert (changed['gradient_per_mille'], changed['radius_m'], changed['directional_speeds_kmh']['0']) == (
        2.25, -800, {'up': 110, 'down': 88},
    )
    paths = run_infrastructure_paths((target / 'corridor.run').read_bytes())
    assert set(paths) == {'West', 'Middle', 'East'}
    graph = project_from({name: (target / 'OTDocuments' / f'{name}.opentrack').read_bytes() for name in paths}, paths,
                         (target / 'OTData/empty.dest').read_bytes())
    assert all(graph.block_end(tuple(left)) == tuple(right) and graph.block_end(tuple(right)) == tuple(left)
               for left, right in receipt['reciprocal_connector_pairs'])
    assert all(sha((target / member).read_bytes()) == digest for member, digest in receipt['member_sha256'].items())


@pytest.mark.parametrize(('fault', 'message'), [('partition', 'complete RailML extent'),
    ('seam', 'away from the native connector seam'), ('speed', 'declared category')])
def test_rebuild_rejects_unproved_partitions_signals_and_profiles(tmp_path, fault, message):
    rebuild, args, target = request_for(tmp_path, 'up', fault)
    with pytest.raises(APIError, match=message):
        rebuild({**args, 'preview_only': False})
    assert not target.exists()
