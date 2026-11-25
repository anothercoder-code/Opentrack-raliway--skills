"""Synthetic directed topology fixtures exercising saved native Shunting actions."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from opentrack_ai.current_archive import path_functions as paths, route_factory, writer
from opentrack_ai.current_archive.current_shunting_tools import EditShuntingStructure, ShuntingParameterEdits
from opentrack_ai.current_archive.current_shunting_workflow import core
from opentrack_ai.current_archive.current_shunting_workflow.structure import edit_structure
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError
from test_itinerary_native_edit import schematic_document


def make_fixture():
    network = generate.spec()
    network['vertices'] = [generate.vertex(name, i * 100) for i, name in enumerate('ABCD')]
    template = network['edges'][0]
    network['edges'] = [{**template, 'key': a + b, 'from': [a, 1], 'to': [b, 0]} for a, b in ('AB', 'BC', 'BD')]
    data, end_pairs = schematic_document(network, [('A', 0), ('B', 0)])
    ends = {name: pair[0] for name, pair in end_pairs.items()}
    data, route = native.build_route(data, name='A-B', end_ids=[ends['A'], ends['B']], description='',
                                     release_groups='global', reserve_previous=False)
    reference = {'name': 'A-B', 'array_id': route['array_id'], 'start_id': route['start_id']}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    return data, catalog, reference, ends


def create_spec(ends, name='B-C Shunting'):
    return {'name': name, 'description': 'Initial', 'end_ids': [ends['B'], ends['C']], 'speed_kmh': 34.5,
            'release_time_s': 10, 'reservation_time_s': 3}


def with_catalog_reference(reference):
    info = native.obj([('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)], [
        ('@', [native.string(reference['name'])]), ('ii', [reference['array_id'], reference['start_id']]),
        ('@', [native.string('Line')]),
    ])
    row = native.obj([('OTDestInfo', 1), ('NSObject', 0)], [
        ('i', [17]), ('@', [native.string('Service')]), ('@', [native.string('Line.opentrack')]),
        ('i', [reference['start_id']]), ('@', [native.arr([info])]),
    ])
    return writer.dump_verified(generate.wrapped('OTDestInfoList', [row]))


def test_active_overlap_can_be_changed_and_then_removed():
    source, catalog, route, ends = make_fixture()
    created, receipt = edit_structure({'Line': source}, catalog, 'Line', 'create', create_spec(ends))
    shunting = {key: receipt['details'][key] for key in ('name', 'start_id', 'array_id')}
    binding = {'route': route, 'shunting': shunting}
    bound, _ = edit_structure({'Line': created}, catalog, 'Line', 'bind_overlap', binding)
    bound_root, version = writer.load(bound)
    paths.select(bound_root, 'OTRoute', **route).contents[9].value = -1
    bound = writer.dump_verified(bound_root, version)
    with pytest.raises(ValueError, match='Dependent Overlap'):
        edit_structure({'Line': bound}, catalog, 'Line', 'delete', {'shunting': shunting})
    moved, receipt = edit_structure({'Line': bound}, catalog, 'Line', 'replace_movement',
                                    {'shunting': shunting, 'end_ids': [ends['B'], ends['D']], 'description': 'Branch'})
    assert receipt['details']['overlap_routes'] == [route]
    assert receipt['details']['operating_validation_required']
    _, _, _, rows = core.load(moved)
    saved = core.select(rows, shunting)
    assert core.detail(saved)['end_ids'] == [ends['B'], ends['D']]
    assert paths.string(saved[1].contents[3].value) == 'Branch'
    assert paths.select(writer.load(moved)[0], 'OTRoute', **route).contents[9].value == -1
    unbound, _ = edit_structure({'Line': moved}, catalog, 'Line', 'unbind_overlap', {'route': route})
    deleted, receipt = edit_structure({'Line': unbound}, catalog, 'Line', 'delete', {'shunting': shunting})
    assert not core.inspect(deleted)['shuntings']
    assert receipt['details']['highestGivenRspID'] == shunting['array_id']


def test_references_and_allocator_are_checked():
    source, catalog, _, ends = make_fixture()
    created, receipt = edit_structure({'Line': source}, catalog, 'Line', 'create', create_spec(ends))
    shunting = {key: receipt['details'][key] for key in ('name', 'start_id', 'array_id')}
    bound_catalog = with_catalog_reference(shunting)
    with pytest.raises(ValueError, match='bound DestInfo'):
        edit_structure({'Line': created}, bound_catalog, 'Line', 'delete', {'shunting': shunting})
    with pytest.raises(ValueError, match='bound DestInfo'):
        edit_structure({'Line': source}, bound_catalog, 'Line', 'create', create_spec(ends))
    two, second = edit_structure({'Line': created}, catalog, 'Line', 'create', create_spec(ends, 'Second'))
    assert second['details']['array_id'] == shunting['array_id'] + 1
    assert len(core.inspect(two)['shuntings']) == 2
    with pytest.raises(ValueError, match='owner End'):
        edit_structure({'Line': created}, catalog, 'Line', 'replace_movement',
                       {'shunting': shunting, 'end_ids': [ends['A'], ends['B']]})


def test_original_first_save_persists_two_allocations_without_a_saved_editor_body():
    source, catalog, _, ends = make_fixture()
    legacy, legacy_receipt = edit_structure({'Line': source}, catalog, 'Line', 'create', create_spec(ends))
    legacy_id = legacy_receipt['details']['array_id']
    request = {**create_spec(ends, 'Original first save'), 'rsp_id_policy': 'original_first_save'}
    created, result = edit_structure({'Line': legacy}, catalog, 'Line', 'create', request)
    assert result['details']['rsp_allocation'] == {
        'rsp_id_policy': 'original_first_save',
        'previous_highest_rsp_id': legacy_id,
        'saved_highest_rsp_id': legacy_id + 2,
        'editor_copy_rsp_id': legacy_id + 1,
    }
    identity = {key: result['details'][key] for key in ('name', 'array_id', 'start_id')}
    assert identity['array_id'] == legacy_id + 2
    _, _, byid, rows = core.load(created)
    path, body, _, _ = core.select(rows, identity)
    reference, = paths.mutable_array(path.contents[4].value)
    assert body.contents[2].values == reference.contents[1].values == [-1, -1]
    assert byid[ends['B']].contents[19].value == legacy_id + 2
    deleted, _ = edit_structure({'Line': created}, catalog, 'Line', 'delete', {'shunting': identity})
    _, following = edit_structure({'Line': deleted}, catalog, 'Line', 'create', create_spec(ends, 'After delete'))
    assert following['details']['array_id'] == legacy_id + 3


def test_original_first_save_refuses_when_only_one_rsp_id_is_available():
    source, catalog, _, ends = make_fixture()
    root, version, _, byid = native.document(source)
    byid[ends['B']].contents[19].value = 2147483646
    source = writer.dump_verified(root, version)
    with pytest.raises(ValueError, match='Insufficient native RSP IDs'):
        edit_structure({'Line': source}, catalog, 'Line', 'create',
                       {**create_spec(ends), 'rsp_id_policy': 'original_first_save'})
    _, legacy = edit_structure({'Line': source}, catalog, 'Line', 'create', create_spec(ends))
    assert legacy['details']['array_id'] == 2147483647


def test_file_save_and_inventory_on_real_filesystem():
    source, catalog, route, ends = make_fixture()
    with TemporaryDirectory(prefix='shunting-edit-', dir=Path(__file__).resolve().parent) as directory:
        data_root = Path(directory)
        project = data_root / 'OTProjects' / 'Line'
        project.mkdir(parents=True)
        output = data_root / 'OTAI' / 'workspaces' / 'Shunting'
        output.mkdir(parents=True)

        def spec_for(path, contents):
            path.write_bytes(contents)
            return {'path': path.relative_to(data_root).as_posix(), 'sha256': sha(contents)}

        doc = spec_for(project / 'Line.opentrack', source)
        other = spec_for(project / 'Other.opentrack', source)
        run = spec_for(project / 'Line.run', b'Infrastructure Document#Line.opentrack#\n'
                      b'Infrastructure Document#Other.opentrack#\nDestInfoFile#Line.dest#\n')
        dest = spec_for(project / 'Line.dest', catalog)
        tools = ShuntingParameterEdits(data_root)
        def request(operation, name, preview_only=True, documents=None):
            return EditShuntingStructure(project_run=run, documents=documents or {'Line': doc, 'Other': other},
                                        target_document='Line', dest_catalog=dest, operation=operation,
                                        preview_only=preview_only, target_path=(output/name).relative_to(data_root).as_posix())

        operation = {'action': 'create', **create_spec(ends)}
        with pytest.raises(APIError) as missing:
            tools.edit_structure(request(operation, 'created.opentrack', documents={'Line': doc}))
        assert missing.value.code == 'DOCUMENT_SCOPE'
        preview = tools.edit_structure(request(operation, 'created.opentrack'))
        assert not preview['saved']
        assert not (output / 'created.opentrack').exists()
        saved = tools.edit_structure(request(operation, 'created.opentrack', False))
        assert saved['saved']
        created = (output / 'created.opentrack').read_bytes()
        assert sha(created) == preview['output_sha256']
        with pytest.raises(APIError) as existing:
            tools.edit_structure(request(operation, 'created.opentrack', False))
        assert existing.value.code == 'TARGET_EXISTS'
        assert (project / 'Line.opentrack').read_bytes() == source
        assert (project / 'Other.opentrack').read_bytes() == source
        native_root, _ = writer.load(created)
        route_factory.document(native_root)
        shunting = core.identity(core.load(created)[3][0][0])
        doc = spec_for(project / 'Line.opentrack', created)
        bound = tools.edit_structure(request({'action': 'bind_overlap', 'route': route, 'shunting': shunting},
                                             'bound.opentrack', False))
        assert bound['saved']
        bound_bytes = (output / 'bound.opentrack').read_bytes()
        bound_route = paths.select(writer.load(bound_bytes)[0], 'OTRoute', **route)
        assert paths.string(bound_route.contents[7].value) == shunting['name']
        doc = spec_for(project / 'Line.opentrack', bound_bytes)
        moved = tools.edit_structure(request({'action': 'replace_movement', 'shunting': shunting,
                                              'end_ids': [ends['B'], ends['D']]}, 'moved.opentrack', False))
        assert moved['saved']
        moved_bytes = (output / 'moved.opentrack').read_bytes()
        assert core.inspect(moved_bytes)['shuntings'][0]['end_ids'] == [ends['B'], ends['D']]
        doc = spec_for(project / 'Line.opentrack', moved_bytes)
        unbound = tools.edit_structure(request({'action': 'unbind_overlap', 'route': route}, 'unbound.opentrack', False))
        assert unbound['saved']
        unbound_bytes = (output / 'unbound.opentrack').read_bytes()
        unbound_route = paths.select(writer.load(unbound_bytes)[0], 'OTRoute', **route)
        assert paths.string(unbound_route.contents[7].value) == ''
        doc = spec_for(project / 'Line.opentrack', unbound_bytes)
        deleted = tools.edit_structure(request({'action': 'delete', 'shunting': shunting}, 'deleted.opentrack', False))
        assert deleted['saved']
        assert not core.inspect((output / 'deleted.opentrack').read_bytes())['shuntings']
        assert (project / 'Line.opentrack').read_bytes() == unbound_bytes
        assert (project / 'Other.opentrack').read_bytes() == source
