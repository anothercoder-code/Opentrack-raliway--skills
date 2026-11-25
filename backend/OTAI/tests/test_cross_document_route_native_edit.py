"""Exercise saved cross-document Route ownership, dependencies and Windows publication."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.movement_edits import _movement_project
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.native_join_entry_mode import EditNativeJoinEntryMode, set_entry_mode
from opentrack_ai.current_archive.route_edit_tools import (
    EditCrossDocumentRoute, RouteProtectionEdits, edit_cross_document_movement,
)
from opentrack_ai.current_archive.route_factory import document, wrapper
from opentrack_ai.current_archive.signal_operating_fields import append_route_aspects
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document


REFERENCE = {'name': 'R:A-B', 'array_id': 0, 'start_id': 0}
NATIVE_PATHS = {name: f'{name}.opentrack' for name in ('A', 'B')}


def fixture():
    docs = {}
    for name in NATIVE_PATHS:
        spec = generate.spec()
        extra = generate.vertex('extra', 130)
        extra['y'] += 45
        spec['vertices'].append(extra)
        left, right = ('left', 'extra') if name == 'A' else ('extra', 'right')
        spec['edges'].append({**spec['edges'][0], 'key': 'alternate',
                              'from': [left, 1], 'to': [right, 0], 'length_m': 1800})
        signal_side = 'left' if name == 'A' else 'right'
        docs[name], _ = schematic_document(spec, [(signal_side, 0), (signal_side, 1)])
    docs, catalog, _ = generate.make_pair(docs, NATIVE_PATHS)
    for name, connector, other, target in (('A', 9, 'B', 8), ('B', 8, 'A', 9)):
        root, version = writer.load_next_compatible(docs[name])
        _, by_id = document(root)
        obj = by_id[connector]
        obj.clazz = writer.Class(b'OTConnModel', 1, obj.clazz)
        obj.contents += [writer.TypedValue(b'@', native.string('')), writer.TypedValue(b'@', native.string(other)),
                         writer.TypedValue(b'i', target), writer.TypedValue(b'i', 0)]
        docs[name] = writer.dump_verified(root, version)
    return docs, catalog


class CrossDocumentRouteTests(unittest.TestCase):
    def test_timed_occupied_entry_preserves_the_moving_block_flag_and_requires_both_parts(self):
        docs, catalog = fixture()
        project = _movement_project(docs, NATIVE_PATHS, catalog)
        identity = tuple(REFERENCE[k] for k in ('name', 'array_id', 'start_id'))
        primary = project.owned(('A', 0), 'OTRoute', identity)
        fragment = project.owned(('B', 0), 'OTRoute', identity)
        signal = project.model(('A', 0)).contents[11].value
        signal.contents[9].values[2] |= 1
        primary.contents[6].values[:] = [11, 20.0, 0.0]
        fragment.contents[6].values[:] = [3, 20.0, 0.0]
        arguments = {
            'source_project': {'project_directory': 'OTProjects/Line', 'execution_root': 'D:/Line',
                               'run_file': 'line.run', 'files': {'line.run': '0' * 64},
                               'complete_project_inventory': True},
            'document': 'A', 'route': REFERENCE, 'expected_signal_id': signal.contents[0].value,
            'expected_primary': {'flags': 11, 'speed_kmh': 20, 'wait_s': 0},
            'expected_continuation': {'flags': 3, 'speed_kmh': 20, 'wait_s': 0},
            'setting': {'mode': 'stop_and_wait', 'wait_s': 45},
        }
        with self.assertRaisesRegex(ValueError, 'receiving fragment'):
            set_entry_mode(project, EditNativeJoinEntryMode(**{**arguments, 'expected_continuation': None}))
        outputs, parts = set_entry_mode(project, EditNativeJoinEntryMode(**arguments))
        self.assertEqual(parts, [(('A', 0), [15, 0.0, 45.0]), (('B', 0), [7, 0.0, 45.0])])
        loaded = _movement_project(outputs, NATIVE_PATHS, catalog)
        for owner, expected in parts:
            self.assertEqual(loaded.owned(owner, 'OTRoute', identity).contents[6].values, expected)
        self.assertEqual(primary.contents[6].values, [11, 20.0, 0.0])
        self.assertEqual(fragment.contents[6].values, [3, 20.0, 0.0])

    def test_move_continuation_to_another_connector_within_the_same_document(self):
        docs, catalog = fixture()
        output, report = edit_cross_document_movement(docs, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [4])
        self.assertEqual(report['old_connector_pair'], [('A', 5), ('B', 0)])
        self.assertEqual(report['new_connector_pair'], [('A', 9), ('B', 8)])
        self.assertEqual(report['affected']['itineraries'], ['I:A-B'])
        self.assertEqual(report['affected']['paths'][0]['name'], 'P:A-B')
        project = _movement_project(output, NATIVE_PATHS, catalog)
        identity = tuple(REFERENCE[k] for k in ('name', 'array_id', 'start_id'))
        primary = project.owned(('A', 0), 'OTRoute', identity)
        continuation = project.owned(('B', 8), 'OTRoute', identity)
        self.assertEqual(project.route_view(primary), [('A', 0), ('A', 8), ('B', 4)])
        self.assertEqual(project.route_view(continuation), [('B', 4)])
        self.assertEqual(primary.contents[5].values[4], 2)
        self.assertEqual(continuation.contents[5].values[4], -1)
        with self.assertRaisesRegex(ValueError, 'Unresolved exact OTRoute'):
            project.owned(('B', 0), 'OTRoute', identity)

    def test_reject_dangling_connector_endpoint_or_unordered_release(self):
        docs, catalog = fixture()
        with self.assertRaisesRegex(ValueError, 'two directional main-signal Ends'):
            edit_cross_document_movement(docs, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [9])
        with self.assertRaisesRegex(ValueError, 'movement order'):
            edit_cross_document_movement(docs, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [4], [8, 0])
        with self.assertRaisesRegex(ValueError, 'Connector expected'):
            edit_cross_document_movement(docs, NATIVE_PATHS, catalog, 'A', REFERENCE, [0], [4])

    def test_write_and_clear_one_slow_zone_split_across_saved_fragments(self):
        docs, catalog = fixture()
        endpoints = [{'document': 'A', 'end_id': 8}, {'document': 'B', 'end_id': 4}]
        output, report = edit_cross_document_movement(docs, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [4],
                                                      slow_speed_zone_ends=endpoints)
        self.assertEqual(report['slow_speed_zone_fragment_end_ids'], {'A': [8, 8], 'B': [None, 4]})
        opposite = endpoints[::-1]
        with self.assertRaisesRegex(ValueError, 'must run forward'):
            edit_cross_document_movement(output, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [4],
                                         slow_speed_zone_ends=opposite)
        _, kept = edit_cross_document_movement(output, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [4])
        self.assertEqual(kept['slow_speed_zone_fragment_end_ids'], report['slow_speed_zone_fragment_end_ids'])
        _, cleared = edit_cross_document_movement(output, NATIVE_PATHS, catalog, 'A', REFERENCE, [0, 8], [4],
                                                  slow_speed_zone_ends=[])
        self.assertEqual(cleared['slow_speed_zone_fragment_end_ids'], {'A': [None, None], 'B': [None, None]})

    def test_replace_only_primary_indication_shared_with_actual_start_signal(self):
        docs, catalog = fixture()
        additions, _ = append_route_aspects(docs, NATIVE_PATHS, catalog, [('A', 0)],
                                           [{'start_end': ['A', 0], 'speeds_kmh': [40]}])
        docs.update(additions)
        project = _movement_project(docs, NATIVE_PATHS, catalog)
        identity = tuple(REFERENCE[k] for k in ('name', 'array_id', 'start_id'))
        primary = project.owned(('A', 0), 'OTRoute', identity)
        old_nodes = project.route_view(primary)
        left, right = [[end for document_name, end in old_nodes if document_name == name] for name in ('A', 'B')]
        output, result = edit_cross_document_movement(docs, NATIVE_PATHS, catalog, 'A', REFERENCE, left, right,
                                                      signal_aspects=[4])
        self.assertEqual(result['primary_signal_aspects'], {'before': [0, 4], 'after': [4]})
        self.assertEqual(result['continuation_signal_aspects'], [])
        saved = _movement_project(output, NATIVE_PATHS, catalog)
        self.assertEqual(saved.route_view(saved.owned(('A', 0), 'OTRoute', identity)), old_nodes)
        self.assertEqual(writer.fingerprint(saved.roots['B']), writer.fingerprint(project.roots['B']))
        signal = saved.model(('A', 0)).contents[11].value
        self.assertEqual([row.contents[0].value for row in wrapper(signal.contents[10].value, 'OTSigIndList')], [0, 4])
        self.assertEqual([row.contents[0].value for row in wrapper(primary.contents[4].value, 'OTSigIndList')], [0, 4])

        # A code on a Route alone is insufficient when the physical starting
        # signal does not actually offer it.
        signal_rows = signal.contents[10].value.contents[0].value
        writer.set_elements(signal_rows, writer.elements(signal_rows)[:1])
        mismatch = {**docs, 'A': writer.dump_verified(saved.roots['A'], saved.versions['A'])}
        with self.assertRaisesRegex(ValueError, 'already present at this main signal'):
            edit_cross_document_movement(mismatch, NATIVE_PATHS, catalog, 'A', REFERENCE, left, right, signal_aspects=[4])

    def test_save_pair_does_not_modify_or_overwrite(self):
        docs, catalog = fixture()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'OTProjects' / 'Route'
            destination = root / 'OTAI/workspaces/Fixture'
            source.mkdir(parents=True)
            destination.mkdir(parents=True)

            def write(file, contents):
                file.write_bytes(contents)
                return {'path': file.relative_to(root).as_posix(), 'sha256': sha(contents)}

            kwargs = {
                'project_run': write(source / 'test.run',
                    b'Infrastructure Document#A.opentrack#\nInfrastructure Document#B.opentrack#\nDestInfoFile#Line.dest#\n'),
                'documents': {name: write(source / filename, docs[name]) for name, filename in NATIVE_PATHS.items()},
                'dest_catalog': write(source / 'Line.dest', catalog),
                'target_document': 'A', 'route': REFERENCE, 'primary_end_ids': [0, 8], 'continuation_end_ids': [4],
                'target_directory': 'OTAI/workspaces/Fixture/Pair',
            }
            service = RouteProtectionEdits(root)
            preview = service.cross_document_movement(EditCrossDocumentRoute(**kwargs))
            self.assertFalse(preview['saved'])
            args = EditCrossDocumentRoute(**kwargs, preview_only=False)
            self.assertTrue(service.cross_document_movement(args)['post_commit_verified'])
            for name, filename in NATIVE_PATHS.items():
                data = (destination / 'Pair' / filename).read_bytes()
                self.assertEqual(sha(data), preview['manifest']['files'][filename]['sha256'])
                self.assertEqual((source / filename).read_bytes(), docs[name])
            self.assertEqual((source / 'Line.dest').read_bytes(), catalog)
            with self.assertRaises(APIError) as repeated:
                service.cross_document_movement(args)
            self.assertEqual(repeated.exception.code, 'TARGET_EXISTS')
            (source / 'B.opentrack').write_bytes(docs['A'])
            with self.assertRaises(APIError) as stale:
                service.cross_document_movement(args)
            self.assertEqual(stale.exception.code, 'SOURCE_CHANGED')
