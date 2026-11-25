"""Native readback for branched RailML worksheet rebuilding with no topology donor."""

from copy import deepcopy
import os
from xml.etree import ElementTree as ET

import pytest

from opentrack_ai.current_archive import course_factories, writer
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag
from opentrack_ai.current_archive.itinerary_edit_tools import run_infrastructure_paths
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError
from opentrack_ai.registry import Registry
from opentrack_ai.service import Service

from test_empty_project import sources


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Native project publication uses an actual Windows root')


def node(parent, element, **attributes):
    return ET.SubElement(parent, tag(element), {key: str(value) for key, value in attributes.items()})


def station_xml(fault=None, *, passing_loop=False):
    root = ET.Element(tag('railml'), {'version': '2.2'})
    infra = node(root, 'infrastructure')
    ocps = node(infra, 'operationControlPoints')
    node(ocps, 'ocp', id='Station', code='STA', name='Shared station')
    tracks = node(infra, 'tracks')
    line = node(node(infra, 'trackGroups'), 'line', id='Line')
    for track_id, length, origin, finish, direction in (('Trunk', 1100, 400, 700, 'up'), ('Branch', 800, 500, 180, 'down')):
        node(line, 'trackRef', ref=track_id)
        track = node(tracks, 'track', id=track_id, name=track_id)
        topo = node(track, 'trackTopology')
        start = node(topo, 'trackBegin', pos=0, id=f'{track_id}Begin')
        if track_id == 'Branch':
            node(start, 'connection', id='Diverging', ref='Unknown' if fault == 'reciprocity' else 'Through')
        else:
            node(start, 'openEnd', id='OpenWest')
            switch = node(node(topo, 'connections'), 'switch', id='Switch', pos=300)
            node(switch, 'connection', id='Through', ref='Diverging',
                 orientation='incoming' if fault == 'orientation' else 'outgoing')
            if passing_loop:
                rejoin = node(topo.find(tag('connections')), 'switch', id='Merge', pos=250 if fault == 'backwards' else 850)
                node(rejoin, 'connection', id='Join', ref='Returning',
                     orientation='outgoing' if fault == 'incoming_orientation' else 'incoming')
        endpoint = node(topo, 'trackEnd', pos=length, id=f'{track_id}End')
        if passing_loop and track_id == 'Branch':
            node(endpoint, 'connection', id='Returning', ref='Unknown' if fault == 'incoming_reciprocity' else 'Join')
        else:
            node(endpoint, 'openEnd', id=f'{track_id}Open')
        node(node(topo, 'crossSections'), 'crossSection', id=f'{track_id}Station', pos=finish, ocpRef='Station')
        eng = node(track, 'trackElements')
        speeds = node(eng, 'speedChanges')
        node(speeds, 'speedChange', id=f'{track_id}Up', dir='up', pos=0,
             vMax=80 if track_id == 'Trunk' else 45, etcsTrainCategory=0)
        node(speeds, 'speedChange', id=f'{track_id}Down', dir='down', pos=length,
             vMax=65 if track_id == 'Trunk' else 30, etcsTrainCategory=0)
        node(node(eng, 'gradientChanges'), 'gradientChange', id=f'{track_id}Grade', pos=0,
             slope=0 if track_id == 'Trunk' else '-3.25')
        node(node(eng, 'radiusChanges'), 'radiusChange', id=f'{track_id}Radius', pos=0,
             radius=0 if track_id == 'Trunk' else -1050)
        node(node(eng, 'platformEdges'), 'platformEdge', id=f'{track_id}Platform', pos=origin, dir=direction,
             length=abs(finish - origin), ocpRef='Station')
        ocs = node(track, 'ocsElements')
        signals = node(ocs, 'signals')
        node(signals, 'signal', id=f'{track_id}Exit', pos=finish, dir=direction, type='main', function='exit', sight=300)
        if fault == 'signal' and track_id == 'Trunk':
            node(signals, 'signal', id='AmbiguousSwitchHome', pos=300, dir='up', type='main', function='home', sight=200)
        post = node(node(ocs, 'stopPosts'), 'stopPost', id=f'{track_id}Stop', pos=finish, dir=direction,
                    platformEdgeRef=f'{track_id}Platform', ocpRef='Station')
        node(post, 'signalRef', ref=f'{track_id}Exit')
    return ET.tostring(root)


def request(tmp_path, fault=None, *, passing_loop=False):
    source = tmp_path / 'OTProjects/Source'
    source.mkdir(parents=True)
    header, shapes = sources()

    def bind(name, data):
        path = source / name
        path.write_bytes(data)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}

    def span(track, start, end):
        return {'track_id': track, 'start_position_m': start, 'end_position_m': end}

    near_switch = 300 if fault == 'turnout_seam' else 200
    trunk_east = 500 if fault == 'platform_seam' else 900
    target = tmp_path / 'OTProjects/RebuiltStation'
    branch_limit = 800 if passing_loop and fault != 'incoming_sheet' else 650
    args = {
        'railml': bind('Source.railml', station_xml(fault, passing_loop=passing_loop)),
        'header_document': bind('SourceHeader.opentrack', header),
        'shapes': bind('Shapes.archive', shapes),
        'worksheets': [
            {'document': 'Approach', 'tracks': [span('Trunk', 0, near_switch)]},
            {'document': 'Station', 'tracks': [span('Branch', 0, branch_limit), span('Trunk', near_switch, trunk_east)]},
            {'document': 'MainEast', 'tracks': [span('Trunk', trunk_east + (fault == 'partition'), 1100)]},
        ],
        'stations': [
            {'track_id': track, 'cross_section_id': f'{track}Station', 'platform_edge_id': f'{track}Platform',
             'stop_post_id': f'{track}Stop', 'exit_signal_id': f'{track}Exit', 'direction': direction,
             'station_anchor': track == 'Branch'}
            for track, direction in (('Trunk', 'up'), ('Branch', 'down'))
        ],
        'train_types': ['Test'],
        'execution_root': target.as_posix(),
        'target_directory': target.relative_to(tmp_path).as_posix(),
    }
    if branch_limit < 800:
        args['worksheets'].append({'document': 'BranchEast', 'tracks': [span('Branch', branch_limit, 800)]})
    if fault == 'facility':
        args['stations'][1]['stop_post_id'] = None
    tool = Registry(Service(tmp_path, False, False), profile='all').tools['opentrack_rebuild_native_railml_station']
    return lambda values: tool.handler(tool.model.model_validate(values)), args, target


def test_publish_facing_turnout_shared_platforms_and_reciprocal_partition(tmp_path):
    rebuild, args, target = request(tmp_path)
    preview = rebuild(args)
    assert not target.exists() and not preview['saved']
    receipt = rebuild({**args, 'preview_only': False})
    assert receipt['saved'] and receipt['member_sha256'] == preview['member_sha256']
    assert not receipt['native_worksheet_geometry_copied'] and not receipt['native_operations_template_copied']
    paths = run_infrastructure_paths((target / 'station.run').read_bytes())
    graph = project_from({name: (target / 'OTDocuments' / f'{name}.opentrack').read_bytes() for name in paths}, paths,
                         (target / 'OTData/empty.dest').read_bytes())
    assert len(receipt['reciprocal_connector_pairs']) == 3
    for left, right in receipt['reciprocal_connector_pairs']:
        assert graph.block_end(tuple(left)) == tuple(right)
        assert graph.block_end(tuple(right)) == tuple(left)

    branch, = receipt['native_turnouts']
    end = graph.model(('Station', branch['turnout_end_id']))
    first, second = [end.contents[index].value for index in (9, 10)]
    assert writer.string(first.contents[19].value) == 'Trunk'
    assert writer.string(second.contents[19].value) == 'Branch'
    assert len({first.contents[0].value, second.contents[0].value}) == 2
    assert (end.contents[21].value, end.contents[22].value) == (0, 0)
    assert (first.contents[0].value, second.contents[0].value) == (branch['first_edge_id'], branch['second_edge_id'])
    assert second.contents[9].values[2:4] == [-1050, -3.25]
    speeds = course_factories.dictionary(second.contents[16].value)
    assert [(key, speed.contents[1].value, speed.contents[2].value) for key, speed in speeds.items()] == [('0', 45, 30)]
    left_seam = receipt['track_edge_bindings']['Trunk'][0]
    right_seam = receipt['track_edge_bindings']['Trunk'][1]
    assert (left_seam['start_position_m'], left_seam['end_position_m'], left_seam['document']) == (0, 200, 'Approach')
    assert (right_seam['start_position_m'], right_seam['end_position_m'], right_seam['document']) == (200, 300, 'Station')

    validation = receipt['validation']
    station, = validation['station_model_bindings']
    assert station['document'] == 'Station' and station['station_sign'] == 'STA'
    assert len(station['reference_end_ids']) == 4
    facility = receipt['facilities_by_document']['Station']
    stops = facility['source_station_cross_sections']
    assert {(row['direction'], row['length_m']) for row in stops.values()} == {('up', 300), ('down', 320)}
    assert len({row['reference_end_id'] for row in stops.values()}) == 2
    assert facility['native_station_groups']['STA']['anchor_reference_end_id'] == stops['BranchStation']['reference_end_id']
    assert all(validation[f'{role}_count'] == 0 for role in ('course', 'timetable', 'incident', 'destination', 'train', 'engine'))
    assert all(sha((target / filename).read_bytes()) == digest for filename, digest in receipt['member_sha256'].items())


def test_rebuilds_paired_turnout_loop_and_exact_directional_platforms(tmp_path):
    rebuild, args, target = request(tmp_path, passing_loop=True)
    preview = rebuild(args)
    receipt = rebuild({**args, 'preview_only': False})
    assert preview['member_sha256'] == receipt['member_sha256']
    paths = run_infrastructure_paths((target / 'station.run').read_bytes())
    graph = project_from({name: (target / 'OTDocuments' / f'{name}.opentrack').read_bytes() for name in paths}, paths,
                         (target / 'OTData/empty.dest').read_bytes())
    assert len(receipt['reciprocal_connector_pairs']) == 2
    assert all(graph.block_end(tuple(left)) == tuple(right) and graph.block_end(tuple(right)) == tuple(left)
               for left, right in receipt['reciprocal_connector_pairs'])

    facing, trailing = receipt['native_turnouts']
    assert [(row['orientation'], row['position_m'], row['branch_position_m']) for row in (facing, trailing)] == [
        ('outgoing', 300, 0), ('incoming', 850, 800),
    ]
    for row, edge_half in ((facing, 7), (trailing, 8)):
        key = row['document'], row['turnout_end_id']
        assert row['document'] == 'Station'
        owner = graph.model(key)
        first, second = [owner.contents[index].value for index in (9, 10)]
        assert [edge.contents[0].value for edge in (first, second)] == [row['first_edge_id'], row['second_edge_id']]
        assert [writer.string(edge.contents[19].value) for edge in (first, second)] == ['Trunk', 'Branch']
        assert first.contents[edge_half].value is second.contents[edge_half].value is owner
        assert (owner.contents[21].value, owner.contents[22].value) == (0, 0)
        assert graph.model(graph.related(key)).contents[10].value is None
    main = receipt['track_edge_bindings']['Trunk']
    loop = receipt['track_edge_bindings']['Branch']
    assert sum(segment['length_m'] for segment in main) == 1100
    assert sum(segment['length_m'] for segment in loop) == 800
    assert loop[-1]['directional_speeds_kmh'] == {'0': {'up': 45, 'down': 30}}
    refs = receipt['facilities_by_document']['Station']['source_station_cross_sections']
    assert {(row['direction'], row['length_m']) for row in refs.values()} == {('up', 300), ('down', 320)}
    assert len(receipt['validation']['station_model_bindings']) == 1
    assert receipt['validation']['destination_count'] == receipt['validation']['course_count'] == 0


def two_loop_request(tmp_path, fault=None):
    rebuild, args, target = request(tmp_path, passing_loop=True)
    file = tmp_path / args['railml']['path']
    root = ET.fromstring(file.read_bytes())
    infra = root.find(tag('infrastructure'))
    tracks = infra.find(tag('tracks'))
    trunk, branch = tracks
    loop_two = deepcopy(branch)
    tracks.append(loop_two)
    old_ids = {'Diverging': 'DivergingTwo', 'Returning': 'ReturningTwo', 'Through': 'ThroughTwo', 'Join': 'JoinTwo'}
    for item in loop_two.iter():
        for key, value in item.attrib.copy().items():
            if key in ('id', 'name', 'ref', 'platformEdgeRef'):
                item.set(key, old_ids.get(value, value.replace('Branch', 'BranchTwo')))
            if key == 'ocpRef':
                item.set(key, 'SecondIsland')
    node(infra.find(tag('operationControlPoints')), 'ocp', id='SecondIsland', code='IS2', name='Second station')
    node(infra.find(tag('trackGroups', 'line')), 'trackRef', ref='BranchTwo')
    trunk.find(tag('trackTopology', 'trackEnd')).set('pos', '2200')
    trunk.find(tag('trackElements', 'speedChanges', 'speedChange') + "[@dir='down']").set('pos', '2200')
    connections = trunk.find(tag('trackTopology', 'connections'))
    node(node(connections, 'switch', id='SecondDeparture', pos=1300), 'connection', id='ThroughTwo',
         ref='DivergingTwo', orientation='outgoing')
    if fault == 'different_main':
        connections = node(branch.find(tag('trackTopology')), 'connections')
        rejoin_position = 700
    else:
        rejoin_position = 850 if fault == 'occupied_switch_position' else 1850
    node(node(connections, 'switch', id='SecondArrival', pos=rejoin_position), 'connection',
         id='JoinTwo', ref='ReturningTwo', orientation='incoming')
    node(trunk.find(tag('trackTopology', 'crossSections')), 'crossSection',
         id='TrunkStationTwo', pos=1700, ocpRef='SecondIsland')
    node(trunk.find(tag('trackElements', 'platformEdges')), 'platformEdge', id='TrunkPlatformTwo',
         pos=1400, dir='up', length=300, ocpRef='SecondIsland', side='left')
    node(trunk.find(tag('ocsElements', 'signals')), 'signal', id='TrunkExitTwo', pos=1700, dir='up',
         type='main', function='exit', sight=300)
    stop = node(trunk.find(tag('ocsElements', 'stopPosts')), 'stopPost', id='TrunkStopTwo',
                pos=1700, dir='up', platformEdgeRef='TrunkPlatformTwo', ocpRef='SecondIsland')
    node(stop, 'signalRef', ref='TrunkExitTwo')
    # The second island has two opposed railML faces along the same travel direction.
    loop_two.find(tag('trackTopology', 'crossSections', 'crossSection')).set('pos', '500')
    area = loop_two.find(tag('trackElements', 'platformEdges', 'platformEdge'))
    area.attrib.update(pos='180', dir='up', side='right')
    for element in (loop_two.find(tag('ocsElements', 'signals', 'signal')),
                    loop_two.find(tag('ocsElements', 'stopPosts', 'stopPost'))):
        element.attrib.update(pos='500', dir='up')
    data = ET.tostring(root)
    file.write_bytes(data)
    args['railml']['sha256'] = sha(data)
    args['worksheets'] = [
        args['worksheets'][0],
        args['worksheets'][1],
        {'document': 'SecondStation', 'tracks': [
            {'track_id': 'Trunk', 'start_position_m': 900, 'end_position_m': 2000},
            {'track_id': 'BranchTwo', 'start_position_m': 0, 'end_position_m': 800},
        ]},
        {'document': 'MainEast', 'tracks': [{'track_id': 'Trunk', 'start_position_m': 2000, 'end_position_m': 2200}]},
    ]
    args['stations'].extend([
        {**args['stations'][0], 'cross_section_id': 'TrunkStationTwo', 'platform_edge_id': 'TrunkPlatformTwo',
         'exit_signal_id': 'TrunkExitTwo', 'stop_post_id': 'TrunkStopTwo'},
        {**args['stations'][1], 'track_id': 'BranchTwo', 'direction': 'up',
         'cross_section_id': 'BranchTwoStation', 'platform_edge_id': 'BranchTwoPlatform',
         'exit_signal_id': 'BranchTwoExit', 'stop_post_id': 'BranchTwoStop'},
    ])
    return rebuild, args, target


@pytest.mark.parametrize('shared_worksheet', [False, True])
def test_rebuilds_two_independent_passing_loops_and_island_faces(tmp_path, shared_worksheet):
    rebuild, args, target = two_loop_request(tmp_path)
    second_document = 'SecondStation'
    if shared_worksheet:
        second_document = 'Station'
        local = args['worksheets'][1]['tracks']
        local[-1]['end_position_m'] = 2000
        local.append(args['worksheets'].pop(2)['tracks'][1])
    preview = rebuild(args)
    saved = rebuild({**args, 'preview_only': False})
    assert saved['saved'] and saved['member_sha256'] == preview['member_sha256']
    assert [(row['main_departure_position_m'], row['main_rejoin_position_m'], row['branch_track_id'])
            for row in saved['passing_loops']] == [(300, 850, 'Branch'), (1300, 1850, 'BranchTwo')]
    assert len(saved['reciprocal_connector_pairs']) == (2 if shared_worksheet else 3)
    paths = run_infrastructure_paths((target / 'station.run').read_bytes())
    graph = project_from({name: (target / 'OTDocuments' / f'{name}.opentrack').read_bytes() for name in paths}, paths,
                         (target / 'OTData/empty.dest').read_bytes())
    for row in saved['native_turnouts']:
        end = graph.model((row['document'], row['turnout_end_id']))
        assert [obj.contents[0].value for obj in (end.contents[9].value, end.contents[10].value)] == [
            row['first_edge_id'], row['second_edge_id'],
        ]
        assert (end.contents[21].value, end.contents[22].value) == (0, 0)
    assert [entry['station_sign'] for entry in saved['validation']['station_model_bindings']] == ['STA', 'IS2']
    facility = saved['facilities_by_document'][second_document]
    faces = [row for row in facility['source_station_cross_sections'].values() if row['sign'] == 'IS2']
    assert {(row['track_id'], row['railml_side'], row['direction']) for row in faces} == {
        ('Trunk', 'left', 'up'), ('BranchTwo', 'right', 'up'),
    }
    assert len(facility['native_station_groups']['IS2']['references']) == 2
    assert all(sha((target / filename).read_bytes()) == digest for filename, digest in saved['member_sha256'].items())


@pytest.mark.parametrize(('fault', 'expected'), [
    ('different_main', 'rejoin the same RailML main track'),
    ('occupied_switch_position', 'unique interior RailML position'),
])
def test_multiple_loops_refuse_ambiguous_shared_turnouts(tmp_path, fault, expected):
    rebuild, args, target = two_loop_request(tmp_path, fault)
    with pytest.raises(APIError, match=expected):
        rebuild({**args, 'preview_only': False})
    assert not target.exists()


@pytest.mark.parametrize(('fault', 'expected'), [
    ('incoming_orientation', 'incoming connection with trackEnd'),
    ('incoming_reciprocity', 'must be reciprocal'),
    ('incoming_sheet', 'containing its reciprocal branch endpoint'),
    ('backwards', 'rejoin the same RailML main track at increasing positions'),
])
def test_passing_loop_rejects_ambiguous_or_misoriented_rejoin(tmp_path, fault, expected):
    rebuild, args, target = request(tmp_path, fault, passing_loop=True)
    with pytest.raises(APIError, match=expected):
        rebuild({**args, 'preview_only': False})
    assert not target.exists()


@pytest.mark.parametrize(('fault', 'expected'), [
    ('reciprocity', 'must be reciprocal'),
    ('orientation', 'outgoing RailML connection'),
    ('turnout_seam', 'inside one worksheet'),
    ('partition', 'no gaps or overlap'),
    ('signal', 'away from turnout and connector seams'),
    ('platform_seam', 'single worksheet away from'),
    ('facility', 'exact source facility and OCP inventory'),
])
def test_station_rejects_unrepresented_native_topology_or_facility_before_publication(tmp_path, fault, expected):
    rebuild, args, target = request(tmp_path, fault)
    with pytest.raises(APIError, match=expected):
        rebuild({**args, 'preview_only': False})
    assert not target.exists()
