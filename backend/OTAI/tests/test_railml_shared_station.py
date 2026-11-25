"""One native StationModel with distinct RailML platform tracks and exit Ends."""

from xml.etree import ElementTree as ET

import pytest

from opentrack_ai.current_archive import catalogs, route_factory, writer
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag, railml_tree
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyFacilities, ExportFacilities, InfrastructureRailMLTools
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document


def node(parent, kind, **attrs):
    return ET.SubElement(parent, tag(kind), {key: str(value) for key, value in attrs.items()})


def footprint(tmp_path, *, incompatible=None):
    spec = generate.spec()
    spec['vertices'] = []
    spec['edges'] = []
    paths = [('A', 'B', 'C', 'D', 'E'), ('U', 'V', 'W', 'X', 'Y')]
    for number, path in enumerate(paths, 1):
        spec['vertices'].extend({**generate.vertex(key, i * 100), 'y': number * 100} for i, key in enumerate(path))
        for from_key, to_key, length in zip(path, path[1:], (90, 180, 120, 250)):
            prototype = generate.spec()['edges'][0]
            spec['edges'].append({**prototype, 'key': from_key+to_key, 'from': [from_key, 1], 'to': [to_key, 0],
                                  'length_m': length, 'track_name': '1' if incompatible == 'label' else str(number)})
    document, vertices = schematic_document(spec, [])
    _, byid = route_factory.document(writer.load_next_compatible(document)[0])
    edge_map = {edge.contents[7].value.contents[0].value: key for key, edge in byid.items()
                if writer.kind(edge) == 'OTEdgeModel'}
    root = ET.Element(tag('railml'), {'version': '2.2'})
    infrastructure = node(root, 'infrastructure')
    tracks = node(infrastructure, 'tracks')
    ocps = node(infrastructure, 'operationControlPoints')
    node(ocps, 'ocp', id='CENTRAL', name='Central station', code='CT')
    if incompatible == 'ocp':
        node(ocps, 'ocp', id='OTHER', name='Central station', code='CT')
    specs = {'tracks': [], 'signals': [], 'stations': []}
    for i, path in enumerate(paths, 1):
        name = f'Track{i}'
        ref = 'OTHER' if incompatible == 'ocp' and i == 2 else 'CENTRAL'
        track = node(tracks, 'track', id=name, name='1' if incompatible == 'label' else str(i))
        topology = node(track, 'trackTopology')
        node(topology, 'trackBegin', id=f'L{i}', pos=0)
        node(topology, 'trackEnd', id=f'R{i}', pos=640)
        node(node(topology, 'crossSections'), 'crossSection', id=f'C{i}', pos=390, ocpRef=ref)
        platform = node(node(track, 'trackElements'), 'platformEdges')
        node(platform, 'platformEdge', id=f'P{i}', pos=90, length=300, dir='up', ocpRef=ref)
        ocs = node(track, 'ocsElements')
        node(node(ocs, 'signals'), 'signal', id=f'S{i}', pos=390, dir='up',
             type='main', function='exit', sight=410)
        post = node(node(ocs, 'stopPosts'), 'stopPost', id=f'SP{i}', pos=390, dir='up',
                    ocpRef=ref, platformEdgeRef=f'P{i}')
        node(post, 'signalRef', ref=f'S{i}')
        specs['tracks'].append({'track_id': name, 'edges': [{'edge_id': edge_map[vertices[key][1]],
                                                             'start_end_id': vertices[key][1]} for key in path[:-1]]})
        specs['signals'].append({'signal_id': f'S{i}'})
        specs['stations'].append({'cross_section_id': f'C{i}', 'platform_edge_id': f'P{i}',
                                  'exit_signal_id': f'S{i}', 'stop_post_id': f'SP{i}', 'direction': 'up',
                                  'station_anchor': i == 2 or incompatible == 'anchor'})
    output = tmp_path / 'OTAI/workspaces/station'
    output.mkdir(parents=True)

    def store(name, content):
        candidate = output / name
        candidate.write_bytes(content)
        return {'path': candidate.relative_to(tmp_path).as_posix(), 'sha256': sha(content)}

    specs.update(railml=store('Platforms.railml', ET.tostring(root)),
                 worksheet=store('Base.opentrack', document),
                 target_directory=(output/'Native').relative_to(tmp_path).as_posix())
    return InfrastructureRailMLTools(tmp_path), output, specs, store, vertices


def imported(tmp_path):
    service, candidates, specs, store, vertices = footprint(tmp_path)
    report = service.facilities(ApplyFacilities(**specs, preview_only=False))
    references = report['source_station_cross_sections']
    signals = report['source_signals']
    worksheet = (candidates / 'Native/Base.opentrack').read_bytes()
    catalog = (candidates / 'Native/FacilityCatalog.stations').read_bytes()
    export = {'worksheet': store('Shared.opentrack', worksheet), 'stations_catalog': store('Station.stations', catalog),
              'tracks': specs['tracks'],
              'signals': [{'signal_id': key, **{field: info[field] for field in ('track_id', 'direction', 'end_id')}}
                          for key, info in signals.items()],
              'stations': [{**pick, 'ocp_id': 'CENTRAL', 'station_sign': 'CT',
                            'track_id': references[pick['cross_section_id']]['track_id']} for pick in specs['stations']],
              'target_path': (candidates / 'Roundtrip.railml').relative_to(tmp_path).as_posix()}
    return service, report, vertices, worksheet, catalog, export


def test_shared_ocp_native_memberships_and_distinct_tracks_roundtrip(tmp_path):
    service, report, vertices, worksheet, catalog, export = imported(tmp_path)
    group = report['native_station_groups']['CT']
    assert group == {'ocp_id': 'CENTRAL', 'tracks': ['Track1', 'Track2'], 'references': [vertices['D'][0], vertices['X'][0]],
                     'anchor_reference_end_id': vertices['X'][0], 'platform_track_names': ['1', '2']}
    assert report['station_readback']['station_count'] == report['station_readback']['multi_platform_station_count'] == 1
    assert report['station_readback']['multi_edge_platform_count'] == 2
    root, _ = writer.load_next_compatible(worksheet)
    models, byid = route_factory.document(root)
    [station] = [model for model in models if writer.kind(model) == 'OTStationModel']
    assert list(catalogs.station_items(writer.load_next_compatible(catalog)[0])) == ['CT']
    assert station.contents[3].value == byid[group['anchor_reference_end_id']].contents[3].value
    for key in 'BCDVWX':
        for end_id in vertices[key]:
            end = byid[end_id]
            assert end.contents[12].value is station
            assert end.contents[20].value == (2 if key in 'DX' else 1)
    # Reverse the request order. The explicit chart anchor still picks Track 2.
    export['stations'].reverse()
    receipt = service.export_facilities(ExportFacilities(**export, preview_only=False))
    assert receipt['reimport']['byte_identical_worksheet']
    assert receipt['native_station_groups']['CT']['anchor_reference_end_id'] == vertices['X'][0]
    data = railml_tree((tmp_path / export['target_path']).read_bytes())
    assert [row.get('id') for row in data.iter(tag('ocp'))] == ['CENTRAL']
    assert {row.get('ocpRef') for row in data.iter(tag('platformEdge'))} == {'CENTRAL'}
    assert {row.get('ref') for row in data.iter(tag('signalRef'))} == {'S1', 'S2'}


@pytest.mark.parametrize(('fault', 'message'), [
    ('ocp', 'OCP IDs sharing native station sign'),
    ('anchor', 'more than one explicit anchor'),
    ('label', 'distinct saved native platform track names'),
])
def test_rejects_ambiguous_shared_station_identification(tmp_path, fault, message):
    service, root, request, *_ = footprint(tmp_path, incompatible=fault)
    with pytest.raises(APIError, match=message):
        service.facilities(ApplyFacilities(**request, preview_only=False))
    assert not (root / 'Native').exists()


def test_export_requires_members_for_all_native_platform_tracks(tmp_path):
    service, _, _, _, _, export = imported(tmp_path)
    export['stations'] = [{**export['stations'][0], 'station_anchor': True}]
    with pytest.raises(APIError, match='does not match the selected station anchor'):
        service.export_facilities(ExportFacilities(**export))
    export['stations'] = [{**export['stations'][0], 'track_id': 'Track2', 'exit_signal_id': 'S2'}]
    with pytest.raises(APIError, match='Unexpected station association/reference type'):
        service.export_facilities(ExportFacilities(**export))
