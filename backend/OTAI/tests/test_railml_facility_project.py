"""Read back a whole pre-service project with directly bound RailML facilities."""

from pathlib import Path

import pytest

from opentrack_ai.current_archive import catalogs, route_factory, writer
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyFacilities
from opentrack_ai.current_archive.multi_document.generate import signal_placement
from opentrack_ai.current_archive.pre_service_project import validate_pre_service_project
from opentrack_ai.current_archive.station_exchange import apply_records, read_catalog
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.current_archive.zero_generation.empty_project import build_empty_project
from opentrack_ai.errors import APIError

from test_empty_project import sources
from test_itinerary_lifecycle import course_archive
from test_railml_facilities import XML, fixture


ROLES = ('depot', 'trains', 'courses', 'timetable')
CATALOG = 'OTData/empty.stations'
SHEET = 'OTDocuments/Worksheet.opentrack'
RUN = 'starter.run'


def prepare_project(tmp_path, *, existing_sign='OLD', reused=True, with_courses=False, virtual=False, xml=XML):
    tool, arguments, ids = fixture(tmp_path, xml)
    header, shapes = sources()
    base = tmp_path / 'OTAI/workspaces/construction-source'
    files, _ = build_empty_project(header, shapes, document_names=['Worksheet'],
                                   execution_root=base.as_posix(), run_filename=RUN, train_types=['instructional'])
    provided = (tmp_path / arguments['worksheet']['path']).read_bytes()
    if reused:
        _, _, _, byid = native.document(provided)
        terminal = ids['C'][0]
        end = byid[terminal]
        mid = max(byid) + 1
        provided, _ = native.build_main_signal(
            provided, end_id=terminal, name='Exit1', model_id=mid,
            placement=signal_placement(end, float(end.contents[2].value), float(end.contents[3].value)), sight_m=450,
            delay_s=4, show_icon=True, show_symbol=False)
        arguments['signals'][0]['existing_model_id'] = mid
        provided, _ = native.build_route(
            provided, name='Existing arrival', end_ids=[ids[name][0] for name in 'ABC'],
            description='Retain native movement', release_groups='each_end', reserve_previous=False)
        if virtual:
            root, version, _, byid = native.document(provided)
            byid[mid].contents[9].values[2] |= 2
            provided = writer.dump_verified(root, version)
    files[SHEET] = provided
    if existing_sign:
        files[CATALOG], _ = apply_records(files[CATALOG], [{'sign': existing_sign, 'name': 'Existing Station'}],
                                           'opentrack_xml', 'reject')
    if with_courses:
        files['OTData/empty.courses'] = course_archive(C01=['Pending'])
    for name, data in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    arguments['worksheet'] = {'path': (base / SHEET).relative_to(tmp_path).as_posix(), 'sha256': sha(provided)}
    arguments['source_project'] = {'project_directory': base.relative_to(tmp_path).as_posix(),
                                   'files': {name: sha(data) for name, data in files.items()},
                                   'complete_project_inventory': True, 'run_file': RUN, 'execution_root': base.as_posix()}
    return tool, arguments, base, files, ids


def test_whole_project_publishes_station_and_existing_signal_on_normal_run_members(tmp_path):
    tool, args, base, before, ids = prepare_project(tmp_path)
    preview = tool.facilities(ApplyFacilities(**args))
    assert not preview['saved'] and not (tmp_path / args['target_directory']).exists()
    assert preview['inserted_station_signs'] == ['CTR']
    if not tmp_path.as_posix().isascii():
        pytest.skip('Windows native publication requires an ASCII --basetemp')
    published = tool.facilities(ApplyFacilities(**args, preview_only=False))
    assert published['saved'] and published['publication']['post_commit_verified']
    assert published['members'] == preview['members'] and set(published['members']) == before.keys()
    assert published['worksheet_member'] == SHEET and published['station_catalog_member'] == CATALOG
    assert published['source_signals']['S']['reused_existing_model']
    target = tmp_path / args['target_directory']
    assert (target / 'output').is_dir()
    files = {name: (target / name).read_bytes() for name in before}
    assert all(files[f'OTData/empty.{role}'] == before[f'OTData/empty.{role}'] for role in ROLES)
    assert all((base / name).read_bytes() == data for name, data in before.items())
    verification = validate_pre_service_project(files, run_file=RUN, execution_root=target.as_posix())
    assert verification == published['complete_project_validation']
    assert verification['station_catalog_signs'] == ['OLD', 'CTR'] and verification['course_count'] == 0
    original = read_catalog(before[CATALOG], mutable=True)[2]['OLD']
    preserved = read_catalog(files[CATALOG], mutable=True)[2]['OLD']
    assert writer.fingerprint(original) == writer.fingerprint(preserved)
    _, _, _, byid = native.document(files[SHEET])
    stop, member = byid[ids['C'][0]], byid[ids['B'][0]]
    assert stop.contents[12].value is member.contents[12].value
    assert (stop.contents[20].value, member.contents[20].value) == (2, 1)
    assert stop.contents[11].value.contents[0].value == args['signals'][0]['existing_model_id']
    assert stop.contents[11].value.contents[16].value == 4
    route, = route_factory.wrapper(byid[ids['A'][0]].contents[15].value, 'OTRouteList')
    assert catalogs.text(route.contents[1].value) == 'Existing arrival'


def test_complete_project_preview_preserves_root_when_target_omitted(tmp_path):
    tool, args, _, before, _ = prepare_project(tmp_path, reused=False)
    result = tool.facilities(ApplyFacilities(**{**args, 'target_directory': None}))
    assert not result['saved'] and result['relocation'] is None
    assert result['members'][RUN]['sha256'] == sha(before[RUN])


@pytest.mark.parametrize(('variation', 'error'), [
    ('station_collision', 'conflicts with an existing native StationFile sign'),
    ('late_course', 'requires zero saved Courses'),
    ('unbound_worksheet', 'exact member bound by this .run'),
    ('wrong_signal', 'match the exact End, name, sight, type, role and virtual flag'),
    ('wrong_signal_sight', 'match the exact End, name, sight, type, role and virtual flag'),
    ('virtual_signal', 'match the exact End, name, sight, type, role and virtual flag'),
])
def test_rejects_unbound_facilities_or_existing_references(tmp_path, variation, error):
    xml = XML.replace(b'sight="450"', b'sight="451"') if variation == 'wrong_signal_sight' else XML
    tool, args, base, before, ids = prepare_project(
        tmp_path, xml=xml, existing_sign='ctr' if variation == 'station_collision' else '',
        with_courses=variation == 'late_course', virtual=variation == 'virtual_signal')
    if variation == 'unbound_worksheet':
        elsewhere = Path(args['railml']['path']).parent / 'Detached.opentrack'
        (tmp_path / elsewhere).write_bytes(before[SHEET])
        args['worksheet']['path'] = elsewhere.as_posix()
    if variation == 'wrong_signal':
        args['signals'][0]['existing_model_id'] = ids['C'][0]
    with pytest.raises(APIError, match=error):
        tool.facilities(ApplyFacilities(**args))
    assert all((base / name).read_bytes() == data for name, data in before.items())
    assert not (tmp_path / args['target_directory']).exists()
