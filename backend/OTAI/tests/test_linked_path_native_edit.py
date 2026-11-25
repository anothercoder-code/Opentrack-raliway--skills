"""Native-format Path edits across real archive aliases and saved references."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.movement_edit_tools import EditPath, MovementEdits
from opentrack_ai.current_archive.movement_edits import _movement_project, edit_path_routes
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import fixture, schematic_document, with_margin, with_overlap


def linked_path_fixture(document_path='Line.opentrack'):
    documents, catalog, names, path_refs = fixture(document_path)
    root, _ = writer.load(documents['Line'])
    original = path_functions.select(root, 'OTRoute', 'R0')
    end_ids = [end.contents[0].value for end in path_functions.mutable_array(original.contents[0].value)]
    document, receipt = native.build_route(documents['Line'], name='R0-alt', end_ids=end_ids,
                                           description='', release_groups='global', reserve_previous=False)
    documents['Line'] = with_margin(with_overlap(document))
    ref = {k: v for k, v in path_refs[0].items() if k != 'document'}
    alternate = {'name': 'R0-alt', 'array_id': receipt['array_id'], 'start_id': receipt['start_id']}
    return documents, catalog, names, ref, alternate


def test_linked_path_replacement_preserves_itinerary_alias_and_overlap():
    documents, catalog, names, ref, alternate = linked_path_fixture()
    saved, receipt = edit_path_routes(documents, 'Line', catalog, ref, [alternate], 'Alternate', document_paths=names)
    assert receipt['dependent_itineraries'] == ['Service']
    assert receipt['rerouted_itineraries'] == []
    assert receipt['before_directional_ends'] == receipt['after_directional_ends']
    assert receipt['running_time_revalidation_required'] and receipt['dest_catalog_bindings_verified']
    checked = _movement_project({'Line': saved}, names, catalog)
    path = checked.owned(('Line', ref['start_id']), 'OTPath', (ref['name'], ref['array_id'], ref['start_id']))
    dest = checked.dests[0]
    assert path_functions.mutable_array(dest.contents[0].value)[0] is path
    assert path_functions.info(path)['saved_references'] == [alternate]
    assert checked.shunting_movements == _movement_project(documents, names, catalog).shunting_movements


def test_linked_path_final_end_and_stale_destinfo_are_rejected():
    documents, catalog, names, ref, alternate = linked_path_fixture()
    original, _ = writer.load(documents['Line'])
    onward = path_functions.select(original, 'OTRoute', 'R1')
    next_route = generate.ref(onward)
    with pytest.raises(ValueError, match='preserve the final directional End'):
        edit_path_routes(documents, 'Line', catalog, ref, [alternate, next_route], document_paths=names)

    root, version = writer.load(catalog)
    row = generate.rf.wrapper(root, 'OTDestInfoList')[0]
    references = path_functions.mutable_array(row.contents[4].value)
    references[0].contents[1].values[0] += 1
    broken = writer.dump_verified(root, version)
    with pytest.raises(ValueError, match='DestInfo Path ExtInfo mismatch'):
        edit_path_routes(documents, 'Line', broken, ref, [alternate], document_paths=names)


def test_linked_path_can_reroute_between_same_station_endpoints_without_distance_margins():
    line = generate.spec()
    line['vertices'] = [generate.vertex(name, index * 100) for index, name in enumerate('ABCD')]
    edge = line['edges'][0]
    line['edges'] = [{**edge, 'key': first + last, 'from': [first, 1], 'to': [last, 0]}
                     for first, last in ['AB', 'AC', 'BD', 'CD']]
    document, ids = schematic_document(line, [('A', 0), ('D', 0)])
    refs = []
    for name, intermediate in [('ByB', 'B'), ('ByC', 'C')]:
        document, receipt = native.build_route(document, name=name,
            end_ids=[ids[key][0] for key in ('A', intermediate, 'D')], description='',
            release_groups='global', reserve_previous=False)
        refs.append({'name': name, 'array_id': receipt['array_id'], 'start_id': receipt['start_id']})
    documents, names = {'Line': document}, {'Line': 'Line.opentrack'}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))

    def dependencies():
        return {'document_paths': names, 'complete_document_set': True,
                'expected_hashes': {'Line': sha(documents['Line']), '$dest_catalog': sha(catalog)}}

    documents, path = operations.create_path(documents, catalog, name='Branch',
        routes=[{'document': 'Line', **refs[0]}], **dependencies())
    output, _ = operations.create_itinerary(documents, catalog, name='Service',
        paths=[path['created']], **dependencies())
    documents, catalog = output['documents'], output['catalog']
    ref = {k: v for k, v in path['created'].items() if k != 'document'}
    saved, receipt = edit_path_routes(documents, 'Line', catalog, ref, refs[1:], document_paths=names)
    assert saved != documents['Line']
    assert receipt['rerouted_itineraries'] == ['Service']
    assert receipt['after_end_ids'] == [ids[key][0] for key in 'ACD']

    documents['Line'] = with_margin(documents['Line'])
    with pytest.raises(ValueError, match='distance-based safety margins'):
        edit_path_routes(documents, 'Line', catalog, ref, refs[1:], document_paths=names)


def test_cross_document_path_continuation_sequence_validated():
    names = {key: f'OTDocuments/{key}.opentrack' for key in 'AB'}
    documents, catalog, _ = generate.make_pair({
        'A': schematic_document(generate.spec(), [('left', 0), ('left', 1)])[0],
        'B': schematic_document(generate.spec(), [('right', 0), ('right', 1)])[0],
    }, names)
    project = _movement_project(documents, names, catalog)
    path = next(path for path in project.paths_objects if generate.ref(path)['name'] == 'P:A-B')
    ref = generate.ref(path)
    document, route = project.path_view(path)[1][0]
    saved, receipt = edit_path_routes(documents, 'A', catalog, ref, [{'document': document, **route}],
                                      'Crossing', document_paths=names)
    assert saved != documents['A']
    assert receipt['after_directional_ends'] == [('A', 0), ('A', 4), ('B', 4)]
    assert receipt['dependent_itineraries'] == ['I:A-B']
    with pytest.raises(ValueError, match='Disconnected Route sequence'):
        edit_path_routes(documents, 'A', catalog, ref, [{'document': 'B', **route}], document_paths=names)


def test_linked_path_service_publishes_new_file_and_reloads():
    # Native handle tests need an ordinary fixed local NTFS directory on Windows.
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
        root = Path(temp)
        project = root / 'OTProjects' / 'Line'
        project.mkdir(parents=True)
        output = root / 'OTAI' / 'workspaces' / 'Output'
        output.mkdir(parents=True)
        documents, catalog, _, ref, alternate = linked_path_fixture()
        inputs = {'Line.opentrack': documents['Line'], 'Line.dest': catalog,
                  'Line.run': b'Infrastructure Document#Line.opentrack#\nDestInfoFile#Line.dest#\n'}
        for name, data in inputs.items():
            (project / name).write_bytes(data)

        def source(name):
            return {'path': (project / name).relative_to(root).as_posix(), 'sha256': sha(inputs[name])}

        args = {'path': ref, 'operation': {
            'action': 'replace_routes', 'target_document': 'Line', 'project_run': source('Line.run'),
            'documents': {'Line': source('Line.opentrack')}, 'dest_catalog': source('Line.dest'),
            'routes': [alternate],
        }}
        service = MovementEdits(root)
        preview = service.edit_path(EditPath(**args))
        assert not preview['saved']
        target = output / 'Line-edited.opentrack'
        save = EditPath(**args, preview_only=False, target_path=target.relative_to(root).as_posix())
        result = service.edit_path(save)
        assert result['saved'] and sha(target.read_bytes()) == preview['output_sha256']
        assert result['change_report']['dependent_itineraries'] == ['Service']
        assert all((project / name).read_bytes() == data for name, data in inputs.items())
        with pytest.raises(APIError) as error:
            service.edit_path(save)
        assert error.value.code == 'TARGET_EXISTS'
