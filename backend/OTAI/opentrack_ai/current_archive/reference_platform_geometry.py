"""Optional native drawing of a platform alongside its physical track edge."""

import math
import struct

from . import route_factory, writer
from .multi_document import core
from .zero_generation import native_signal_routes


RECTANGLE_CLASS = [
    ('OTRectModel', 0), ('OTResizeModel', 0), ('OTGraphicModel', 1), ('NSObject', 0),
]
PALETTE_CLASS = [('NSColor', 0), ('NSObject', 0)]
RECTANGLE_FIELDS = ['i', 'f', 'f', 'f', 'i', 'i', '@', 'if', 'ff', 'ff', '@', '@']


def _float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def _gray_palette(root):
    for color in writer.objects(root):
        if writer.kind(color) != 'NSColor':
            continue
        try:
            core.layout(color, PALETTE_CLASS, ['c', 'ff'])
        except ValueError:
            continue
        if color.contents[0].values == [3] and color.contents[1].values == [0.5, 1.0]:
            return color
    raise ValueError('The native document has no audited opaque gray drawing palette')


def add_platform_rectangle(blob, area, drawing_side, width_m=None):
    """Draw an OTRectModel from the native edge's horizontal graphic bounds."""
    root, version = writer.load_next_compatible(blob)
    models, by_id = route_factory.document(root)
    edge = by_id[area['area_edge_id']]
    left, right = (edge.contents[index].value for index in (7, 8))
    x1, y1 = (float(left.contents[index].value) for index in (2, 3))
    x2, y2 = (float(right.contents[index].value) for index in (2, 3))
    if not all(map(math.isfinite, (x1, y1, x2, y2))) or x1 == x2 or y1 != y2:
        raise ValueError('Platform graphics require one visible horizontal platform track edge')
    scale = abs(x2 - x1) / area['length_m']
    height = width_m * scale if width_m is not None else 12.0
    # Offset only the drawing, not the operational boundary or model coordinates.
    gap = 6.0
    x = _float32(min(x1, x2))
    y = _float32(y1 - gap - height if drawing_side == 'above' else y1 + gap)
    width_drawn, height_drawn = _float32(abs(x2 - x1)), _float32(height)
    if not all(map(math.isfinite, (y, width_drawn, height_drawn))) or height_drawn <= 0:
        raise ValueError('Platform drawing dimensions must fit the native drawing format')
    frame_origin = [_float32(x - 2), _float32(y - 3)]
    frame_size = [_float32(width_drawn + 5), _float32(height_drawn + 5)]
    if frame_size[1] <= 5:
        raise ValueError('Platform width is too small at the selected drawing scale')
    model_id = max(by_id) + 1
    if model_id > 2**31 - 1:
        raise ValueError('Platform drawing has no free native model ID')
    color = _gray_palette(root)
    values = [[model_id], [0.0], [x], [y], [0], [0], [None], [2, 1.0],
              frame_origin, frame_size, [color], [color]]
    graphic = native_signal_routes.obj(RECTANGLE_CLASS, list(zip(RECTANGLE_FIELDS, values)))
    # Keep the existing model-array encodings and reference aliases intact.
    model_array = root.contents[2].value
    model_array.contents[0].value = len(models) + 1
    model_array.contents.append(writer.TypedGroup([b'@'], [graphic]))
    output = writer.dump_verified(root, version)

    saved_root, saved_version = writer.load_next_compatible(output)
    saved_models, saved_ids = route_factory.document(saved_root)
    saved = saved_ids[model_id]
    core.layout(saved, RECTANGLE_CLASS, RECTANGLE_FIELDS)
    if (saved_models[-1] is not saved or saved.contents[8].values != frame_origin
            or saved.contents[9].values != frame_size
            or saved.contents[2].value != x or saved.contents[3].value != y):
        raise ValueError('Platform drawing failed native readback')
    saved_array = saved_root.contents[2].value
    saved_array.contents.pop()
    saved_array.contents[0].value = len(models)
    original, original_version = writer.load_next_compatible(blob)
    if writer.dump_verified(saved_root, saved_version) != writer.dump_verified(original, original_version):
        raise ValueError('Adding the platform drawing changed non-graphic objects')
    return output, {
        'model_id': model_id,
        'class': 'OTRectModel',
        'drawing_side': drawing_side,
        'drawing_rect': [x, y, width_drawn, height_drawn],
        'width_m': width_m,
        'width_scale': 'relative_to_platform_edge' if width_m is not None else 'schematic',
        'area_edge_id': area['area_edge_id'],
    }
