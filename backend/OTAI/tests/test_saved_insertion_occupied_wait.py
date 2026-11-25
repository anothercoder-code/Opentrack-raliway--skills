"""Review the new inserted-document native wait independently of speed entry."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive.saved_geometry import transform
from opentrack_ai.current_archive.saved_geometry_tools import InsertOperationalDocumentSpan

from test_path_lifecycle_native import course_catalog
from test_saved_document_insertion import chain


def with_wait(base):
    operation = deepcopy(base)
    route = operation['routes'][0]
    route['preserve_local_protection'] = True
    route['expected_occupied_entry'] = {'terminal_end': {'document': 'B', 'end_id': 8}, 'stop_edge_id': 9,
                                  'expected_wait_s': 45, 'expected_safety_element_id': 6, 'station_sign': 'B',
                                  'receiver_course': 'FIRST', 'donor_course': 'SECOND'}
    return operation


def test_insertion_wait_schema_requires_all_five_banks_and_distinct_courses(chain):
    operation = with_wait(chain[-1])
    with pytest.raises(ValueError, match='five operating archive hashes'):
        InsertOperationalDocumentSpan.model_validate(operation)
    operation['operating_sha256'] = {role: 'a' * 64 for role in ('courses', 'timetable', 'trains', 'depot', 'stations')}
    InsertOperationalDocumentSpan.model_validate(operation)
    wait = operation['routes'][0]['expected_occupied_entry']
    wait['receiver_course'] = wait['donor_course']
    with pytest.raises(ValueError, match='distinct occupied-entry'):
        InsertOperationalDocumentSpan.model_validate(operation)
    wait['receiver_course'] = 'FIRST'
    wait['expected_speed_kmh'] = 20.0
    with pytest.raises(ValueError, match='Extra inputs are not permitted'):
        InsertOperationalDocumentSpan.model_validate(operation)


def test_native_writer_guards_implicit_wait_and_wrong_saved_native_mode(chain):
    documents, paths, dest, _, base = chain
    operation = with_wait(base)
    courses = course_catalog()
    with pytest.raises(ValueError, match='exact bound five operating archives'):
        transform(documents, paths, dest, 'A', operation, courses=courses)
    with pytest.raises(ValueError, match='stop-and-wait setting on both original Route fragments'):
        transform(documents, paths, dest, 'A', operation, courses=courses, platform_inputs={'courses': courses})
