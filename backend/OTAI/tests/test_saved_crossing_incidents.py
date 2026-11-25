"""Focused native .courses target migration and graph-preservation coverage."""

import pytest

from opentrack_ai.current_archive import catalogs, incident_operations, route_factory, writer
from opentrack_ai.current_archive.incident_set_workflow.core import make_set
from opentrack_ai.current_archive.infrastructure_incidents.core import create
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.saved_crossing_incidents import rebind_track_incidents, track_incident_bindings
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document


@pytest.fixture
def tracks():
    line = generate.spec()
    vertices = 'ABCDEF'
    line['vertices'] = [generate.vertex(name, index * 100) for index, name in enumerate(vertices)]
    track = line['edges'][0]
    line['edges'] = [{**track, 'key': first + second, 'from': [first, 1], 'to': [second, 0]}
                     for first, second in zip(vertices, vertices[1:])]
    worksheet, _ = schematic_document(line, [])
    root, version = writer.load_next_compatible(worksheet)
    _, models = route_factory.document(root)
    ids = [index for index, obj in models.items() if writer.kind(obj) == 'OTEdgeModel']
    replacement = max(models) + 1
    models[ids[0]].contents[0].value = replacement
    return {'Line': worksheet}, {'Line': writer.dump_verified(root, version)}, ids, replacement


def course_root():
    return native.obj([('OTCourseList', 3), ('OTMutableArray', 0), ('NSObject', 0)],
                      [('i', [17]), ('@', [native.arr()]), ('@', [native.arr()]),
                       ('@', [native.arr()]), ('@', [native.arr()])])


def incident(root, name, kind, ids):
    targets = {'model_id': ids[0]} if kind == 'edge_blockage' else {'model_ids': ids}
    return create({'name': name, 'type': kind, 'document': 'Line', 'begin_time': '08:00:00',
                   'end_time': '08:03:00', 'begin_day': 0, 'end_day': 0, 'enabled': False,
                   'probability_percentage': 54, 'comment': 'Keep original metadata', **targets},
                  root.contents[1].value)


def save(root, records):
    writer.set_elements(root.contents[1].value, records)
    return writer.dump_verified(root)


def review(name, expected, mapping):
    return {'name': name, 'document': 'Line', 'expected_edge_ids': expected,
            'edge_rebindings': [{'old_edge_id': old, 'new_edge_ids': new} for old, new in mapping]}


def test_migrates_scalar_and_expands_group_in_place_preserving_set_aliases(tracks):
    original, updated, (a, b, c, d, e), replacement = tracks
    root = course_root()
    group = incident(root, 'Group', 'edge_group_blockage', [b, a, c])
    single = incident(root, 'Single', 'edge_blockage', [a])
    unrelated = incident(root, 'Unchanged', 'edge_group_blockage', [b, e])
    # An unused scalar from an old type change and an unrelated shared member must survive.
    single.contents[5].values[0] = 55
    group.contents[5].values[1] = 71
    old_numbers = catalogs.array(group.contents[20].value)
    writer.set_elements(unrelated.contents[20].value, [old_numbers[0], catalogs.array(unrelated.contents[20].value)[1]])
    chosen_set = make_set(root, 'Evening group', [single, group])
    chosen_set.contents[3].value = incident_operations.string('Original set note')
    writer.set_elements(root.contents[2].value, [chosen_set])
    source = save(root, [group, unrelated, single])
    reviews = [review('Single', [a], [(a, [replacement])]), review('Group', [b, a, c], [(a, [replacement, d])])]
    output, receipts = rebind_track_incidents(source, original, updated, reviews)
    assert [(item['name'], item['edge_ids'], item['incident_index']) for item in track_incident_bindings(output)] == [
        ('Group', [b, replacement, d, c], 0), ('Unchanged', [b, e], 1), ('Single', [replacement], 2)
    ]
    assert [(item['before_edge_ids'], item['after_edge_ids']) for item in receipts] == [
        ([a], [replacement]), ([b, a, c], [b, replacement, d, c])
    ]
    fresh, _ = writer.load_next_compatible(output)
    saved_group, saved_other, saved_single = catalogs.array(fresh.contents[1].value)
    native_set, = catalogs.array(fresh.contents[2].value)
    set_single, set_group = catalogs.array(native_set.contents[0].value)
    assert set_single is saved_single and set_group is saved_group
    assert catalogs.text(native_set.contents[3].value) == 'Original set note'
    assert saved_single.contents[5].values == [55, replacement, 3]
    assert saved_group.contents[5].values == [-1, 71, 9]
    assert catalogs.text(saved_single.contents[16].value) == 'Keep original metadata'
    assert saved_single.contents[7].value == 0 and saved_single.contents[19].value == 54
    assert catalogs.array(saved_group.contents[20].value)[0] is catalogs.array(saved_other.contents[20].value)[0]
    assert writer.fingerprint(saved_other) == writer.fingerprint(unrelated)
    assert rebind_track_incidents(source, original, updated, []) == (source, [])


def test_group_allows_simultaneous_overlap_only_when_final_members_are_distinct(tracks):
    original, updated, (a, b, c, d, e), _ = tracks
    root = course_root()
    source = save(root, [incident(root, 'Group', 'edge_group_blockage', [a, b, c])])
    changed, _ = rebind_track_incidents(source, original, original, [review('Group', [a, b, c], [(a, [b]), (b, [d])])])
    assert track_incident_bindings(changed)[0]['edge_ids'] == [b, d, c]
    for mapping in ([(a, [b])], [(a, [e]), (c, [e])]):
        with pytest.raises(ValueError, match='duplicate final'):
            rebind_track_incidents(source, original, original, [review('Group', [a, b, c], mapping)])
    with pytest.raises(ValueError, match='Updated target'):
        rebind_track_incidents(source, original, updated, [review('Group', [a, b, c], [(b, [d])])])


def test_shared_group_requires_all_owners_to_request_one_identical_change(tracks):
    original, _, (a, b, c, d, e), _ = tracks
    root = course_root()
    first = incident(root, 'First', 'edge_group_blockage', [a, b])
    second = incident(root, 'Second', 'edge_group_blockage', [a, b])
    second.contents[20].value = first.contents[20].value
    source = save(root, [first, second])
    one = review('First', [a, b], [(a, [c])])
    with pytest.raises(ValueError, match='Every owner'):
        rebind_track_incidents(source, original, original, [one])
    with pytest.raises(ValueError, match='same rebind'):
        rebind_track_incidents(source, original, original, [one, review('Second', [a, b], [(a, [d])])])
    result, _ = rebind_track_incidents(source, original, original, [one, {**one, 'name': 'Second'}])
    saved, _ = writer.load_next_compatible(result)
    x, y = catalogs.array(saved.contents[1].value)
    assert x.contents[20].value is y.contents[20].value


def test_refuses_stale_cross_document_or_missing_target_and_single_member_expansion(tracks):
    original, updated, (a, b, c, d, e), replacement = tracks
    root = course_root()
    source = save(root, [incident(root, 'Single', 'edge_blockage', [a])])
    valid = review('Single', [a], [(a, [replacement])])
    with pytest.raises(ValueError, match='same|exact native Incident worksheet'):
        rebind_track_incidents(source, original, updated, [{**valid, 'document': 'Other'}])
    with pytest.raises(ValueError, match='complete saved order'):
        rebind_track_incidents(source, original, updated, [{**valid, 'expected_edge_ids': [b]}])
    with pytest.raises(ValueError, match='existing native track'):
        rebind_track_incidents(source, original, original, [valid])
    with pytest.raises(ValueError, match='exactly one replacement'):
        rebind_track_incidents(source, original, updated, [review('Single', [a], [(a, [replacement, b])])])
    with pytest.raises(ValueError, match='nonempty ordered list'):
        rebind_track_incidents(source, original, updated, [review('Single', [a], [(a, [True])])])
    assert track_incident_bindings(source)[0]['edge_ids'] == [a]
