"""Complete native publication from a verified blank worksheet and run."""

from copy import deepcopy
import os

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.multi_document.bundle import validate_no_service_bundle
from opentrack_ai.current_archive.network_generation_tools import NetworkGeneration
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.current_archive.zero_generation.empty_project import build_empty_project
from opentrack_ai.current_archive.zero_operations import run_bundle
from opentrack_ai.errors import APIError
from opentrack_ai.registry import Registry
from opentrack_ai.service import Service

from test_empty_project import sources, spec
from test_itinerary_native_edit import fixture as itinerary_fixture


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Complete publication binds the actual Windows project root')

RUN = 'starter.run'
WORKSHEET = 'OTDocuments/Station.opentrack'
DEST = 'OTData/empty.dest'


@pytest.fixture
def blank_network(tmp_path):
    source = tmp_path / 'OTProjects/StationStart'
    donors = tmp_path / 'OTProjects/Shapes'
    destination = 'OTProjects/StationNetwork'

    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}

    header, shapes = sources()
    files, _ = build_empty_project(header, shapes, **spec(execution_root=source.as_posix()))
    files[RUN] = files[RUN].replace(b'/output#', b'/reports/traffic#').replace(
        b'Start Time#00:00:00#', b'Start Time#09:00:00#')
    for path, data in files.items():
        write(source / path, data)
    templates, catalog, _, paths = itinerary_fixture('Line.opentrack')
    first = paths[0]
    graph = generate.spec()

    def end(vertex, side=0):
        return {'vertex': vertex, 'side': side}

    for edge in graph['edges']:
        edge['from_end'] = end(*edge.pop('from'))
        edge['to_end'] = end(*edge.pop('to'))

    request = {
        'sources': {'header_document': write(donors / 'Header.opentrack', header),
                    'shape_archive': write(donors / 'Shapes.archive', shapes),
                    'template_document': write(donors / 'Line.opentrack', templates['Line']),
                    'template_dest_catalog': write(donors / 'Line.dest', catalog)},
        'templates': {'path_name': first['name'], 'path_array_id': first['array_id'],
                      'path_start_id': first['start_id'], 'itinerary_name': 'Service'},
        'source_project': {'project_directory': source.relative_to(tmp_path).as_posix(),
                           'files': {name: sha(data) for name, data in files.items()},
                           'complete_project_inventory': True, 'run_file': RUN, 'execution_root': source.as_posix()},
        'target_directory': destination,
        'document_name': 'Station', 'catalog_filename': 'empty.dest', 'network': graph,
        'signals': [{'name': name, 'end': end(vertex), 'angle': 0, 'alignment_x': 1,
                     'alignment_y': 0, 'sight_m': 500, 'delay_s': 0, 'show_symbol': True, 'show_icon': True}
                    for name, vertex in (('Entry', 'left'), ('Exit', 'right'))],
        'routes': [{'name': 'Arrival', 'ends': [end('left'), end('right')], 'description': '',
                    'release_groups': 'each_end', 'reserve_previous': False}],
        'paths': [{'name': 'Run', 'routes': ['Arrival'], 'description': ''}],
        'itineraries': [{'name': 'Teaching service', 'paths': ['Run'], 'description': ''}],
    }
    tool = Registry(Service(tmp_path, False, False), profile='all').tools['opentrack_generate_current_network_archives']

    def call(payload):
        return tool.handler(tool.model.model_validate(payload))

    return call, request, files, source, tmp_path / destination, write


def test_public_network_generator_publishes_bound_project_and_keeps_pair_mode(blank_network):
    call, request, before, source, target, _ = blank_network
    pair = call({key: value for key, value in request.items() if key not in ('source_project', 'target_directory')})
    assert pair['manifest']['format'] == 'opentrack-current-network-archives-v1'
    assert set(pair['manifest']['files']) == {'Station.opentrack', 'empty.dest'}
    unbound = call({key: value for key, value in request.items() if key != 'target_directory'})
    assert unbound['relocation'] is None and unbound['member_sha256'][RUN] == sha(before[RUN])
    preview = call(request)
    assert not target.exists() and not preview['saved']
    assert preview['relocation']['path_changes']['dest_owner_paths'] == 1
    assert preview['member_sha256'][WORKSHEET] == pair['manifest']['files']['Station.opentrack']['sha256']

    result = call({**request, 'preview_only': False})
    actual = {path.relative_to(target).as_posix(): path.read_bytes()
              for path in target.rglob('*') if path.is_file()}
    hashes = {name: sha(data) for name, data in actual.items()}
    assert result['saved'] and result['fresh_archive_reload_verified'] and not result['native_application_started']
    assert hashes == result['member_sha256'] == preview['member_sha256']
    assert set(actual) == set(before) and {key for key in before if before[key] != actual[key]} == {RUN, WORKSHEET, DEST}
    assert all((source / name).read_bytes() == data for name, data in before.items())
    assert (target / 'reports/traffic').is_dir() and not list((target / 'reports/traffic').iterdir())
    assert [raw for key, _, raw in run_bundle.records(before[RUN]) if key not in run_bundle.PATH_KEYS] == [
        raw for key, _, raw in run_bundle.records(actual[RUN]) if key not in run_bundle.PATH_KEYS]
    catalog, _ = writer.load_next_compatible(actual[DEST])
    row, = writer.elements(catalog.contents[0].value)
    assert writer.string(row.contents[2].value) == (target / WORKSHEET).as_posix()
    cold = validate_no_service_bundle(actual, run_file=RUN, expected_hashes=hashes, complete_file_set=True)
    assert cold['destination_count'] == 1 and cold['station_count'] == 0 and cold['no_service_catalogs']
    with pytest.raises(APIError) as duplicate:
        call({**request, 'preview_only': False})
    assert duplicate.value.code == 'TARGET_EXISTS'


def test_rejects_wrong_catalog_source_header_and_populated_worksheet(blank_network):
    call, request, _, source, target, write = blank_network
    with pytest.raises(APIError, match='existing run-bound DestInfo filename'):
        call({**request, 'catalog_filename': 'wrong.dest'})
    wrong = deepcopy(request)
    header, version = writer.load_next_compatible((source / WORKSHEET).read_bytes())
    header.contents[19].value = native.string('Different import provenance')
    wrong['sources']['header_document'] = write(source.parent / 'Shapes/WrongHeader.opentrack',
                                                writer.dump_verified(header, version))
    with pytest.raises(APIError, match='supplied worksheet header differs'):
        call(wrong)
    populated, _ = sources()
    request['source_project']['files'][WORKSHEET] = write(source / WORKSHEET, populated)['sha256']
    with pytest.raises(APIError, match='selected worksheet must have empty graphic'):
        call(request)
    assert not target.exists()


def test_rechecks_donor_and_project_bytes_before_publication(blank_network, monkeypatch):
    call, request, _, source, target, _ = blank_network
    real_compose = NetworkGeneration.compose
    shape_file = source.parents[1] / request['sources']['shape_archive']['path']
    shape_bytes = shape_file.read_bytes()
    station_file = source / 'OTData/empty.stations'
    station_bytes = station_file.read_bytes()

    for dependency, original in ((shape_file, shape_bytes), (station_file, station_bytes)):
        def changed_after_compose(*args, **kwargs):
            result = real_compose(*args, **kwargs)
            dependency.write_bytes(original + b'changed concurrently')
            return result

        monkeypatch.setattr(NetworkGeneration, 'compose', staticmethod(changed_after_compose))
        with pytest.raises(APIError) as stale:
            call({**request, 'preview_only': False})
        assert stale.value.code == 'SOURCE_CHANGED' and not target.exists()
        dependency.write_bytes(original)
