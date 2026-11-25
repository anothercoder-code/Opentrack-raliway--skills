import pytest

from opentrack_ai.current_archive import catalogs, course_factories, native_connections, writer
from opentrack_ai.current_archive.native_station_rebind import grouped_rows, rewrite_station_occurrences
from opentrack_ai.current_archive.operating_plan_edit import text

from test_operating_plan_edit import sample


def link(plan):
    obj, = catalogs.array(plan.row('A01', 0).contents[9].value)
    return native_connections.record(obj)


def test_an_unselected_waiting_course_follows_the_remote_station_reference():
    plan = sample()
    selected = plan.row('A02', 0)
    course_factories.settext(selected, 2, '0')
    selected.contents[11].value = 0
    prior = link(plan)
    review, = rewrite_station_occurrences(plan, grouped_rows(plan.rows()), {('A02', 0): 'RDG'})
    assert text(selected, 5) == 'RDG'
    assert link(plan) == {**prior, 'target_station_sign': 'RDG'}
    assert review['from_target_station'] == 'EA' and review['to_target_station'] == 'RDG'
    plan.validate()


def test_interval_cannot_be_left_behind_and_two_sided_migration_preserves_its_offset():
    plan = sample()
    before = writer.fingerprint(plan.table)
    with pytest.raises(ValueError, match='Interval-linked Courses'):
        rewrite_station_occurrences(plan, grouped_rows(plan.rows()), {('A01', 0): 'RDG'})
    assert writer.fingerprint(plan.table) == before

    old = link(plan)
    rewrite_station_occurrences(plan, grouped_rows(plan.rows()), {('A01', 0): 'RDG', ('A02', 0): 'RDG'})
    assert link(plan) == {**old, 'station_sign': 'RDG', 'target_station_sign': 'RDG'}
    interval = plan.row('A02', 0)
    assert text(interval, 2) == 'A01' and interval.contents[11].value == 120
    plan.validate()


def test_repeated_target_with_two_projected_codes_requires_review():
    plan = sample()
    course_factories.settext(plan.row('A02', 1), 5, 'EA')
    course_factories.settext(plan.row('A02', 0), 2, '0')
    plan.row('A02', 0).contents[11].value = 0
    with pytest.raises(ValueError, match='Repeated visits'):
        rewrite_station_occurrences(plan, grouped_rows(plan.rows()), {('A02', 0): 'RDG'})
