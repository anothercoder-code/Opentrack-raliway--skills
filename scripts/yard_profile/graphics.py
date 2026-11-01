"""Four native rectangle graphics for the eight-track station drawing.

Pure immutable bytes in/out; no file writes, runtime calls, or platform business
semantics. The rectangles are schematic island-platform graphics. Their drawing
dimensions are not metres, stopping extents, passenger facilities, or capacity.

Contract: OTRectModel0 -> OTResizeModel0 -> OTGraphicModel1 -> NSObject0.
The stock coder adds no Rect fields; Resize adds if, ff, ff, @, @ after the
seven Graphic groups. Nonzero saved frame restores its visible dimensions.
OTGraphicView.updateGraphicRect insets frame x/y by2/3 and shrinks sizes by5.
Thus a desired visible(x,y,w,h) is saved as frame(x-2,y-3,w+5,h+5).
Resize flags2 means filled=True, flipped=False. There is no serialized control
point array: the native ResizeView supplies the ordinary X/Y resize handles.
"""
from __future__ import annotations

import copy
import hashlib
import math
import struct

from opentrack_ai.current_archive import writer as w, route_factory as rf

STOCK_EXE_SHA256 = 'f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104'
SOURCE_BANK = '20261027-bank-v027-timetable-export'
SOURCE_SHA256 = {
    'modules/02_infrastructure/classes/OTRectModel/metadata.json': '538921c0742c253ce18527945d62047b4f65807e3aa8b4b2a879031a4babe00b',
    'modules/02_infrastructure/classes/OTResizeModel/metadata.json': '62aa738dceb8a2c15a47cb230bd18835da2396e661c6acd9542e0d1bdda1f8d1',
    'modules/02_infrastructure/classes/OTGraphicModel/functions/004dbf90.c': '0fa6e677a0e975e6d76c292ef9586bff20501a9b5f017f39d78497e3fc9be63d',
    'modules/02_infrastructure/classes/OTGraphicModel/functions/004dcb30.c': 'dd56ef4dc02304d81960cf58c9452ba68afb574f7d61316911db423eb6a97a2b',
    'modules/02_infrastructure/classes/OTGraphicModel/functions/004dca18.c': 'ec59a252c7e5f8a447a523b066683d8b26435ea23be66cca5b6a1a1df877bfbd',
    'modules/02_infrastructure/classes/OTRectModel/functions/005a2858.c': 'db685b04b843869389791fcddc199899d36ee9494e635ffd3aa5061faa5a8684',
    'modules/02_infrastructure/classes/OTRectModel/functions/005a2828.c': '7b47eaf92767efe2afaa7ae965c8d411972bf2dabf074a7e6a7636a0ffabfc08',
    'modules/02_infrastructure/classes/OTResizeModel/functions/005a4764.c': '8f8f03208967b826c90d50d92b15d5a439bfb0caa785f7e8e3175c2ff9cd6c1a',
    'modules/02_infrastructure/classes/OTResizeModel/functions/005a4654.c': 'e27354ccdee2002ea5defc22bc689f5e5ca84f860e64c5b5d8f1bcfabf005a3c',
    'modules/02_infrastructure/classes/OTResizeModel/functions/005a43ac.c': 'efcbd9579bf2f873076ec0729d9cec6770facafffad44100e05fe805e14d804b',
    'modules/03_canvas/classes/OTResizeView/functions/005a4aec.c': 'ba4343004bbb590a55b6fd6738d94c2444e57bbdb0073b417f958df9d7700ebe',
    'modules/03_canvas/classes/OTResizeView/functions/005a4c94.c': '3d1cfcb9d33818fff646ba90cba20fccd36415f50dee87fb3c246a317b1122bf',
    'modules/03_canvas/classes/OTGraphicView/functions/004de430.c': '20439e8fcebe5c7f36f2652aacedf5a3e0f504c60f87ca6ac0eb9570b7501ea0',
    'modules/03_canvas/classes/OTRectView/functions/005a2924.c': 'c8e49d2fa07adf7e6b37c1f85e28b601a4fa86e97441dbbc1e087156252db6b9',
}
RECT_CHAIN = [('OTRectModel', 0), ('OTResizeModel', 0), ('OTGraphicModel', 1), ('NSObject', 0)]
RECT_ENCODINGS = ['i', 'f', 'f', 'f', 'i', 'i', '@', 'if', 'ff', 'ff', '@', '@']

PLATFORM_RECTS = tuple((140.0, y, 180.0, 44.0) for y in (118.0, 318.0, 518.0, 718.0))


class PlatformGraphicsError(ValueError):
    pass


def _need(ok, message):
    if not ok:
        raise PlatformGraphicsError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _chain(obj):
    result = []
    cls = obj.clazz
    while cls is not None:
        result.append((cls.name.decode('ascii'), cls.version))
        cls = cls.superclass
    return result


def _encodings(obj):
    return [b''.join(group.encodings).decode('ascii') for group in obj.contents]


def _f32(value):
    _need(type(value) in (int, float) and math.isfinite(value), 'Finite explicit drawing coordinate required')
    result = struct.unpack('<f', struct.pack('<f', value))[0]
    _need(math.isfinite(result) and abs(result) <= 1000005, 'Drawing value outside bounded binary32 domain')
    return result


def _read(blob):
    _need(type(blob) is bytes and bool(blob), 'Immutable nonempty document bytes required')
    root, version = w.load_next_compatible(blob)
    models, byid = rf.document(root)
    _need(root.contents[0].value == 17, 'Current Document marker17 required')
    _need(all(type(i) is int and 0 <= i <= 2147483647 for i in byid), 'Nonnegative unique local model IDs required')
    return root, version, models, byid


def _gray(color):
    _need(_chain(color) == [('NSColor', 0), ('NSObject', 0)], 'Only existing observed NSColor0 palette objects supported')
    _need(_encodings(color) == ['c', 'ff'], 'Only observed native white/alpha NSColor layout supported')
    _need(color.contents[0].values == [3], 'Only observed NSColor code3 palette object supported')
    white, alpha = color.contents[1].values
    _need(isinstance(white, (int, float)) and not isinstance(white, bool) and
          isinstance(alpha, (int, float)) and not isinstance(alpha, bool) and
          math.isfinite(white) and math.isfinite(alpha), 'Finite palette components required')
    _need(0 <= white <= 1 and alpha == 1, 'Opaque observed palette color required')
    return float(white), float(alpha)


def _palette(root):
    for color in w.objects(root):
        if w.kind(color) != 'NSColor':
            continue
        try:
            if _gray(color) == (0.5, 1.0):
                return color
        except PlatformGraphicsError:
            continue
    raise PlatformGraphicsError('Input document lacks an observed opaque NSColor0 gray0.5 palette object; no color schema is invented')


def _rectangle(model_id, rect, color):
    x, y, width, height = map(_f32, rect)
    _need(width > 0 and height > 0, 'Visible rectangle width/height must be positive')
    cls = None
    for name, version in reversed(RECT_CHAIN):
        cls = w.Class(name.encode('ascii'), version, cls)
    values = [[model_id], [0.0], [x], [y], [0], [0], [None], [2, 1.0],
              [_f32(x - 2), _f32(y - 3)], [_f32(width + 5), _f32(height + 5)], [color], [color]]
    return w.GenericArchivedObject(cls, None, [w.TypedGroup(w.split_types(e.encode('ascii')), v)
                                             for e, v in zip(RECT_ENCODINGS, values)])


def _inspect_rect(model, expected):
    _need(_chain(model) == RECT_CHAIN, 'Unexpected native rectangle class/version chain')
    _need(_encodings(model) == RECT_ENCODINGS, 'Unexpected native rectangle coder groups')
    _need(all(len(g.encodings) == len(g.values) for g in model.contents), 'Malformed rectangle group values')
    _need(model.contents[1].value == 0 and model.contents[4].value == model.contents[5].value == 0, 'Only unrotated0/0 rectangle profile supported')
    _need(model.contents[6].value is None, 'No invented native platform/label attachment supported')
    _need(model.contents[7].values == [2, 1.0], 'Expected native filled/unflipped2 and linewidth1')
    x, y, width, height = expected
    frame = list(model.contents[8].values) + list(model.contents[9].values)
    _need(frame == [x - 2, y - 3, width + 5, height + 5], 'Saved Resize frame differs from expected visible rectangle')
    _need([model.contents[2].value, model.contents[3].value] == [x, y], 'Graphic loc differs from visible rectangle origin')
    _need(_gray(model.contents[10].value) == _gray(model.contents[11].value) == (0.5, 1.0), 'Existing opaque gray palette not retained')
    return {'model_id': model.contents[0].value, 'visible_drawing_rect': list(expected), 'saved_view_frame': frame,
            'filled': True, 'flipped': False, 'line_width_drawing_units': 1.0,
            'source_palette_white_alpha': [0.5, 1.0], 'business_platform_or_length_fields': False}


def validate_platforms(blob: bytes) -> dict:
    """Fresh-decode exactly four expected native rectangle graphics; no GUI claim."""
    root, version, models, byid = _read(blob)
    rects = [o for o in models if w.kind(o) == 'OTRectModel']
    _need(len(rects) == 4, 'Exactly four island rectangle graphics required')
    rows = [_inspect_rect(model, rect) for model, rect in zip(rects, PLATFORM_RECTS)]
    reachable = [o for o in w.objects(root) if w.kind(o) == 'OTRectModel']
    _need({id(o) for o in reachable} == {id(o) for o in rects}, 'Hidden rectangle objects outside graphicArray')
    return {'passed': True, 'rectangle_count': 4, 'rectangles': rows, 'stream_version': version,
            'model_count': len(models), 'source_sha256': _sha(blob),
            'native_rectangle_coder_layout_verified': True, 'drawing_units_are_metres': False,
            'stopping_platforms_supported': False, 'native_graphics_visibility_runtime_verified': False,
            'native_application_executed': False}


def add_platforms(blob: bytes) -> tuple[bytes, dict]:
    """Append four schematic native filled rectangles and prove rollback.

    Caller performs railway/Station/service construction first: older business
    binders intentionally reject Rect models. This helper makes no such calls.
    The input must contain the existing gray0.5 opaque native palette sample.
    No external names or business lengths are serialized into the rectangles.
    """
    root, version, models, byid = _read(blob)
    _need(not any(w.kind(o) == 'OTRectModel' for o in w.objects(root)), 'Existing rectangles refused; no duplicate platform append')
    color = _palette(root)
    start = max(byid, default=-1) + 1
    _need(start + 3 <= 2147483647, 'Fresh native graphic ID domain exhausted')
    added = [_rectangle(start + i, rect, color) for i, rect in enumerate(PLATFORM_RECTS)]
    
    
    array = root.contents[2].value
    array.contents[0].value = len(models) + len(added)
    array.contents.extend(w.TypedGroup([b'@'], [model]) for model in added)
    output = w.dump_verified(root, version)
    validation = validate_platforms(output)
    checked, checked_version, checked_models, _ = _read(output)
    new_ids = set(range(start, start + 4))
    _need(len(checked_models) == len(models) + 4, 'Unexpected model count change')
    _need([o.contents[0].value for o in checked_models[-4:]] == sorted(new_ids), 'New rectangle suffix changed')
    checked_array = checked.contents[2].value
    checked_array.contents = checked_array.contents[:-4]
    checked_array.contents[0].value = len(models)
    original, original_version, _, _ = _read(blob)
    _need(w.dump_verified(checked, checked_version) == w.dump_verified(original, original_version), 'Removing only new rectangles did not restore the complete canonical original graph')
    receipt = {'operation': 'append_four_native_island_rectangle_graphics', 'input_sha256': _sha(blob),
               'output_sha256': _sha(output), 'previous_model_count': len(models), 'new_graphic_ids': sorted(new_ids),
               'validation': validation, 'full_canonical_input_graph_rollback_verified': True,
               'railway_objects_and_operating_geometry_changed': False,
               'palette_source': 'Existing input-document NSColor0(code3,white0.5,alpha1) reused without mutation',
               'source_bank': SOURCE_BANK, 'source_sha256': copy.deepcopy(SOURCE_SHA256),
               'original_stock_executable_sha256': STOCK_EXE_SHA256,
               'PE_type_string_evidence': {'0x007b4c8c': 'if', '0x007b4c8f': 'ff', '0x00771f3f': 'i', '0x00771f41': 'f'},
               'control_point_contract': 'No extra archived control-point array. Native ResizeView supports canResizeX/Y; nonzero saved frame is restored and generic updateGraphicRect derives the visible inset.',
               'native_business_platform_model_created': False, 'stopping_platforms_supported': False,
               'native_graphics_visibility_runtime_verified': False, 'native_application_executed': False,
               'scope': 'Four source-evidenced native diagram rectangle graphics only. No stopping envelope, dwell, platform allocation, passenger model, calibration, or general graphic editor parity.'}
    return output, receipt
