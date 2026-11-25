"""Physical RailML platform mapping across reciprocal native worksheet boundaries."""

from xml.etree import ElementTree as ET

import pytest

from opentrack_ai.current_archive import catalogs, route_factory, writer
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyCrossDocumentPlatform, InfrastructureRailMLTools
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.multi_document.core import Project
from opentrack_ai.current_archive.network_operating_plan import route_trace
from opentrack_ai.current_archive.route_fetch_tools import SelectedRoute, fetch_routes
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.current_archive.zero_operations import station_binding
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document


def node(parent, element, **attrs):
    return ET.SubElement(parent, tag(element), {key: str(value) for key, value in attrs.items()})


def network(label, lengths, terminal, signal):
    spec = generate.spec()
    spec['vertices'] = [generate.vertex(key, 50 + i * 100) for i, key in enumerate(label)]
    default = spec['edges'][0]
    spec['edges'] = [{**default, 'key': first+second, 'from': [first, 1], 'to': [second, 0], 'length_m': n}
                     for first, second, n in zip(label, label[1:], lengths)]
    blob, labels = schematic_document(spec, signal)
    return blob, labels[terminal] if terminal is not None else labels


def fixture(tmp_path, direction='up', fault=None, *, middle=False):
    routed = fault == 'scheduled_block'
    left, caps_left = network('ABC', (50,240), 'C', [('B',1)] if direction == 'down' else ([('A', 0)] if routed else []))
    right, caps_right = network('DEF', (60,100), 'D', [('E',0)] if direction == 'up' else [])
    items = {'Left': (left, [(caps_left[1], 'Right', caps_right[0])]),
             'Right': (right, [(caps_right[0], 'Left', caps_left[1])])}
    if middle:
        signals = [('N', 0)] if fault in ('scheduled_block', 'unscheduled_block') else []
        middle_bytes, caps = network('MNO', (35, 45), None, signals)
        items = {'Left': (left, [(caps_left[1], 'Middle', caps['M'][0])]),
                 'Middle': (middle_bytes, [(caps['M'][0], 'Left', caps_left[1]),
                                           (caps['O'][1], 'Right', caps_right[0])]),
                 'Right': (right, [(caps_right[0], 'Middle', caps['O'][1])])}
    folder = tmp_path/'OTAI/workspaces/cross'
    folder.mkdir(parents=True)

    def put(name, data):
        path = folder/name
        path.write_bytes(data)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}

    references, trace, docs = [], [], {}
    for document, (blob, link_pairs) in items.items():
        root, version = writer.load_next_compatible(blob)
        models, byid = route_factory.document(root)
        for end_id, receiver, receiving_id in link_pairs:
            connector = byid[end_id]
            connector.clazz = writer.Class(b'OTConnModel', 1, connector.clazz)
            target = 'Unprovided' if fault == 'connector' and document == 'Left' else receiver
            if fault == 'second_connector' and document == 'Right':
                receiving_id = caps['M'][0]
            connector.contents += [writer.TypedValue(b'@',native.string('')), writer.TypedValue(b'@',native.string(target)),
                                   writer.TypedValue(b'i',receiving_id), writer.TypedValue(b'i',0)]
        if document == 'Middle' and fault in ('scheduled_block', 'unscheduled_block'):
            byid[caps['N'][0]].contents[11].value.contents[8].values[1] = 3
        if document == 'Left' and routed:
            origin = station_binding.obj([('OTStationModel',1),('OTGraphicModel',1),('NSObject',0)], [
                ('i',[max(byid) + 1]),('f',[0.0]),('f',[50.0]),('f',[30.0]),('i',[0]),('i',[0]),('@',[None]),
                ('@',[station_binding.string('EntryOrigin')]),('ii',[2,4]),('ii',[1,0]),
            ])
            for index in (0, 1):
                byid[index].contents[12].value = origin
                byid[index].contents[20].value = 2
            writer.set_elements(root.contents[2].value, [*models, origin])
        docs[document] = writer.dump_verified(root, version)
        trace.extend({'document':document,'edge_id':edge.contents[0].value,
                      'start_end_id':edge.contents[7].value.contents[0].value} for edge in models
                     if writer.kind(edge) == 'OTEdgeModel')
    if routed:
        paths = {key: key + '.opentrack' for key in docs}
        graph = Project(docs, document_paths=paths, expected_hashes={key: sha(blob) for key, blob in docs.items()},
                        complete_document_set=True)
        dest = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
        routes = []
        for name, chain, reserve in (
            ('Arrival', [('Left', 0), ('Left', 4), ('Left', 8), ('Middle', 4)], False),
            ('Continued block', [('Middle', 4), ('Middle', 8), ('Right', 4)], True),
        ):
            edges = [graph.edge_between(a, b) for a, b in zip(chain, chain[1:])]
            distance = sum(graph.model(edge).contents[9].values[1] for edge in edges)
            routes.append(SelectedRoute(name=name, candidate={'end_sequence': chain, 'edge_sequence': edges,
                                                              'distance_m': distance}, reserve_previous=reserve).model_dump())
        changed, receipt = fetch_routes(docs, paths, dest, routes)
        docs.update(changed)

        def options():
            return {'document_paths': paths, 'complete_document_set': True,
                    'expected_hashes': {**{key: sha(blob) for key, blob in docs.items()}, '$dest_catalog': sha(dest)}}

        refs = [{'document': row['owner'][0], **row['route']} for row in receipt['created_routes']]
        rewritten, path = operations.create_path(docs, dest, name='Platform path', routes=refs, **options())
        docs.update(rewritten)
        result, _ = operations.create_itinerary(docs, dest, name='Platform trip', paths=[path['created']], **options())
        docs = result['documents']
    references = [put(name+'.opentrack', blob) for name, blob in docs.items()]
    catalog = put('Project.stations', writer.dump_verified(station_binding.dictionary([])))
    rule = ET.Element(tag('railml'), {'version':'2.2'})
    infra=node(rule, 'infrastructure')
    track=node(node(infra,'tracks'),'track',id='T',name='1')
    topology=node(track,'trackTopology')
    node(topology,'trackBegin',id='Start',pos=0)
    extent = 80 if middle else 0
    node(topology,'trackEnd',id='Finish',pos=450 + extent)
    start, finish = (50,350 + extent) if direction == 'up' else (350 + extent,50)
    if fault == 'extent':
        start += 1
    node(node(topology,'crossSections'),'crossSection',id='Entry',pos=finish,ocpRef='O')
    node(node(node(track,'trackElements'),'platformEdges'),'platformEdge',id='P',pos=start,
         length=abs(finish-start),dir=direction,ocpRef='O')
    ocs=node(track,'ocsElements')
    node(node(ocs,'signals'),'signal',id='SI',type='main',function='exit',pos=finish, dir=direction,
         sight=321 if fault == 'signal' else 300,name='S0')
    if fault in ('extra_xml_block', 'scheduled_block', 'unscheduled_block'):
        node(ocs.find(tag('signals')), 'signal', id='Block', type='main', function='blocking', pos=325,
             dir=direction, sight=300, name='S0')
    post=node(node(ocs,'stopPosts'),'stopPost',id='SP',pos=finish,dir=direction,platformEdgeRef='P',ocpRef='O')
    node(post,'signalRef',ref='WRONG' if fault == 'post' else 'SI')
    node(node(infra,'operationControlPoints'),'ocp',id='O',code='P',name='Cross Platform')
    if fault=='order':
        trace[1],trace[2]=trace[2],trace[1]
    pick={'railml':put('Rail.railml',ET.tostring(rule)),'documents':references,'stations_catalog':catalog,
          'track':{'track_id':'T','edges':trace},
          'station':{'cross_section_id':'Entry','platform_edge_id':'P','exit_signal_id':'SI','stop_post_id':'SP','direction':direction},
          'target_directory':(folder/'Output').relative_to(tmp_path).as_posix()}
    return InfrastructureRailMLTools(tmp_path), pick, folder


@pytest.mark.parametrize('direction', ('up','down'))
def test_cross_worksheet_binding_is_local_but_catalog_and_stop_identity_are_single(tmp_path, direction):
    service, request, folder = fixture(tmp_path, direction)
    result = service.cross_document_platform(ApplyCrossDocumentPlatform(**request,preview_only=False))
    assert result['saved'] and result['native_graph_readback_verified'] and result['single_catalog_identity']
    area, final = (['Left','Right'], 'Right') if direction=='up' else (['Right','Left'],'Left')
    assert [span['document'] for span in result['area_edges']] == area
    assert [span['length_m'] for span in result['area_edges']] == ([240,60] if direction=='up' else [60,240])
    assert result['area_length_m'] == 300 and result['stopping_edge'][0] == result['reference_end'][0] == final
    assert {key[0] for key in result['reference_members']} == {final}
    local_names = []
    for document, ident in result['local_station_model_ids'].items():
        root,_=writer.load_next_compatible((folder/'Output'/f'{document}.opentrack').read_bytes())
        _, byid=route_factory.document(root)
        local_names.append(catalogs.text(byid[ident].contents[7].value))
        for key, end_id in result['ordinary_members'] + result['reference_members']:
            if document==key:
                assert byid[end_id].contents[12].value is byid[ident]
        for key, end_id in result['reciprocal_connectors']:
            if document==key:
                assert writer.kind(byid[end_id]) == 'OTConnModel'
                assert byid[end_id].contents[12].value is None
    assert local_names == ['P','P']
    out = folder/'Output/Project.stations'
    catalog,_=writer.load_next_compatible(out.read_bytes())
    assert list(catalogs.station_items(catalog)) == ['P']
    existing={**request, 'stations_catalog':{'path':out.relative_to(tmp_path).as_posix(),'sha256':sha(out.read_bytes())}}
    result = service.cross_document_platform(ApplyCrossDocumentPlatform(**existing))
    assert not result['station_catalog_row_added']


@pytest.mark.parametrize(('fault','error'), [
    ('connector','Missing connector document'),
    ('extent','complete contiguous native Edges'),
    ('signal','exact native directional main exit signal and sight'),
    ('post','Stop post differs'),
    ('order','continuous directed native Edge chain'),
])
def test_cross_worksheet_platform_requires_exact_geometry_and_saved_exit(tmp_path, fault, error):
    service, request, folder = fixture(tmp_path, fault=fault)
    with pytest.raises(APIError, match=error):
        service.cross_document_platform(ApplyCrossDocumentPlatform(**request,preview_only=False))
    assert not (folder/'Output').exists()


@pytest.mark.parametrize(('fault', 'error'), [
    ('second_connector', 'nonreciprocal'),
    ('extra_xml_block', 'RailML interior signals differ'),
    ('unscheduled_block', 'exact advanced-reservation Route'),
])
def test_three_worksheet_platform_rejects_unreviewed_connector_or_interior_signal(tmp_path, fault, error):
    service, request, folder = fixture(tmp_path, fault=fault, middle=True)
    with pytest.raises(APIError, match=error):
        service.cross_document_platform(ApplyCrossDocumentPlatform(**request, preview_only=False))
    assert not (folder / 'Output').exists()


def test_through_block_keeps_full_three_worksheet_planned_berth(tmp_path):
    service, request, folder = fixture(tmp_path, fault='scheduled_block', middle=True)
    report = service.cross_document_platform(ApplyCrossDocumentPlatform(**request, preview_only=False))
    assert report['interior_block_signals'] == [{'end': ['Middle', 4], 'position': 325,
                                                 'signal_name': 'S0', 'sight_m': 300, 'railml_signal_id': 'Block'}]
    files = {name: (folder / 'Output' / (name + '.opentrack')).read_bytes() for name in ('Left', 'Middle', 'Right')}
    graph = Project(files, document_paths={key: key + '.opentrack' for key in files},
                    expected_hashes={name: sha(blob) for name, blob in files.items()}, complete_document_set=True)
    itinerary, = graph.dests
    profile = route_trace(graph, itinerary)
    assert [row['station_sign'] for row in profile['visits']] == ['EntryOrigin', 'P']
    stop = profile['visits'][-1]
    assert stop['end_key'] == ('Right', 4) and stop['distance_m'] == 430
    assert stop['stopping_area_length_m'] == 380 and [edge[0] for edge in stop['stopping_area_edge_keys']] == [
        'Left', 'Middle', 'Middle', 'Right']
