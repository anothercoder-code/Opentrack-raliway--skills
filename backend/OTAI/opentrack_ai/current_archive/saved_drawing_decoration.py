"""Move, style and import supported native standalone worksheet drawings."""

import math
import re

from . import path_functions, writer
from .graph_references import reference_inventory
from .multi_document.core import layout, need
from .saved_geometry import model_id, position
from .saved_rich_labels import encode_native_color, native_color
from .zero_generation.topology import flt, signature


_GRAPHIC_CHAIN = [('OTGraphicModel', 1), ('NSObject', 0)]
_GRAPHIC_FIELDS = ['i', 'f', 'f', 'f', 'i', 'i', '@']
_RESIZABLE = {'OTRectModel', 'OTLineModel', 'OTCircleModel'}
_SUPPORTED = _RESIZABLE | {'OTLabelModel', 'OTLogoModel'}
# OTGraphicView.updateGraphicRect removes five points from each view dimension.
_FRAME_MARGIN = 5.0
_RTF_TEXT = re.compile(rb'(?s)^(\{\\rtf0\\ansi\{\\fonttbl[^\r\n]+\}\r?\n'
                       rb'\\pard[^\r\n]+\r?\n\r?\n\\f0\\fs[0-9]+ \\cf0 \x08\x08)'
                       rb'([ -~]{1,64})(\}\r?\n)$')


def _drawing(root, mid):
    models = path_functions.mutable_array(root.contents[2].value)
    matches = [item for item in models if model_id(item) == mid]
    need(len(matches) == 1, 'A drawing must resolve exactly once in the native document')
    model = matches[0]
    kind = writer.kind(model)
    need(kind in _SUPPORTED and reference_inventory(root)[1][id(model)] == 1,
         'Only standalone native Drawings, Labels and Logos without graph observers are supported')
    if kind in _RESIZABLE:
        parents = [(kind, 0), ('OTResizeModel', 0), *_GRAPHIC_CHAIN]
        layout(model, parents, _GRAPHIC_FIELDS + ['if', 'ff', 'ff', '@', '@'])
        frame_index = 8
    elif kind == 'OTLabelModel':
        layout(model, [('OTLabelModel', 1), *_GRAPHIC_CHAIN],
               _GRAPHIC_FIELDS + ['@', 'ffff', '@', 'iii', '@', '@'])
        need(model.contents[9].value is None and model.contents[10].values[1:] == [0, 0],
             'Temporary or owner-bound labels need an explicit dependency contract')
        frame_index = 8
    else:
        layout(model, [('OTLogoModel', 1), *_GRAPHIC_CHAIN],
               _GRAPHIC_FIELDS + ['@', 'ff', 'ffff', 'i'])
        need(writer.kind(model.contents[7].value) in {'NSBitmapImageRep', 'NSEPSImageRep'},
             'Only known original bitmap or EPS image representations may be moved')
        frame_index = 9
    need(model.contents[6].value is None, 'Owner attachment is outside the standalone drawing contract')
    return model, frame_index


def _move(model, frame_slot, dx, dy):
    if dx == 0 and dy == 0:
        return
    for index, delta in enumerate((dx, dy)):
        frame = model.contents[frame_slot].values
        model.contents[index + 2].value = flt(float(model.contents[index + 2].value) + delta, 'Graphic coordinate')
        frame[index] = flt(float(frame[index]) + delta, 'Graphic frame coordinate')


def _label_text(model, text):
    need(writer.kind(model) == 'OTLabelModel' and re.fullmatch(r'[ -~]{1,64}', text)
         and not set(text).intersection('\\{}'), 'Text replacements require a native label and plain printable text')
    data = model.contents[7].value
    path_functions.hierarchy(data, [('NSMutableData', 0), ('NSData', 0), ('NSObject', 0)])
    size, payload = [group.value for group in data.contents]
    need(type(size) is int and 0 < size <= 1024 and data.contents[0].encodings == [b'i']
         and data.contents[1].encodings == [f'[{size}c]'.encode('ascii')] and isinstance(payload, writer.Array)
         and type(payload.elements) is bytes and len(payload.elements) == size, 'Unsupported native label data record')
    match = _RTF_TEXT.fullmatch(payload.elements)
    need(match is not None and not set(match[2]).intersection(b'\\{}'),
         'Label has formatted or unsupported RTF content')
    raw = match[1] + text.encode('ascii') + match[3]
    model.contents[7].value = writer.GenericArchivedObject(data.clazz, contents=[
        writer.TypedValue(b'i', len(raw)), writer.TypedValue(f'[{len(raw)}c]'.encode('ascii'), writer.Array(raw)),
    ])


def _resize_appearance(model):
    flags, line_width = model.contents[7].values
    size = model.contents[9].values
    need(flags in (0, 1, 2, 3), 'Expected native flipped and filled drawing flags')
    need(math.isfinite(line_width) and all(map(math.isfinite, size)), 'Expected finite native drawing dimensions')
    return {'frame_size_points': list(size), 'line_width_points': line_width,
            'flipped': bool(flags & 1), 'filled': bool(flags & 2),
            'fill_color': native_color(model.contents[10].value),
            'line_color': native_color(model.contents[11].value)}


def _apply_style(model, style):
    kind = writer.kind(model)
    need(kind in _RESIZABLE, 'Drawing style requires a standalone Line, Rectangle or Circle')
    before = _resize_appearance(model)
    fields = model.contents
    width, height = style.get('width_points'), style.get('height_points')
    if width is not None or height is not None:
        need(fields[1].value % 360 == 0, 'Size changes require an unrotated drawing')
        frame = fields[9].values
        resized = [old if value is None else flt(value + _FRAME_MARGIN, 'Drawing frame size')
                   for old, value in zip(frame, (width, height))]
        if kind == 'OTLineModel':
            need(min(resized) >= _FRAME_MARGIN and max(resized) > _FRAME_MARGIN, 'A line needs one positive dimension')
        else:
            need(min(resized) > _FRAME_MARGIN, 'A rectangle or circle needs two positive dimensions')
        frame[:] = resized
    if style.get('line_width_points') is not None:
        fields[7].values[1] = flt(style['line_width_points'], 'Drawing stroke width')
    if style.get('line_rgb') is not None:
        fields[11].value = encode_native_color(style['line_rgb'])
    if (line_flipped := style.get('line_flipped')) is not None:
        need(type(line_flipped) is bool and kind == 'OTLineModel' and fields[1].value % 360 == 0,
             'Diagonal orientation requires an unrotated standalone native Line and a Boolean flag')
        # OTLineView.calcDisplay chooses the endpoints from OTResizeModel's flipped bit.
        fields[7].values[0] = (fields[7].values[0] & ~1) | int(line_flipped)
    if style.get('filled') is not None or style.get('fill_rgb') is not None:
        need(kind != 'OTLineModel', 'Native lines use stroke appearance')
        if style.get('filled') is not None:
            fields[7].values[0] = (fields[7].values[0] & 1) | (2 * style['filled'])
        if style.get('fill_rgb') is not None:
            fields[10].value = encode_native_color(style['fill_rgb'])
    return before, _resize_appearance(model)


def verify_style(project, document, report):
    model, _ = _drawing(project.roots[document], report['graphic_id'])
    need(_resize_appearance(model) == report['drawing_style_after'], 'Drawing style changed during native readback')


def edit_decoration(project, document, operation):
    model, frame_slot = _drawing(project.roots[document], operation['graphic_id'])
    before = position(model)
    dx, dy = operation['delta_x'], operation['delta_y']
    text = operation['text']
    style = operation.get('drawing_style')
    need(dx != 0 or dy != 0 or text is not None or style, 'Supply a relocation, drawing style or label text')
    _move(model, frame_slot, dx, dy)
    if text is not None:
        _label_text(model, text)
    report = {'graphic_id': model_id(model), 'type': writer.kind(model), 'before_xy': before,
              'after_xy': position(model), 'text_changed': text is not None, 'image_payload_changed': False}
    if style is not None:
        report['drawing_style_before'], report['drawing_style_after'] = _apply_style(model, style)
    return report


def import_decoration(project, document, operation, donor):
    donor_root, donor_version = writer.load_next_compatible(donor)
    need(writer.kind(donor_root) == 'OTDocument' and donor_root.clazz.version in (3, 4)
         and donor_version == project.versions[document], 'Donor must be an original Document3/4 of the same stream version')
    model, frame_slot = _drawing(donor_root, operation['graphic_id'])
    target_root = project.roots[document]
    signatures = {obj.clazz.name: signature(obj.clazz) for obj in writer.objects(target_root)}
    for source in writer.objects(model):
        shape = signature(source.clazz)
        need(signatures.get(source.clazz.name, shape) == shape, 'Donor graphic references a conflicting class version')
        need(writer.kind(source) not in ('OTEndModel', 'OTConnModel', 'OTSignalModel', 'OTStationModel'),
             'Donor drawing is tied to infrastructure')
    new = path_functions.clone(model)
    mid = max(project.byid[document], default=-1) + 1
    need(mid < 2147483647, 'Graphic ID exhausted')
    new.contents[0].value = mid
    _move(new, frame_slot, operation['delta_x'], operation['delta_y'])
    if operation['text'] is not None:
        _label_text(new, operation['text'])
    field = target_root.contents[2]
    field.value = path_functions.array_like(field.value, [*project.models[document], new])
    report = {'graphic_id': mid, 'donor_graphic_id': model_id(model), 'type': writer.kind(new),
              'xy': position(new), 'text_changed': operation['text'] is not None, 'image_payload_changed': False}
    if (style := operation.get('drawing_style')) is not None:
        report['drawing_style_before'], report['drawing_style_after'] = _apply_style(new, style)
    return report
