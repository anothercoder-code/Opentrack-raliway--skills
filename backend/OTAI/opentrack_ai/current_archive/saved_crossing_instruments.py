"""Move reviewed measurement Edge-array members and their owner during a saved track edit."""

from collections import Counter, defaultdict
from dataclasses import dataclass

from . import native_monitoring, path_functions, writer
from .graph_references import incoming_counts
from .multi_document.core import need
from .saved_crossing_dependencies import crossing_edge_changes
from .zero_generation.topology import flt


@dataclass(frozen=True)
class InstrumentEdgePlan:
    document: str
    instrument_id: int
    end_id: int
    new_end_id: int
    before: tuple[int, ...]
    after: tuple[int, ...]
    settings_sha256: str
    before_drawing: tuple
    after_drawing: tuple


def relocated_instrument_ends(plan, *, after=False):
    return {(row.document, row.new_end_id if after else row.end_id) for row in plan if row.end_id != row.new_end_id}


def _drawing(instrument):
    return tuple(instrument.contents[slot].value for slot in (2, 3, 4, 5)), tuple(instrument.contents[9].values)


def _translated_drawing(instrument, old, new):
    drawing, frame = _drawing(instrument)
    delta = native_monitoring.floats([new.contents[slot].value - old.contents[slot].value for slot in (2, 3)])
    xy = [flt(value, 'Instrument drawing position') for value in native_monitoring.floats(
        [position + shift for position, shift in zip(drawing[:2], delta, strict=True)])]
    # The stock view treats an all-zero frame as unset. Preserve the sentinel.
    size = instrument.contents[10].values
    if any((*frame, *size)):
        need(all(value > 0 for value in native_monitoring.floats([float(value) for value in size])),
             'A configured measuring-instrument frame needs positive width and height')
        frame = tuple(flt(value, 'Measuring window origin') for value in native_monitoring.floats(
            [position + shift for position, shift in zip(frame, delta, strict=True)]))
    return (*xy, new.contents[4].value, new.contents[5].value), frame


def _write_drawing(instrument, geometry):
    drawing, frame = geometry
    for slot, value in zip((2, 3, 4, 5), drawing, strict=True):
        instrument.contents[slot].value = value
    instrument.contents[9].values = list(frame)


def _read_instrument(project, document, instrument_id, expected_end_id, counts, *, relocating=False, ignore_local_id=False,
                     owned_label=None):
    items = project.byid[document]
    instrument = native_monitoring.model(items, instrument_id, 'OTMeasuringModel')
    native_monitoring.instrument_shape(instrument)
    end = native_monitoring.paired_instrument_end(items, expected_end_id)
    array = instrument.contents[12].value
    need(instrument.contents[7].value is end and end.contents[13].value is instrument,
         'The reviewed ordinary End does not carry this source instrument')
    need(counts[id(instrument)] == (2 if owned_label is None else 3) and counts[id(array)] == 1
         and instrument.contents[6].value is owned_label,
         'An instrument or its native Edge array has an unreviewed saved observer or label')
    native_monitoring.validate_instrument_location(items, end, instrument.contents[15].value, check_incidence=True)
    edges = path_functions.mutable_array(array)
    for edge in edges:
        native_monitoring.verified_edge_ends(items, edge)
    ids = tuple(native_monitoring.identifier(edge) for edge in edges)
    need(len(set(ids)) == len(ids), 'The original instrument Edge array has repeated members')

    # Check the End, member pointers and permitted drawing changes separately.
    groups = [writer.TypedGroup(list(group.encodings), list(group.values)) for group in instrument.contents]
    if ignore_local_id:
        groups[0].value = 0
    for slot in (6, 7, 12):
        groups[slot].value = None
    if relocating:
        for slot in (2, 3, 4, 5):
            groups[slot].value = 0
        groups[9].values = [0, 0]
    settings = writer.GenericArchivedObject(instrument.clazz, groups)
    return instrument, array, ids, writer.fingerprint(settings)


def _branch_ends(project, references):
    result = set()
    for row in references:
        document = row['document']
        edge = native_monitoring.model(project.byid[document], row['edge_id'], 'OTEdgeModel')
        for endpoint in native_monitoring.verified_edge_ends(project.byid[document], edge):
            key = project.key(endpoint)
            result.update((key, project.related(key)))
    return result


def prepare_instrument_edge_rebindings(project, dependency, reviews):
    """Validate explicit native owners and compute exact incoming Edge pointer allowances."""
    old_only, new_only = crossing_edge_changes(dependency)
    scope = {(row['document'], row['edge_id']) for field in ('old_edges', 'replacement_edges')
             for row in dependency[field]}
    keys = {(row['document'], row['instrument_id']) for row in reviews}
    need(len(keys) == len(reviews), 'Review each worksheet-qualified measuring instrument only once')
    counts = {name: incoming_counts(project.roots[name]) for name in {doc for doc, _ in keys if doc in project.roots}}
    plan, destinations = [], set()
    branches = None
    previous, revised = defaultdict(Counter), defaultdict(Counter)
    for row in reviews:
        document, instrument_id, end_id = row['document'], row['instrument_id'], row['expected_end_id']
        need(document in counts, 'Select a measuring instrument in a verified worksheet')
        selected_target = row.get('replacement_end_id')
        new_end_id = end_id if selected_target is None else selected_target
        relocating = selected_target is not None
        need(not relocating or new_end_id != end_id, 'Select a different replacement measuring-instrument End')
        instrument, _, before, settings = _read_instrument(project, document, instrument_id, end_id, counts[document],
                                                            relocating=relocating)
        need(tuple(row['expected_edge_ids']) == before, 'The saved instrument Edge order differs from the review')
        mapping = {item['old_edge_id']: item['new_edge_ids'] for item in row['edge_rebindings']}
        need((mapping or relocating) and len(mapping) == len(row['edge_rebindings']) and mapping.keys() <= set(before),
             'Review each current instrument Edge to rebind only once')
        need(all((document, old) in old_only and new and all((document, edge) in new_only for edge in new)
                 for old, new in mapping.items()),
             'Instrument members must move from old-only track to same-worksheet replacement track')
        need(all(edge in mapping for edge in before if (document, edge) in old_only),
             'Review all old-only Edge members of the selected instrument')
        after = tuple(replacement for edge in before for replacement in mapping.get(edge, [edge]))
        need(len(after) == len(set(after)), 'The transferred instrument would repeat an Edge')
        items = project.byid[document]
        drawing = _drawing(instrument)
        proposed = drawing
        if relocating:
            target = native_monitoring.paired_instrument_end(items, new_end_id)
            need(target.contents[13].value is None and (document, new_end_id) not in destinations,
                 'Each replacement End must be free and selected once')
            native_monitoring.validate_instrument_location(items, target, instrument.contents[15].value, check_incidence=True)
            if branches is None:
                branches = [(_branch_ends(project, branch['old_edges']), _branch_ends(project, branch['replacement_edges']))
                            for branch in dependency.get('crossings', [dependency])]
            need(any((document, end_id) in old and (document, new_end_id) in new for old, new in branches),
                 'The instrument owners must follow the corresponding reviewed original and replacement branch')
            proposed = _translated_drawing(instrument, items[end_id], target)
            destinations.add((document, new_end_id))
        for edge in after:
            native_monitoring.verified_edge_ends(items, native_monitoring.model(items, edge, 'OTEdgeModel'))
        previous[document].update(edge for edge in before if (document, edge) in scope)
        revised[document].update(edge for edge in after if (document, edge) in scope)
        plan.append(InstrumentEdgePlan(document, instrument_id, end_id, new_end_id, before, after, settings, drawing, proposed))
    return plan, {name: dict(values) for name, values in previous.items()}, {name: dict(values) for name, values in revised.items()}


def _checked_arrays(project, plan, *, after=False):
    counts = {name: incoming_counts(project.roots[name]) for name in {row.document for row in plan}}
    arrays = []
    for row in plan:
        changed = row.end_id != row.new_end_id
        end_id = row.new_end_id if after else row.end_id
        instrument, array, edges, settings = _read_instrument(project, row.document, row.instrument_id, end_id, counts[row.document],
                                                               relocating=changed)
        need(edges == (row.after if after else row.before) and settings == row.settings_sha256
             and _drawing(instrument) == (row.after_drawing if after else row.before_drawing),
             'Saved instrument settings, attachment or ordered Edge members differ from the reviewed transaction')
        if changed:
            if after and row.end_id in project.byid[row.document]:
                need(project.model((row.document, row.end_id)).contents[13].value is None,
                     'The original End still has a measurement attachment after transfer')
            if not after:
                target = project.model((row.document, row.new_end_id))
                need(target.contents[13].value is None
                     and _translated_drawing(instrument, project.model((row.document, row.end_id)), target) == row.after_drawing,
                     'The replacement measurement End is occupied or moved after review')
        arrays.append((instrument, array))
    return arrays


def apply_instrument_edge_rebindings(project, plan):
    arrays = _checked_arrays(project, plan)
    receipts = []
    for row, (instrument, array) in zip(plan, arrays, strict=True):
        edges = [project.model((row.document, edge)) for edge in row.after]
        writer.set_elements(array, edges)
        receipts.append({'document': row.document, 'instrument_id': row.instrument_id, 'end_id': row.new_end_id,
                         'before_edge_ids': list(row.before), 'after_edge_ids': list(row.after),
                         'settings_sha256': row.settings_sha256})
        if row.end_id != row.new_end_id:
            old, target = [project.model((row.document, end_id)) for end_id in (row.end_id, row.new_end_id)]
            old.contents[13].value = None
            target.contents[13].value = instrument
            instrument.contents[7].value = target
            drawing, frame = row.after_drawing
            _write_drawing(instrument, row.after_drawing)
            receipts[-1].update(before_end_id=row.end_id, after_end_id=row.new_end_id,
                                before_graphic_xy=list(row.before_drawing[0][:2]), after_graphic_xy=list(drawing[:2]),
                                before_frame_origin=list(row.before_drawing[1]), after_frame_origin=list(frame))
    return receipts


def verify_instrument_edge_rebindings(project, plan):
    _checked_arrays(project, plan, after=True)
