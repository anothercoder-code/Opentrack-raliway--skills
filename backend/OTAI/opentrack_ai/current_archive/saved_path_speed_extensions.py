"""Exact whole-Path speed event dependencies for a reviewed worksheet insertion."""

from . import catalogs, incident_operations, writer
from .disturbance_tools import run_window
from .infrastructure_incidents import core as incidents
from .itinerary_edit_tools import _float32
from .multi_document.core import need, ref
from .prepare_contract.auxiliary import incident_bindings, records


def path_speed_extensions(project, courses, run_bytes, approvals, affected):
    need(type(run_bytes) is bytes, 'A run-selected Path-speed extension requires the exact bound .run file')
    window = run_window(run_bytes)
    names = [value for key, value, _ in records(run_bytes) if key == 'Incident']
    chosen = {row['name']: row for row in incident_bindings(courses, names)['selected']}
    requested = {row['event']: row for row in approvals}
    need(len(requested) == len(approvals), 'Approve each affected Path-speed Incident only once')

    affected_paths = {}
    for _, owner, identity in affected:
        document = owner[0]
        path = project.owned(owner, 'OTPath', identity)
        actual = {'document': document, **ref(path)}
        affected_paths[document.casefold(), identity[1], identity[2]] = actual
    keys_by_number = {(array_id, start_id) for _, array_id, start_id in affected_paths}
    known_documents = {name.casefold() for name in project.roots}
    root, _ = writer.load_next_compatible(courses)
    catalogs.course_items(root)
    need(root.contents[0].value == 17, 'Unsupported native CourseList marker')
    stored = catalogs.array(root.contents[1].value)
    registered = {id(obj) for obj in stored}
    approved = {}
    for event in writer.objects(root):
        if writer.kind(event) != 'OTIncident':
            continue
        fields = event.contents
        need(event.clazz.version in (9, 10, 11, 12) and len(fields) > 5
             and fields[2].encodings == [b'@'] and fields[5].encodings == [b'i'] * 3,
             'Cannot verify Path references in this native Incident layout')
        array_id, start_id, kind = fields[5].values
        if kind != 5 or (array_id, start_id) not in keys_by_number:
            continue
        document = catalogs.text(fields[2].value)
        need(document.casefold() in known_documents, 'An affected Path-speed Incident has an ambiguous document')
        target = affected_paths.get((document.casefold(), array_id, start_id))
        if target is None:
            continue
        name = catalogs.text(fields[0].value)
        approval = requested.get(name)
        need(approval is not None, 'An affected Path-speed Incident needs explicit whole-Path extension approval')
        need(id(event) in registered and name in chosen and chosen[name]['stored_type'] == 5
             and chosen[name]['stored_use_flag'] == 1 and document == target['document']
             and target == approval['path'] and name not in approved,
             'A Path-speed approval must bind one enabled run-selected event and its exact affected Path')
        catalogs.shape(event, 'OTIncident', 12, incident_operations.SCHEMA)
        item = incidents.item_from_object(event)
        speed = item['reduced_speed_kmh']
        need(speed > 0 and speed == _float32(approval['expected_speed_kmh'])
             and item['probability_percentage'] == 100
             and not any(key in item for key in ('periodic', 'begin_distribution', 'duration_distribution',
                                                  'head_only', 'discrete_moving_block')),
             'Path-speed extension requires a positive fixed-speed, fixed-window whole-train event')
        incidents.validate(item, project, window, root)
        need(writer.fingerprint(event) == writer.fingerprint(incidents.create(item, root.contents[1].value)),
             'Unrecognized native fields on the affected Path-speed Incident')
        approved[name] = {'event': name, 'path': target, 'type': 'path_speed', 'reduced_speed_kmh': speed,
                          'begin_time': item['begin_time'], 'end_time': item['end_time'],
                          'begin_day': item['begin_day'], 'end_day': item['end_day'],
                          'extends_over_inserted_track': True, 'stored_event_unchanged': True}
    need(approved.keys() == requested.keys(), 'A Path-speed approval does not match an affected native Path event')
    return [approved[name] for name in requested]
