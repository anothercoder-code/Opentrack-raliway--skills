"""Move an original measuring instrument across one reviewed worksheet boundary."""

from . import native_monitoring, writer
from .graph_references import incoming_counts
from .multi_document.core import need
from .saved_crossing_instruments import _drawing, _read_instrument, _translated_drawing, _write_drawing
from .saved_geometry import _movement_manifest, project_from
from .saved_rich_labels import native_color
from .saved_temporary_labels import label_index
from .zero_generation.topology import flt


def _end_ref(reference):
    return reference['document'], reference['end_id']


def _alignment(project, references, old_key, new_key):
    chain = [_end_ref(row) for row in references]
    need(len(set(chain)) == len(chain) and old_key in chain and new_key in chain
         and chain.index(old_key) < chain.index(new_key),
         'Review a nonrepeating directed chain from the original to the replacement measuring End')
    need(all(writer.kind(project.model(key)) == 'OTEndModel' for key in chain),
         'Review the ordinary directional Ends of the chain, excluding connector halves')
    crossings = [(a, b) for a, b in zip(chain, chain[1:]) if a[0] != b[0]]
    need(len(crossings) == 1 and {key[0] for key in chain} == {old_key[0], new_key[0]},
         'The reviewed measuring alignment must use exactly one native worksheet boundary')
    departure, arrival = crossings[0]
    sending = project.related(departure)
    receiving = project.block_end(sending)
    need(receiving[0] == arrival[0] and project.block_end(receiving) == sending,
         'The reviewed measuring alignment lacks reciprocal connectors')
    edges = [project.edge_between(a, b) for a, b in zip(chain, chain[1:])]
    return edges, (sending, receiving)


def _label_bounds(label, base):
    center = tuple(label.contents[index].value for index in (2, 3))
    return center, tuple(label.contents[base + 1].values)


def _owned_label(instrument, local, expected_id, counts):
    label = instrument.contents[6].value
    if expected_id is None:
        need(label is None, 'Confirm the existing owned measuring Label ID before moving it')
        return None, None, None
    need(label is not None and label is local.get(expected_id) and writer.kind(label) == 'OTLabelModel',
         'The reviewed Label ID does not select the locally owned measuring Label')
    base = label_index(label)
    need(counts[id(label)] == 2 and (base == 6 or label.contents[6].value is None)
         and label.contents[base + 2].value is instrument,
         'The measuring Label must be reciprocally attached without another saved observer or child Label')
    _, label_type, flags = label.contents[base + 3].values
    need(label_type == 0 and flags in (0, 1), 'Temporary or simulation measuring Labels cannot be transferred')
    data = label.contents[base].value
    data_kind = writer.kind(data)
    need(data_kind in ('NSData', 'NSMutableData'), 'The saved measuring Label must contain native text data')
    size, payload = (group.value for group in data.contents) if len(data.contents) == 2 else (None, None)
    need(type(size) is int and size > 0 and [group.encodings for group in data.contents] == [[b'i'], [f'[{size}c]'.encode()]]
         and isinstance(payload, writer.Array) and isinstance(payload.elements, bytes) and len(payload.elements) == size,
         'Malformed archived measuring Label text data')
    colors = [native_color(label.contents[base + offset].value) for offset in (4, 5)]
    need(all(color is not None and 'rgb' in color for color in colors), 'Unsupported measuring Label colors')
    center, frame = _label_bounds(label, base)
    native_monitoring.floats([float(value) for value in (*center, *frame)])
    need(frame[2] > 0 and frame[3] > 0, 'An owned measuring Label needs a positive saved frame size')
    groups = [writer.TypedGroup(list(group.encodings), list(group.values)) for group in label.contents]
    for slot in (0, 2, 3):
        groups[slot].value = 0
    groups[base + 1].values[:2] = [0, 0]
    groups[base + 2].value = None
    settings = writer.fingerprint(writer.GenericArchivedObject(label.clazz, groups))
    return label, base, settings


def _move_label(label, base, old, new):
    center, frame = _label_bounds(label, base)
    delta = [new.contents[slot].value - old.contents[slot].value for slot in (2, 3)]
    center = tuple(flt(value, 'Measuring Label center') for value in native_monitoring.floats(
        [position + direction for position, direction in zip(center, delta, strict=True)]))
    origin = tuple(flt(value, 'Measuring Label frame origin') for value in native_monitoring.floats(
        [position + direction for position, direction in zip(frame[:2], delta, strict=True)]))
    return center, (*origin, *frame[2:])


def _read(project, key, instrument_id, label_id):
    document, end_id = key
    counts = incoming_counts(project.roots[document])
    graphics = project.roots[document].contents[2].value
    need(counts[id(graphics)] == 1, 'The native worksheet graphic collection has another saved observer')
    instrument = native_monitoring.model(project.byid[document], instrument_id, 'OTMeasuringModel')
    native_monitoring.instrument_shape(instrument)
    label, base, label_settings = _owned_label(instrument, project.byid[document], label_id, counts)
    instrument, array, edges, settings = _read_instrument(
        project, document, instrument_id, end_id, counts, relocating=True, ignore_local_id=True, owned_label=label)
    return instrument, array, edges, settings, label, base, label_settings


def _detach(project, key, moved):
    project.model(key).contents[13].value = None
    document = key[0]
    graphics = project.roots[document].contents[2].value
    writer.set_elements(graphics, [obj for obj in project.models[document] if obj not in moved])


def relocate_cross_document_measuring_instrument(documents, paths, dest, document, operation):
    old_key, new_key = (_end_ref(operation[field]) for field in ('from_end', 'to_end'))
    source, target = old_key[0], new_key[0]
    need(source == document and source != target, 'Select the source worksheet and a different destination worksheet')
    project = project_from(documents, paths, dest)
    chain = operation['reviewed_end_chain']
    alignment = _alignment(project, chain, old_key, new_key)
    old_id = operation['instrument_id']
    old_label_id = operation.get('expected_label_id')
    instrument, array, old_edges, settings, label, label_base, label_settings = _read(project, old_key, old_id, old_label_id)
    need(old_edges == tuple(operation['expected_edge_ids']), 'The saved instrument Edge order differs from the review')

    target_items = project.byid[target]
    old = project.model(old_key)
    new = native_monitoring.paired_instrument_end(target_items, new_key[1])
    need(new.contents[13].value is None, 'The replacement End already has a measuring instrument')
    native_monitoring.validate_instrument_location(target_items, new, instrument.contents[15].value, check_incidence=True)
    name = writer.string(instrument.contents[11].value)
    native_monitoring.unique_name(target_items, 'OTMeasuringModel', 11, name)
    new_edges = tuple(operation['replacement_edge_ids'])
    need(len(set(new_edges)) == len(new_edges), 'Select distinct destination worksheet instrument Edges')
    members = [native_monitoring.model(target_items, edge, 'OTEdgeModel') for edge in new_edges]
    for edge in members:
        native_monitoring.verified_edge_ends(target_items, edge)

    target_graphics = project.roots[target].contents[2].value
    counts = incoming_counts(project.roots[target])
    need(counts[id(target_graphics)] == 1, 'The destination worksheet graphic collection has another saved observer')
    new_id = native_monitoring.new_id(target_items)
    new_label_id = new_id + 1 if label is not None else None
    need(new_label_id is None or new_label_id <= 2_147_483_647, 'Native identity space for the measuring Label is exhausted')
    before = _drawing(instrument)
    after = _translated_drawing(instrument, old, new)
    movements = _movement_manifest(project)

    moved = (instrument,) if label is None else (instrument, label)
    _detach(project, old_key, moved)
    unselected = {sheet: writer.fingerprint(project.roots[sheet]) for sheet in (source, target)}
    instrument.contents[0].value = new_id
    instrument.contents[7].value = new
    new.contents[13].value = instrument
    writer.set_elements(array, members)
    _write_drawing(instrument, after)
    label_receipt = {}
    if label is not None:
        old_center, old_frame = _label_bounds(label, label_base)
        center, frame = _move_label(label, label_base, old, new)
        label.contents[0].value = new_label_id
        for slot, value in zip((2, 3), center, strict=True):
            label.contents[slot].value = value
        label.contents[label_base + 1].values = list(frame)
        label_receipt = {
            'from_label': {'document': source, 'label_id': old_label_id},
            'to_label': {'document': target, 'label_id': new_label_id}, 'label_settings_sha256': label_settings,
            'before_label_center': list(old_center), 'after_label_center': list(center),
            'before_label_frame': list(old_frame), 'after_label_frame': list(frame),
        }
    writer.set_elements(target_graphics, [*project.models[target], *moved])
    outputs = {sheet: writer.dump_verified(project.roots[sheet], project.versions[sheet]) for sheet in unselected}

    fresh = project_from({**documents, **outputs}, paths, dest)
    saved, _, saved_edges, saved_settings, saved_label, saved_base, saved_label_settings = _read(
        fresh, new_key, new_id, new_label_id)
    need(old_id not in fresh.byid[source] and fresh.model(old_key).contents[13].value is None
         and saved_edges == new_edges and saved_settings == settings and _drawing(saved) == after,
         'Transferred instrument ownership, Edge order, settings or drawing differ after cold read')
    if saved_label is not None:
        need(old_label_id not in fresh.byid[source] and saved_label_settings == label_settings
             and _label_bounds(saved_label, saved_base) == (center, frame),
             'Transferred measuring Label identity, geometry or settings differ after cold read')
    need(_movement_manifest(fresh) == movements and _alignment(fresh, chain, old_key, new_key) == alignment,
         'Saved movements or the reviewed measuring alignment changed after cold read')
    _detach(fresh, new_key, (saved,) if saved_label is None else (saved, saved_label))
    need(all(writer.fingerprint(fresh.roots[sheet]) == expected for sheet, expected in unselected.items()),
         'A saved object outside the approved instrument transfer changed')
    return outputs, {
        'action': operation['action'], 'document': document, 'changed_documents': sorted(outputs),
        'from_instrument': {'document': source, 'instrument_id': old_id}, 'from_end': old_key,
        'to_instrument': {'document': target, 'instrument_id': new_id}, 'to_end': new_key,
        'instrument_name': name, 'before_edge_ids': list(old_edges), 'after_edge_ids': list(new_edges),
        'before_graphic_xy': list(before[0][:2]), 'after_graphic_xy': list(after[0][:2]),
        'before_frame_origin': list(before[1]), 'after_frame_origin': list(after[1]),
        'settings_sha256': settings, 'reviewed_edges': alignment[0], 'connector_pair': alignment[1],
        'movement_count_checked': len(movements), 'nonselected_graph_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False,
        **label_receipt,
    }
