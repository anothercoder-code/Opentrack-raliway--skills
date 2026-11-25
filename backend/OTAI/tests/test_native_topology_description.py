"""Regression cases for saved topology description exports."""

import pytest

from opentrack_ai.current_archive import native_topology_description as desc
from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.course_factories import dictionary
from opentrack_ai.current_archive.itinerary_edit_tools import EditableItineraryProject
from opentrack_ai.current_archive.native_topology_description_tools import MovementDescriptions, NativeDescriptions
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import fixture


def test_worksheet_description_lists_saved_ids_and_exact_edge_endpoints():
    docs, _, _, _ = fixture('Line.opentrack')
    root, _ = writer.load(docs['Line'])
    models, _ = route_factory.document(root)
    before = writer.fingerprint(root)
    output, report = desc.worksheet(root, 'Line', 'Line.desc')
    rows = [line for line in output.decode().splitlines() if line.startswith('ID = ')]
    assert report['object_count'] == len(models)
    assert [int(line.partition('\t')[0][5:]) for line in rows] == [item.contents[0].value for item in models]
    edge = next(item for item in models if writer.kind(item) == 'OTEdgeModel')
    first, last = (slot.value.contents[0].value for slot in edge.contents[7:9])
    assert f'ID = {edge.contents[0].value}\tTyp = Edge\tEnd 0 ID = {first}\tEnd 1 ID = {last}' in rows
    assert writer.fingerprint(root) == before


def test_project_description_orders_sections_and_expands_directional_track_profiles(tmp_path):
    root = tmp_path / 'OTProjects' / 'LineModel'
    root.mkdir(parents=True)
    docs, catalog, names, _ = fixture('Line.opentrack')
    document = root / 'Line.opentrack'
    run = root / 'Line.run'
    run.write_bytes(b'Infrastructure Document#Line.opentrack#\nDestInfoFile#Line.dest#\n'
                    b'TrainType#Type A#\nTrainType#Type B#\n')
    dest = root / 'Line.dest'
    dest.write_bytes(catalog)
    project = EditableItineraryProject(docs, document_paths=names,
                                       expected_hashes={'Line': sha(docs['Line'])}, complete_document_set=True)
    nodes, _ = project.dest_view(project.dests[0])
    first, last = nodes[:2]
    edge = project.model(project.edge_between(first, last))
    edge.contents[9].values[2:4] = [250.0, 3.5]
    speed = dictionary(edge.contents[16].value)['0']
    speed.contents[1].value = 55
    speed.contents[2].value = 35
    original = writer.fingerprint(project.roots['Line'])
    forward = list(desc.track_profile(project, [first, last], 2, {}))[1].split('\t')
    reverse = list(desc.track_profile(project, [project.related(last), project.related(first)], 2, {}))[1].split('\t')
    assert {tuple(forward[2:4]), tuple(reverse[2:4])} == {('3.50', '250'), ('-3.50', '-250')}
    assert {tuple(forward[5:7]), tuple(reverse[5:7])} == {('55', '200'), ('35', '200')}
    assert writer.fingerprint(project.roots['Line']) == original
    document.write_bytes(writer.dump_verified(project.roots['Line'], project.versions['Line']))

    def ref(path):
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(path.read_bytes())}

    service = NativeDescriptions(tmp_path)
    args = {'project_run': ref(run), 'documents': {'Line': ref(document)}, 'dest_catalog': ref(dest),
            'sections': ['routes', 'itineraries'], 'detailed_routes': True, 'detailed_itinerary_profiles': True}
    preview = service.export_movements(MovementDescriptions.model_validate(args))
    assert preview['file_name'] == 'Network.IR.desc'
    assert preview['sections'] == ['itineraries', 'routes']
    assert preview['record_counts'] == {'itineraries': 1, 'routes': 2}
    assert preview['profile_speed_count'] == 2
    assert preview['saved'] is False
    output, _ = desc.movements(project, ['routes', 'itineraries'], preview['file_name'],
                              detailed_routes=True, profile_speed_count=2)
    assert sha(output) == preview['file_sha256']
    assert b'Service \t\t\t(Contains 2 Paths / 2 Routes' in output
    assert output.index(b'\tFirst \t\t') < output.index(b'\tLast \t\t')
    assert b'\nRoutes\n\n' in output and b'\nPaths\n\n' not in output
    with pytest.raises(APIError, match='SHA'):
        document.write_bytes(docs['Line'])
        service.export_movements(MovementDescriptions.model_validate(args))
