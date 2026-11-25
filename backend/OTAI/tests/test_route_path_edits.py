"""Archived-data regression tests using a synthetic four-End movement chain."""

from pathlib import Path
import tempfile
import unittest

from opentrack_ai.current_archive import movement_edits, path_append, path_functions, route_factory, writer
from opentrack_ai.current_archive.movement_edit_tools import EditPath, EditRoute, MovementEdits
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native, topology
from opentrack_ai.errors import APIError


def groups(shape):
    defaults = {'i': 0, 'f': 0.0, '@': None}
    return [(encoding, [defaults[code] for code in encoding]) for encoding in shape]


def fixture(*, referenced=False):
    end_chain = [('OTEndModel', 7), ('OTGraphicModel', 1), ('NSObject', 0)]
    ends = {number: native.obj(end_chain, groups(route_factory.END)) for number in (10, 11, 20, 21, 30, 31, 40, 41)}
    models = list(ends.values())
    safety = native.obj([('OTElement', 0), ('OTGraphicModel', 1), ('NSObject', 0)],
                        groups(['i', 'f', 'f', 'f', 'i', 'i', '@', '@']))
    safety.contents[0].value = 60
    safety.contents[7].value = native.arr(models)
    models.append(safety)
    for number, end in ends.items():
        end.contents[0].value = number
        end.contents[7].value = safety
        end.contents[8].value = number ^ 1
        for slot, kind in ((15, 'OTRouteList'), (16, 'OTShuntingList'), (17, 'OTPathList')):
            end.contents[slot].value = native.wrapped(kind, [])
        end.contents[19].value = -1
    for number, a, b in ((70, 11, 40), (71, 41, 20), (72, 21, 30)):
        edge = native.obj([('OTEdgeModel', 3), ('OTGraphicModel', 1), ('NSObject', 0)], groups(route_factory.EDGE))
        edge.contents[0].value = number
        edge.contents[7].value, edge.contents[8].value = ends[a], ends[b]
        edge.contents[9].values[1] = 500
        ends[a].contents[9].value = ends[b].contents[9].value = edge
        models.append(edge)
    for number in (10, 20, 30):
        signal = native.obj([('OTSignalModel', 11), ('OTGraphicModel', 1), ('NSObject', 0)], groups(route_factory.SIGNAL))
        signal.contents[0].value = number + 80
        signal.contents[7].value = ends[number]
        signal.contents[8].values[0] = 1
        signal.contents[9].values[0] = 2
        ends[number].contents[11].value = signal
        models.append(signal)

    shared_description = native.string('Original')
    route_objects = []
    for name, array_id, nodes in (('A-B', 0, [10, 40, 20]), ('A-B alt', 1, [10, 40, 20]), ('B-C', 0, [20, 30])):
        route = native.obj(path_functions.SHAPES['OTRoute'][0], groups(path_functions.SHAPES['OTRoute'][1]))
        route.contents[0].value = native.arr([ends[number] for number in nodes])
        route.contents[1].value = native.string(name)
        route.contents[2].values[:] = [array_id, nodes[0]]
        route.contents[3].value = shared_description
        signal_indication = native.obj([('OTSigInd', 0), ('NSObject', 0)], [('i', [0]), ('@', [route])])
        route.contents[4].value = native.wrapped('OTSigIndList', [signal_indication])
        route.contents[5].values[:] = [0, 400, 5, 0, -1, 0]
        route.contents[7].value = native.string('')
        route.contents[9].value = -1
        route.contents[10].values[:] = [5000, 0, 0]
        route.contents[11].value = 2
        route.contents[12].values[0] = native.arr([ends[nodes[0]], ends[nodes[-1]]])
        holder = ends[nodes[0]].contents[15].value.contents[0].value
        writer.set_elements(holder, [*writer.elements(holder), route])
        ends[nodes[0]].contents[19].value = array_id
        route_objects.append(route)

    def route_info(route):
        return native.obj([('OTArrayInfo', 0), ('NSObject', 0)],
                          [('@', [route.contents[1].value]), ('ii', list(route.contents[2].values))])

    path = native.obj(path_functions.SHAPES['OTPath'][0], groups(path_functions.SHAPES['OTPath'][1]))
    path.contents[0].value = native.arr([route_objects[0]])
    path.contents[1].value = native.string('A-C')
    path.contents[2].values[:] = [2, 10]
    path.contents[3].value = shared_description
    path.contents[4].value = native.arr([route_info(route_objects[index]) for index in (0, 2)])
    ends[10].contents[17].value = native.wrapped('OTPathList', [path])
    ends[10].contents[19].value = 2
    root = native.obj([('OTDocument', 4), ('NSObject', 0)], groups(topology.DOC_ENC))
    root.contents[2].value = native.arr(models)
    rows = []
    if referenced:
        ext_ref = native.obj([('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)],
                             [('@', [path.contents[1].value]), ('ii', list(path.contents[2].values)),
                              ('@', [native.string('Line')])])
        row = native.obj([('OTDestInfo', 1), ('NSObject', 0)],
                         [('i', [17]), ('@', [native.string('Dependent')]), ('@', [native.string('Line.opentrack')]),
                          ('i', [10]), ('@', [native.arr([ext_ref])])])
        rows.append(row)
    catalog = native.wrapped('OTDestInfoList', rows)
    return writer.dump_verified(root), writer.dump_verified(catalog)


ROUTE_A_B = {'name': 'A-B', 'array_id': 0, 'start_id': 10}
ROUTE_ALTERNATE = {'name': 'A-B alt', 'array_id': 1, 'start_id': 10}
ROUTE_B_C = {'name': 'B-C', 'array_id': 0, 'start_id': 20}
PATH = {'name': 'A-C', 'array_id': 2, 'start_id': 10}


class MovementEditTests(unittest.TestCase):
    def test_existing_route_fields_round_trip_and_preserve_shared_bit_and_description(self):
        data, _ = fixture()
        changed, report = movement_edits.edit_route(data, ROUTE_A_B, {
            'release_time_s': 12, 'reserve_previous': True, 'description': 'New',
            'approach_length_m': 120.125, 'approach_speed_kmh': 45.0, 'release_groups': 'each_end',
        })
        self.assertEqual(report['after']['release_groups'], [10, 40, 20])
        root, _ = writer.load(changed)
        route = path_append.select(root, 'OTRoute', ROUTE_A_B)
        self.assertEqual(route.contents[11].value, 3)
        self.assertEqual(route.contents[5].values[:4], [0, 400, 12, 0])
        self.assertEqual(path_append.select(root, 'OTRoute', ROUTE_ALTERNATE).contents[11].value, 2)
        self.assertEqual(path_functions.info(path_append.select(root, 'OTPath', PATH))['description'], 'Original')
        second, _ = movement_edits.edit_route(changed, ROUTE_A_B, {'approach_speed_kmh': 50})
        self.assertNotEqual(changed, second)

    def test_route_approach_pair_and_path_owner_are_checked(self):
        data, catalog = fixture()
        with self.assertRaisesRegex(ValueError, 'Approach length and speed'):
            movement_edits.edit_route(data, ROUTE_A_B, {'approach_length_m': 20})
        with self.assertRaisesRegex(ValueError, 'different End'):
            movement_edits.edit_path_routes({'Line': data}, 'Line', catalog, PATH, [ROUTE_B_C])
        with self.assertRaisesRegex(ValueError, 'Disconnected'):
            movement_edits.edit_path_routes({'Line': data}, 'Line', catalog, PATH, [ROUTE_A_B, ROUTE_ALTERNATE])

    def test_native_approach_batch_keeps_route_identity_and_supports_both_orders(self):
        data, _ = fixture()
        root, version = writer.load(data)
        first = path_append.select(root, 'OTRoute', ROUTE_A_B)
        alternative = path_append.select(root, 'OTRoute', ROUTE_ALTERNATE)
        last = path_append.select(root, 'OTRoute', ROUTE_B_C)
        first.contents[3].value = native.string('Zulu')
        last.contents[3].value = native.string('Alpha')
        indications = alternative.contents[4].value.contents[0].value
        more = native.obj([('OTSigInd', 0), ('NSObject', 0)], [('i', [1]), ('@', [alternative])])
        writer.set_elements(indications, [*writer.elements(indications), more])
        fixture_data = writer.dump_verified(root, version)
        refs = [ROUTE_A_B, ROUTE_B_C, ROUTE_ALTERNATE]

        unchanged, listing = movement_edits.approach_batch(fixture_data, refs, {}, 'description')
        self.assertEqual(unchanged, fixture_data)
        self.assertEqual([row['identity'] for row in listing['routes']], [ROUTE_B_C, ROUTE_ALTERNATE, ROUTE_A_B])
        saved, receipt = movement_edits.approach_batch(
            fixture_data, refs, {'approach_length_m': 400}, 'number_of_signal_aspects')
        self.assertEqual(receipt['changed_route_count'], 3)
        self.assertEqual(receipt['routes'][0]['identity'], ROUTE_ALTERNATE)
        self.assertTrue(all(row['has_approach_zone'] and row['after']['approach_speed_kmh'] == 0
                            for row in receipt['routes']))
        final, _ = movement_edits.approach_batch(saved, refs[:2], {'approach_speed_kmh': 18}, 'selection')
        result, _ = writer.load(final)
        self.assertEqual(path_append.select(result, 'OTRoute', ROUTE_A_B).contents[8].values, [400.0, 18.0])
        self.assertEqual(path_append.select(result, 'OTRoute', ROUTE_ALTERNATE).contents[8].values, [400.0, 0.0])
        self.assertEqual(path_functions.info(path_append.select(result, 'OTPath', PATH))['saved_references'],
                         [ROUTE_A_B, ROUTE_B_C])
        with self.assertRaisesRegex(ValueError, 'Duplicate Route selection'):
            movement_edits.approach_batch(saved, [ROUTE_A_B, ROUTE_A_B], {'approach_speed_kmh': 18}, 'selection')

    def test_path_replacement_writes_native_first_route_and_infos(self):
        data, catalog = fixture()
        edited, report = movement_edits.edit_path_routes({'Line': data}, 'Line', catalog, PATH, [ROUTE_ALTERNATE], 'Shorter')
        root, _ = writer.load(edited)
        path = path_append.select(root, 'OTPath', PATH)
        first, = path_functions.mutable_array(path.contents[0].value)
        self.assertIs(first, path_append.select(root, 'OTRoute', ROUTE_ALTERNATE))
        self.assertEqual(report['after']['saved_references'], [ROUTE_ALTERNATE])
        self.assertEqual(report['after']['description'], 'Shorter')
        self.assertEqual(report['after_end_ids'], [10, 40, 20])

    def test_dest_catalog_reference_rejects_route_change_even_on_same_ends(self):
        data, catalog = fixture(referenced=True)
        with self.assertRaisesRegex(ValueError, 'DestInfo catalog'):
            movement_edits.edit_path_routes({'Line': data}, 'Line', catalog, PATH, [ROUTE_ALTERNATE])
        with self.assertRaisesRegex(ValueError, 'DestInfo catalog'):
            movement_edits.edit_path_routes({'Line': data}, 'Line', catalog, PATH, [ROUTE_ALTERNATE, ROUTE_B_C])
        _, report = movement_edits.edit_path_description(data, PATH, 'Description only')
        self.assertEqual(report['after']['description'], 'Description only')

    def test_preview_save_no_overwrite_and_stale_source(self):
        data, catalog = fixture()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            project = root / 'OTProjects' / 'Line'
            project.mkdir(parents=True)

            def put(path, content):
                (project / path).write_bytes(content)
                return {'path': f'OTProjects/Line/{path}', 'sha256': sha(content)}

            source = put('Line.opentrack', data)
            dest = put('Line.dest', catalog)
            run = put('Line.run', b'Infrastructure Document#Line.opentrack#\nDestInfoFile#Line.dest#\n')
            service = MovementEdits(root)
            path_args = {'path': PATH, 'operation': {'action': 'replace_routes', 'target_document': 'Line',
                'project_run': run, 'documents': {'Line': source}, 'dest_catalog': dest, 'routes': [ROUTE_ALTERNATE]}}
            preview = service.edit_path(EditPath(**path_args))
            self.assertFalse(preview['saved'])
            args = EditPath(**path_args, preview_only=False, target_path='OTProjects/Line/path-edited.opentrack')
            saved = service.edit_path(args)
            self.assertTrue(saved['saved'])
            self.assertEqual(sha((project / 'path-edited.opentrack').read_bytes()), preview['output_sha256'])
            self.assertEqual((project / 'Line.opentrack').read_bytes(), data)
            self.assertEqual((project / 'Line.dest').read_bytes(), catalog)
            route_args = EditRoute(source=source, route=ROUTE_A_B, changes={'reserve_time_s': 8},
                                   preview_only=False, target_path='OTProjects/Line/route-edited.opentrack')
            route_saved = service.route(route_args)
            self.assertTrue(route_saved['saved'])
            changed_root, _ = writer.load((project / 'route-edited.opentrack').read_bytes())
            saved_route = path_append.select(changed_root, 'OTRoute', ROUTE_A_B)
            self.assertEqual(saved_route.contents[5].values[3], 8)
            self.assertEqual((project / 'Line.opentrack').read_bytes(), data)
            with self.assertRaises(APIError) as error:
                service.route(route_args)
            self.assertEqual(error.exception.code, 'TARGET_EXISTS')
            (project / 'Line.opentrack').write_bytes((project / 'path-edited.opentrack').read_bytes())
            with self.assertRaises(APIError) as error:
                service.route(route_args)
            self.assertEqual(error.exception.code, 'SOURCE_CHANGED')


if __name__ == '__main__':
    unittest.main()
