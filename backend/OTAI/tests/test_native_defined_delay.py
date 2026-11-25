import pytest

from opentrack_ai.current_archive import course_factories, defined_delay, writer
from opentrack_ai.current_archive.native_run_evaluation import protocol_matches_frozen_run
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.prepare_contract.auxiliary import records
from opentrack_ai.current_archive.runfile_parameters import RunfileError, edit_runfile
from opentrack_ai.native_execution import batch_runfile

from test_native_execution import RUN
from test_operating_plan_edit import sample


def selected(station='EA', clear=False):
    return {'course_id': 'A01', 'index': 0, 'station_sign': station, 'delay_s': 90,
            'clear_distribution': clear}


def test_native_defined_selection_is_exact_and_preserved_in_a_worker_candidate():
    patched = edit_runfile(RUN, {b'Delay Scenario': b'-1', b'Mean Delay': b'12'})
    values = {key: value for key, value, _ in records(batch_runfile(patched, -1))}
    assert values['Delay Scenario'] == '-1' and values['Mean Delay'] == '12'
    assert b'// Delay Scenario#9# remains a comment' in patched
    with pytest.raises(RunfileError, match='invalid native option'):
        edit_runfile(RUN, {b'Delay Scenario': b'-2'})


def test_defined_delay_visit_uses_saved_occurrence_and_preserves_other_native_rows():
    plan = sample()
    with pytest.raises(ValueError, match='different saved Station'):
        defined_delay.update_visits(plan, [selected(station='RDG')])
    with pytest.raises(ValueError, match='selected twice'):
        defined_delay.update_visits(plan, [selected(), selected()])
    first = plan.row('A01', 0)
    course_factories.settext(first, 16, 'Named')
    with pytest.raises(ValueError, match='Confirm removal'):
        defined_delay.update_visits(plan, [selected()])
    before_other = text(plan.row('A01', 1), 12)
    record, = defined_delay.update_visits(plan, [selected(clear=True)])
    report = defined_delay.preflight({'Delay Scenario': ['-1'], 'Mean Delay': ['12']},
        'D:/Inputs/plan.timetable', writer.dump_verified(plan.table))
    assert text(first, 12) == '90' and text(first, 16) == ''
    assert text(plan.row('A01', 1), 12) == before_other
    assert record['removed_distribution_name'] == 'Named'
    assert report['index_zero_rows_with_nonzero_mean'] == 1
    assert report['timetable_rows_with_named_distribution'] == 0


def test_defined_future_native_protocol_must_equal_original_numeric_format():
    frozen = {'delay_scenario': '-1', 'paths': {'TimetableFile': 'D:/Inputs/plan.timetable'},
              'topology_documents': ['D:/Inputs/route.opentrack']}
    protocol = {'delay_scenario': '-1', 'paths': frozen['paths'], 'active_topology_files': frozen['topology_documents']}
    protocol_matches_frozen_run(protocol, frozen, None)
    with pytest.raises(ValueError, match='does not confirm'):
        protocol_matches_frozen_run({**protocol, 'delay_scenario': 'None'}, frozen, None)
