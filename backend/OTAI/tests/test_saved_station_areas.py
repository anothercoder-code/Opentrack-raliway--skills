import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.saved_geometry import inspect_vertex, model_id, project_from, transform
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import fixture
from test_saved_geometry import shapes_for


STATION_ID = 10000


@pytest.fixture
def binding():
    docs, catalog, paths, _ = fixture('Line.opentrack')
    project = project_from(docs, paths, catalog)
    first, last = project.route_view(project.routes[0])
    first_pair = first, project.related(first)
    last_pair = last, project.related(last)
    station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [STATION_ID]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string('RDG')]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])
    for key in first_pair + last_pair:
        end = project.model(key)
        end.contents[12].value = station
        end.contents[20].value = 2 if key in last_pair else 1
    root = project.roots['Line']
    models = root.contents[2].value
    writer.set_elements(models, [*writer.elements(models), station])
    docs['Line'] = writer.dump_verified(root, project.versions['Line'])
    edge_id = model_id(project.model(project.edge_between(first, last)))
    return docs, catalog, paths, first_pair, last_pair, edge_id


def test_platform_split_preserves_station_and_active_operational_references(binding):
    docs, catalog, paths, first_pair, last_pair, edge_id = binding
    shape = shapes_for(docs['Line'])
    operation = {'action': 'split_platform_edge', 'edge_id': edge_id, 'station_id': STATION_ID,
                 'first_length_m': 280}
    output, report = transform(docs, paths, catalog, 'Line', operation, shapes=shape)
    checked = project_from(output, paths, catalog)
    station = checked.model(('Line', STATION_ID))
    total = checked.model(('Line', edge_id)).contents[9].values[1]
    total += checked.model(('Line', report['new_edge_id'])).contents[9].values[1]
    assert report['lengths_m'] == [280, total - 280]
    assert report['station_sign'] == 'RDG' and report['station_member_end_ids_added'] == report['new_end_ids']
    assert report['movement_count_checked'] > 2 and report['destination_catalog_unchanged']
    assert all(checked.model(key).contents[20].value == 2 for key in last_pair)
    for end_id in report['new_end_ids']:
        member = checked.model(('Line', end_id))
        assert member.contents[12].value is station
        assert member.contents[20].value == 1 and member.contents[11].value is None
    first, last = first_pair[0], last_pair[0]
    assert checked.route_view(checked.routes[0]) == [first, ('Line', report['new_end_ids'][0]), last]
    with pytest.raises(ValueError, match='Use split_platform_edge'):
        transform(docs, paths, catalog, 'Line', {**operation, 'action': 'split_edge'}, shapes=shape)


def test_group_and_ungroup_ordinary_members_preserving_station_reference_and_used_area(binding):
    docs, catalog, paths, first_pair, last_pair, _ = binding
    source = project_from(docs, paths, catalog)
    unused = next(model_id(end) for end in source.models['Line']
                  if writer.kind(end) == 'OTEndModel' and end.contents[2].value == 300)

    def edit(documents, add=(), remove=()):
        return transform(documents, paths, catalog, 'Line', {
            'action': 'edit_station_area', 'station_id': STATION_ID,
            'add_end_ids': add, 'remove_end_ids': remove,
        })

    output, report = edit(docs, add=[unused])
    assert len(report['station_member_end_ids_added']) == 2
    reset, restored = edit(output, remove=[unused])
    checked = project_from(reset, paths, catalog)
    assert restored['station_member_end_ids_removed'] == report['station_member_end_ids_added']
    assert checked.model(('Line', unused)).contents[12].value is None
    assert all(checked.model(key).contents[20].value == 2 for key in last_pair)
    with pytest.raises(ValueError, match='active movement'):
        edit(output, remove=[first_pair[0][1]])
    with pytest.raises(ValueError, match='station reference'):
        edit(output, remove=[last_pair[0][1]])


def test_convert_ordinary_vertex_and_group_approach_on_first_station_reference(binding):
    docs, catalog, paths, first_pair, last_pair, edge_id = binding
    ordinary = project_from(docs, paths, catalog)
    for key in (*first_pair, *last_pair):
        half = ordinary.model(key)
        half.contents[12].value = None
        half.contents[20].value = 1
    source = {'Line': writer.dump_verified(ordinary.roots['Line'], ordinary.versions['Line'])}
    before = inspect_vertex(source['Line'], last_pair[0][1])
    assert [end['station_end_type'] for end in before['ends']] == [1, 1]
    output, report = transform(source, paths, catalog, 'Line', {
        'action': 'convert_station_reference', 'station_id': STATION_ID,
        'end_id': last_pair[0][1], 'area_end_ids': [first_pair[0][1]],
    })
    after = inspect_vertex(output['Line'], last_pair[0][1])
    assert [end['station_end_type'] for end in after['ends']] == [2, 2]
    assert [end['station_model_id'] for end in after['ends']] == [STATION_ID, STATION_ID]
    assert report['station_area_end_ids'] == sorted(key[1] for key in first_pair)
    assert report['station_reference_end_ids'] == sorted(key[1] for key in last_pair)
    assert report['grouped_approach_edges'][0]['edge_id'] == edge_id
    assert report['movement_count_checked'] > 2 and report['nonselected_graph_verified']
    saved = project_from(output, paths, catalog)
    assert all(saved.model(key).contents[20].value == 1 for key in first_pair)
    assert writer.fingerprint(saved.roots['Line']) == writer.fingerprint(project_from(docs, paths, catalog).roots['Line'])


def test_station_reference_requires_ordinary_distinct_same_owner_pairs(binding):
    docs, catalog, paths, first_pair, last_pair, _ = binding
    core = {'action': 'convert_station_reference', 'station_id': STATION_ID}
    with pytest.raises(ValueError, match='ordinary type-1'):
        transform(docs, paths, catalog, 'Line', {**core, 'end_id': last_pair[0][1]})
    with pytest.raises(ValueError, match='distinct logical double vertex'):
        transform(docs, paths, catalog, 'Line', {
            **core, 'end_id': first_pair[0][1], 'area_end_ids': [first_pair[1][1]],
        })
    output, report = transform(docs, paths, catalog, 'Line', {**core, 'end_id': first_pair[0][1]})
    assert report['station_member_end_ids_added'] == []
    assert report['station_reference_end_ids'] == sorted(key[1] for key in first_pair)
    assert [end['station_end_type'] for end in inspect_vertex(output['Line'], first_pair[0][1])['ends']] == [2, 2]

    project = project_from(docs, paths, catalog)
    other = path_functions.clone(project.model(('Line', STATION_ID)))
    other.contents[0].value = STATION_ID + 1
    other.contents[7].value = native.string('ALT')
    for key in first_pair:
        project.model(key).contents[12].value = other
    root = project.roots['Line']
    writer.set_elements(root.contents[2].value, [*project.models['Line'], other])
    foreign = {'Line': writer.dump_verified(root, project.versions['Line'])}
    with pytest.raises(ValueError, match='another StationModel'):
        transform(foreign, paths, catalog, 'Line', {**core, 'end_id': first_pair[0][1]})
