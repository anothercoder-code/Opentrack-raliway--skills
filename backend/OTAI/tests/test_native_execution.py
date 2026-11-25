import pytest
from pydantic import ValidationError

from opentrack_ai.current_archive.prepare_contract.auxiliary import records
from opentrack_ai.current_archive.runfile_parameters import RunfileError, edit_runfile
from opentrack_ai.native_execution import batch_runfile, interactive_break, summarize_delays
from opentrack_ai.simulation_evidence import Control


RUN = (b'// Delay Scenario#9# remains a comment\r\n'
       b'Start Day Offset#0#\r\nStart Time#08:00:00#\r\n'
       b'Stop Day Offset#0#\r\nStop Time#10:00:00#\r\nStep#0.2#\r\n'
       b'Delay Scenario#9#\r\nBreak Time#09:00:00#\r\nIncident#Closed route#\r\n')


def test_scenario_preserves_incident_selection_and_uses_unique_options():
    edited = batch_runfile(RUN, 17)
    values = {key: value for key, value, _ in records(edited)}
    assert values['Delay Scenario'] == '17'
    assert values['Break Time'] == '00:00:00'
    assert values['Output Course & Station Statistics'] == '1'
    assert values['Incident'] == 'Closed route'
    assert edited.startswith(b'// Delay Scenario#9# remains a comment\r\n')
    assert RUN.count(b'Delay Scenario#9#') == 2


def test_interactive_launch_preserves_breakpoint_and_enables_native_panel_observation():
    source = RUN + b'Show Train#0#\r\nTime Ratio#5:1#\r\nLabel Size#XL#\r\n'
    edited = batch_runfile(source, 17, interactive=True)
    values = {key: value for key, value, _ in records(edited)}
    assert interactive_break(edited) == 9 * 3600
    assert values['Delay Scenario'] == '17' and values['Time Ratio'] == '5:1'
    assert values['Label Size'] == 'XL' and values['Incident'] == 'Closed route'
    assert all(values[key] == '1' for key in ('Multithreaded', 'Show Current Time', 'Show Train',
                                              'Show Train ID', 'Show Messages'))
    with pytest.raises(ValueError, match='strictly within'):
        interactive_break(source.replace(b'Break Time#09:00:00', b'Break Time#10:00:00'))
    params = dict(action='start', mode='interactive', project_directory='source',
                  run_file='test.run', job_directory='job')
    assert Control(**params).mode == 'interactive'
    with pytest.raises(ValidationError, match='one scenario'):
        Control(**params, scenarios=[0, 1])


def test_saved_run_modifier_can_append_options_and_still_refuses_paths_and_bad_values():
    edited = edit_runfile(RUN, {b'Mean Delay': b'12.0', b'Delay Scenario': b'2', b'Output Acc./Time': b'1'})
    assert edited == RUN.replace(b'\r\nDelay Scenario#9#\r\n', b'\r\nDelay Scenario#2#\r\n') + (
        b'Mean Delay#12.0#\r\nOutput Acc./Time#1#\r\n')
    for change in ({b'OutputPath': b'D:/elsewhere'}, {b'Mean Delay': b'nan'},
                   {b'Output Acc./Time': b'2'}, {b'Step': b'0'}):
        with pytest.raises(RunfileError):
            edit_runfile(RUN, change)


def test_visual_and_moving_block_preferences_use_stock_values():
    changes = {b'Time Ratio': b'5:1', b'Label Size': b'XXXXL', b'Delay Format': b'M:SS',
               b'Communication Period': b'6', b'Optimization Period': b'31', b'Safety Margin': b'9.5'}
    edited = edit_runfile(RUN, changes)
    values = dict((key.encode(), value.encode()) for key, value, _ in records(edited) if key)
    assert all(values[key] == value for key, value in changes.items())
    for key, value in ((b'Time Ratio', b'5'), (b'Time Ratio', b'7:1'), (b'Label Size', b'XXXXXL'),
                       (b'Delay Format', b'MM:SS'), (b'Communication Period', b'0')):
        with pytest.raises(RunfileError):
            edit_runfile(RUN, {key: value})


def test_batch_summary_separates_repeated_station_events_and_unverified_scenarios():
    def evaluation(delays, verified):
        return {
            'native_run_verified': verified,
            'courses': [{'course_id': 'C01', 'events': [
                {'station': 'Alpha', 'kind': 'Arr.', 'planned_s': 32000, 'delay_s': delay}
                for delay in delays
            ]}],
        }

    summary = summarize_delays([(1, evaluation([10, 20], True)),
                                (2, evaluation([-4, 26], True)),
                                (3, evaluation([1000, 1000], False))])
    assert summary['included_scenarios'] == [1, 2]
    assert summary['unverified_scenarios'] == [3]
    first, second = summary['events']
    assert (first['occurrence'], first['mean_delay_s'], first['late_count']) == (1, 3, 1)
    assert (second['occurrence'], second['median_delay_s'], second['sample_count']) == (2, 23, 2)
