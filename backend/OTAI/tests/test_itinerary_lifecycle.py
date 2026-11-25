"""Regression cases for native Itinerary definitions, DestInfo and Course references."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from opentrack_ai.current_archive import catalogs, path_functions, route_factory, writer
from opentrack_ai.current_archive.itinerary_lifecycle_tools import (
    ItineraryLifecycle, ItineraryLifecycleTools, _course_bindings, edit_lifecycle,
)
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError
from test_itinerary_native_edit import fixture, schematic_document, with_margin


def course_archive(**bindings):
    courses = []
    _, groups = catalogs.LAYOUTS['OTCourse']
    for course_id, names in bindings.items():
        slots = [[{'@': None, 'f': 0.0, 'i': 0}[code] for code in group] for group in groups]
        slots[0] = [native.string(course_id)]
        slots[2] = [native.arr(native.string(name) for name in names)]
        courses.append(native.obj([('OTCourse', 11), ('NSObject', 0)], list(zip(groups, slots))))
    root = native.obj([('OTCourseList', 3), ('OTMutableArray', 0), ('NSObject', 0)], [
        ('i', [17]), ('@', [native.arr()]), ('@', [native.arr()]), ('@', [native.arr()]), ('@', [native.arr(courses)]),
    ])
    return writer.dump_verified(root)


def names_for_courses(blob):
    root, _ = writer.load(blob)
    return {key: [catalogs.text(ref) for ref in values] for key, (_, _, values) in _course_bindings(root).items()}


class ItineraryLifecycleTest(unittest.TestCase):
    def test_rename_preserves_order_and_updates_every_course_occurrence(self):
        docs, catalog, names, references = fixture('OTDocuments/Line.opentrack')
        courses = course_archive(Fast=['Service', 'Service'], Local=['Service'], Blank=[])
        output, dest, new_courses, report = edit_lifecycle(
            docs, names, catalog, courses, {'action': 'rename', 'name': 'Service', 'new_name': 'New'})
        self.assertNotEqual(output, docs)
        self.assertNotEqual(dest, catalog)
        self.assertEqual(report['after']['saved_references'], references[:2])
        self.assertEqual(names_for_courses(new_courses), {'Fast': ['New', 'New'], 'Local': ['New'], 'Blank': []})
        self.assertEqual(report['course_reference_replacements'], [
            {'course_id': 'Fast', 'indexes': [0, 1]}, {'course_id': 'Local', 'indexes': [0]},
        ])

    def test_duplicate_then_delete_requires_or_applies_equivalent_course_replacement(self):
        docs, catalog, names, references = fixture('OTDocuments/Line.opentrack')
        docs['Line'] = with_margin(docs['Line'])
        docs['Line'], _ = path_functions.set_description(docs['Line'], 'OTDest', 'Service', 'Source notes')
        courses = course_archive(Fast=['Service'], Another=['Service', 'Service'])
        duplicated, new_catalog, untouched, report = edit_lifecycle(
            docs, names, catalog, courses, {'action': 'duplicate', 'name': 'Service', 'new_name': 'Spare'})
        self.assertIsNone(untouched)
        self.assertEqual(report['after']['saved_references'], references[:2])
        self.assertEqual(report['after']['description'], '')
        with self.assertRaisesRegex(ValueError, 'referenced by Courses'):
            edit_lifecycle(duplicated, names, new_catalog, courses, {'action': 'delete', 'name': 'Service'})
        conflicting = course_archive(Fast=['Service', 'Spare'])
        operation = {'action': 'delete', 'name': 'Service', 'replacement_itinerary': 'Spare'}
        with self.assertRaisesRegex(ValueError, 'already references'):
            edit_lifecycle(duplicated, names, new_catalog, conflicting, operation)
        _, _, rewritten, report = edit_lifecycle(duplicated, names, new_catalog, courses, operation)
        self.assertEqual(report['replacement_itinerary'], 'Spare')
        self.assertEqual(names_for_courses(rewritten), {'Fast': ['Spare'], 'Another': ['Spare', 'Spare']})

    def test_rebuild_recovers_missing_catalog_entries_and_rejects_missing_definitions(self):
        docs, catalog, names, _ = fixture('OTDocuments/Line.opentrack')
        root, version = writer.load(catalog)
        writer.set_elements(root.contents[0].value, [])
        incomplete = writer.dump_verified(root, version)
        operation = {'action': 'rebuild_dest_catalog'}
        output, dest, changed_courses, report = edit_lifecycle(
            docs, names, incomplete, course_archive(Fast=['Service']), operation)
        self.assertEqual(output, docs)
        self.assertIsNone(changed_courses)
        self.assertEqual(len(route_factory.wrapper(writer.load(dest)[0], 'OTDestInfoList')), 1)
        self.assertEqual((report['prior_entry_count'], report['new_entry_count']), (0, 1))
        with self.assertRaisesRegex(ValueError, 'references missing Itinerary'):
            edit_lifecycle(docs, names, incomplete, course_archive(Fast=['Missing']), operation)

    def test_endpoint_change_rechecks_course_bindings_and_distance_margins(self):
        docs, catalog, names, references = fixture('OTDocuments/Line.opentrack')
        docs['Line'] = with_margin(docs['Line'])
        operation = {'action': 'reconfigure', 'name': 'Service', 'paths': references[:1]}
        with self.assertRaisesRegex(ValueError, 'requires an unused Itinerary'):
            edit_lifecycle(docs, names, catalog, course_archive(Fast=['Service']), operation)
        with self.assertRaisesRegex(ValueError, 'explicitly clear'):
            edit_lifecycle(docs, names, catalog, course_archive(), operation)
        rows = [{'position_m': 30, 'safety_margin_m': 9}]
        _, _, _, report = edit_lifecycle(docs, names, catalog, course_archive(),
                                          {**operation, 'description': 'Short turn', 'safety_margins': rows})
        self.assertEqual(report['after_safety_margins'], rows)
        self.assertEqual(report['after']['description'], 'Short turn')
        self.assertEqual(report['after']['saved_references'], references[:1])
        self.assertTrue(report['running_time_revalidation_required'])

    def test_reconfigure_can_move_unbound_definition_to_first_path_document(self):
        names = {name: f'OTDocuments/{name}.opentrack' for name in 'AB'}
        docs, catalog, _ = generate.make_pair({
            'A': schematic_document(generate.spec(), [('left', 0), ('left', 1)])[0],
            'B': schematic_document(generate.spec(), [('right', 0), ('right', 1)])[0],
        }, names)
        catalog_root, _ = writer.load(catalog)
        reverse = next(row for row in route_factory.wrapper(catalog_root, 'OTDestInfoList')
                       if catalogs.text(row.contents[1].value) == 'I:B-A')
        item, = writer.elements(reverse.contents[4].value)
        array_id, start_id = item.contents[1].values
        reference = {'document': 'B', 'name': catalogs.text(item.contents[0].value),
                     'array_id': array_id, 'start_id': start_id}
        output, _, _, report = edit_lifecycle(docs, names, catalog, course_archive(Fast=['I:B-A']), {
            'action': 'reconfigure', 'name': 'I:A-B', 'paths': [reference],
        })
        self.assertTrue(all(output[name] != docs[name] for name in names))
        self.assertEqual(report['new_owner_document'], 'B')
        self.assertEqual(report['after']['saved_references'], [reference])

    def test_reconfigure_active_course_can_take_alternate_track_with_reviewed_margins(self):
        spec = generate.spec()
        spec['vertices'] = [generate.vertex(name, x) for name, x in [('A', 0), ('C', 100), ('D', 150), ('B', 300)]]
        spec['edges'] = [{**spec['edges'][0], 'key': first + last, 'from': [first, 1], 'to': [last, 0]}
                         for first, last in ('AC', 'CB', 'AD', 'DB')]
        document, end_ids = schematic_document(spec, [('A', 0), ('B', 0)])
        names = {'Line': 'OTDocuments/Line.opentrack'}
        catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
        selected = []
        for via in 'CD':
            label = f'Route-{via}'
            start, middle, last = (end_ids[name][0] for name in ['A', via, 'B'])
            document, route = native.build_route(document, name=label, end_ids=[start, middle, last],
                                                  description='', release_groups='global', reserve_previous=False)
            docs, receipt = operations.create_path({'Line': document}, catalog, document_paths=names,
                expected_hashes={'Line': sha(document), '$dest_catalog': sha(catalog)}, complete_document_set=True,
                name=f'Path-{via}', routes=[{'document': 'Line', 'name': label, 'start_id': start, 'array_id': route['array_id']}])
            document = docs['Line']
            selected.append(receipt['created'])
        created, _ = operations.create_itinerary(docs, catalog, name='Service', paths=selected[:1],
            document_paths=names, expected_hashes={'Line': sha(document), '$dest_catalog': sha(catalog)},
            complete_document_set=True)
        docs = {'Line': with_margin(created['documents']['Line'])}
        courses = course_archive(Fast=['Service'])
        operation = {'action': 'reconfigure', 'name': 'Service', 'paths': selected[1:]}
        with self.assertRaisesRegex(ValueError, 'explicitly clear'):
            edit_lifecycle(docs, names, created['catalog'], courses, operation)
        _, _, rewritten, report = edit_lifecycle(docs, names, created['catalog'], courses,
                                                  {**operation, 'safety_margins': []})
        self.assertIsNone(rewritten)
        self.assertEqual(report['after']['saved_references'], selected[1:])
        self.assertEqual(report['after_safety_margins'], [])
        self.assertTrue(report['running_time_revalidation_required'])
        for field in ('before_end_keys', 'after_end_keys'):
            self.assertEqual([report[field][0][1], report[field][-1][1]], [end_ids['A'][0], end_ids['B'][0]])

    def test_bundle_checks_run_binding_and_reloads_published_files(self):
        docs, catalog, _, _ = fixture('OTDocuments/Line.opentrack')
        with TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            project = root / 'OTProjects' / 'Fixture'
            (project / 'OTDocuments').mkdir(parents=True)
            (project / 'OTData').mkdir()
            (root / 'OTAI' / 'workspaces' / 'Edit').mkdir(parents=True)
            blobs = {
                'OTDocuments/Line.opentrack': docs['Line'],
                'OTData/line.dest': catalog, 'OTData/line.courses': course_archive(Fast=['Service']),
                'OTData/wrong.courses': course_archive(Fast=['Service']),
                'line.run': b'Infrastructure Document#OTDocuments/Line.opentrack#\n'
                            b'DestInfoFile#OTData/line.dest#\nCourseFile#OTData/line.courses#\n',
            }
            for filename, data in blobs.items():
                (project / filename).write_bytes(data)

            def source(name):
                return {'path': (project / name).relative_to(root).as_posix(), 'sha256': sha(blobs[name])}

            service = ItineraryLifecycleTools(root)
            defaults = dict(project_run=source('line.run'), documents={'Line': source('OTDocuments/Line.opentrack')},
                            catalog=source('OTData/line.dest'), courses=source('OTData/line.courses'),
                            operation={'action': 'rename', 'name': 'Service', 'new_name': 'New'},
                            target_directory='OTAI/workspaces/Edit/pair')
            with self.assertRaisesRegex(APIError, 'match the run CourseFile'):
                service.edit(ItineraryLifecycle(**{**defaults, 'courses': source('OTData/wrong.courses')}))
            self.assertFalse(service.edit(ItineraryLifecycle(**defaults))['saved'])
            target = root / defaults['target_directory']
            self.assertFalse(target.exists())
            result = service.edit(ItineraryLifecycle(**defaults, preview_only=False))
            self.assertTrue(result['saved'])
            members = result['manifest']['files']
            self.assertEqual(set(members), {'Line.opentrack', 'line.dest', 'line.courses'})
            self.assertEqual({name: sha((target / name).read_bytes()) for name in members},
                             {name: row['sha256'] for name, row in members.items()})
            self.assertEqual(names_for_courses((target / 'line.courses').read_bytes()), {'Fast': ['New']})
            self.assertEqual({name: (project / name).read_bytes() for name in blobs}, blobs)


if __name__ == '__main__':
    unittest.main()
