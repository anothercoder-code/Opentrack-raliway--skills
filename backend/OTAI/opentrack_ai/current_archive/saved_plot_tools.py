"""Read and edit Plot Inspector fields on existing ordinary OpenTrack worksheets."""

from copy import deepcopy
import math
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import catalogs, writer
from .bundle_tools import Source
from .graph_references import incoming_counts
from .multi_document.core import layout, need
from .next_tools import Ordinal, Save
from .occupation_plot_files import OccupationFile, plot_from_file, saved_points
from .plot_annotations import (
    DELAY_BAR_ONLINE, DELAY_BAR_PAUSED, AxisMarkerGroups, AxisValue, BarSeriesList, Caption, PenWidth, ReplaceBars,
    bar_extents, delay_bar_for_update, describe_bars, describe_markers, native_bars, native_markers, owned_array,
    replaceable_bars, replaceable_markers, runtime_delay_seed,
)
from .plot_point_files import PointFile, archived_lines, bounds, gray, point, read_point_data, read_points
from .tools import ArchiveTools, Input, sha
from .zero_generation.native_signal_routes import arr, obj, string
from .zero_generation.topology import DOC_ENC, flt, signature as class_signature


GRAPHIC_FIELDS = ['i', 'f', 'f', 'f', 'i', 'i']
RESIZE_FIELDS = ['if', 'ff', 'ff', '@', '@']
PLOT_FIELDS = ['@'] * 7 + ['ff', 'ffff', 'ii', '@', 'i', '@', '@', '@', '@']
PLOT_TAIL = {'series': 0, 'x_markers': 1, 'y_markers': 2, 'minimum': 3, 'maximum': 4, 'data_minimum': 5,
             'data_maximum': 6, 'increments': 7, 'axis_types': 9, 'occupation_series': 10, 'flags': 11,
             'bars': 12, 'x_title': 13, 'y_title': 14}
GRID_FLAGS = {'x_grid': 1, 'y_grid': 2, 'x_station_grid': 4, 'y_station_grid': 8,
              'x_detail_grid': 16, 'y_detail_grid': 32, 'show_x_legend': 64, 'show_y_legend': 128}
LINE_RUN_FLAGS = {'allows_overwrite_data': 1, 'overwrite_data': 2, 'allows_plot_online': 4, 'plot_online': 8}


class ExplicitChanges(Input):
    @model_validator(mode='after')
    def explicit(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Supply one or more explicit non-null plot changes')
        return self


class AxisRange(Input):
    minimum: AxisValue
    maximum: AxisValue


class AxisChanges(ExplicitChanges):
    x_title: Caption | None = None
    y_title: Caption | None = None
    x_range: AxisRange | None = None
    y_range: AxisRange | None = None
    x_grid: StrictBool | None = None
    y_grid: StrictBool | None = None
    x_station_grid: StrictBool | None = None
    y_station_grid: StrictBool | None = None
    x_detail_grid: StrictBool | None = None
    y_detail_grid: StrictBool | None = None
    show_x_legend: StrictBool | None = None
    show_y_legend: StrictBool | None = None


class SeriesChanges(ExplicitChanges):
    name: Caption | None = None
    line_width: PenWidth | None = None
    overwrite_data: StrictBool | None = None
    plot_online: StrictBool | None = None


class EditSeries(Input):
    index: Ordinal
    expected_name: StrictStr
    changes: SeriesChanges


class ReadPlot(Input):
    source: Source
    include_bar_points: StrictBool = False


class EditPlot(Save):
    source: Source
    plot_id: Ordinal
    axes: AxisChanges | None = None
    series: Annotated[list[EditSeries], Field(max_length=128)] = Field(default_factory=list)
    bars: ReplaceBars | None = None
    runtime_delay_bar: StrictBool | None = Field(
        default=None, description='Enable the original global actual-delay bar on a blank Plot or toggle its existing binding.',
    )
    axis_marker_groups: AxisMarkerGroups | None = None

    @model_validator(mode='after')
    def explicit_plot(self):
        has_changes = self.axes or self.series or self.bars or self.axis_marker_groups or self.runtime_delay_bar is not None
        if not has_changes or len({item.index for item in self.series}) != len(self.series):
            raise ValueError('Select plot changes and list each series index once')
        if self.runtime_delay_bar is not None and (self.bars or self.series):
            raise ValueError('Runtime delay binding requires an independent numeric Plot')
        if self.runtime_delay_bar and self.axis_marker_groups and self.axis_marker_groups.x is not None:
            raise ValueError('The original runtime delay update owns X-axis marker groups')
        return self


class SeriesSource(Input):
    worksheet: Source | None = None
    plot_id: Ordinal
    index: Ordinal
    expected_name: StrictStr


class InsertLine(Input):
    action: Literal['insert_existing_series']
    index: Ordinal
    donor: SeriesSource
    name: Caption | None = None


class DeleteLine(Input):
    action: Literal['delete_series']
    index: Ordinal
    expected_name: StrictStr


class InsertExternalLine(PointFile):
    action: Literal['insert_external_series']
    index: Ordinal


LineOperation = Annotated[InsertLine | DeleteLine | InsertExternalLine, Field(discriminator='action')]


class EditPlotSeries(Save):
    source: Source
    plot_id: Ordinal
    operations: Annotated[list[LineOperation], Field(min_length=1, max_length=128)]
    viewport: Literal['preserve', 'fit_line_data'] = 'preserve'


class PlotFrame(Input):
    x: AxisValue
    y: AxisValue
    width: Annotated[StrictInt | StrictFloat, Field(gt=80, le=500000, allow_inf_nan=False)]
    height: Annotated[StrictInt | StrictFloat, Field(gt=65, le=500000, allow_inf_nan=False)]


class CreatePlot(Save):
    source: Source
    frame: PlotFrame
    point_files: Annotated[list[PointFile], Field(max_length=32)] = Field(default_factory=list)
    occupation_files: Annotated[list[OccupationFile], Field(max_length=32)] = Field(default_factory=list)
    bar_series: BarSeriesList = Field(default_factory=list)
    runtime_delay_bar: StrictBool = Field(
        default=False, description='Create the original global actual-delay bar bound to active simulation Courses.',
    )
    axis_marker_groups: AxisMarkerGroups | None = None
    x_title: Caption | None = None
    y_title: Caption | None = None
    x_range: AxisRange | None = None
    y_range: AxisRange | None = None

    @model_validator(mode='after')
    def reviewed_series_kind(self):
        if sum(bool(series) for series in (self.point_files, self.occupation_files, self.bar_series, self.runtime_delay_bar)) > 1:
            raise ValueError('Choose one data family for the new Plot: occupation, numeric lines, offline bars or runtime delay')
        if self.runtime_delay_bar and self.axis_marker_groups and self.axis_marker_groups.x is not None:
            raise ValueError('The original runtime delay update owns X-axis marker groups')
        return self


def load_worksheet(raw):
    root, stream = writer.load_next_compatible(raw)
    version = root.clazz.version
    fields = {1: DOC_ENC[:14], 3: DOC_ENC[:19], 4: DOC_ENC}.get(version)
    need(fields is not None, 'A reviewed ordinary OTDocument1/3/4 worksheet is required')
    layout(root, [('OTDocument', version), ('NSObject', 0)], fields)
    objects = catalogs.array(root.contents[2].value)
    models = {}
    for model in objects:
        need(model.contents and model.contents[0].encodings == [b'i'], 'Malformed native Graphic ID')
        mid = model.contents[0].value
        need(type(mid) is int and 0 <= mid < 2**31 and mid not in models, 'Duplicate or invalid native Graphic ID')
        models[mid] = model
    return root, stream, {mid: model for mid, model in models.items() if writer.kind(model) == 'OTPlotModel'}


def check_series(record):
    version = record.clazz.version
    need(version in (0, 1), 'Only reviewed OTPlot0/1 inline series are supported')
    layout(record, [('OTPlot', version), ('NSObject', 0)],
           ['@', '@', 'ffff', 'fi', '@'] + (['@', 'ii'] if version == 1 else []))
    catalogs.text(record.contents[1].value)
    return catalogs.array(record.contents[0].value)


def plot_fields(model):
    version = model.clazz.version
    graphic = model.clazz.superclass.superclass.version
    need(version in (3, 4) and graphic in (0, 1), 'Only reviewed OTPlotModel3/4 layouts are supported')
    prefix = GRAPHIC_FIELDS + (['@'] if graphic else []) + RESIZE_FIELDS
    layout(model, [('OTPlotModel', version), ('OTResizeModel', 0), ('OTGraphicModel', graphic), ('NSObject', 0)],
           prefix + PLOT_FIELDS)
    if graphic:
        need(model.contents[6].value is None, 'A Plot attached to another worksheet model needs its owning editor')
    fields = {key: model.contents[len(prefix) + index] for key, index in PLOT_TAIL.items()}
    flags = fields['flags'].value
    need(type(flags) is int and 0 <= flags <= (63 if version == 3 else 255), 'Unrecognized saved Plot flags')
    for key in ('minimum', 'maximum'):
        catalogs.shape(fields[key].value, 'OTPlotPoint', 0, ['ff'])
    return fields


def describe(model, *, include_bar_points=False):
    fields = plot_fields(model)
    flags = fields['flags'].value
    settings = {key: catalogs.text(fields[key].value) for key in ('x_title', 'y_title')}
    low, high = (fields[key].value.contents[0].values for key in ('minimum', 'maximum'))
    for index, axis in enumerate(('x', 'y')):
        settings[f'{axis}_range'] = {'minimum': low[index], 'maximum': high[index]}
    settings.update({key: bool(flags & bit) or (model.clazz.version == 3 and bit >= 64)
                     for key, bit in GRID_FLAGS.items()})
    series = []
    for index, record in enumerate(catalogs.array(fields['series'].value)):
        row = {'index': index, 'name': catalogs.text(record.contents[1].value),
               'line_width': record.contents[3].values[0], 'point_count': len(check_series(record))}
        if record.clazz.version == 1:
            plot_type, flags = record.contents[6].values
            row['run_updates'] = {
                'plot_type': plot_type, 'course_id': writer.string(record.contents[5].value),
                **{name: bool(flags & bit) for name, bit in LINE_RUN_FLAGS.items()},
            }
        series.append(row)
    result = {'plot_id': model.contents[0].value, 'plot_version': model.clazz.version, 'axes': settings,
              'axis_types': list(fields['axis_types'].values), 'axis_increments': list(fields['increments'].values),
              'series': series}
    occupation = []
    if fields['occupation_series'].value is not None:
        for record in catalogs.array(fields['occupation_series'].value):
            if writer.kind(record) == 'OTOccupationPlot' and record.clazz.version == 2 and len(record.contents) == 7:
                occupation.append({'name': writer.string(record.contents[1].value),
                                   'point_count': len(catalogs.array(record.contents[0].value)),
                                   'time_bounds_s': list(record.contents[2].values),
                                   'show_reservations': bool(record.contents[5].value & 1)})
    if occupation:
        result['occupation_series'] = occupation
    bars = describe_bars(fields['bars'].value, include_points=include_bar_points)
    if bars:
        result['bar_series'] = bars
    groups = {}
    for axis in ('x', 'y'):
        if marker_groups := describe_markers(fields[f'{axis}_markers'].value):
            groups[axis] = marker_groups
    if groups:
        result['axis_marker_groups'] = groups
    return result


def line_run_flags(record, changes):
    need(record.clazz.version == 1, 'Run updates require native OTPlot1')
    flags = record.contents[6].values[1]
    need(type(flags) is int and 0 <= flags <= 15, 'Unrecognized saved line update flags')
    overwrite = changes.get('overwrite_data')
    online = changes.get('plot_online')
    need(not (overwrite is False and online is True), 'Online plotting also requires overwriting data')
    if overwrite is True or online is True:
        need(writer.string(record.contents[5].value), 'Run updates require an original Course binding')
        need(flags & LINE_RUN_FLAGS['allows_overwrite_data'], 'This saved line does not allow overwriting data')
    if online is True:
        need(flags & LINE_RUN_FLAGS['allows_plot_online'], 'This saved line does not allow online plotting')
    # OTPlot.setOverwriteData / setPlotOnline, 0x560098 / 0x5600f4.
    if overwrite is False:
        flags &= ~10
    elif overwrite is True:
        flags |= 2
    if online is True:
        flags |= 10
    elif online is False:
        flags &= ~8
    return flags


def axis_increment(low, high, kind):
    # Original PlotModel.calculateDeltaXandDeltaY, 0x563270.
    span = flt(float(high) - float(low), 'Plot range span')
    if span <= 0:
        return 0.0
    if kind == 1:
        return 1.0
    step = flt(10.0 ** (math.ceil(math.log10(span)) - 1), 'Plot auto tick')
    need(step > 0, 'Plot tick spacing collapses in the native format')
    result = flt(float(step) / 10.0, 'Plot auto tick') if span / step < 2.1 else step
    need(result > 0, 'Plot tick spacing collapses in the native format')
    return result


def named_line(records, index, expected_name):
    need(0 <= index < len(records), 'Plot series index is outside the saved line array')
    record = records[index]
    need(expected_name == catalogs.text(record.contents[1].value), 'Selected Plot series name differs')
    return record


def replacement_point(template, coordinates):
    return writer.GenericArchivedObject(template.clazz, contents=[writer.TypedGroup([b'f', b'f'], coordinates)])


def edit_archive(raw, plot_id, axes, series, *, bars=None, runtime_delay_bar=None, axis_marker_groups=None):
    root, stream, models = load_worksheet(raw)
    model = models.get(plot_id)
    need(model is not None, 'No matching owned Plot graphic ID')
    counts = incoming_counts(root)
    need(counts[id(model)] == 1, 'Shared Plot graphic cannot be edited independently')
    fields = plot_fields(model)
    before, signature = describe(model), writer.fingerprint(root)
    records = catalogs.array(fields['series'].value)
    undo = []

    def replace(group, index, value):
        undo.append((group, index, group.values[index]))
        group.values[index] = value

    if bars is not None:
        occupation = fields['occupation_series'].value
        need(not records and (occupation is None or not catalogs.array(occupation))
             and fields['axis_types'].values == [0, 0], 'Offline bars require a numeric Plot without lines or occupation data')
        if bars.series:
            check_bar_versions(writer.objects(root))
        replaceable_bars(fields['bars'].value, counts)
        rows = native_bars(bars.series)
        replace(fields['bars'], 0, arr(rows))
        extents = bar_extents(rows)
        replace(fields['data_minimum'], 0, point(*extents[:2]) if extents else None)
        replace(fields['data_maximum'], 0, point(*extents[2:]) if extents else None)
        if extents is not None and bars.fit_viewport:
            low, high, _ = plot_viewport(extents, [0, 0], [None, None])
            axes = {**{f'{axis}_range': {'minimum': float(low[index]), 'maximum': float(high[index])}
                       for index, axis in enumerate(('x', 'y'))}, **axes}

    edited_delay_bar = None
    if runtime_delay_bar is not None:
        occupation = fields['occupation_series'].value
        need(not records and (occupation is None or not catalogs.array(occupation))
             and fields['axis_types'].values == [0, 0], 'Runtime delay requires a numeric Plot without lines or occupation data')
        bar_slot = fields['bars']
        saved_bars = owned_array(bar_slot.value, counts, 'bar series') if bar_slot.value is not None else []
        x_slot = fields['x_markers']
        x_groups = (owned_array(x_slot.value, counts, 'X-axis marker groups')
                    if runtime_delay_bar and x_slot.value is not None else [])
        if saved_bars or not runtime_delay_bar:
            edited_delay_bar = delay_bar_for_update(saved_bars, counts)
            need(not runtime_delay_bar or x_slot.value is not None, 'Runtime delay requires its native X-axis marker array')
            replace(edited_delay_bar.contents[6], 1, DELAY_BAR_ONLINE if runtime_delay_bar else DELAY_BAR_PAUSED)
        else:
            need(not x_groups, 'A blank X-axis marker array is required to enable runtime delay')
            objects = writer.objects(root)
            check_bar_versions(objects)
            need(version_set(objects, 'OTPlotAxisLegend') <= {0}, 'Unsupported native Plot axis marker version')
            bar, markers = runtime_delay_seed()
            replace(bar_slot, 0, arr([bar]))
            replace(x_slot, 0, markers)
            axes = {'x_title': '', 'y_title': 's', **axes}

    if axis_marker_groups is not None:
        need(version_set(writer.objects(root), 'OTPlotAxisLegend') <= {0}, 'Unsupported native Plot axis marker version')
        for axis in ('x', 'y'):
            groups = getattr(axis_marker_groups, axis)
            if groups is None:
                continue
            slot = fields[f'{axis}_markers']
            if slot.value is not None:
                replaceable_markers(slot.value, counts)
            replace(slot, 0, native_markers(groups))

    for key in ('x_title', 'y_title'):
        if key in axes:
            replace(fields[key], 0, string(axes[key]))
    flags = fields['flags'].value
    for key, bit in GRID_FLAGS.items():
        if key in axes:
            need(model.clazz.version == 4 or bit < 64, 'Legend visibility requires native PlotModel4')
            flags = flags | bit if axes[key] else flags & ~bit
    if flags != fields['flags'].value:
        replace(fields['flags'], 0, flags)

    if any(f'{axis}_range' in axes for axis in ('x', 'y')):
        points = [fields[key].value for key in ('minimum', 'maximum')]
        values = [list(point.contents[0].values) for point in points]
        for index, axis in enumerate(('x', 'y')):
            if f'{axis}_range' not in axes:
                continue
            bounds = axes[f'{axis}_range']
            minimum, maximum = (flt(bounds[key], 'Plot visible bound') for key in ('minimum', 'maximum'))
            need(minimum < maximum, 'Plot bounds must increase in native binary32 precision')
            values[0][index], values[1][index] = minimum, maximum
        for field, reference_point, coordinates in zip(('minimum', 'maximum'), points, values, strict=True):
            # The original Inspector replaces visible-point objects instead of touching a shared data point.
            replace(fields[field], 0, replacement_point(reference_point, coordinates))
        for index, kind in enumerate(fields['axis_types'].values):
            replace(fields['increments'], index, axis_increment(values[0][index], values[1][index], kind))

    for item in series:
        record = named_line(records, item['index'], item['expected_name'])
        need(counts[id(record)] == 1, 'Shared Plot series cannot be edited independently')
        changes = item['changes']
        if 'name' in changes:
            replace(record.contents[1], 0, string(changes['name']))
        if 'line_width' in changes:
            width = flt(changes['line_width'], 'Plot series line width')
            need(width > 0, 'Plot line width collapses in the native format')
            replace(record.contents[3], 0, width)
        if 'overwrite_data' in changes or 'plot_online' in changes:
            replace(record.contents[6], 1, line_run_flags(record, changes))

    after = describe(model)
    annotations = {key: writer.dump_verified(fields[key].value) for key in ('bars', 'x_markers', 'y_markers')
                   if (key == 'bars' and edited_delay_bar is not None) or any(group is fields[key] for group, _, _ in undo)}
    output = writer.dump_verified(root, stream)
    for group, index, value in reversed(undo):
        group.values[index] = value
    need(writer.fingerprint(root) == signature, 'An unrelated native field or reference changed')
    loaded = load_worksheet(output)[2][plot_id]
    need(describe(loaded) == after, 'Fresh native Plot options differ')
    cold_fields = plot_fields(loaded)
    need(all(writer.dump_verified(cold_fields[key].value) == data for key, data in annotations.items()),
         'Fresh native Plot bar points or axis markers differ')
    return output, {'before': before, 'after': after, 'original_object_graph_preserved_outside_edits': True,
                    'fresh_archive_reload_verified': True}


def checked_native_line(record):
    points = check_series(record)
    for point in points:
        catalogs.shape(point, 'OTPlotPoint', 0, ['ff'])
        need(all(math.isfinite(coordinate) for coordinate in point.contents[0].values), 'Nonfinite native line point')
    color = record.contents[4].value
    need(writer.kind(color) == 'NSColor' and color.clazz.version == 0
         and [group.encodings for group in color.contents] in ([[b'c'], [b'f', b'f']], [[b'c'], [b'f'] * 4]),
         'Unrecognized native line color')
    catalogs.hierarchy(color)
    minimum_x, minimum_y, maximum_x, maximum_y = record.contents[2].values
    need(all(math.isfinite(value) for value in record.contents[2].values)
         and minimum_x <= maximum_x and minimum_y <= maximum_y, 'Invalid saved native line data bounds')
    if record.clazz.version == 1:
        if record.contents[5].value is not None:
            catalogs.text(record.contents[5].value)
        need(0 <= record.contents[6].values[1] <= 15, 'Unrecognized native line options')
    return points


def fit_line_viewport(rows, kinds):
    # The native minDataPoint/maxDataPoint methods aggregate cached line extents.
    # In the automatic visible-points method, time uses 600-second boundaries.
    point_counts = [len(checked_native_line(record)) for record in rows]
    need(any(point_counts), 'Fitting requires nonempty saved line data')
    extents = [record.contents[2].values for record in rows]
    bounds = [[], []]
    increments = []
    for i, kind in enumerate(kinds):
        low, high = min(extent[i] for extent in extents), max(extent[i + 2] for extent in extents)
        need(math.isfinite(low) and math.isfinite(high) and low < high, 'Fitting requires two nondegenerate line axes')
        increment = axis_increment(low, high, kind)
        base = 600.0 if kind == 1 else float(increment)
        bounds[0].append(flt(math.floor(low / base) * base, 'Fitted plot minimum'))
        bounds[1].append(flt(math.ceil(high / base) * base, 'Fitted plot maximum'))
        increments.append(increment)
    return bounds, increments


def version_set(objects, name):
    encoded = name.encode('ascii')
    versions = {version for item in objects for classname, version in class_signature(item.clazz)
                if classname == encoded}
    need(len(versions) <= 1, f'Existing worksheet has conflicting {name} classes')
    return versions


def check_bar_versions(objects):
    for classname, version in (('OTPlot', 1), ('OTBarPlot', 0), ('OTBarPoint', 1)):
        need(version_set(objects, classname) <= {version}, f'Offline bars require native {classname} v{version}')


def point_file_data(spec, files):
    path = spec['source']['path']
    return read_point_data(files[path], path, spec.get('name'))


def ensure_axes(data, kinds, titles):
    need(tuple(kinds) == data.axes, 'Point file and destination must use the same native axis types')
    need(all(provided is None or expected is None or expected == provided
             for expected, provided in zip(titles, data.captions, strict=True)),
         'Point file and destination must use compatible axis captions')


def point_receipt(data, rows, index):
    version = rows[0].clazz.version
    saved_metadata = None
    if version == 1:
        kind, flags = rows[0].contents[6].values
        saved_metadata = {'course_id': writer.string(rows[0].contents[5].value),
                          'plot_type': kind, 'option_flags': flags}
    return {'action': 'insert_external_series', 'index': index, 'name': data.name,
            'series_count': len(rows), 'point_counts': [len(column) for column in data.columns],
            'description': data.description, 'axis_types': list(data.axes),
            'archived_line_version': version, 'saved_course_and_options': saved_metadata}


def verify_imported_lines(rows, imported):
    for row, expected in zip(rows, imported, strict=True):
        if expected is not None:
            need(read_points(row) == list(expected),
                 'Points from the external file differ on native readback')
            need(row.contents[2].values == bounds(expected),
                 'Saved external line bounds differ on native readback')


def line_extents(records):
    extents = [record.contents[2].values for record in records]
    if extents:
        return [min(row[i] for row in extents) for i in (0, 1)] + [max(row[i] for row in extents) for i in (2, 3)]
    return None


def edit_series_archive(raw, plot_id, operations, viewport, donor_blobs, point_files=None, *, fit_empty=False):
    root, stream, models = load_worksheet(raw)
    model = models.get(plot_id)
    need(model is not None, 'No matching owned Plot graphic ID')
    counts = incoming_counts(root)
    fields = plot_fields(model)
    line_array = fields['series'].value
    need(counts[id(model)] == counts[id(line_array)] == 1 and writer.kind(line_array) == 'NSMutableArray',
         'Plot lifecycle requires one owned native mutable line array')
    before, signature = describe(model), writer.fingerprint(root)
    records = list(catalogs.array(line_array))
    imported = [None] * len(records)
    versions = version_set(writer.objects(root), 'OTPlot')
    titles = [catalogs.text(fields[f'{axis}_title'].value) for axis in ('x', 'y')]
    donor_graphs = {None: load_worksheet(raw)[2], **{key: load_worksheet(data)[2] for key, data in donor_blobs.items()}}
    receipts = []
    for operation in operations:
        index = operation['index']
        if operation['action'] == 'delete_series':
            selected = named_line(records, index, operation['expected_name'])
            need(counts.get(id(selected), 1) == 1, 'Shared Plot series cannot be removed independently')
            records.pop(index)
            imported.pop(index)
            receipts.append({'action': 'delete_series', 'index': index, 'name': operation['expected_name']})
            continue

        need(0 <= index <= len(records), 'Insertion index must identify a line position including the end')
        if operation['action'] == 'insert_external_series':
            data = point_file_data(operation, point_files or {})
            ensure_axes(data, fields['axis_types'].values, titles)
            version = next(iter(versions), 1)
            need(version in (0, 1), 'Unsupported native line archive version')
            rows = archived_lines(data, version)
            records[index:index] = rows
            imported[index:index] = data.columns
            versions.add(version)
            receipts.append(point_receipt(data, rows, index))
            continue

        spec = operation['donor']
        external = spec.get('worksheet')
        key = external['path'] if external else None
        donor = donor_graphs[key].get(spec['plot_id'])
        need(donor is not None, 'No matching native source Plot graphic ID')
        donor_fields = plot_fields(donor)
        need(fields['axis_types'].values == donor_fields['axis_types'].values
             and all(catalogs.text(fields[f'{axis}_title'].value) == catalogs.text(donor_fields[f'{axis}_title'].value)
                     for axis in ('x', 'y')), 'Source and destination must use the same saved axis types and captions')
        source = named_line(catalogs.array(donor_fields['series'].value), spec['index'], spec['expected_name'])
        points = checked_native_line(source)
        version = source.clazz.version
        need(not versions or version in versions, 'Source line class differs from the destination worksheet')
        if external and version == 1:
            need(source.contents[6].values[1] & 10 == 0, 'Active online or overwrite series requires its original worksheet')
        inserted = deepcopy(source)
        name = operation.get('name')
        if name is not None:
            inserted.contents[1].value = string(name)
        records.insert(index, inserted)
        imported.insert(index, None)
        versions.add(version)
        receipts.append({'action': 'insert_existing_series', 'index': index, 'name': catalogs.text(inserted.contents[1].value),
                         'donor_plot_id': spec['plot_id'], 'donor_index': spec['index'], 'donor_worksheet': key,
                         'point_count': len(points)})

    array_copy = writer.GenericArchivedObject(line_array.clazz, contents=[])
    writer.set_elements(array_copy, records)
    undo = {'series': line_array}
    fields['series'].value = array_copy
    if any(line is not None for line in imported):
        extents = line_extents(records)
        for key, coordinates in zip(('data_minimum', 'data_maximum'), (extents[:2], extents[2:]), strict=True):
            undo[key] = fields[key].value
            fields[key].value = point(*coordinates)
    empty_viewport = not before['series'] and any(
        bounds['minimum'] >= bounds['maximum']
        for bounds in (before['axes']['x_range'], before['axes']['y_range']))
    autofit = fit_empty and empty_viewport and any(line is not None for line in imported)
    kinds = fields['axis_types'].values
    if autofit:
        low, high, increments = plot_viewport(line_extents(records), kinds, (None, None))
        fitted = (low, high)
    elif viewport == 'fit_line_data':
        fitted, increments = fit_line_viewport(records, kinds)
    else:
        fitted = None
    if fitted:
        for key, coordinates in zip(('minimum', 'maximum'), fitted, strict=True):
            undo[key] = fields[key].value
            fields[key].value = replacement_point(fields[key].value, coordinates)
        prior_increments = fields['increments'].values.copy()
        fields['increments'].values[:] = increments
    after = describe(model)
    output = writer.dump_verified(root, stream)
    for key, value in undo.items():
        fields[key].value = value
    if fitted:
        fields['increments'].values[:] = prior_increments
    need(writer.fingerprint(root) == signature, 'An unrelated native field or reference changed')
    loaded = load_worksheet(output)[2][plot_id]
    need(describe(loaded) == after, 'Fresh native line array or viewport differs')
    verify_imported_lines(catalogs.array(plot_fields(loaded)['series'].value), imported)
    return output, {'before': before, 'after': after,
                    'viewport': 'fit_line_data' if autofit else viewport, 'operations': receipts,
                    'fresh_archive_reload_verified': True, 'original_object_graph_preserved_outside_edits': True}


def plot_viewport(data_bounds, kinds, explicit):
    low, high = [], []
    for index, (kind, manual) in enumerate(zip(kinds, explicit, strict=True)):
        if manual is not None:
            lo, hi = manual.minimum, manual.maximum
        elif data_bounds is None:
            lo, hi = 0, 1
        else:
            lo, hi = data_bounds[index], data_bounds[index + 2]
            constant = lo == hi
            if constant:
                span = max(abs(float(lo)) * .01, 1.0)
                lo, hi = float(lo) - span, float(hi) + span
            if kind == 1 or not constant:
                step = 600.0 if kind == 1 else axis_increment(lo, hi, kind)
                lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step
        lo, hi = flt(float(lo), 'Plot visible minimum'), flt(float(hi), 'Plot visible maximum')
        need(lo < hi, 'Plot bounds must increase in native binary32 precision')
        low.append(lo)
        high.append(hi)
    return low, high, [axis_increment(lo, hi, kind) for lo, hi, kind in zip(low, high, kinds, strict=True)]


def axis_font():
    # Current Windows NSFont21 archive for Helvetica 8pt, as saved in Demo and Training.
    style = b'\x05\x00\x00\x00\t\x00\x00\x00Helvetica\x00\x00\x00'
    return obj([('NSFont', 21), ('NSObject', 0)], [
        ('i', [len(style)]), (f'[{len(style)}c]', [writer.Array(style)]), ('f', [8.0]),
        ('c', [0]), ('c', [1]), ('c', [0]), ('c', [0]),
    ])


def create_plot_archive(raw, args, file_blobs):
    root, stream, _ = load_worksheet(raw)
    need(root.clazz.version in (3, 4), 'Creating a Plot requires an OTDocument3/4 worksheet')
    objects = writer.objects(root)
    versions = version_set(objects, 'OTPlotModel')
    plot_version = next(iter(versions), 4 if root.clazz.version == 4 else 3)
    graphic = next(iter(version_set(objects, 'OTGraphicModel')), 1)
    series_version = next(iter(version_set(objects, 'OTPlot')), 1)
    need(plot_version in (3, 4) and graphic in (0, 1) and series_version in (0, 1)
         and version_set(objects, 'NSFont') <= {21}, 'Unreviewed native Plot class combination')
    datasets = [point_file_data(spec.model_dump(), file_blobs) for spec in args.point_files]
    kinds = datasets[0].axes if datasets else (0, 0)
    titles = [next((dataset.captions[i] for dataset in datasets if dataset.captions[i] is not None), None)
              for i in (0, 1)]
    records, receipts, imported = [], [], []
    for data in datasets:
        ensure_axes(data, kinds, titles)
        rows = archived_lines(data, series_version)
        receipts.append(point_receipt(data, rows, len(records)))
        records.extend(rows)
        imported.extend(data.columns)

    data_bounds = line_extents(records)
    bars = []
    if args.bar_series or args.runtime_delay_bar:
        check_bar_versions(objects)
    if args.bar_series:
        bars = native_bars(args.bar_series)
        data_bounds = bar_extents(bars)
    markers = args.axis_marker_groups
    if markers is not None or args.runtime_delay_bar:
        need(version_set(objects, 'OTPlotAxisLegend') <= {0}, 'Unsupported native Plot axis marker version')
    x_markers, y_markers = (native_markers(getattr(markers, axis, None) or []) for axis in ('x', 'y'))
    if args.runtime_delay_bar:
        bar, x_markers = runtime_delay_seed()
        bars = [bar]
    occupancy = [plot_from_file(file_blobs[spec.source.path], spec) for spec in args.occupation_files]
    if occupancy:
        kinds = (1, 0)
        titles = ['Time', '']
        need(len({receipt['resource'] for _, _, receipt in occupancy}) == len(occupancy),
             'Include each occupation resource once')
        need(sum(len(points) for _, points, _ in occupancy) <= 200000,
             'The new occupation plot exceeds 200,000 timed events')
        data_bounds = [min(receipt['time_bounds_s'][0] for _, _, receipt in occupancy), 0.0,
                       max(receipt['time_bounds_s'][1] for _, _, receipt in occupancy), 1.0]
        receipts.extend(receipt for _, _, receipt in occupancy)
    viewport_bounds = bar_extents(bars) if args.runtime_delay_bar else data_bounds
    lo, hi, increments = plot_viewport(viewport_bounds, kinds, [args.x_range, args.y_range])
    defaults = ('', 's') if args.runtime_delay_bar else (('', '') if datasets or bars else ('[km]', '[km/h]'))
    captions = [requested if requested is not None else (stored if stored is not None else default)
                for requested, stored, default in zip(
                    (args.x_title, args.y_title), titles, defaults, strict=True)]
    group = root.contents[2]
    source_array = group.value
    need(writer.kind(source_array) == 'NSMutableArray' and incoming_counts(root)[id(source_array)] == 1,
         'An owned native worksheet graphic list is required')
    other_models = catalogs.array(source_array)
    plot_id = max((item.contents[0].value for item in other_models), default=-1) + 1
    need(plot_id < 2**31, 'Worksheet Graphic ID exhausted')
    x, y, width, height = [flt(getattr(args.frame, dim), 'Plot frame') for dim in ('x', 'y', 'width', 'height')]
    color_fill, color_border = gray(1.0), gray(0.0)
    plot = obj([('OTPlotModel', plot_version), ('OTResizeModel', 0), ('OTGraphicModel', graphic), ('NSObject', 0)], [
        ('i', [plot_id]), ('f', [0.0]), ('f', [flt(float(x) + 2, 'Plot anchor x')]),
        ('f', [flt(float(y) + height - 2, 'Plot anchor y')]), ('i', [0]), ('i', [0]),
        *([('@', [None])] if graphic else []),
        ('if', [1, 1.0]), ('ff', [x, y]), ('ff', [width, height]), ('@', [color_fill]), ('@', [color_border]),
        ('@', [arr(records)]), ('@', [x_markers]), ('@', [y_markers]), ('@', [point(*lo)]), ('@', [point(*hi)]),
        ('@', [point(*data_bounds[:2]) if data_bounds else None]),
        ('@', [point(*data_bounds[2:]) if data_bounds else None]),
        ('ff', increments), ('ffff', [40.0, 40.0, 35.0, 30.0]), ('ii', list(kinds)),
        ('@', [arr(series for series, _, _ in occupancy)]),
        ('i', [192 if plot_version == 4 else 0]), ('@', [arr(bars)]),
        ('@', [string(captions[0])]), ('@', [string(captions[1])]), ('@', [axis_font()]),
    ])
    original_graph = writer.fingerprint(root)
    source_array.contents[0].value = len(other_models) + 1
    source_array.contents.append(writer.TypedValue(b'@', plot))
    result = writer.dump_verified(root, stream)
    cold, _, plots = load_worksheet(result)
    saved = plots[plot_id]
    need(describe(saved) == describe(plot), 'Freshly saved native Plot settings differ')
    verify_imported_lines(catalogs.array(plot_fields(saved)['series'].value), imported)
    saved_occupancy = catalogs.array(plot_fields(saved)['occupation_series'].value)
    need([saved_points(series) for series in saved_occupancy] == [points for _, points, _ in occupancy],
         'Fresh original occupation data differs')
    saved_fields, planned_fields = plot_fields(saved), plot_fields(plot)
    need(all(writer.dump_verified(saved_fields[key].value) == writer.dump_verified(planned_fields[key].value)
             for key in ('bars', 'x_markers', 'y_markers')), 'Fresh native Plot bar points or axis markers differ')
    cold_array = cold.contents[2].value
    need(cold_array.contents[-1].value is saved, 'New Plot is not the last saved worksheet graphic')
    cold_array.contents.pop()
    cold_array.contents[0].value = len(other_models)
    need(writer.fingerprint(cold) == original_graph, 'Original worksheet changed outside the new native Plot')
    return result, {'plot': describe(saved), 'frame_xywh': [x, y, width, height], 'operations': receipts,
                    'original_object_graph_preserved_outside_edits': True, 'fresh_archive_reload_verified': True}


class PlotTools(ArchiveTools):
    def source(self, spec):
        path = self.path(spec.path)
        if path.suffix.casefold() != '.opentrack':
            raise APIError('NATIVE_PLOT_SOURCE', 'An ordinary native .opentrack worksheet is required')
        raw = self.secure_bytes(path)
        if sha(raw) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'Plot source differs from the requested SHA-256')
        return path, raw

    def inspect(self, args):
        _, raw = self.source(args.source)
        try:
            root, _, models = load_worksheet(raw)
            return {'worksheet_version': root.clazz.version, 'source_sha256': sha(raw),
                    'plots': [describe(model, include_bar_points=args.include_bar_points) for model in models.values()]}
        except (ValueError, TypeError, IndexError, AttributeError, OverflowError) as exc:
            raise APIError('NATIVE_PLOT_INVALID', str(exc)[:500]) from exc

    def edit(self, args):
        source, raw = self.source(args.source)
        try:
            axes = args.axes.model_dump(exclude_unset=True) if args.axes else {}
            output, receipt = edit_archive(raw, args.plot_id, axes, [edit.model_dump(exclude_unset=True) for edit in args.series],
                                           bars=args.bars, runtime_delay_bar=args.runtime_delay_bar,
                                           axis_marker_groups=args.axis_marker_groups)
        except (ValueError, TypeError, IndexError, AttributeError, OverflowError) as exc:
            raise APIError('NATIVE_PLOT_INVALID', str(exc)[:500]) from exc
        return self.publish(args, source, raw, output, receipt)

    def edit_series(self, args):
        source, raw = self.source(args.source)
        specs = [action.source for action in args.operations if isinstance(action, InsertExternalLine)]
        points, inputs = self.point_inputs(specs, source, raw)
        donors = {}
        for operation in args.operations:
            if not isinstance(operation, InsertLine) or operation.donor.worksheet is None:
                continue
            spec = operation.donor.worksheet
            path, data = self.source(spec)
            if (path == source and data != raw) or (path in inputs and inputs[path] != data):
                raise APIError('SOURCE_CHANGED', 'Plot worksheet changed during the transaction snapshot')
            donors[spec.path] = data
            inputs[path] = data
        try:
            operations = [action.model_dump(exclude_none=True) for action in args.operations]
            output, receipt = edit_series_archive(raw, args.plot_id, operations, args.viewport, donors, points,
                                                  fit_empty='viewport' not in args.model_fields_set)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            raise APIError('NATIVE_PLOT_SERIES_INVALID', str(exc)[:500]) from exc
        receipt['donor_sha256'] = {name: sha(bytes_) for name, bytes_ in donors.items()}
        if points:
            receipt['point_file_sha256'] = {name: sha(bytes_) for name, bytes_ in points.items()}
        return self.publish(args, source, raw, output, receipt, inputs)

    def point_inputs(self, specs, worksheet, original):
        points, inputs = {}, {}
        for spec in specs:
            path = self.path(spec.path)
            data = self.secure_bytes(path)
            if (data is None or sha(data) != spec.sha256 or (path in inputs and inputs[path] != data)
                    or (path == worksheet and data != original)):
                raise APIError('SOURCE_CHANGED', 'Plot point file differs from its requested SHA-256')
            points[spec.path] = data
            inputs[path] = data
        return points, inputs

    def create(self, args):
        source, raw = self.source(args.source)
        point_files, inputs = self.point_inputs([spec.source for spec in (*args.point_files, *args.occupation_files)],
                                               source, raw)
        try:
            output, receipt = create_plot_archive(raw, args, point_files)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            raise APIError('NATIVE_PLOT_INVALID', str(exc)[:500]) from exc
        receipt['point_file_sha256'] = {name: sha(bytes_) for name, bytes_ in point_files.items()}
        return self.publish(args, source, raw, output, receipt, inputs)

    def publish(self, args, source, raw, output, receipt, additional=None):
        result = {'saved': False, 'preview_only': args.preview_only, 'source_sha256': sha(raw),
                  'output_sha256': sha(output), 'output_bytes': len(output), **receipt}
        inputs = {source: raw, **(additional or {})}
        if args.preview_only:
            if any(self.secure_bytes(path) != saved for path, saved in inputs.items()):
                raise APIError('SOURCE_CHANGED', 'A Plot worksheet changed during preview')
            return result
        if self.path(args.target_path).suffix.casefold() != '.opentrack':
            raise APIError('NATIVE_PLOT_TARGET', 'Use a fresh .opentrack worksheet target')
        if len(output) > 20 * 1024 * 1024:
            raise APIError('ARCHIVE_SIZE', 'Generated worksheet exceeds 20 MiB')
        return self.save_copy(source, raw, output, result, args.target_path, additional_inputs=additional,
                              validate_output=load_worksheet)


def tool_definitions(root):
    api = PlotTools(root)
    return [('opentrack_inspect_saved_plot_settings', 'Inspect editable native Plot graphs and their inline series.',
             ReadPlot, api.inspect),
            ('opentrack_edit_saved_plot_settings', 'Write native Plot axes, grid, line appearance, offline bars, runtime delay or axis marker groups '
             'to a fresh OpenTrack worksheet. Preserve unselected series and graphics.',
             EditPlot, api.edit, False, False),
            ('opentrack_edit_saved_plot_series', 'Copy native line data, insert editable lines from a numeric point '
             'file, or delete a selected saved line. Preserve the viewport or fit the remaining line data.',
             EditPlotSeries, api.edit_series, False, False),
            ('opentrack_create_saved_plot', 'Create an editable native worksheet Plot with a blank viewport, offline bars, '
             'active simulation delay, OpenTrack numeric line or occupation file data, with optional axis marker groups.',
             CreatePlot, api.create, False, False)]
