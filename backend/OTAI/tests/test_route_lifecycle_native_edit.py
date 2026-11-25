"""Round-trip lifecycle operations on native current-document Route fixtures."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from opentrack_ai.current_archive import path_functions as paths, route_factory, writer
from opentrack_ai.current_archive.infrastructure_incidents.core import create as create_incident
from opentrack_ai.current_archive.movement_edits import _movement_project
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.route_lifecycle_tools import EditRouteLifecycle, RouteLifecycle, edit_route_lifecycle
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError

from test_cross_document_route_native_edit import NATIVE_PATHS, REFERENCE, fixture
from test_itinerary_native_edit import schematic_document


def mutate(blob, edit):
    root, version = writer.load_next_compatible(blob)
    _, nodes = route_factory.document(root)
    edit(root, nodes)
    return writer.dump_verified(root, version)


def without_forward_dependencies(documents, catalog):
    def unlink(root, nodes):
        writer.set_elements(nodes[0].contents[17].value.contents[0].value, [])
        writer.set_elements(root.contents[5].value.contents[0].value, [])

    output = {**documents, 'A': mutate(documents['A'], unlink)}
    root, version = writer.load_next_compatible(catalog)
    items = route_factory.wrapper(root, 'OTDestInfoList')
    writer.set_elements(root.contents[0].value, [item for item in items if paths.string(item.contents[1].value) != 'I:A-B'])
    return output, writer.dump_verified(root, version)


def replace(*fragments):
    return {'action': 'replace_extent', 'segments': [
        {'document': document, 'end_ids': ends, 'release_group_end_ids': releases}
        for document, ends, releases in fragments
    ]}


def incident_catalog(start_id, array_id):
    incidents = native.arr()
    row = create_incident({'name': 'Speed limit', 'type': 'route_speed', 'document': 'A', 'enabled': True,
        'begin_time': '00:00:00', 'end_time': '01:00:00', 'begin_day': 0, 'end_day': 0,
        'start_end_id': start_id, 'array_id': array_id, 'probability_percentage': 100,
        'reduced_speed_kmh': 50}, incidents)
    writer.set_elements(incidents, [row])
    return writer.dump_verified(native.obj([('OTCourseList', 3), ('NSObject', 0)],
        [('i', [17]), ('@', [incidents]), ('@', [native.arr()]),
         ('@', [native.arr()]), ('@', [native.arr()])]))


class RouteLifecycleTests(unittest.TestCase):
    def test_rename_updates_primary_fragment_and_saved_path(self):
        documents, catalog = fixture()
        outputs, report = edit_route_lifecycle(documents, NATIVE_PATHS, catalog, 'A', REFERENCE,
                                              {'action': 'rename', 'new_name': 'Main Route'})
        checked = _movement_project(outputs, NATIVE_PATHS, catalog)
        ident = ('Main Route', 0, 0)
        self.assertEqual(checked.route_view(checked.owned(('A', 0), 'OTRoute', ident)),
                         [('A', 0), ('A', 4), ('B', 4)])
        self.assertEqual(checked.route_view(checked.owned(('B', 0), 'OTRoute', ident)), [('B', 4)])
        linked = checked.owned(('A', 0), 'OTPath', ('P:A-B', 1, 0))
        self.assertEqual(checked.path_view(linked)[1], [('A', {**REFERENCE, 'name': 'Main Route'})])
        self.assertEqual(report['affected'], {'paths': [], 'itineraries': []})

    def test_receiving_document_can_be_replaced(self):
        documents, catalog = without_forward_dependencies(*fixture())
        documents['C'], _ = schematic_document(generate.spec(), [('right', 0), ('right', 1)])

        def retarget(_, nodes):
            nodes[9].contents[25].value = native.string('C')
            nodes[9].contents[26].value = 0

        def withdraw(_, nodes):
            connector = nodes[8]
            connector.clazz = connector.clazz.superclass
            connector.contents = connector.contents[:24]

        def receive(_, nodes):
            connector = nodes[0]
            connector.clazz = writer.Class(b'OTConnModel', 1, connector.clazz)
            connector.contents += [writer.TypedValue(b'@', native.string('')),
                                   writer.TypedValue(b'@', native.string('A')),
                                   writer.TypedValue(b'i', 9), writer.TypedValue(b'i', 0)]

        for doc, edit in [('A', retarget), ('B', withdraw), ('C', receive)]:
            documents[doc] = mutate(documents[doc], edit)
        filenames = {**NATIVE_PATHS, 'C': 'C.opentrack'}
        outputs, report = edit_route_lifecycle(documents, filenames, catalog, 'A', REFERENCE,
                                              replace(('A', [0, 8], [0]), ('C', [4], [4])))
        self.assertEqual(report['new_directional_ends'], [('A', 0), ('A', 8), ('C', 4)])
        self.assertEqual(report['old_receiving_connector'], ('B', 0))
        self.assertEqual(report['new_receiving_connector'], ('C', 0))
        rebuilt = _movement_project(outputs, filenames, catalog)
        with self.assertRaisesRegex(ValueError, 'Unresolved exact OTRoute'):
            rebuilt.owned(('B', 0), 'OTRoute', ('R:A-B', 0, 0))
        self.assertIsNotNone(rebuilt.owned(('C', 0), 'OTRoute', ('R:A-B', 0, 0)))

    def test_local_start_relocation_allocates_new_identity(self):
        spec = generate.spec()
        spec['vertices'].append(generate.vertex('alternative', 40))
        edge = spec['edges'][0]
        spec['edges'].append({**edge, 'key': 'feed', 'from': ['alternative', 1], 'to': ['right', 0]})
        blob, ends = schematic_document(spec, [('left', 0), ('alternative', 0), ('right', 0)])
        start, other, end = [ends[name][0] for name in ('left', 'alternative', 'right')]
        blob, _ = native.build_route(blob, name='Switchable', end_ids=[start, end], description='',
                                     release_groups='global', reserve_previous=False)
        catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
        selector = {'name': 'Switchable', 'start_id': start, 'array_id': 0}
        output, report = edit_route_lifecycle({'A': blob}, {'A': 'A.opentrack'}, catalog, 'A', selector,
                                              replace(('A', [other, end], [other, end])))
        self.assertEqual(report['after'], {'document': 'A', 'name': 'Switchable', 'start_id': other, 'array_id': 0})
        project = _movement_project(output, {'A': 'A.opentrack'}, catalog)
        self.assertEqual(project.model(('A', start)).contents[19].value, 0)
        self.assertEqual(project.model(('A', other)).contents[19].value, 0)
        moved = project.owned(('A', other), 'OTRoute', ('Switchable', 0, other))
        self.assertEqual(project.route_view(moved), [('A', other), ('A', end)])
        with self.assertRaisesRegex(ValueError, 'Route-speed Incident'):
            edit_route_lifecycle({'A': blob}, {'A': 'A.opentrack'}, catalog, 'A', selector,
                                 replace(('A', [other, end], [other, end])), incident_catalog(other, 0))

    def test_deletion_requires_unused_route_and_keeps_highwater(self):
        documents, catalog = fixture()
        with self.assertRaisesRegex(ValueError, 'dependent Paths'):
            edit_route_lifecycle(documents, NATIVE_PATHS, catalog, 'A', REFERENCE, {'action': 'delete'})
        documents, catalog = without_forward_dependencies(documents, catalog)
        with self.assertRaisesRegex(ValueError, 'Route-speed Incident'):
            edit_route_lifecycle(documents, NATIVE_PATHS, catalog, 'A', REFERENCE,
                                 {'action': 'delete'}, incident_catalog(0, 0))
        outputs, report = edit_route_lifecycle(documents, NATIVE_PATHS, catalog, 'A', REFERENCE,
                                              {'action': 'delete'})
        self.assertIsNone(report['after'])
        checked = _movement_project(outputs, NATIVE_PATHS, catalog)
        self.assertEqual(checked.model(('A', 0)).contents[19].value, 1)
        self.assertEqual(len(checked.continuations), 1)
        self.assertEqual(checked.continuations[0]['route']['name'], 'R:B-A')

    def test_service_requires_actual_run_course_binding_on_delete(self):
        documents, catalog = without_forward_dependencies(*fixture())
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'OTProjects' / 'Routes'
            project.mkdir(parents=True)

            def member(name, data):
                file = project / name
                file.write_bytes(data)
                return {'path': file.relative_to(root).as_posix(), 'sha256': sha(data)}

            params = {'project_run': member('test.run',
                b'Infrastructure Document#A.opentrack#\nInfrastructure Document#B.opentrack#\n'
                b'DestInfoFile#Line.dest#\nCourseFile#Line.courses#\n'),
                'dest_catalog': member('Line.dest', catalog), 'target_document': 'A', 'route': REFERENCE,
                'documents': {name: member(file, documents[name]) for name, file in NATIVE_PATHS.items()},
                'operation': {'action': 'delete'}}
            tool = RouteLifecycle(root)
            with self.assertRaisesRegex(APIError, 'unique run-bound CourseFile'):
                tool.edit(EditRouteLifecycle(**params))
            with self.assertRaisesRegex(APIError, 'Route-speed Incident'):
                tool.edit(EditRouteLifecycle(**params, courses=member('Line.courses', incident_catalog(0, 0))))


if __name__ == '__main__':
    unittest.main()
