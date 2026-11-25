"""Synthetic native-format fixtures for current Itinerary save and reload."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.current_shunting_workflow import core as shunting
from opentrack_ai.current_archive.finite_itinerary_workflow import FiniteItineraryProject
from opentrack_ai.current_archive.itinerary_edit_tools import (
    EditItinerary, EditableItineraryProject, ItineraryEditTools, replace_paths, set_safety_margins,
)
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native, topology
from opentrack_ai.errors import APIError


def schematic_document(line, signal_ends):
    shell_groups = {
        0: [17], 2: [native.arr()], 5: [generate.wrapped('OTMutableArray', [])],
        12: [generate.wrapped('OTOccInfoList', [])],
        **{index: [native.string('')] for index in (17, 18, 19, 20)},
    }
    shell = native.obj([('OTDocument', 4), ('NSObject', 0)], [
        (encoding, shell_groups.get(index, [{'@': None, 'f': 0.0, 'i': 0}[code] for code in encoding]))
        for index, encoding in enumerate(topology.DOC_ENC)
    ])
    prototypes = [native.arr(), native.string(''),
                  native.obj([('NSMutableDictionary', 0), ('NSDictionary', 0), ('NSObject', 0)], [('i', [0])])]
    for name, (version, groups, graphic, mutable) in topology.CLASS_SHAPES.items():
        chain = [(name, version)]
        if graphic:
            chain.append(('OTGraphicModel', 1))
        if mutable:
            chain.append(('OTMutableArray', 0))
        chain.append(('NSObject', 0))
        prototypes.append(native.obj(chain, [(encoding, [None if code == '@' else 0 for code in encoding])
                                            for encoding in groups]))
    document, report = topology.generate_network(writer.dump_verified(shell), writer.dump_verified(native.arr(prototypes)), line)
    for index, (vertex_name, half) in enumerate(signal_ends):
        end_id = report['vertex_end_ids'][vertex_name][half]
        root, _ = writer.load(document)
        models, by_id = route_factory.document(root)
        document, _ = native.build_main_signal(
            document, end_id=end_id, name=f'S{index}', model_id=max(m.contents[0].value for m in models) + 1,
            placement=generate.signal_placement(by_id[end_id], index * 100, 10), sight_m=300,
            delay_s=0.0, show_symbol=True, show_icon=True,
        )
    return document, report['vertex_end_ids']


def fixture(document_path):
    line = generate.spec()
    line['vertices'] = [generate.vertex(name, i * 100) for i, name in enumerate('ABCD')]
    edge = line['edges'][0]
    line['edges'] = [{**edge, 'key': start + stop, 'from': [start, 1], 'to': [stop, 0]}
                     for start, stop in ('AB', 'BC', 'CD')]
    document, vertex_ids = schematic_document(line, [(key, 0) for key in 'ABC'])
    ids = [vertex_ids[name][0] for name in 'ABC']
    route_refs = []
    for index, (first, last) in enumerate(zip(ids, ids[1:])):
        name = f'R{index}'
        document, receipt = native.build_route(document, name=name, end_ids=[first, last], description='',
                                               release_groups='global', reserve_previous=False)
        route_refs.append(dict(document='Line', name=name, array_id=receipt['array_id'], start_id=first))
    document_paths = {'Line': document_path}
    documents = {'Line': document}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    path_refs = []

    def dependencies():
        return {'document_paths': document_paths, 'complete_document_set': True,
                'expected_hashes': {**{name: sha(data) for name, data in documents.items()},
                                    '$dest_catalog': sha(catalog)}}

    for name, refs in [('First', route_refs[:1]), ('Last', route_refs[1:]), ('Through', route_refs)]:
        documents, receipt = operations.create_path(documents, catalog, name=name, routes=refs, **dependencies())
        path_refs.append(receipt['created'])
    output, _ = operations.create_itinerary(documents, catalog, name='Service', paths=path_refs[:2], **dependencies())
    return output['documents'], output['catalog'], document_paths, path_refs


def with_margin(document):
    root, version = writer.load(document)
    itinerary = path_functions.select(root, 'OTDest', 'Service')
    margin = native.obj([('OTSafetyMargin', 0), ('NSObject', 0)], [('ff', [100.0, 5.0])])
    writer.set_elements(itinerary.contents[5].value.contents[0].value, [margin])
    return writer.dump_verified(root, version)


def with_overlap(document):
    root, _ = writer.load(document)
    route = path_functions.select(root, 'OTRoute', 'R1')
    start = path_functions.mutable_array(route.contents[0].value)[-1]
    _, by_id = route_factory.document(root)
    related = by_id[start.contents[8].value]
    ends = related.contents[9].value.contents[7:9]
    terminal, = [slot.value for slot in ends if slot.value is not related]
    new, receipt = shunting.create(document, dict(name='S:C-D', description='Stored overlap',
        end_ids=[start.contents[0].value, terminal.contents[0].value], speed_kmh=40.0,
        release_time_s=3, reservation_time_s=2))
    return shunting.bind_overlap(new, generate.ref(route),
                                 {k: receipt['details'][k] for k in ('name', 'array_id', 'start_id')})[0]


class ItineraryNativeEditTest(unittest.TestCase):
    def test_valid_structural_edit_updates_both_native_roots(self):
        docs, catalog, names, references = fixture('OTDocuments/Line.opentrack')
        docs['Line'] = with_margin(docs['Line'])
        edited_doc, edited_catalog, report = replace_paths(docs, catalog, names, 'Service', references[2:], 'Direct')
        self.assertNotEqual(docs['Line'], edited_doc)
        self.assertNotEqual(catalog, edited_catalog)
        self.assertEqual(report['after']['description'], 'Direct')
        self.assertEqual(report['after']['saved_references'], references[2:])
        project = FiniteItineraryProject({'Line': edited_doc}, document_paths=names,
                                         expected_hashes={'Line': sha(edited_doc)}, complete_document_set=True)
        self.assertEqual(project.check_dest_catalog(edited_catalog), 1)
        self.assertEqual(path_functions.info(project.dests[0])['persisted_object_count'], 1)
        margins = route_factory.wrapper(project.dests[0].contents[5].value, 'OTSafetyMarginArray')
        self.assertEqual(margins[0].contents[0].values, [100.0, 5.0])

    def test_known_shunting_and_overlap_preserved_by_structural_edit(self):
        docs, catalog, names, references = fixture('OTDocuments/Line.opentrack')
        docs['Line'] = with_overlap(docs['Line'])
        init = {'document_paths': names, 'expected_hashes': {'Line': sha(docs['Line'])}, 'complete_document_set': True}
        with self.assertRaisesRegex(ValueError, 'Nonempty ShuntingList'):
            FiniteItineraryProject(docs, **init)
        before = EditableItineraryProject(docs, **init)
        edited, new_catalog, report = replace_paths(docs, catalog, names, 'Service', references[2:])
        after = EditableItineraryProject({'Line': edited}, **{**init, 'expected_hashes': {'Line': sha(edited)}})
        self.assertEqual(after.check_dest_catalog(new_catalog), 1)
        self.assertEqual(before.shunting_movements, after.shunting_movements)
        self.assertEqual(shunting.inspect(docs['Line'])['shuntings'], shunting.inspect(edited)['shuntings'])
        for source in (docs['Line'], edited):
            root, _ = writer.load(source)
            route = path_functions.select(root, 'OTRoute', 'R1')
            self.assertEqual(path_functions.string(route.contents[7].value), 'S:C-D')
        self.assertEqual(report['after']['saved_references'], references[2:])
        root, version = writer.load(docs['Line'])
        route = path_functions.select(root, 'OTRoute', 'R1')
        route.contents[9].value = -1
        with_fallback = writer.dump_verified(root, version)
        _, _, fallback_report = replace_paths({'Line': with_fallback}, catalog, names, 'Service', references[2:])
        self.assertEqual(fallback_report['after']['saved_references'], references[2:])
        route.contents[7].value = native.string('Absent shunting')
        with self.assertRaisesRegex(ValueError, 'Unresolved exact Route Overlap'):
            replace_paths({'Line': writer.dump_verified(root, version)}, catalog, names, 'Service', references[2:])

    def test_safety_margin_rows_use_native_float32_and_keep_duplicate_order(self):
        docs, _, _, _ = fixture('OTDocuments/Line.opentrack')
        original = with_margin(docs['Line'])
        rows = [{'position_m': 100.1, 'safety_margin_m': 10}, {'position_m': 100.1, 'safety_margin_m': 20}]
        output, report = set_safety_margins(original, 'Service', rows)
        self.assertEqual(report['before'], [{'position_m': 100.0, 'safety_margin_m': 5.0}])
        self.assertAlmostEqual(report['after'][0]['position_m'], 100.1, places=4)
        self.assertEqual([r['safety_margin_m'] for r in report['after']], [10.0, 20.0])
        cleared, report = set_safety_margins(output, 'Service', [])
        self.assertEqual(report['after'], [])
        self.assertEqual(path_functions.inspect_archive(cleared, 'OTDest', 'Service'),
                         path_functions.inspect_archive(original, 'OTDest', 'Service'))
        with self.assertRaisesRegex(ValueError, 'nondecreasing'):
            set_safety_margins(original, 'Service', [rows[0], {**rows[1], 'position_m': 99}])

    def test_two_document_route_continuation_is_preserved(self):
        names = {key: f'OTDocuments/{key}.opentrack' for key in 'AB'}
        documents, catalog, _ = generate.make_pair({
            'A': schematic_document(generate.spec(), [('left', 0), ('left', 1)])[0],
            'B': schematic_document(generate.spec(), [('right', 0), ('right', 1)])[0],
        }, names)
        documents, candidate = operations.create_path(
            documents, catalog, document_paths=names,
            expected_hashes={**{key: sha(blob) for key, blob in documents.items()}, '$dest_catalog': sha(catalog)},
            complete_document_set=True, name='Alternate-A-B',
            routes=[{'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 0}],
        )
        edited_owner, edited_catalog, report = replace_paths(documents, catalog, names, 'I:A-B', [candidate['created']])
        edited = {**documents, 'A': edited_owner}
        project = FiniteItineraryProject(edited, document_paths=names,
                                         expected_hashes={key: sha(blob) for key, blob in edited.items()},
                                         complete_document_set=True)
        self.assertEqual(project.check_dest_catalog(edited_catalog), 2)
        self.assertEqual(report['owner_document'], 'A')
        self.assertEqual(report['after']['saved_references'], [candidate['created']])
        chosen = next(row for row in project.report()['itineraries'] if row['name'] == 'I:A-B')
        self.assertEqual(chosen['runtime_end_keys'], [('A', 0), ('A', 4), ('B', 4)])
        self.assertFalse(report['running_time_revalidation_required'])

    def test_path_start_end_and_identity_must_match(self):
        docs, catalog, names, references = fixture('OTDocuments/Line.opentrack')
        with self.assertRaisesRegex(ValueError, 'last directional End'):
            replace_paths(docs, catalog, names, 'Service', references[:1])
        with self.assertRaisesRegex(ValueError, 'exact directional End'):
            replace_paths(docs, catalog, names, 'Service', references[1:2])
        wrong = deepcopy(references[2:])
        wrong[0]['array_id'] += 20
        with self.assertRaisesRegex(ValueError, 'Unresolved exact OTPath'):
            replace_paths(docs, catalog, names, 'Service', wrong)

    def test_publication_and_refusal_to_overwrite(self):
        docs, catalog, _, references = fixture('OTDocuments/Line.opentrack')
        docs['Line'] = with_overlap(docs['Line'])
        with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            project = root / 'OTProjects' / 'Fixture'
            project.mkdir(parents=True)
            (project / 'OTDocuments').mkdir()
            (project / 'OTData').mkdir()
            (root / 'OTAI' / 'workspaces' / 'Edit').mkdir(parents=True)
            document = project / 'OTDocuments' / 'Line.opentrack'
            dest = project / 'OTData' / 'line.dest'
            run = project / 'line.run'
            members = {
                document: docs['Line'], dest: catalog,
                run: b'Infrastructure Document#OTDocuments/Line.opentrack#\nDestInfoFile#OTData/line.dest#\n',
            }
            for path, data in members.items():
                path.write_bytes(data)

            def source(path):
                return {'path': path.relative_to(root).as_posix(), 'sha256': sha(members[path])}

            service = ItineraryEditTools(root)
            args = dict(action='replace_paths', name='Service', paths=references[2:],
                        project_run=source(run), documents={'Line': source(document)}, catalog=source(dest),
                        description='Direct', target_directory='OTAI/workspaces/Edit/pair')
            preview = service.edit(EditItinerary(edit=args))
            self.assertFalse(preview['saved'])
            self.assertFalse((root / args['target_directory']).exists())
            with self.assertRaises(ValidationError):
                EditItinerary(edit={**args, 'description': None})
            with self.assertRaises(APIError) as nested:
                service.edit(EditItinerary(edit={**args, 'target_directory': 'OTProjects/Fixture/forbidden'}))
            self.assertEqual(nested.exception.code, 'ITINERARY_DOCUMENT_SCOPE')
            args['preview_only'] = False
            result = service.edit(EditItinerary(edit=args))
            self.assertTrue(result['saved'])
            output = root / args['target_directory']
            self.assertTrue((output / 'bundle-manifest.json').is_file())
            blobs = {name: (output / name).read_bytes() for name in (document.name, dest.name)}
            for name, data in blobs.items():
                self.assertEqual(sha(data), result['manifest']['files'][name]['sha256'])
            with self.assertRaises(APIError) as existing:
                service.edit(EditItinerary(edit=args))
            self.assertEqual(existing.exception.code, 'TARGET_EXISTS')

            create_target = 'OTAI/workspaces/Edit/new-itinerary'
            result = service.edit(EditItinerary(edit={**args, 'action': 'create_itinerary',
                'name': 'New service', 'paths': references[:2], 'target_directory': create_target}))
            self.assertTrue(result['saved'])
            self.assertEqual(result['change_report']['ordered_paths'], references[:2])
            created_doc = (root / create_target / document.name).read_bytes()
            created_cat = (root / create_target / dest.name).read_bytes()
            reconstructed = EditableItineraryProject({'Line': created_doc},
                document_paths={'Line': 'OTDocuments/Line.opentrack'}, expected_hashes={'Line': sha(created_doc)},
                complete_document_set=True)
            self.assertEqual(reconstructed.check_dest_catalog(created_cat), 2)
            self.assertEqual(path_functions.inspect_archive(created_doc, 'OTDest', 'New service')['description'], 'Direct')
            self.assertEqual(path_functions.inspect_archive(created_doc, 'OTDest', 'Service')['saved_references'], references[:2])
            with self.assertRaisesRegex(APIError, 'name already exists'):
                service.edit(EditItinerary(edit={**args, 'action': 'create_itinerary'}))

            description_target = 'OTAI/workspaces/Edit/described.opentrack'
            result = service.edit(EditItinerary(edit=dict(action='set_description', source=source(document),
                name='Service', description='Renumbered', target_path=description_target, preview_only=False)))
            self.assertTrue(result['saved'])
            actual = path_functions.inspect_archive((root / description_target).read_bytes(), 'OTDest', 'Service')
            self.assertEqual(actual['description'], 'Renumbered')
            self.assertEqual(actual['saved_references'], references[:2])

            margin_target = 'OTAI/workspaces/Edit/margins.opentrack'
            margin_rows = [{'position_m': 0, 'safety_margin_m': 18}, {'position_m': 400, 'safety_margin_m': 37.25}]
            result = service.edit(EditItinerary(edit=dict(action='set_safety_margins', source=source(document),
                name='Service', rows=margin_rows, target_path=margin_target, preview_only=False)))
            self.assertTrue(result['saved'])
            self.assertEqual(result['change_report']['after'], margin_rows)
            margin_root, _ = writer.load((root / margin_target).read_bytes())
            profile = path_functions.select(margin_root, 'OTDest', 'Service').contents[5].value
            self.assertEqual([row.contents[0].values for row in route_factory.wrapper(profile, 'OTSafetyMarginArray')],
                             [[0.0, 18.0], [400.0, 37.25]])
            self.assertEqual({path: path.read_bytes() for path in members}, members)


if __name__ == '__main__':
    unittest.main()
