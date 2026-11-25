"""First native services use external record shapes without inheriting donor operations."""

import pytest

from opentrack_ai.current_archive import catalogs, course_factories as factory, writer
from opentrack_ai.current_archive.catalog_batch_reuse.course_batch import course_record
from opentrack_ai.current_archive.catalog_batch_reuse.timetable_batch import timetable_record
from opentrack_ai.current_archive.network_operating_plan import GenerateNetworkPlan, build_catalogs
from opentrack_ai.current_archive.operating_plan_edit import set_sequence
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_lifecycle import course_archive
from test_operating_plan_edit import connection, dictionary
from test_saved_multi_document_reroute import chain
from test_saved_platform_replacement import occupied_platform
from test_saved_platform_resize import _operating


def planned_course(course_id, offset):
    return {'course_id': course_id, 'train': 'Passenger', 'itinerary': 'I:chain:forward', 'speed_type': 'Passenger',
            'visits': [{'station_sign': station, 'arrival_s': arrival + offset, 'departure_s': departure + offset, 'stop': stop}
                       for station, arrival, departure, stop in [('A', 28920, 28920, False), ('B', 29400, 29520, True),
                                                                  ('C', 30000, 30000, True)]]}


def plan():
    return {'source_project': {'project_directory': 'project', 'execution_root': 'D:/project', 'run_file': 'chain.run',
                               'complete_project_inventory': True, 'files': {'chain.run': 'a' * 64}},
            'course_template_id': 'Booked', 'timetable_template_key': 'Booked#1',
            'course_template_archive': {'path': 'example/donor.courses', 'sha256': 'b' * 64},
            'timetable_template_archive': {'path': 'example/donor.timetable', 'sha256': 'c' * 64},
            'courses': [planned_course('New01', 0), planned_course('New02', 1200)]}


def donor_archives(banks):
    root = writer.load_next_compatible(banks['courses'])[0]
    course, = catalogs.course_items(root)
    set_sequence(course, 2, [native.string('Foreign-Route')])
    factory.settext(course, 3, 'Foreign-Train')
    factory.settext(course, 10, 'Foreign description')
    factory.settext(course, 11, 'Foreign comment')
    course.contents[1].value = 80.0
    course.contents[6].value = 63
    course.contents[7].values[:] = [100.0, 7.0]
    course.contents[8].value = 3
    course.contents[9].value = 70
    course.contents[12].values[:] = [20.0, 25.0]
    table = writer.load_next_compatible(banks['timetable'])[0]
    row = factory.timetable(table)['Booked#1']
    for slot, label in ((2, 'ForeignInterval'), (5, 'ForeignStation'), (12, '33'), (13, '08:14:13'),
                        (14, '08:17:47'), (16, 'ForeignDistribution'), (18, 'ForeignPlatform')):
        factory.settext(row, slot, label)
    row.contents[11].value = 180.0
    row.contents[17].value = 5.0
    return writer.dump_verified(root), writer.dump_verified(table)


def test_empty_banks_receive_only_requested_native_services_and_timetable_rows(occupied_platform):
    docs, paths, dest, _, _ = occupied_platform
    project = project_from(docs, paths, dest)
    banks, run, _ = _operating((connection('Booked', 'ForeignFeeder', 'B'),))
    seed = donor_archives(banks)
    local = {**banks, 'courses': course_archive(), 'timetable': writer.dump_verified(dictionary({})), 'dest': dest}
    state = {'roles': {name: name for name in local}, 'files': local, 'run': run, 'selected': local}
    args = GenerateNetworkPlan.model_validate(plan())
    changed, report = build_catalogs(state, project, args, first_service_archives=seed)
    assert changed.keys() == {'courses', 'timetable'} and report['course_count'] == 2
    assert [item['visits'][1]['stopping_point']['distance_m'] for item in report['services']] == [2000, 2000]
    saved_course_list = writer.load_next_compatible(changed['courses'])[0]
    courses = list(map(course_record, catalogs.course_items(saved_course_list)))
    assert [row['course_id'] for row in courses] == ['New01', 'New02']
    for row in courses:
        assert row['itineraries'] == ['I:chain:forward'] and row['train'] == row['speed_type'] == 'Passenger'
        assert row['enabled'] and row['train_number'] == row['course_id'] and row['spacing_mode'] == 'discrete'
        assert row['description'] == row['comment'] == '' and row['entering_speed_kmh'] == row['output_offset_m'] == 0
        assert row['acceleration_percent'] == row['delayed_acceleration_percent'] == 100
        assert row['additional_reservation_time_s'] == row['additional_release_time_s'] == 0
    table = factory.timetable(writer.load_next_compatible(changed['timetable'])[0])
    assert set(table) == {f'New0{number}#{index}' for number in (1, 2) for index in range(3)}
    for key, model in table.items():
        row = timetable_record(key, model)
        assert row['station_sign'] in ('A', 'B', 'C') and row['interval_reference_course_id'] is None
        assert row['interval_offset_s'] == row['mean_delay_s'] == row['delta_mass_t'] == 0
        assert row['connections'] == [] and row['distribution_name'] == row['track_id'] == ''
        assert row['actual_arrival'] == row['actual_departure'] == 'HH:MM:SS'
    assert timetable_record('New01#1', table['New01#1'])['dwell_s'] == 120

    for role in ('courses', 'timetable'):
        with pytest.raises(ValueError, match='empty current destination Course and Timetable'):
            build_catalogs({**state, 'files': {**local, role: banks[role]}}, project, args, first_service_archives=seed)
    missing = GenerateNetworkPlan.model_validate({**plan(), 'course_template_id': 'Missing'})
    with pytest.raises(ValueError, match='no exact selected Course template'):
        build_catalogs(state, project, missing, first_service_archives=seed)


def test_first_service_donors_are_an_append_only_pair():
    options = plan()
    with pytest.raises(ValueError, match='both first-service shape archives in append mode'):
        GenerateNetworkPlan.model_validate({**options, 'timetable_template_archive': None})
    with pytest.raises(ValueError, match='both first-service shape archives in append mode'):
        GenerateNetworkPlan.model_validate({**options, 'mode': 'replace_plan'})
