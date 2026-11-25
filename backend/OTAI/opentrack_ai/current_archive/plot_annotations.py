"""Native bar records and typed axis legend groups."""

from math import isfinite
from struct import pack, unpack
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from . import catalogs, writer
from .multi_document.core import layout, need
from .plot_point_files import bounds, gray, point
from .tools import Input
from .zero_generation.native_signal_routes import arr, obj, string
from .zero_generation.topology import flt


MAX_POINTS = 8192
Caption = Annotated[StrictStr, Field(max_length=200, pattern=r'^[ -~]*$')]
AxisValue = Annotated[StrictInt | StrictFloat, Field(ge=-1e12, le=1e12, allow_inf_nan=False)]
PenWidth = Annotated[StrictInt | StrictFloat, Field(gt=0, le=100, allow_inf_nan=False)]
BarOutlineWidth = Annotated[StrictInt | StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)]
Channel = Annotated[StrictInt, Field(ge=0, le=255)]
RGB = Annotated[list[Channel], Field(min_length=3, max_length=3)]
MARKER_KINDS = {'text': 0, 'signal': 4, 'station': 5}
BAR_CHAIN = [('OTBarPlot', 0), ('OTPlot', 1), ('NSObject', 0)]
BAR_FIELDS = ['@', '@', 'ffff', 'fi', '@', '@', 'ii']
BAR_POINT_CHAIN = [('OTBarPoint', 1), ('OTPlotPoint', 0), ('NSObject', 0)]
BAR_POINT_FIELDS = ['ff', 'i', '@', '@', 'f']
MARKER_CHAIN = [('OTPlotAxisLegend', 0), ('NSObject', 0)]
MARKER_FIELDS = ['if', '@', '@', '@']
DELAY_BAR_NAME = 'OT_Delay.delact'
DELAY_BAR_TYPE = 36
DELAY_BAR_PAUSED = 5
DELAY_BAR_ONLINE = 15


class BarPoint(Input):
    value: AxisValue
    course_id: Caption = ''
    station_sign: Caption = ''
    time_s: Annotated[StrictInt | StrictFloat, Field(ge=0, le=1e9, allow_inf_nan=False)] | None = None


class BarSeries(Input):
    name: Annotated[Caption, Field(min_length=1)]
    points: Annotated[list[BarPoint], Field(min_length=1, max_length=MAX_POINTS)]
    color_rgb: RGB = Field(default_factory=lambda: [0, 0, 0])
    outline_width: BarOutlineWidth = 1

BarSeriesList = Annotated[list[BarSeries], Field(max_length=16)]


class ReplaceBars(Input):
    series: BarSeriesList
    fit_viewport: StrictBool = True


class AxisMarker(Input):
    name: Caption
    point: Annotated[list[AxisValue], Field(min_length=2, max_length=2)]
    kind: Literal['text', 'signal', 'station'] = 'text'
    angle_deg: Annotated[StrictInt | StrictFloat, Field(ge=-360, le=360, allow_inf_nan=False)] = 0
    color_rgb: RGB = Field(default_factory=lambda: [0, 0, 0])


MarkerGroup = Annotated[list[AxisMarker], Field(min_length=1, max_length=MAX_POINTS)]
MarkerGroups = Annotated[list[MarkerGroup], Field(max_length=32)]


class AxisMarkerGroups(Input):
    x: MarkerGroups | None = None
    y: MarkerGroups | None = None

    @model_validator(mode='after')
    def explicit_axis(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Select one or both exact axes for native marker-group replacement')
        return self


def color(rgb):
    if not any(rgb):
        return gray(0.0)
    return obj([('NSColor', 0), ('NSObject', 0)], [
        ('c', [1]), ('ffff', [*(flt(channel / 255, 'Plot color') for channel in rgb), 1.0]),
    ])


def color_rgb(record):
    if writer.kind(record) != 'NSColor' or record.clazz.version != 0 or len(record.contents) != 2:
        return None
    space, channels = record.contents[0].values, record.contents[1].values
    if space == [3] and len(channels) == 2:
        channels = [channels[0]] * 3
    elif space == [1] and len(channels) == 4:
        channels = channels[:3]
    else:
        return None
    if all(isinstance(channel, (int, float)) and 0 <= channel <= 1 for channel in channels):
        return [round(channel * 255) for channel in channels]
    return None


def bar_point(coordinates, course_id, station_sign, time_s):
    return obj(BAR_POINT_CHAIN, [('ff', list(coordinates)), ('i', [0]), ('@', [string(course_id)]),
                                 ('@', [None if station_sign is None else string(station_sign)]), ('f', [time_s])])


def bar_record(name, points, extents, width, color_rgb, *, plot_type=0, flags=0):
    return obj(BAR_CHAIN, [('@', [arr(points)]), ('@', [string(name)]), ('ffff', extents),
                           ('fi', [width, 0]), ('@', [color(color_rgb)]), ('@', [None]), ('ii', [plot_type, flags])])


def native_bars(specs):
    need(sum(len(spec.points) for spec in specs) <= MAX_POINTS, 'A Plot accepts up to 8,192 offline bar points')
    need(len({spec.name for spec in specs}) == len(specs), 'Use distinct Plot bar series names')
    records = []
    for spec in specs:
        coordinates = [(float(index), flt(row.value, 'Bar value')) for index, row in enumerate(spec.points, 1)]
        points = [bar_point(coords, row.course_id, row.station_sign,
                            -1.0 if row.time_s is None else flt(row.time_s, 'Bar time'))
                  for row, coords in zip(spec.points, coordinates, strict=True)]
        width = flt(spec.outline_width, 'Bar outline width')
        need(not spec.outline_width or width > 0, 'Bar outline width collapses in native binary32 precision')
        records.append(bar_record(spec.name, points, bounds(coordinates), width, spec.color_rgb))
    return records


def native_markers(groups):
    need(sum(map(len, groups)) <= MAX_POINTS, 'An axis accepts up to 8,192 markers')
    return arr(arr(obj(MARKER_CHAIN, [
        ('if', [unpack('<i', pack('<f', MARKER_KINDS[item.kind]))[0], flt(item.angle_deg, 'Axis marker angle')]),
        ('@', [point(*(flt(value, 'Axis marker coordinate') for value in item.point))]),
        ('@', [string(item.name)]), ('@', [color(item.color_rgb)]),
    ]) for item in group) for group in groups)


def runtime_delay_seed():
    # prepareEmptyBarPlot (0x568a7c) calls the inherited initWithX:andY: (0x569d0c).
    # The new point's station and time fields stay nil and zero, respectively.
    seed = bar_point((0.0, 0.0), '0', None, 0.0)
    series = bar_record(DELAY_BAR_NAME, [seed], [0.0] * 4, 1.0, [0, 0, 0], plot_type=DELAY_BAR_TYPE,
                        flags=DELAY_BAR_ONLINE)
    return series, native_markers([[AxisMarker(name='', point=[0, 0], angle_deg=90)]])


def is_runtime_delay(record, name):
    plot_type, flags = record.contents[6].values
    return (name == DELAY_BAR_NAME and plot_type == DELAY_BAR_TYPE and record.contents[5].value is None
            and flags in (DELAY_BAR_PAUSED, DELAY_BAR_ONLINE))


def delay_bar_for_update(records, counts):
    need(len(records) == 1, 'Select a Plot with one exclusive actual-delay bar series')
    bar = records[0]
    layout(bar, BAR_CHAIN, BAR_FIELDS)
    need(counts[id(bar)] == 1 and is_runtime_delay(bar, catalogs.text(bar.contents[1].value)),
         'The selected bar is outside the reviewed global actual-delay binding')
    for row in owned_array(bar.contents[0].value, counts, 'delay bar points'):
        layout(row, BAR_POINT_CHAIN, BAR_POINT_FIELDS)
    return bar


def optional_array(record):
    try:
        return catalogs.array(record)
    except ValueError:
        return []


def describe_bar_point(row):
    layout(row, BAR_POINT_CHAIN, BAR_POINT_FIELDS)
    category, value = row.contents[0].values
    return {'category': category, 'value': value, 'type': row.contents[1].value,
            'course_id': writer.string(row.contents[2].value), 'station_sign': writer.string(row.contents[3].value),
            'time_s': row.contents[4].value}


def describe_bars(array, *, include_points=False):
    result = []
    for record in optional_array(array):
        try:
            layout(record, BAR_CHAIN, BAR_FIELDS)
            points = catalogs.array(record.contents[0].value)
            name = catalogs.text(record.contents[1].value)
        except ValueError:
            continue
        bar = {'name': name, 'point_count': len(points), 'data_bounds': list(record.contents[2].values),
               'outline_width': record.contents[3].values[0], 'color_rgb': color_rgb(record.contents[4].value),
               'plot_type': record.contents[6].values[0], 'run_flags': record.contents[6].values[1]}
        if is_runtime_delay(record, name):
            bar['run_updates'] = {'source': 'simulation_actual_delay', 'course_scope': 'all_active_simulation_courses',
                                  'overwrite_data': bool(bar['run_flags'] & 2), 'plot_online': bool(bar['run_flags'] & 8)}
        if include_points and len(points) <= MAX_POINTS:
            try:
                bar['points'] = [describe_bar_point(row) for row in points]
            except ValueError:
                pass
        result.append(bar)
    return result


def describe_markers(array):
    result = []
    for group in optional_array(array):
        markers = []
        for item in optional_array(group):
            try:
                layout(item, MARKER_CHAIN, MARKER_FIELDS)
                coordinates = catalogs.shape(item.contents[1].value, 'OTPlotPoint', 0, ['ff'])
                name = writer.string(item.contents[2].value)
            except ValueError:
                continue
            kind_raw, angle = item.contents[0].values
            if not -2**31 <= kind_raw < 2**31:
                continue
            native = unpack('<f', pack('<i', kind_raw))[0]
            kind = next((key for key, value in MARKER_KINDS.items() if value == native), None)
            markers.append({'name': name, 'point': list(coordinates.contents[0].values),
                            'kind': kind, 'native_type_raw': kind_raw, 'angle_deg': angle,
                            'color_rgb': color_rgb(item.contents[3].value)})
        result.append(markers)
    return result


def bar_extents(records):
    if not records:
        return None
    extents = [record.contents[2].values for record in records]
    last_category = max(len(catalogs.array(record.contents[0].value)) for record in records)
    return [0.0, min(0.0, *(row[1] for row in extents)),
            1.0 + last_category, max(0.0, *(row[3] for row in extents))]


def owned_array(record, counts, kind):
    need(writer.kind(record) == 'NSMutableArray' and counts.get(id(record), 0) == 1,
         f'Native {kind} needs an independently owned mutable array')
    return catalogs.array(record)


def replaceable_bars(record, counts):
    for item in owned_array(record, counts, 'bar series') if record is not None else []:
        layout(item, BAR_CHAIN, BAR_FIELDS)
        need(item.contents[6].values == [0, 0] and item.contents[5].value is None and counts[id(item)] == 1,
             'Replace only independently owned offline bars without native simulation update bindings')
        for row in owned_array(item.contents[0].value, counts, 'bar points'):
            layout(row, BAR_POINT_CHAIN, BAR_POINT_FIELDS)
            need(counts[id(row)] == 1, 'A bar point also belongs to another native object')


def replaceable_markers(record, counts):
    for group in owned_array(record, counts, 'axis marker groups'):
        for item in owned_array(group, counts, 'axis markers'):
            layout(item, MARKER_CHAIN, MARKER_FIELDS)
            need(counts[id(item)] == 1, 'An axis marker also belongs to another native object')
