"""Original numeric Plot text and independent archived OTPlot line records."""

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Annotated

from pydantic import Field, StrictStr

from . import writer
from .bundle_tools import Source
from .multi_document.core import need
from .tools import Input
from .zero_generation.native_signal_routes import arr, obj, string
from .zero_generation.topology import flt


Caption = Annotated[StrictStr, Field(max_length=200, pattern=r'^[ -~]*$')]
NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
PLOT_AXES = {'OT_Plot': (0, 0), 'OT_TimeXPlot': (1, 0), 'OT_TimeYPlot': (0, 1)}
# OTPlotModel.readPlotFromExternal: type, capabilities (OD and PO), and initial width.
COURSE_STYLE = {
    'OT_vs': (4, 5, 2.0), 'OT_vs2': (4, 1, 2.0), 'OT_vsb': (57, 0, 0.5),
    'OT_vt': (5, 5, 2.0), 'OT_at': (7, 5, 2.0), 'OT_as': (6, 5, 2.0),
    'OT_st1': (3, 5, 2.0), 'OT_st2': (3, 1, 2.0),
    'OT_ts1': (27, 5, 2.0), 'OT_ts2': (27, 1, 2.0),
    'OT_step1': (28, 1, 1.0), 'OT_step2': (29, 1, 1.0),
    'OT_ms': (30, 1, 1.0), 'OT_PowerSupply': (64, 1, 1.0),
}


class PointFile(Input):
    source: Source
    name: Caption | None = None


@dataclass(frozen=True)
class PointData:
    name: str
    axes: tuple[int, int]
    captions: tuple[str | None, str | None]
    description: str | None
    course_id: str | None
    columns: tuple[tuple[tuple[float, float], ...], ...]


def read_point_data(raw, path, name=None):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    filename = PurePosixPath(path.replace('\\', '/')).name
    stem = PurePosixPath(filename).stem
    columns = [[] for _ in range(5)]
    fields = {}
    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('//'):
            key, separator, value = line[2:].partition(':')
            key, value = key.strip(), value.strip()
            net_key = key.casefold() if separator else ''
            if net_key == 'desc.' and not re.match(r'//\s*Desc\.\s+:', line):
                # The output header also contains a free-text "// Desc.:" before the typed descriptor.
                continue
            if net_key in {'type', 'desc.', 'x-legend', 'y-legend'}:
                need(net_key not in fields or fields[net_key] == value, f'Conflicting Plot header on line {number}')
                fields[net_key] = value
            continue
        tokens = line.split()
        need(2 <= len(tokens) <= 6 and all(NUMBER.fullmatch(token) for token in tokens),
             f'Expected X and one to five numeric Y columns on line {number}')
        x, *ys = [flt(float(token), f'Plot coordinates on line {number}') for token in tokens]
        for column, value in zip(columns, ys):
            column.append((x, value))
    need(columns[0], 'The point file has no numeric data')
    kind = fields.get('type', 'OT_Plot')
    need(kind in PLOT_AXES, f'Expected a numeric line Plot file, got {kind}')
    description = fields.get('desc.')
    need(description not in {'OT_occ', 'OT_ins', 'OT_delayact'}, 'A specialist Plot result needs its own reader')
    axes = (PLOT_AXES[kind][0], 2) if description == 'OT_tunnel' else PLOT_AXES[kind]
    titles = []
    for axis, key in zip(axes, ('x-legend', 'y-legend'), strict=True):
        caption = fields.get(key)
        if axis == 1:
            caption = 'Time'
        elif axis == 2:
            caption = ''
        elif caption is not None and caption.casefold() == 'none':
            caption = None
        titles.append(caption)
    return PointData(name if name is not None else filename, axes, tuple(titles), description,
                     stem[3:] if stem.startswith('OT_') else None,
                     tuple(tuple(column) for column in columns if column))


def point(x, y):
    return obj([('OTPlotPoint', 0), ('NSObject', 0)], [('ff', [x, y])])


def gray(value):
    return obj([('NSColor', 0), ('NSObject', 0)], [('c', [3]), ('ff', [value, 1.0])])


def bounds(points):
    return [min(value[i] for value in points) for i in (0, 1)] + [max(value[i] for value in points) for i in (0, 1)]


def archived_lines(data, version):
    kind, flags, width = COURSE_STYLE.get(data.description, (0, 0, 1.0))
    rows = []
    for column in data.columns:
        fields = [
            ('@', [arr(point(x, y) for x, y in column)]),
            ('@', [string(data.name)]),
            ('ffff', bounds(column)),
            ('fi', [width, 0]),
            ('@', [gray(0.0)]),
        ]
        if version == 1:
            fields += [('@', [string(data.course_id) if data.course_id else None]), ('ii', [kind, flags])]
        rows.append(obj([('OTPlot', version), ('NSObject', 0)], fields))
    return rows


def read_points(record):
    return [tuple(point.contents[0].values) for point in writer.elements(record.contents[0].value)]
