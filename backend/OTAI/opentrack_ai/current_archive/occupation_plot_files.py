"""Original OT_occ point records for an editable worksheet occupation graph."""

from pathlib import PurePosixPath

from pydantic import StrictBool

from . import catalogs, native_evaluation_formats as fmt, writer
from .bundle_tools import Source
from .multi_document.core import layout, need
from .plot_point_files import gray
from .tools import Input
from .zero_generation.native_signal_routes import arr, obj, string
from .zero_generation.topology import flt


class OccupationFile(Input):
    source: Source
    show_reservations: StrictBool = True


# OTPlotModel typeForOcc: maps the optional end of pre-reservation to type 7.
EVENT = {'SR': 1, 'SO': 2, 'EO': 3, 'ER': 4, 'EP': 7}


def plot_from_file(raw, spec):
    filename = PurePosixPath(spec.source.path.replace('\\', '/')).name
    need(filename.startswith('OT_Occ_') and filename.endswith('.occ'), 'Expected an original OT_Occ_*.occ file')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    events = fmt.occupations(text)
    resources = {row['resource'] for row in events}
    need(len(resources) == 1, 'Use an original result file for one occupation resource')
    resource, = resources
    need(filename == f'OT_Occ_{resource}.occ', 'Original occupation resource differs from its filename')
    points = [(flt(row['time_s'], 'Original occupation time'), EVENT[row['event']], row['course_id'])
              for row in events if row['time_s'] is not None]
    need(0 < len(points) <= 100000, 'One occupation plot needs 1–100,000 timed events')
    need(all(course.isascii() and course.isprintable() for _, _, course in points),
         'Expected printable ASCII native Course IDs')
    left = min(item[0] for item in points)
    right = max(item[0] for item in points)
    series = obj([('OTOccupationPlot', 2), ('NSObject', 0)], [
        ('@', [arr(obj([('OTOccupationPoint', 0), ('NSObject', 0)], [
            ('fii', [time, code, 0]), ('@', [string(course)]),
        ]) for time, code, course in points)]),
        ('@', [string(resource.replace('_', ' '))]), ('ff', [left, right]),
        ('fi', [1.0, 0]), ('@', [gray(0.0)]), ('i', [3 if spec.show_reservations else 2]),
        ('i', [41 if spec.show_reservations else 43]),
    ])
    result = {'resource': resource, 'point_count': len(points), 'show_reservations': spec.show_reservations,
              'time_bounds_s': [left, right], 'untimed_events_omitted': len(events) - len(points)}
    return series, tuple(points), result


def saved_points(record):
    layout(record, [('OTOccupationPlot', 2), ('NSObject', 0)], ['@', '@', 'ff', 'fi', '@', 'i', 'i'])
    result = []
    for point in catalogs.array(record.contents[0].value):
        layout(point, [('OTOccupationPoint', 0), ('NSObject', 0)], ['fii', '@'])
        time, code, reserved = point.contents[0].values
        need(reserved == 0 and code in EVENT.values(), 'Unrecognized saved occupation point')
        result.append((time, code, writer.string(point.contents[1].value)))
    return tuple(result)
