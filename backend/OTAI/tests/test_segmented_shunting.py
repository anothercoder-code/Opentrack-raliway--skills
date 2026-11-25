"""Native automatic Shunting Paths in a cross-document Itinerary."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.itinerary_edit_tools import _project
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.segmented_shunting_tools import (
    EditSegmentedShunting, SegmentedShuntingTools, _match_boundaries, edit_segmented,
)
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes
from opentrack_ai.errors import APIError
from test_itinerary_native_edit import schematic_document


def pair_fixture(document_paths):
    source_documents = {}
    for key, pair, signals in [('A', ('side', 'left'), [('left', 0), ('left', 1), ('side', 0)]),
                               ('B', ('right', 'side'), [('right', 0), ('right', 1), ('side', 0)])]:
        spec = generate.spec()
        spec['vertices'].append(generate.vertex('side', 450))
        left, right = pair
        spec['edges'].append({**spec['edges'][0], 'key': key + 'side', 'from': [left, 1], 'to': [right, 0]})
        source_documents[key], _ = schematic_document(spec, signals)
    return generate.make_pair(source_documents, document_paths)[:2]


class SegmentedShuntingTest(unittest.TestCase):
    def test_three_boundary_receipt_requires_exact_order_and_intervening_shunting(self):
        crossings = [(('A', 8), ('B', 4), 0), (('B', 8), ('C', 4), 2), (('C', 8), ('D', 4), 2)]
        connectors = [(('A', 9), ('B', 0)), (('B', 9), ('C', 0)), (('C', 9), ('D', 0))]
        expected = [{'source_connector': a, 'receiving_connector': b} for a, b in connectors]
        related, block, actual = {}, {}, {}
        for (start, end, _), (local, remote) in zip(crossings, connectors, strict=True):
            related[start], related[remote] = local, (end[0], 1)
            block[local], block[remote] = remote, local
            actual[start] = related[remote]
        connector = native_signal_routes.obj([('OTConnModel', 1), ('NSObject', 0)], [])
        geometry = SimpleNamespace(related=related.__getitem__, block_end=block.__getitem__,
                                   actual_related=actual.__getitem__, model=lambda key: connector,
                                   edge_between=lambda a, b: (b[0], b[1] + 100))
        nodes = [end for start, finish, _ in crossings for end in (start, finish)]
        refs = ['First native Path', 'Local shunting', 'Remaining native Path']
        kinds = ['path', 'shunting', 'path']
        matches = _match_boundaries(geometry, nodes, refs, kinds, crossings, expected)
        self.assertEqual([row['receiving_connector'] for row in matches], [('B', 0), ('C', 0), ('D', 0)])
        self.assertEqual([row['crossing_path'] for row in matches], [refs[0], refs[2], refs[2]])
        with self.assertRaisesRegex(ValueError, 'Actual directed connector pair differs'):
            _match_boundaries(geometry, nodes, refs, kinds, crossings, expected[::-1])
        with self.assertRaisesRegex(ValueError, 'number of declared'):
            _match_boundaries(geometry, nodes, refs, kinds, crossings, expected[:2])
        with self.assertRaisesRegex(ValueError, 'local Shunting Path between'):
            _match_boundaries(geometry, nodes, refs, ['shunting', 'path', 'path'], crossings, expected)

    def test_named_rebind_builds_crossing_path_and_preserves_walk(self):
        paths = {'A': 'A.opentrack', 'B': 'B.opentrack'}
        docs, catalog = pair_fixture(paths)
        bridge = {'kind': 'path', 'document': 'A', 'name': 'P:A-B', 'start_id': 0, 'array_id': 1}
        left = {'kind': 'create_shunting', 'document': 'A', 'name': 'BeforeLink', 'description': '',
                'end_ids': [8, 0], 'speed_kmh': 17, 'release_time_s': 2, 'reservation_time_s': 1}
        right = {**left, 'document': 'B', 'name': 'AfterLink', 'end_ids': [4, 8]}
        docs, catalog, first = edit_segmented(docs, paths, catalog, 'Segmented', [left, bridge, right],
                                              'create_itinerary')
        project = _project(docs, paths, catalog)
        ordinary = project.owned(('A', 0), 'OTPath', ('P:A-B', 1, 0))
        route_doc, route = project.path_view(ordinary)[1][0]
        requests = [{'kind': kind, **ref} for kind, ref in zip(first['segment_kinds'], first['ordered_paths'], strict=True)]
        requests[1] = {'kind': 'create_crossing_path', 'document': route_doc, 'path_name': 'Dedicated crossing', **route}
        local = project.related(('A', 4))
        remote = project.block_end(local)
        boundary = {'source_connector': local, 'receiving_connector': remote}
        updated, new_catalog, result = edit_segmented(docs, paths, catalog, 'Segmented', requests, 'replace_paths',
                                                       boundaries=[boundary])
        self.assertEqual(result['runtime_end_keys'], first['runtime_end_keys'])
        self.assertEqual(result['directed_boundary']['crossing_path']['name'], 'Dedicated crossing')
        self.assertEqual(result['directed_boundary']['source_connector'], local)
        self.assertEqual(result['directed_boundary']['receiving_connector'], remote)
        self.assertEqual([row['speed_kmh'] for row in result['shunting_controls']], [17, 17])
        checked = _project(updated, paths, new_catalog)
        self.assertEqual(checked.path_view(checked.owned(('A', 0), 'OTPath', ('P:A-B', 1, 0)))[1],
                         project.path_view(ordinary)[1])
        with self.assertRaisesRegex(ValueError, 'Actual directed connector pair differs'):
            edit_segmented(docs, paths, catalog, 'Segmented', requests, 'replace_paths',
                           boundaries=[{'source_connector': remote, 'receiving_connector': local}])

    def test_save_new_and_replace_existing_over_connected_documents(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            project = root / 'OTProjects/source'
            project.mkdir(parents=True)
            (root / 'OTProjects/edited').mkdir()
            doc_names = {'A': 'A.opentrack', 'B': 'B.opentrack'}
            documents, catalog = pair_fixture(doc_names)

            def put(file, data):
                (project / file).write_bytes(data)
                return {'path': 'OTProjects/source/' + file, 'sha256': sha(data)}

            source = {key: put(doc_names[key], data) for key, data in documents.items()}
            run = put('pair.run', b'Infrastructure Document#A.opentrack#\nInfrastructure Document#B.opentrack#\nDestInfoFile#pair.dest#\n')
            dest = put('pair.dest', catalog)
            left = {'kind': 'create_shunting', 'document': 'A', 'name': 'BeforeLink', 'end_ids': [8, 0],
                    'speed_kmh': 17, 'release_time_s': 2, 'reservation_time_s': 1}
            right = {**left, 'document': 'B', 'name': 'AfterLink', 'end_ids': [4, 8], 'speed_kmh': 13,
                     'rsp_id_policy': 'original_first_save'}
            connection = {'kind': 'path', 'document': 'A', 'name': 'P:A-B', 'start_id': 0, 'array_id': 1}
            common = {'project_run': run, 'documents': source, 'catalog': dest, 'name': 'Segmented'}
            request = {**common, 'action': 'create_itinerary', 'paths': [left, connection, right],
                       'target_directory': 'OTProjects/edited/pair', 'preview_only': False}
            service = SegmentedShuntingTools(root)
            with self.assertRaisesRegex(APIError, 'join at the same directional End'):
                service.edit(EditSegmentedShunting(**{**request, 'paths': [connection, left]}))
            self.assertFalse((root / request['target_directory']).exists())
            result = service.edit(EditSegmentedShunting(**request))
            self.assertTrue(result['saved'])
            self.assertEqual(result['change_report']['segment_kinds'], ['shunting', 'path', 'shunting'])
            output = root / request['target_directory']
            changed = {key: (output / name).read_bytes() for key, name in doc_names.items()}
            changed_catalog = (output / 'pair.dest').read_bytes()
            self.assertEqual((project / 'A.opentrack').read_bytes(), documents['A'])
            self.assertEqual((project / 'B.opentrack').read_bytes(), documents['B'])
            verified = _project(changed, doc_names, changed_catalog)
            allocation, = result['change_report']['created_shunting_rsp_allocations']
            owner = verified.model(('B', 4))
            self.assertEqual(owner.contents[19].value, allocation['saved_highest_rsp_id'])
            self.assertEqual(allocation['editor_copy_rsp_id'], allocation['previous_highest_rsp_id'] + 1)
            right_path, = route_factory.wrapper(owner.contents[16].value, 'OTShuntingList')
            self.assertEqual(right_path.contents[2].values, [allocation['previous_highest_rsp_id'] + 2, 4])
            right_body, = path_functions.mutable_array(right_path.contents[0].value)
            right_ref, = path_functions.mutable_array(right_path.contents[4].value)
            self.assertEqual(right_body.contents[2].values, [-1, -1])
            self.assertEqual(right_ref.contents[1].values, [-1, -1])
            itinerary = next(row for row in verified.dests if path_functions.info(row)['name'] == 'Segmented')
            self.assertEqual(verified.dest_view(itinerary)[0], [('A', 8), ('A', 0), ('A', 4), ('B', 4), ('B', 8)])
            embedded = path_functions.mutable_array(itinerary.contents[0].value)[0]
            self.assertIs(embedded, route_factory.wrapper(verified.model(('A', 8)).contents[16].value, 'OTShuntingList')[0])
            self.assertEqual(writer.kind(path_functions.mutable_array(embedded.contents[0].value)[0]), 'OTShunting')
            self.assertFalse(result['change_report']['single_cross_document_shunting_record'])
            with self.assertRaises(APIError) as exists:
                service.edit(EditSegmentedShunting(**request))
            self.assertEqual(exists.exception.code, 'TARGET_EXISTS')

            new_sources = {key: put(doc_names[key], data) for key, data in changed.items()}
            new_dest = put('pair.dest', changed_catalog)
            existing = [{'kind': kind, **ref} for kind, ref in zip(result['change_report']['segment_kinds'],
                                                                    result['change_report']['ordered_paths'])]
            replace = {**request, 'action': 'replace_paths', 'documents': new_sources, 'catalog': new_dest,
                       'paths': existing, 'description': 'Edited local shunting itinerary',
                       'target_directory': 'OTProjects/edited/new'}
            replaced = service.edit(EditSegmentedShunting(**replace))
            self.assertTrue(replaced['saved'])
            self.assertEqual(replaced['change_report']['after']['description'], replace['description'])
            self.assertEqual(set(replaced['manifest']['files']), {'A.opentrack', 'pair.dest'})
