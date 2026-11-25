"""Verify native Route field writes on both supported SecurityArray layouts."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.route_edit_tools import (
    EditRouteMovement, EditRouteProtection, RouteProtectionEdits, edit_movement, edit_protection,
)
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from test_itinerary_native_edit import schematic_document
from test_route_path_edits import ROUTE_ALTERNATE, ROUTE_A_B, fixture as movement_fixture


TEST_DIRECTORY = Path(__file__).resolve().parent


def fixture(version):
    route_identity, alternate_identity = ROUTE_A_B, ROUTE_ALTERNATE
    document, _ = movement_fixture()
    root, stream_version = writer.load(document)
    alternate = path_functions.select(root, 'OTRoute', **alternate_identity)
    alternate.contents[4].value.contents[0].value.contents[1].value.contents[0].value = 3
    chosen = path_functions.select(root, 'OTRoute', **route_identity)
    chosen.contents[6].values[0] = 8
    if version == 5:
        for route in [obj for obj in writer.objects(root) if writer.kind(obj) == 'OTRoute']:
            route.clazz.superclass.version = 5
            del route.contents[10]
    return writer.dump_verified(root, stream_version), route_identity, alternate_identity


class ProtectionTests(unittest.TestCase):
    def test_native_flags_ordered_groups_zone_and_aspects_roundtrip(self):
        for version in (5, 6):
            with self.subTest(version=version):
                before, identity, other = fixture(version)
                output, report = edit_protection(before, identity, {
                    'allow_occupied_entry': True, 'occupied_entry_use_speed': True,
                    'occupied_entry_speed_kmh': 28.25, 'occupied_entry_wait_s': 3.5,
                    'release_group_end_ids': [10, 40, 20], 'slow_speed_zone_end_ids': [40, 20],
                    'slow_speed_only_for_head': False, 'signal_aspects': [3, 0],
                })
                self.assertTrue(report['after']['discrete_for_moving_block'])
                self.assertEqual(report['after']['signal_aspects'], [3, 0])
                parsed, _ = writer.load(output)
                route = next(obj for obj in writer.objects(parsed) if writer.kind(obj) == 'OTRoute' and
                             path_functions.string(obj.contents[1].value) == identity['name'])
                self.assertEqual(route.clazz.superclass.version, version)
                self.assertEqual(route.contents[6].values, [11, 28.25, 3.5])
                sibling = next(obj for obj in writer.objects(parsed) if writer.kind(obj) == 'OTRoute' and
                               path_functions.string(obj.contents[1].value) == other['name'])
                sibling_indication = writer.elements(sibling.contents[4].value.contents[0].value)[0]
                self.assertEqual(sibling_indication.contents[0].value, 3)
                self.assertIs(sibling_indication.contents[1].value, sibling)
                _, cleared = edit_protection(output, identity, {'clear_slow_speed_zone': True})
                self.assertIsNone(cleared['after']['slow_speed_zone_end_ids'])

    def test_invalid_order_and_foreign_aspect_are_rejected(self):
        data, route, _ = fixture(6)
        with self.assertRaisesRegex(ValueError, 'movement order'):
            edit_protection(data, route, {'slow_speed_zone_end_ids': [20, 10]})
        with self.assertRaisesRegex(ValueError, 'already present'):
            edit_protection(data, route, {'signal_aspects': [99]})
        with self.assertRaisesRegex(ValueError, 'must include'):
            edit_protection(data, route, {'release_group_end_ids': [10, 40]})

    def test_windows_persists_a_fresh_verified_native_file(self):
        contents, route, _ = fixture(6)
        with TemporaryDirectory(dir=TEST_DIRECTORY) as td:
            root = Path(td)
            project = root / 'OTProjects' / 'Line'
            project.mkdir(parents=True)
            source = project / 'original.opentrack'
            source.write_bytes(contents)
            result = RouteProtectionEdits(root).edit(EditRouteProtection(
                source={'path': source.relative_to(root).as_posix(), 'sha256': sha(contents)},
                route=route, changes={'occupied_entry_wait_s': 4.0},
                target_path='OTProjects/Line/edited.opentrack', preview_only=False,
            ))
            self.assertTrue(result['saved'])
            self.assertEqual(sha((project / 'edited.opentrack').read_bytes()), result['output_sha256'])
            self.assertEqual(source.read_bytes(), contents)


class RouteMovementTests(unittest.TestCase):
    def test_reroute_same_signals_and_preserve_native_path_and_itinerary(self):
        line = generate.spec()
        line['vertices'] = [generate.vertex(name, number * 100) for number, name in enumerate('ABCD')]
        template = line['edges'][0]
        line['edges'] = [{**template, 'key': start + end, 'from': [start, 1], 'to': [end, 0]}
                         for start, end in ('AB', 'BC', 'AD', 'DC')]
        data, ids = schematic_document(line, [('A', 0), ('C', 0)])
        start, end = ids['A'][0], ids['C'][0]
        data, built = native.build_route(data, name='Via-B', end_ids=[start, ids['B'][0], end],
                                         description='', release_groups='global', reserve_previous=False)
        reference = dict(name='Via-B', array_id=built['array_id'], start_id=start)
        catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))

        def bindings(documents):
            return {'document_paths': {'Line': 'Line.opentrack'}, 'complete_document_set': True,
                    'expected_hashes': {**{name: sha(blob) for name, blob in documents.items()},
                                        '$dest_catalog': sha(catalog)}}

        documents = {'Line': data}
        documents, path_receipt = operations.create_path(documents, catalog, **bindings(documents),
            name='TrainPath', routes=[{'document': 'Line', **reference}])
        project, _ = operations.create_itinerary(documents, catalog, **bindings(documents), name='TrainItinerary',
                                                  paths=[path_receipt['created']])
        documents, catalog = project['documents'], project['catalog']
        alternative = [start, ids['D'][0], end]
        with self.assertRaisesRegex(ValueError, 'two directional'):
            edit_movement(documents, {'Line': 'Line.opentrack'}, catalog, 'Line', reference, [start, ids['D'][0]],
                          [start, ids['D'][0]])
        with TemporaryDirectory(dir=TEST_DIRECTORY) as td:
            root = Path(td)
            folder = root / 'OTProjects' / 'Route'
            folder.mkdir(parents=True)

            def write(name, data):
                source = folder / name
                source.write_bytes(data)
                return {'path': source.relative_to(root).as_posix(), 'sha256': sha(data)}

            result = RouteProtectionEdits(root).movement(EditRouteMovement(
                project_run=write('Line.run', b'Infrastructure Document#Line.opentrack#\nDestInfoFile#Line.dest#\n'),
                dest_catalog=write('Line.dest', catalog), documents={'Line': write('Line.opentrack', documents['Line'])},
                target_document='Line', route=reference, end_ids=alternative, release_group_end_ids=[start, end],
                target_path='OTProjects/Route/changed.opentrack', preview_only=False,
            ))
            self.assertTrue(result['saved'])
            self.assertEqual(result['change_report']['affected']['itineraries'], ['TrainItinerary'])
            self.assertEqual(result['change_report']['affected']['paths'][0]['name'], 'TrainPath')
            self.assertEqual((folder / 'Line.opentrack').read_bytes(), documents['Line'])
            self.assertEqual((folder / 'Line.dest').read_bytes(), catalog)
