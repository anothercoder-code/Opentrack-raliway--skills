import pytest

from opentrack_ai.current_archive.native_platform_join import (
    joint_contact, match_platform, planned_itineraries, platform_signals, timetable_contact,
)


LEGEND = ('// Produced by OpenTrack: local parser fixture\n// Signal Positions of Course: SUPPLY\n'
          '// Itineraries: 1: Preferred D1 / 2: Alternative D2\n'
          '// Type    : OT_Legend\n// Desc.   : OT_Signals\n// x-Legend: [km]\n'
          '29.1000\tMDS\tD_HOME_L_S_R4_D_HOME\tTS\n')
D1 = '30.0000\tMS\tD1_REF_L_S_R4_D1_REF\tTS\n'
D2 = '30.0000\tMS\tD2_REF_L_S_R4_D2_REF\tTS\n'
OPTIONS = [{'itinerary': name, 'signal_label': f'{platform}_REF_L_S_R4_{platform}_REF',
            'end_key': ('R4', end), 'stop_edge_key': ('R4', edge), 'distance_m': 30000}
           for name, platform, end, edge in (('Preferred D1', 'D1', 108, 318), ('Alternative D2', 'D2', 120, 326))]


def test_signal_rows_select_actual_equal_length_platform_over_planned_priority():
    content = planned_itineraries(LEGEND + D2, ['Preferred D1', 'Alternative D2'], 'sigpos')
    chosen, metre, kind = match_platform(OPTIONS, platform_signals(content, 'SUPPLY'), 0)
    assert [item['end_key'] for item in chosen] == [('R4', 120)]
    assert (metre, kind) == (30000, 'MS')
    with pytest.raises(ValueError, match='planned Itinerary header'):
        planned_itineraries(content, ['Alternative D2', 'Preferred D1'], 'sigpos')


@pytest.mark.parametrize(('rows', 'error'), [
    (D2.replace('\tMS\t', '\tVMS\t'), 'one observed candidate'),
    (D1 + D2, 'one observed candidate'),
    (D1 + D1, 'more than once'),
    (D2.replace('30.0000', '30.0010'), 'signed Course distance'),
])
def test_native_platform_requires_unique_physical_label_and_consistent_axis(rows, error):
    with pytest.raises(ValueError, match=error):
        match_platform(OPTIONS, platform_signals(LEGEND + rows, 'SUPPLY'), 0)


def test_same_label_cannot_distinguish_two_saved_platform_ends():
    choices = [OPTIONS[0], {**OPTIONS[1], 'signal_label': OPTIONS[0]['signal_label']}]
    with pytest.raises(ValueError, match='ambiguous original signal label'):
        match_platform(choices, platform_signals(LEGEND + D1, 'SUPPLY'), 0)


def test_contact_reconciles_compressed_stops_at_midnight_with_two_distance_axes():
    receiver = {'speed': [(87396, 25), (87397.1, 0), (89820, 0), (89821, 5)],
                'distance': [(87396, 29990), (87397.1, 30000), (89820, 30000), (89821, 30001)]}
    donor = {'speed': [(88540, 5), (88545.75, 0), (88980, 0)],
             'distance': [(88540, 59780), (88545.75, 59790.9), (88980, 59790.9)]}
    contact = joint_contact(receiver, donor, 30000, 60000, 209, '00:35:45', .3)
    assert contact['reported_join_time_s'] == 88545 and contact['contact_time_s'] == 88545.75
    assert contact['donor_front_behind_reference_m'] == 209.1
    assert contact['receiver_onward_sample']['time_s'] == 89821
    name = 'Ring Station R4'
    origin = {'station': name, 'kind': 'Arr.', 'time_s': 87397}
    departure = {'station': name, 'kind': 'Dep.', 'time_s': 89820}
    donor_arrival = {'station': name, 'kind': 'Arr.', 'time_s': 88545}
    clocks = timetable_contact({'events': [origin, departure]}, {'last_observed_event': donor_arrival}, name, contact)
    assert clocks['receiver_departure'] == departure
    with pytest.raises(ValueError, match='terminal arrival'):
        timetable_contact({'events': [origin, departure]}, {'last_observed_event': {**donor_arrival, 'time_s': 88980}},
                          name, contact)
    with pytest.raises(ValueError, match='receiver tail'):
        joint_contact(receiver, donor, 30000, 60001, 209, '00:35:45', .3)
    with pytest.raises(ValueError, match='stopping onset'):
        joint_contact(receiver, donor, 30000, 60000, 209, '00:35:47', .3)
