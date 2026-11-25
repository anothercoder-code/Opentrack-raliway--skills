"""Native bulk Route indications and category-indexed Signal11 fields."""

from . import catalogs, path_functions, route_factory, writer
from .graphic_alignment import make_signal_placement
from .graph_references import incoming_counts
from .infrastructure_incidents.core import number_object, number_value
from .movement_edits import _movement_project
from .multi_document.core import ident, need
from .route_discovery_tools import main_signal
from .stock_operations import CATEGORY_LAYOUT
from .zero_generation import native_signal_routes as native
from .zero_generation.topology import flt


PERFORMANCE_SIGNAL = 50
COASTING_SIGNAL = 49


def _archive_transaction(project, changes, documents, paths, dest, verify, restore):
    outputs = {doc: writer.dump_verified(project.roots[doc], project.versions[doc]) for doc in sorted(changes)}
    saved = _movement_project({**documents, **outputs}, paths, dest, allow_external_destinations=True)
    verify(saved)
    restore()
    for doc in outputs:
        old_root, old_version = writer.load_next_compatible(documents[doc])
        need(writer.dump_verified(project.roots[doc], project.versions[doc])
             == writer.dump_verified(old_root, old_version), 'An untargeted native field or graph reference changed')
    return outputs


def _indication_records(holder, owner):
    rows = route_factory.wrapper(holder, 'OTSigIndList')
    codes = []
    for row in rows:
        route_factory.layout(row, 'OTSigInd', 0, ['i', '@'])
        need(type(row.contents[0].value) is int and row.contents[1].value is owner,
             'Unknown native aspect value or owner')
        codes.append(row.contents[0].value)
    need(len(codes) <= 64 and len(codes) == len(set(codes)), 'Aspect lists require unique saved codes')
    return rows, codes


def _append_indications(holder, existing, codes, owner):
    replacement = path_functions.clone(holder)
    rows = [
        native.obj([('OTSigInd', 0), ('NSObject', 0)], [('i', [code]), ('@', [owner])])
        for code in codes
    ]
    replacement.contents[0].value = path_functions.array_like(holder.contents[0].value, [*existing, *rows])
    return replacement


def append_route_aspects(documents, paths, dest, selected, signal_speed_edits=()):
    project = _movement_project(documents, paths, dest, allow_external_destinations=True)
    owners = set()
    for route in project.routes:
        owner = project.owners[id(route)]
        if writer.kind(project.model(owner)) == 'OTEndModel':
            owners.add(owner)
    if selected is not None:
        targets = [tuple(key) for key in selected]
        need(len(targets) == len(set(targets)) and set(targets) <= owners, 'Select distinct saved primary Route starts')
    else:
        targets = sorted(owners)
    signal_changes = {tuple(row['start_end']): row['speeds_kmh'] for row in signal_speed_edits}
    need(len(signal_changes) == len(signal_speed_edits) and set(signal_changes) <= set(targets),
         'Each metric signal edit must address a different selected primary Route start')
    touched = set()
    undo = []
    found = []
    signals = []
    for key in targets:
        owner = project.model(key)
        need(main_signal(owner), 'The selected Route start does not carry a native main signal')
        signal = owner.contents[11].value
        holder = signal.contents[10].value
        rows, available_codes = _indication_records(holder, owner)
        if key in signal_changes:
            need(signal.contents[9].values[0] == 2, 'The explicit speed editor requires the native metric indication profile')
            speeds = signal_changes[key]
            need(len(speeds) == len(set(speeds)), 'Supply distinct metric signal speeds')
            # OTSigInd::speedKmhForTrainType:handleOccEntry: decodes show2
            # values <1000 as code*10 and larger values as code-1000.
            converted = [speed // 10 if speed % 10 == 0 else 1000 + speed for speed in speeds]
            additional = [code for code in converted if code not in available_codes]
            if additional:
                need(len(available_codes) + len(additional) <= 64, 'Metric source aspect list exceeds supported size')
                signal.contents[10].value = _append_indications(holder, rows, additional, owner)
                undo.append((signal, 10, holder))
                touched.add(key[0])
            available_codes = available_codes + additional
            signals.append({'owner': key, 'requested_speed_kmh': speeds, 'appended': additional,
                            'after': available_codes})
        array = route_factory.wrapper(owner.contents[15].value, 'OTRouteList')
        for route in array:
            holder = route.contents[4].value
            rows, prior = _indication_records(holder, route)
            extra = [code for code in available_codes if code not in prior]
            if extra:
                need(len(prior) + len(extra) <= 64, 'Combined native Route indication list exceeds supported size')
                undo.append((route, 4, holder))
                route.contents[4].value = _append_indications(holder, rows, extra, route)
                touched.add(key[0])
            found.append({'owner': key, 'route': ident(route), 'before': prior, 'signal_aspects': available_codes,
                          'appended': extra, 'after': prior + extra})

    def verify(saved):
        for row in signals:
            owner = saved.model(row['owner'])
            need(_indication_records(owner.contents[11].value.contents[10].value, owner)[1] == row['after'],
                 'Fresh saved source signal aspect order differs')
        for row in found:
            route = saved.owned(row['owner'], 'OTRoute', row['route'])
            need(_indication_records(route.contents[4].value, route)[1] == row['after'],
                 'Fresh saved route aspect order differs')

    def restore():
        for model, slot, prior in undo:
            model.contents[slot].value = prior

    changed = _archive_transaction(project, touched, documents, paths, dest, verify, restore)
    return changed, {'routes': found, 'signals': signals, 'updated_route_count': sum(bool(row['appended']) for row in found),
                     'original_codes_preserved': True,
                     'verified_irrelevant_graph_unchanged': True, 'native_runtime_verified': False}


def category_order(train_bytes):
    root, _ = writer.load_next_compatible(train_bytes)
    catalogs.train_items(root)
    categories = []
    for item in catalogs.array(root.contents[1].value):
        catalogs.shape(item, 'OTTrainCategory', 19, CATEGORY_LAYOUT)
        categories.append(catalogs.text(item.contents[1].value))
    need(1 <= len(categories) <= 999 and all(categories) and len(set(categories)) == len(categories)
         and len({name.casefold() for name in categories}) == len(categories),
         'The bound TrainList must contain unique ordered train categories')
    return categories


def _performance_values(row):
    route_factory.layout(row, 'OTDelayPerformance', 0, ['ff'])
    delay, performance = row.contents[0].values
    need(0 <= delay <= 86400 and 0 < performance <= 200, 'Stored category delay or performance outside known domain')
    return float(delay), float(performance)


def _performance_row(delay=0, performance=100):
    return native.obj([('OTDelayPerformance', 0), ('NSObject', 0)],
                      [('ff', [flt(delay, 'Category delay'), flt(performance, 'Category performance')])])


def _category_rows(signal, index, count):
    source = signal.contents[index].value
    if source is None:
        return []
    rows = path_functions.mutable_array(source)
    need(len(rows) <= count, 'Saved signal category array extends beyond the run-bound category order')
    return rows


def _category_state(signal, categories):
    kind = signal.contents[8].values[0]
    field = {PERFORMANCE_SIGNAL: 14, COASTING_SIGNAL: 15}[kind]
    rows = _category_rows(signal, field, len(categories))
    if kind == PERFORMANCE_SIGNAL:
        values = [_performance_values(row) for row in rows]
        values += [(0.0, 100.0)] * (len(categories) - len(values))
        return {'kind': 'performance_category', 'stored_rows': len(rows),
                'categories': [dict(category=name, delay_s=delay, performance_percent=performance)
                               for name, (delay, performance) in zip(categories, values)]}
    values = [number_value(row) for row in rows]
    values += [0] * (len(categories) - len(values))
    return {'kind': 'coasting', 'stored_rows': len(rows), 'lower_speed_kmh': signal.contents[9].values[3],
            'upper_speed_kmh': signal.contents[11].value,
            'categories': [dict(category=name, enabled=bool(value)) for name, value in zip(categories, values)]}


def _category_signal(project, document, end, op, mid):
    need(end.contents[11].value is None and end.contents[13].value is None,
         'Use an ordinary End without an existing signal or measuring instrument')
    need(writer.kind(project.model(project.related(project.key(end)))) == 'OTEndModel',
         'The original signal constructor requires an ordinary paired vertex')
    name = op['name']
    models = path_functions.mutable_array(project.roots[document].contents[2].value)
    need(not any(writer.kind(model) == 'OTSignalModel' and catalogs.text(model.contents[13].value).casefold()
                 == name.casefold() for model in models), 'Signal name already exists in this worksheet')
    placement = make_signal_placement(end, op['x'], op['y'])
    code = PERFORMANCE_SIGNAL if op['kind'] == 'performance_category' else COASTING_SIGNAL
    # Ordinary Signal11 constructor with explicit supported fields. Native
    # isMainSignal excludes both of these type codes.
    aspect = native.obj([('OTSigInd', 0), ('NSObject', 0)], [('i', [0]), ('@', [end])])
    return native.obj([('OTSignalModel', 11), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [mid]), ('f', [0.0]), ('f', [flt(placement['x'], 'Signal drawing x')]),
        ('f', [flt(placement['y'], 'Signal drawing y')]),
        ('i', [placement['alignment_x']]), ('i', [placement['alignment_y']]), ('@', [None]),
        ('@', [end]), ('iii', [code, 4, 2]), ('iiii', [2, 500, 644, 100 if code == PERFORMANCE_SIGNAL else 0]),
        ('@', [native.wrapped('OTSigIndList', [aspect])]), ('i', [0]), ('i', [7]),
        ('@', [native.string(name)]), ('@', [native.arr()]), ('@', [native.arr()]), ('f', [0.0]),
    ])


def _update_category_fields(signal, operation, categories):
    values = operation['rows']
    names = [row['category'] for row in values]
    need(len(set(names)) == len(names) and set(names) <= set(categories), 'Use distinct run-bound category names')
    performance = operation['kind'] == 'performance_category'
    slot = 14 if performance else 15
    indexed = {categories.index(row['category']): row for row in values}
    array = signal.contents[slot].value
    items = list(_category_rows(signal, slot, len(categories)))
    factory = _performance_row if performance else lambda: number_object(0)
    for _ in range(len(items), max(indexed, default=-1) + 1):
        items.append(factory())
    for index, row in indexed.items():
        if performance:
            items[index] = _performance_row(row['delay_s'], row['performance_percent'])
        else:
            items[index] = number_object(int(row['enabled']))
    if indexed:
        signal.contents[slot].value = native.arr(items) if array is None else path_functions.array_like(array, items)
    if not performance:
        lower, upper = operation['lower_speed_kmh'], operation['upper_speed_kmh']
        if lower is not None:
            signal.contents[9].values[3], signal.contents[11].value = lower, upper
        need(0 < signal.contents[9].values[3] < signal.contents[11].value <= 1000,
             'Store a positive lower coasting threshold below the upper threshold')


def edit_category_signals(documents, paths, dest, train_bytes, operations):
    categories = category_order(train_bytes)
    project = _movement_project(documents, paths, dest, allow_external_destinations=True)
    max_ids = {name: max(index, default=-1) for name, index in project.byid.items()}
    counts = {name: incoming_counts(root) for name, root in project.roots.items()}
    undo_fields, undo_models, inserted, reports, touched, used = [], {}, [], [], set(), set()
    for op in operations:
        doc = op['document']
        end = project.model((doc, op['end_id']))
        need(writer.kind(end) == 'OTEndModel' and (doc, op['end_id']) not in used,
             'Choose distinct ordinary signal-owner Ends')
        used.add((doc, op['end_id']))
        if op['action'] == 'insert':
            max_ids[doc] += 1
            need(max_ids[doc] < 2147483647, 'Graphic ID exhausted')
            signal = _category_signal(project, doc, end, op, max_ids[doc])
            prior = None
            root = project.roots[doc]
            field = root.contents[2]
            undo_models.setdefault(doc, field.value)
            field.value = path_functions.array_like(field.value, [*path_functions.mutable_array(field.value), signal])
            end.contents[11].value = signal
            inserted.append(end)
        else:
            code = PERFORMANCE_SIGNAL if op['kind'] == 'performance_category' else COASTING_SIGNAL
            signal = project.model((doc, op['signal_id']))
            need(writer.kind(signal) == 'OTSignalModel' and end.contents[11].value is signal
                 and signal.contents[8].values[0] == code and counts[doc][id(signal)] == 2,
                 'Select a known originating signal type with exact ownership')
            prior = _category_state(signal, categories)
            undo_fields.append((signal, {group: list(signal.contents[group].values) for group in (9, 11, 14, 15)}))
        _update_category_fields(signal, op, categories)
        after = _category_state(signal, categories)
        reports.append({'document': doc, 'end_id': op['end_id'], 'signal_id': signal.contents[0].value,
                        'before': prior, 'after': after})
        touched.add(doc)

    def verify(saved):
        for row in reports:
            end = saved.model((row['document'], row['end_id']))
            signal = saved.model((row['document'], row['signal_id']))
            need(end.contents[11].value is signal and signal.contents[7].value is end
                 and _category_state(signal, categories) == row['after'], 'Native category signal readback differs')

    def restore():
        for end in inserted:
            end.contents[11].value = None
        for doc, original in undo_models.items():
            project.roots[doc].contents[2].value = original
        for signal, original in undo_fields:
            for slot, values in original.items():
                signal.contents[slot].values[:] = values

    # Published routes stay in the same main-signal family and graph. An
    # auxiliary signal is meaningful precisely because it can affect physics.
    changed = _archive_transaction(project, touched, documents, paths, dest, verify, restore)
    return changed, {'category_order': categories, 'signals': reports,
                     'verified_irrelevant_graph_unchanged': True, 'native_runtime_verified': False}
