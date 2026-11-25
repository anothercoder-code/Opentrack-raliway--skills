"""Check booked native stopping locations before and after moving a halt signal."""

from .multi_document.core import need
from .saved_platform_resize import _course_stops, _operating_data, _review_stops


def _tail_positions(visits):
    return {key: {**visit, 'tail_distance_m': visit['head_distance_m'] - visit['train_length_m']}
            for key, visit in visits.items()}


def review_halt_relocation(before_project, after_project, *, terminal, platform, platform_length,
                           affected_itineraries, operating_inputs, run_bytes, visit_reviews):
    """Validate both original train plans and every changed booked stop in the cold graph."""
    need(isinstance(visit_reviews, (list, tuple)), 'Provide explicit booked stop reviews for the native halt relocation')
    operating = _operating_data(operating_inputs, run_bytes, affected_itineraries)
    before, other_before = _course_stops(before_project, operating, terminal, platform, platform_length)
    after, other_after = _course_stops(after_project, operating, terminal, platform, platform_length)
    need(before.keys() == after.keys() and other_before == other_after,
         'Moving the halt marker also changes another booked stopping area or visit')
    before, after = _tail_positions(before), _tail_positions(after)
    fields = ('stop_signal_id', 'stop_edge', 'head_distance_m', 'tail_distance_m')
    affected = [key for key in before if any(before[key][name] != after[key][name] for name in fields)]
    if affected:
        reports = _review_stops({key: before[key] for key in affected}, {key: after[key] for key in affected}, visit_reviews)
        for row in visit_reviews:
            key = row['course_id'], row['visit_index']
            need(row.get('expected_tail_distance_m') == before[key]['tail_distance_m']
                 and row.get('replacement_tail_distance_m') == after[key]['tail_distance_m'],
                 f'Reviewed native train tail position differs for {key[0]}#{key[1]}')
    else:
        need(not visit_reviews, 'The halt marker move does not change any reviewed booked stop')
        reports = []
    return {'verified_platform_visits': reports, 'checked_operating_courses': list(operating[0]),
            'checked_directed_platform_stops': len(before)}
