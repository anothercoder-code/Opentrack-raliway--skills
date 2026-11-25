"""Verified native StationModel membership on ordinary paired worksheet Ends."""

from . import path_functions, route_factory, writer
from .multi_document.core import need
from .zero_operations.station_binding import MODEL


def station_model(project, document, station_id, *, require_reference=True):
    station = project.model((document, station_id))
    route_factory.layout(station, 'OTStationModel', 1, MODEL, graphic=True)
    sign = path_functions.string(station.contents[7].value)
    need(sign, 'Station must have a saved station sign')
    if require_reference:
        need(any(writer.kind(end) == 'OTEndModel' and end.contents[12].value is station
                 and end.contents[20].value == 2 for end in project.models[document]),
             'Station must have a saved reference vertex')
    return station


def end_pair(project, document, end):
    key = project.key(end)
    pair = project.model(project.related(key))
    need(key[0] == document and all(writer.kind(half) == 'OTEndModel' for half in (end, pair)),
         'Station areas require ordinary local double vertices')
    need(pair.contents[20].value == end.contents[20].value,
         'The two halves disagree on their station reference type')
    need(pair.contents[12].value is end.contents[12].value,
         'The two halves already have inconsistent station memberships')
    return end, pair


def edit_members(project, document, operation, active_ends):
    station = station_model(project, document, operation['station_id'])
    changes = {}
    for field, add in (('add_end_ids', True), ('remove_end_ids', False)):
        for end_id in operation[field]:
            pair = end_pair(project, document, project.model((document, end_id)))
            need(pair[0].contents[20].value == 1, 'A station reference or special End cannot be regrouped')
            need(pair[0].contents[12].value is (None if add else station),
                 'A member must be ungrouped for addition or already belong to this station for removal')
            for half in pair:
                key = project.key(half)
                need(key[1] not in changes, 'Select each logical double vertex only once')
                need(add or key not in active_ends, 'An active movement uses this station area member')
                changes[key[1]] = add
    need(changes, 'Provide at least one native station area membership change')
    for end_id, add in changes.items():
        project.model((document, end_id)).contents[12].value = station if add else None
    return {'station_id': operation['station_id'], 'station_sign': path_functions.string(station.contents[7].value),
            'station_member_end_ids_added': sorted(end_id for end_id, add in changes.items() if add),
            'station_member_end_ids_removed': sorted(end_id for end_id, add in changes.items() if not add)}


def platform_split_station(project, document, operation, first, last):
    station = station_model(project, document, operation['station_id'])
    for end in (first, last):
        end_pair(project, document, end)
        need(end.contents[12].value is station and end.contents[20].value in (1, 2),
             'Both platform Edge endpoints must belong to the selected station area')
    need(1 in (first.contents[20].value, last.contents[20].value),
         'A platform Edge between two station reference vertices requires a separate stop contract')
    return station


def verify_members(project, document, report):
    station = station_model(project, document, report['station_id'])
    for key, station_model_ref in (('station_member_end_ids_added', station), ('station_member_end_ids_removed', None)):
        for end_id in report.get(key, ()):
            end = project.model((document, end_id))
            end_pair(project, document, end)
            need(end.contents[12].value is station_model_ref and end.contents[20].value == 1,
                 'Station membership or ordinary End type failed native archive readback')


def reference_approaches(project, pair, station):
    approaches = []
    for end in pair:
        signal = end.contents[11].value
        for slot in (9, 10):
            edge = end.contents[slot].value
            if edge is None:
                continue
            a, b = (edge.contents[index].value for index in (7, 8))
            other = b if a is end else a
            if writer.kind(other) == 'OTEndModel' and other.contents[12].value is station and other.contents[20].value == 1:
                end_pair(project, project.key(end)[0], other)
                approaches.append({
                    'reference_end_id': project.key(end)[1], 'area_end_id': project.key(other)[1],
                    'edge_id': project.key(edge)[1], 'length_m': edge.contents[9].values[1],
                    'signal_id': project.key(signal)[1] if signal is not None else None,
                })
    return sorted(approaches, key=lambda row: (row['reference_end_id'], row['edge_id']))


def convert_reference(project, document, operation):
    station = station_model(project, document, operation['station_id'], require_reference=False)
    root = project.roots[document]
    picked = [operation['end_id'], *operation.get('area_end_ids', ())]
    changes = {}
    for position, end_id in enumerate(picked):
        pair = end_pair(project, document, project.model((document, end_id)))
        need(pair[0].contents[20].value == 1, 'Only an ordinary type-1 double vertex can be selected')
        owner = pair[0].contents[12].value
        need(owner is None or owner is station, 'Selected double vertex belongs to another StationModel')
        for half in pair:
            key = project.key(half)[1]
            need(key not in changes, 'Select one End ID per distinct logical double vertex')
            path_functions.guard_counter_references(root, half, allow_local_shunting=True)
            changes[key] = half, position == 0, owner is None
    for half, reference, _ in changes.values():
        half.contents[12].value = station
        if reference:
            half.contents[20].value = 2
    refs = sorted(key for key, (_, reference, _) in changes.items() if reference)
    return {
        'station_id': operation['station_id'], 'station_sign': path_functions.string(station.contents[7].value),
        'station_reference_end_ids': refs, 'station_reference_end_type': 2,
        'station_area_end_ids': sorted(key for key, (_, is_reference, _) in changes.items() if not is_reference),
        'station_member_end_ids_added': sorted(key for key, (_, _, added) in changes.items() if added),
        'grouped_approach_edges': reference_approaches(project, [changes[key][0] for key in refs], station),
    }


def verify_reference(project, document, report, original_fingerprint):
    station = station_model(project, document, report['station_id'])
    reference_ids = report['station_reference_end_ids']
    pair = end_pair(project, document, project.model((document, reference_ids[0])))
    need(sorted(project.key(end)[1] for end in pair) == reference_ids
         and all(end.contents[20].value == 2 and end.contents[12].value is station for end in pair),
         'Station reference pair failed native archive readback')
    need(reference_approaches(project, pair, station) == report['grouped_approach_edges'],
         'Grouped approach Edge readback differs')
    for end_id in report['station_area_end_ids']:
        end = project.model((document, end_id))
        end_pair(project, document, end)
        need(end.contents[20].value == 1 and end.contents[12].value is station,
             'Ordinary paired station area membership failed native archive readback')
    for end in pair:
        end.contents[20].value = 1
    for end_id in report['station_member_end_ids_added']:
        project.model((document, end_id)).contents[12].value = None
    need(writer.fingerprint(project.roots[document]) == original_fingerprint,
         'Station reference conversion changed unselected worksheet fields or references')
