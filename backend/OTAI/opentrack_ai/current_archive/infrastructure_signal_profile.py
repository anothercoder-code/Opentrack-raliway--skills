"""Rebuild tabular-import signals from verified native Inspector-equivalent settings."""

from . import catalogs, route_factory, writer
from .graphic_alignment import validate_generated_signal_alignment
from .infrastructure_ivt import MAX_SIGNALS, require
from .multi_document.generate import signal_placement
from .zero_generation import native_signal_routes as native, topology


def inspect_signal_template(raw, signal_id):
    root, _ = writer.load_next_compatible(raw)
    topology.doc_layout(root)
    models = catalogs.array(root.contents[2].value)
    selected = [model for model in models if model.contents[0].value == signal_id]
    require(len(selected) == 1, 'Select a unique native signal template model ID')
    signal, = selected
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    end = signal.contents[7].value
    require(signal.contents[6].value is None and end in models and writer.kind(end) == 'OTEndModel'
            and end.contents[11].value is signal, 'Signal template needs one reciprocally attached ordinary End')
    sig_type, main_role, location = signal.contents[8].values
    show, sight, flags, release = signal.contents[9].values
    warning, dispatch, delay = (signal.contents[index].value for index in (11, 12, 16))
    require(sig_type in (1, 2, 3) and main_role in (2, 3, 4) and location in (1, 2),
            'Signal template requires a reviewed current main, distant or combined profile')
    require(writer.string(signal.contents[13].value) == '', 'Signal template must have its native blank name')
    require(show == 2 and (flags & ~(640 | 4 | 8)) == 0 and (flags & 640) == 640
            and release == 0 and warning in (-1, 0) and dispatch == 7,
            'Signal template requires reviewed Inspector constructor settings')
    native.integer(sight, 1, 100000)
    native.number(float(delay), 0, 86400)
    indications = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
    require(len(indications) == 1, 'Signal template requires one track-speed indication')
    indication, = indications
    route_factory.layout(indication, 'OTSigInd', 0, ['i', '@'])
    require(indication.contents[0].value == 0 and indication.contents[1].value is end
            and not catalogs.array(signal.contents[14].value) and not catalogs.array(signal.contents[15].value),
            'Signal template has external indications or per-category overrides')
    return {'model_id': signal_id, 'native_signal_type': sig_type, 'main_role': main_role, 'location': location,
            'show_type': show, 'sight_m': sight, 'flags': flags, 'release_speed_kmh': release,
            'warning_speed_kmh': warning, 'dispatch_type': dispatch, 'delay_s': delay}


def attach_template_signals(document, selections, template):
    require(len(selections) <= MAX_SIGNALS, 'Too many tabular signal placements')
    if not selections:
        return document, []
    require(template is not None, 'Tabular signal placements need a pinned native signal profile')
    root, stream, _, records = native.document(document)
    array = root.contents[2].value
    new_id = max(records) + 1
    planned = []
    for signal in selections:
        end = records[signal['end_id']]
        require(end.contents[11].value is None, 'An imported signal requires a free native End')
        flags = template['flags']
        main_role = signal.get('main_role', template['main_role'])
        virtual = signal.get('virtual', False)
        placement = signal_placement(end, float(end.contents[2].value), float(end.contents[3].value))
        model = native.signal_model(end, name='', model_id=new_id, placement=placement, sight_m=template['sight_m'],
                                    delay_s=float(template['delay_s']), show_symbol=bool(flags & 4),
                                    show_icon=not bool(flags & 8), signal_type=1, main_type=main_role, virtual=virtual)
        model.contents[8].values[:] = [signal['type_raw'], main_role, template['location']]
        model.contents[11].value = template['warning_speed_kmh']
        end.contents[11].value = model
        array.contents.append(writer.TypedValue(b'@', model))
        planned.append({**signal, 'signal_id': new_id})
        new_id += 1
    array.contents[0].value += len(planned)
    result = writer.dump_verified(root, stream)
    check, _, _, saved = native.document(result)
    native.validate_topology(check)
    for signal in planned:
        model, end = saved[signal['signal_id']], saved[signal['end_id']]
        validate_generated_signal_alignment(model)
        main_role = signal.get('main_role', template['main_role'])
        flags = template['flags'] | (2 if signal.get('virtual', False) else 0)
        require(model.contents[7].value is end and end.contents[11].value is model
                and model.contents[8].values == [signal['type_raw'], main_role, template['location']]
                and model.contents[9].values == [template['show_type'], template['sight_m'], flags, template['release_speed_kmh']]
                and [model.contents[index].value for index in (11, 12, 16)] ==
                    [template[key] for key in ('warning_speed_kmh', 'dispatch_type', 'delay_s')],
                'Saved tabular signal profile, placement or End ownership differs')
        require(route_factory.wrapper(model.contents[10].value, 'OTSigIndList')[0].contents[1].value is end,
                'Saved tabular signal indication needs the new End owner')
        end.contents[11].value = None
    checked_array = check.contents[2].value
    checked_array.contents[0].value -= len(planned)
    del checked_array.contents[-len(planned):]
    original, _ = writer.load_next_compatible(document)
    require(writer.fingerprint(check) == writer.fingerprint(original), 'Unrelated tabular worksheet graph changed')
    return result, planned
