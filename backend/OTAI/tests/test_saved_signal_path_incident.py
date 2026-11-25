"""Keep one original whole-Route speed incident across a cross-sheet subdivision."""

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.incident_set_workflow.core import make_set
from opentrack_ai.current_archive.incident_source import validate_set_graph
from opentrack_ai.current_archive.infrastructure_incidents.core import create, item_from_object
from opentrack_ai.current_archive.multi_document.core import ref
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import MainSignalRouteSplit
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route

from test_itinerary_lifecycle import course_archive
from test_saved_main_signal_split import sending_corridor


@pytest.fixture
def route_speed_case(sending_corridor):
    docs, paths, dest, project, base = sending_corridor
    route = base['split_route']['route']
    selected, = project.paths_objects
    path = {'document': 'A', **ref(selected)}
    review = {'name': 'Whole route speed', 'path': path, 'expected_speed_kmh': 40}
    op = {**base, 'split_route': {**base['split_route'], 'route_speed_incident_to_path': review}}
    item = {'name': review['name'], 'type': 'route_speed', 'document': route['document'],
            'start_end_id': route['start_id'], 'array_id': route['array_id'], 'reduced_speed_kmh': 40,
            'begin_time': '10:00:00', 'end_time': '11:00:00', 'begin_day': 0, 'end_day': 0,
            'enabled': True, 'probability_percentage': 100, 'comment': 'Preserve event and set alias'}
    return docs, paths, dest, project, op, item


def source_events(*items):
    root, version = writer.load_next_compatible(course_archive(C01=['I:A-B']))
    array = root.contents[1].value
    rows = [create(item, array) for item in items]
    writer.set_elements(array, rows)
    writer.set_elements(root.contents[2].value, [make_set(root, 'Morning speed restrictions', rows)])
    return writer.dump_verified(root, version)


def test_retargets_whole_route_with_original_membership_and_path_geometry(route_speed_case):
    docs, paths, dest, original, op, item = route_speed_case
    MainSignalRouteSplit.model_validate(op['split_route'])
    old = source_events(item)
    changed, receipt = insert_signal_in_saved_route(docs, paths, dest, 'A', op, old)
    cold, version = writer.load_next_compatible(changed.pop('$course_catalog'))
    (event,), sets = validate_set_graph(cold)
    selected, = catalogs.array(sets['Morning speed restrictions'].contents[0].value)
    assert selected is event
    review = receipt['route_speed_incident_to_path']
    assert item_from_object(event) == {**item, 'type': 'path_speed', 'array_id': review['native_path']['array_id']}
    after = project_from({**docs, **changed}, paths, dest)
    before_path, = original.paths_objects
    after_path, = after.paths_objects
    assert original.path_view(before_path)[0] == after.path_view(after_path)[0]
    assert len(original.path_view(before_path)[1]) == 1 and len(after.path_view(after_path)[1]) == 2
    event.contents[5].values[:] = [item['array_id'], item['start_end_id'], 4]
    assert writer.dump_verified(cold, version) == old


def test_rejects_competing_path_or_route_event(route_speed_case):
    docs, paths, dest, _, op, item = route_speed_case
    path = op['split_route']['route_speed_incident_to_path']['path']
    path_event = {**item, 'name': 'Competing path', 'type': 'path_speed', 'array_id': path['array_id']}
    with pytest.raises(ValueError, match='Path-speed Incident'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', op, source_events(item, path_event))
    with pytest.raises(ValueError, match='Another saved Route-speed Incident'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', op, source_events(item, {**item, 'name': 'Other route'}))


def test_rejects_wrong_path_wrong_speed_and_omitted_review(route_speed_case):
    docs, paths, dest, _, op, item = route_speed_case
    saved = source_events(item)
    plan = op['split_route']
    review = plan['route_speed_incident_to_path']
    review['path']['name'] = 'wrong'
    with pytest.raises(ValueError, match='exact original OTPath'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', op, saved)
    review['path']['name'] = 'P:A-B'
    review['expected_speed_kmh'] = 41
    with pytest.raises(ValueError, match='exact enabled deterministic positive'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', op, saved)
    plan.pop('route_speed_incident_to_path')
    with pytest.raises(ValueError, match='Route-speed Incident references'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', op, saved)
