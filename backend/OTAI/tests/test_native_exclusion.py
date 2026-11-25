import pytest

from opentrack_ai.current_archive.native_exclusion import examine


def trace(*cycles):
    rows = ['// Produced by OpenTrack: Mon Nov 23 2026', '// Type    : OT_TimeXPlot', '// Desc.   : OT_occ',
            '// x-Legend: [s]', '// y-Legend: none']
    for course, times in cycles:
        rows.extend(f'{clock:.2f}\tJ22_Safety23\t{event}\t{course}'
                    for event, clock in zip(('SR', 'SO', 'EO', 'ER'), times))
    return '\n'.join(rows) + '\n'


def test_safety_element_accepts_touching_reservations_and_requires_two_trains_to_pass():
    data = trace(('H2E1', (40, 60, 85, 91.54)), ('V2N1', (91.54, 101, 115, 125)))
    result = examine(data, 'J22_Safety23', ['H2E1', 'V2N1'])
    assert result['verified'] and result['cycle_count'] == 2
    assert not examine(data, 'J22_Safety23', ['H2E1', 'Turn'])['verified']


def test_reservation_overlap_can_fail_even_if_physical_trains_do_not_overlap():
    data = trace(('H2E1', (40, 60, 85, 100)), ('V2N1', (94, 101, 115, 125)))
    result = examine(data, 'J22_Safety23', ['H2E1', 'V2N1'])
    assert not result['verified']
    assert result['reservation']['examples'][0]['overlap_s'] == 6
    assert result['occupation']['overlapping_cycle_count'] == 0


def test_more_recent_own_course_cannot_hide_another_train_overlap():
    data = trace(('Earlier', (10, 20, 40, 50)), ('Shared', (14, 24, 47, 60)),
                 ('Shared', (42, 45, 55, 65)))
    result = examine(data, 'J22_Safety23', ['Earlier', 'Shared'])
    assert not result['verified']
    assert result['reservation']['overlapping_cycle_count'] == 2
    with pytest.raises(ValueError, match='complete'):
        examine(data[:data.rfind('65.00')], 'J22_Safety23', ['Earlier', 'Shared'])
