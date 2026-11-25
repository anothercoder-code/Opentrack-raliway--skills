"""Rebind current saved track-blockage targets in their original worksheet."""

from . import catalogs, route_factory, writer
from .graph_references import incoming_counts
from .incident_operations import SCHEMA
from .infrastructure_incidents.core import number_object, number_value
from .operating_plan_edit import need


def _edge_ids(values):
    need(type(values) is list and values
         and all(type(value) is int and 0 <= value <= 2147483647 for value in values)
         and len(set(values)) == len(values), 'Expected a nonempty ordered list of distinct native track IDs')
    return values


def _track_records(root):
    catalogs.course_items(root)
    need(root.contents[0].value == 17, 'Current CourseList marker 17 required for track-blockage binding')
    incidents = catalogs.array(root.contents[1].value)
    need({id(obj) for obj in writer.objects(root) if writer.kind(obj) == 'OTIncident'}
         == {id(obj) for obj in incidents}, 'A saved Incident is outside the native Incident list')
    records = {}
    names = set()
    for ordinal, incident in enumerate(incidents):
        catalogs.shape(incident, 'OTIncident', 12, SCHEMA)
        name = catalogs.text(incident.contents[0].value)
        need(name and name not in names, 'Expected unique saved Incident names')
        names.add(name)
        _, scalar_id, kind = incident.contents[5].values
        if kind in (3, 9):
            document = catalogs.text(incident.contents[2].value)
            ids = [scalar_id] if kind == 3 else [
                number_value(item) for item in catalogs.array(incident.contents[20].value)
            ]
            records[name] = incident, {'name': name, 'document': document, 'type': kind,
                                       'edge_ids': _edge_ids(ids), 'incident_index': ordinal}
    return records


def track_incident_bindings(courses: bytes) -> list[dict]:
    """Return the exact saved target IDs in native incident and member order."""
    root, _ = writer.load_next_compatible(courses)
    return [binding for _, binding in _track_records(root).values()]


def _edge_models(documents, document):
    need(document in documents and type(documents[document]) is bytes,
         'The selected native worksheet must exist under its exact document name')
    root, _ = writer.load_next_compatible(documents[document])
    _, models = route_factory.document(root)
    return models


def _check_targets(models, document, ids, stage):
    for edge_id in ids:
        model = models.get(edge_id)
        need(writer.kind(model) == 'OTEdgeModel', f'{stage} target {document}:{edge_id} must be an existing native track')
        first, second = (model.contents[slot].value for slot in (7, 8))
        need(first is not second and all(end is not None and models.get(end.contents[0].value) is end
                                        and model in [end.contents[slot].value for slot in (9, 10)]
                                        for end in (first, second)),
             f'{stage} target {document}:{edge_id} must be linked from both native endpoints')


def _replacement_ids(spec, expected, kind):
    need(type(spec) is list and spec, 'At least one explicit track rebind required')
    mapping = {}
    for change in spec:
        need(type(change) is dict and set(change) == {'old_edge_id', 'new_edge_ids'},
             'Expected old_edge_id and ordered new_edge_ids')
        old = change['old_edge_id']
        need(type(old) is int and old in expected and old not in mapping,
             'Each rebind must identify one distinct saved track member')
        new = _edge_ids(change['new_edge_ids'])
        need(new != [old], 'Track rebind would leave the selected member unchanged')
        if kind == 3:
            need(len(new) == 1, 'Native single-track blockage requires exactly one replacement track')
        mapping[old] = new
    revised = [new for old in expected for new in mapping.get(old, [old])]
    need(len(set(revised)) == len(revised), 'Rebound track group has duplicate final members')
    need(revised != expected, 'Rebound track list must change')
    return mapping, revised


def rebind_track_incidents(courses: bytes, original_documents: dict[str, bytes],
                           updated_documents: dict[str, bytes], reviews: list[dict]) -> tuple[bytes, list[dict]]:
    """Return a fresh native .courses archive and audited target deltas."""
    need(type(courses) is bytes and type(original_documents) is dict and type(updated_documents) is dict
         and type(reviews) is list, 'Expected immutable native archives and explicit track incident reviews')
    if not reviews:
        return courses, []
    root, version = writer.load_next_compatible(courses)
    records = _track_records(root)
    baseline = writer.fingerprint(root)
    model_cache = {}
    array_edits = {}
    new_numbers = {}
    scalar_edits = []
    receipts = []
    reviewed = set()
    for review in reviews:
        need(type(review) is dict and set(review) == {'name', 'document', 'expected_edge_ids', 'edge_rebindings'},
             'Expected exact Incident name, worksheet, saved IDs and explicit track rebindings')
        name, document = review['name'], review['document']
        need(type(name) is str and name in records and name not in reviewed,
             'Each review must name one distinct saved single- or multi-track blockage')
        incident, binding = records[name]
        need(type(document) is str and document == binding['document'],
             'Track rebind must keep the exact native Incident worksheet name')
        expected = _edge_ids(review['expected_edge_ids'])
        need(expected == binding['edge_ids'], 'Expected track IDs must match the complete saved order')
        kind = binding['type']
        mapping, revised = _replacement_ids(review['edge_rebindings'], expected, kind)
        for stage, documents, ids in (('Original', original_documents, expected), ('Updated', updated_documents, revised)):
            key = stage, document
            if key not in model_cache:
                model_cache[key] = _edge_models(documents, document)
            _check_targets(model_cache[key], document, ids, stage)
        if kind == 3:
            scalar_edits.append((incident.contents[5].values, expected[0], revised[0]))
        else:
            array = incident.contents[20].value
            slots = []
            for old, number in zip(expected, catalogs.array(array), strict=True):
                for new in mapping.get(old, [old]):
                    if new == old:
                        slots.append(number)
                    else:
                        key = id(number), new
                        if key not in new_numbers:
                            new_numbers[key] = number_object(new)
                        slots.append(new_numbers[key])
            existing = array_edits.get(id(array))
            if existing is None:
                array_edits[id(array)] = array, slots, 1
            else:
                need(existing[1] == slots, 'Shared track group owners must request the same rebind')
                array_edits[id(array)] = array, slots, existing[2] + 1
        receipts.append({**binding, 'before_edge_ids': expected, 'after_edge_ids': revised,
                         'edge_rebindings': [{'old_edge_id': old, 'new_edge_ids': new}
                                             for old, new in mapping.items()]})
        reviewed.add(name)

    counts = incoming_counts(root)
    need(all(counts[id(array)] == count for array, _, count in array_edits.values()),
         'Every owner of a shared native track group must be included in the rebind')
    snapshots = [(array, array.contents) for array, _, _ in array_edits.values()]
    for values, _, new in scalar_edits:
        values[1] = new
    for array, slots, _ in array_edits.values():
        writer.set_elements(array, slots)
    output = writer.dump_verified(root, version)
    fresh, _ = writer.load_next_compatible(output)
    actual = [binding for _, binding in _track_records(fresh).values()]
    changed = {receipt['name']: receipt['after_edge_ids'] for receipt in receipts}
    expected = [{**binding, 'edge_ids': changed.get(name, binding['edge_ids'])}
                for name, (_, binding) in records.items()]
    need(actual == expected, 'Native track-blockage readback differs from the reviewed rebind')
    for array, previous in snapshots:
        array.contents = previous
    for values, old, _ in scalar_edits:
        values[1] = old
    need(writer.fingerprint(root) == baseline, 'Native Incident graph changed outside the selected target fields')
    return output, receipts
