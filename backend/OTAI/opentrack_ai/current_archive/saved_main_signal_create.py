"""Create a native main signal on a free directional End in a verified project."""

from . import path_functions, route_factory, writer
from .graphic_alignment import validate_generated_signal_alignment
from .graph_references import incoming_counts
from .multi_document.core import need
from .saved_cross_platform_halts import _guard_signal_incidents
from .saved_geometry import _movement_manifest, project_from
from .signal_type_workflow.core import ROLES
from .zero_generation.native_signal_routes import main_signal_model


def create_saved_main_signal(documents, paths, dest, document, operation, courses):
    project = project_from(documents, paths, dest)
    key = document, operation['end_id']
    end = project.model(key)
    need(writer.kind(end) == 'OTEndModel' and writer.kind(project.model(project.related(key))) == 'OTEndModel'
         and end.contents[11].value is None, 'Select an ordinary paired End with an empty signal slot')
    need(any(end.contents[slot].value is not None for slot in (9, 10))
         and end.contents[13].value is None, 'The selected signal End needs an approaching Edge and no measuring instrument')
    movements = _movement_manifest(project)
    need(not any(key in nodes for nodes, _, _ in movements.values()),
         'The selected direction is used by a saved movement and needs a joint signal and Route edit')
    root = project.roots[document]
    models = root.contents[2].value
    counts = incoming_counts(root)
    need(counts[id(root)] == 0 and counts[id(models)] == 1, 'The source worksheet graphic collection is shared')
    path_functions.guard_counter_references(root, end)
    name = operation['signal_name']
    need(all(writer.string(item.contents[13].value).casefold() != name.casefold()
             for item in project.models[document] if writer.kind(item) == 'OTSignalModel' and item.contents[13].value is not None),
         'The target worksheet already has this signal name')
    signal_id = max(project.byid[document]) + 1
    _guard_signal_incidents(courses, [(document, signal_id)])
    signal = main_signal_model(end, name=name, model_id=signal_id, placement=operation['placement'],
        sight_m=operation['sight_m'], delay_s=operation['delay_s'], show_symbol=operation['show_symbol'],
        show_icon=operation['show_icon'])
    signal.contents[8].values[1] = ROLES[operation['main_role']]
    unedited = writer.fingerprint(root)
    end.contents[11].value = signal
    writer.set_elements(models, [*project.models[document], signal])
    output = writer.dump_verified(root, project.versions[document])
    fresh = project_from({**documents, document: output}, paths, dest)
    saved_end, saved = fresh.model(key), fresh.model((document, signal_id))
    validate_generated_signal_alignment(saved)
    indication, = route_factory.wrapper(saved.contents[10].value, 'OTSigIndList')
    need(indication.contents[0].value == 0 and indication.contents[1].value is saved_end
         and saved.contents[8].values == signal.contents[8].values and _movement_manifest(fresh) == movements,
         'Main signal or unchanged movement references differ after native readback')
    saved_end.contents[11].value = None
    fresh_root = fresh.roots[document]
    writer.set_elements(fresh_root.contents[2].value, [item for item in fresh.models[document] if item is not saved])
    need(writer.fingerprint(fresh_root) == unedited, 'Something besides the new main signal changed in this worksheet')
    return {document: output}, {'action': operation['action'], 'document': document, 'end_id': key[1],
        'signal_id': signal_id, 'signal_name': name, 'main_role': operation['main_role'],
        'unchanged_movements': len(movements), 'nonselected_graph_verified': True, 'native_execution_tested': False}
