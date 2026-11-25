"""Embed raster or vector imagery as an editable native worksheet Picture."""

import math
import re
import struct
from typing import Annotated
import zlib

from pydantic import Field, StrictFloat, StrictInt, model_validator

from ..errors import APIError
from . import catalogs, writer
from .bundle_tools import Source
from .graph_references import incoming_counts
from .multi_document.core import layout, need
from .native_bitmap import external_tiff, png_rgb, rgb_tiff, tiff_rgb
from .next_tools import Ordinal, Save
from .saved_plot_tools import load_worksheet
from .tools import ArchiveTools, Input, sha
from .zero_generation.native_signal_routes import obj
from .zero_generation.topology import flt, signature


BITMAP_CHAIN = [('NSBitmapImageRep', 17), ('NSImageRep', 17), ('NSObject', 0)]
BITMAP_SIGNATURE = tuple((name.encode('ascii'), version) for name, version in BITMAP_CHAIN)
EPS_CHAIN = [('NSEPSImageRep', 17), ('NSImageRep', 17), ('NSObject', 0)]
EPS_SIGNATURE = tuple((name.encode('ascii'), version) for name, version in EPS_CHAIN)
DATA_CHAIN = [('NSData', 0), ('NSObject', 0)]
EPS_HEADER = re.compile(rb'%!PS-Adobe-[0-9]+\.[0-9]+ EPSF-[0-9]+\.[0-9]+(?:[ \t].*)?\Z')
EPS_BOUNDS = re.compile(rb'%%BoundingBox:[ \t]+(-?[0-9]{1,7})[ \t]+(-?[0-9]{1,7})[ \t]+'
                        rb'(-?[0-9]{1,7})[ \t]+(-?[0-9]{1,7})[ \t]*\Z')
EPS_LINE_END = re.compile(rb'\r\n|[\r\n]')
EPS_DATA = re.compile(rb'%%Begin(Data|Binary):[ \t]+([0-9]{1,9})(?:[ \t]+(ASCII|Hex|Binary))?'
                      rb'(?:[ \t]+(Bytes|Lines))?[ \t]*\Z')
GRAPHIC = ['i', 'f', 'f', 'f', 'i', 'i']
Coordinate = Annotated[StrictInt | StrictFloat, Field(ge=-1e6, le=1e6, allow_inf_nan=False)]
Dimension = Annotated[StrictInt | StrictFloat, Field(gt=0, le=1e6, allow_inf_nan=False)]
Channel = Annotated[StrictInt, Field(ge=0, le=255)]


class Frame(Input):
    x: Coordinate
    y: Coordinate
    width: Dimension | None = None
    height: Dimension | None = None


class PicturePlacement(Save):
    worksheet: Source
    frame: Frame | None = None
    graphic_id: Ordinal | None = None

    @model_validator(mode='after')
    def require_placement(self):
        if self.graphic_id is None and self.frame is None:
            raise ValueError('Set a frame origin for new Pictures or identify a Picture to replace')
        return self


class EmbedPNG(PicturePlacement):
    png: Source
    background_rgb: Annotated[list[Channel], Field(min_length=3, max_length=3)] | None = None


class EmbedPicture(PicturePlacement):
    image: Source
    background_rgb: Annotated[list[Channel], Field(min_length=3, max_length=3)] | None = None


class InspectPicture(Input):
    worksheet: Source
    graphic_id: Ordinal


def pictures(raw):
    root, stream, _ = load_worksheet(raw)
    models = catalogs.array(root.contents[2].value)
    return root, stream, models, {model.contents[0].value: model for model in models if writer.kind(model) == 'OTLogoModel'}


def picture_signature(version):
    return [('OTLogoModel', version), ('OTGraphicModel', version), ('NSObject', 0)]


def picture_slots(picture):
    version = picture.clazz.version
    need(version in (0, 1), 'Only reviewed native Picture versions are supported')
    trailing = (['@'] if version else []) + ['@', 'ff', 'ffff'] + (['i'] if version else [])
    layout(picture, picture_signature(version), GRAPHIC + trailing)
    if version:
        need(picture.contents[6].value is None, 'An attached Picture needs its owning editor')
    return 6 + version, 7 + version, 8 + version


def bitmap_payload(tiff):
    return obj(BITMAP_CHAIN, [('i', [len(tiff)]), (f'[{len(tiff)}c]', [writer.Array(tiff)])])


def eps_dsc_lines(raw):
    position = 0
    while position < len(raw):
        ending = EPS_LINE_END.search(raw, position)
        line = raw[position:ending.start()] if ending else raw[position:]
        position = ending.end() if ending else len(raw)
        if not line.startswith((b'%%BeginData:', b'%%BeginBinary:')):
            yield line
            continue
        block = EPS_DATA.fullmatch(line)
        need(block is not None, 'Invalid EPS counted data section')
        kind, count, _, units = block.groups()
        count = int(count)
        if units == b'Lines':
            need(kind == b'Data', 'EPS BeginBinary requires a byte count')
            for _ in range(count):
                ending = EPS_LINE_END.search(raw, position)
                need(ending is not None, 'Truncated EPS counted lines')
                position = ending.end()
        else:
            position += count
            need(position <= len(raw), 'Truncated EPS counted bytes')
            ending = EPS_LINE_END.match(raw, position)
            if ending:
                position = ending.end()
        finish = b'%%End' + kind
        need(raw.startswith(finish, position), 'EPS counted data section ends at the wrong byte')
        position += len(finish)
        need(position == len(raw) or raw[position:position + 1] in (b'\r', b'\n'),
             'Invalid EPS counted data end marker')


def eps_bounds(raw):
    lines = eps_dsc_lines(raw)
    first = next(lines, b'')
    need(EPS_HEADER.fullmatch(first), 'Expected a DSC Encapsulated PostScript header')
    header = []
    for line in lines:
        if not line.startswith(b'%') or line == b'%%EndComments':
            break
        header.append(line)
    bounds = [line for line in header if line.startswith(b'%%BoundingBox:')]
    need(len(bounds) == 1, 'EPS requires one outer BoundingBox declaration')
    if bounds[0].split() == [b'%%BoundingBox:', b'(atend)']:
        block_depth, trailer = 0, False
        bounds = []
        for line in eps_dsc_lines(raw):
            if line.startswith(b'%%BeginDocument:'):
                block_depth += 1
            elif line.startswith(b'%%EndDocument'):
                block_depth -= 1
                need(block_depth >= 0, 'EPS contains an unmatched embedded document')
            elif not block_depth and line == b'%%EOF':
                break
            elif not block_depth and line == b'%%Trailer':
                trailer = True
            elif not block_depth and trailer and line.startswith(b'%%BoundingBox:'):
                bounds.append(line)
        need(block_depth == 0 and len(bounds) == 1, 'EPS trailer requires one outer BoundingBox')
    parsed = EPS_BOUNDS.fullmatch(bounds[0])
    need(parsed, 'EPS BoundingBox requires four integers')
    left, bottom, right, top = map(int, parsed.groups())
    need(all(abs(coord) <= 1e6 for coord in (left, bottom, right, top))
         and 0 < right - left <= 1e6 and 0 < top - bottom <= 1e6, 'EPS BoundingBox exceeds supported extent')
    return (left, bottom), (right - left, top - bottom)


def eps_payload(raw, origin, dimensions):
    data = obj(DATA_CHAIN, [('i', [len(raw)]), (f'[{len(raw)}c]', [writer.Array(raw)])])
    return obj(EPS_CHAIN, [('ff', list(dimensions)), ('c', [0]), ('c', [0]), ('iii@', [0, 0, 0, None]),
                           ('ff', list(origin)), ('@', [data])])


def image_bytes(data, chain):
    size = data.contents[0].value
    need(type(size) is int and size > 0, 'Invalid native image byte count')
    layout(data, chain, ['i', f'[{size}c]'])
    encoded = data.contents[1].value
    need(isinstance(encoded, writer.Array) and isinstance(encoded.elements, bytes) and len(encoded.elements) == size,
         'Invalid native image byte payload')
    return encoded.elements


def inspect_picture(picture):
    bitmap_index, original_index, frame_index = picture_slots(picture)
    model = picture.contents[bitmap_index].value
    kind = writer.kind(model)
    frame = list(picture.contents[frame_index].values)
    need(all(math.isfinite(value) for value in frame) and frame[2] > 0 and frame[3] > 0, 'Invalid native Picture frame')
    natural_size = list(picture.contents[original_index].values)
    result = {'graphic_id': picture.contents[0].value, 'picture_version': picture.clazz.version,
              'natural_size': natural_size, 'frame_xywh': frame, 'center_xy': [picture.contents[i].value for i in (2, 3)]}
    if kind == 'NSBitmapImageRep':
        need(signature(model.clazz) == BITMAP_SIGNATURE, 'Expected the reviewed native bitmap representation')
        content = image_bytes(model, BITMAP_CHAIN)
        dimensions, pixels = tiff_rgb(content)
        return {**result, 'representation': 'tiff', 'dimensions_px': list(dimensions), 'pixel_sha256': sha(pixels),
                'native_tiff_sha256': sha(content)}
    need(kind == 'NSEPSImageRep' and signature(model.clazz) == EPS_SIGNATURE,
         'Expected an original bitmap or an EPS picture')
    layout(model, EPS_CHAIN, ['ff', 'c', 'c', 'iii@', 'ff', '@'])
    need(model.contents[1].value == model.contents[2].value == 0 and model.contents[3].values == [0, 0, 0, None],
         'Unsupported native EPS display properties')
    data = model.contents[5].value
    need(writer.kind(data) == 'NSData', 'Expected exact EPS bytes in a native NSData object')
    content = image_bytes(data, DATA_CHAIN)
    origin, dimensions = eps_bounds(content)
    need(list(origin) == model.contents[4].values and list(dimensions) == model.contents[0].values == natural_size,
         'Native EPS bounds differ from the archived source')
    return {**result, 'representation': 'eps', 'bounding_box_origin': list(origin),
            'native_eps_sha256': sha(content)}


def display_frame(frame, dimensions):
    actual_width, actual_height = dimensions
    width, height = frame.get('width'), frame.get('height')
    if width is None and height is None:
        width, height = actual_width, actual_height
    elif width is None:
        width = height * actual_width / actual_height
    elif height is None:
        height = width * actual_height / actual_width
    result = [flt(value, 'Picture frame coordinate') for value in (frame['x'], frame['y'], width, height)]
    need(result[2] > 0 and result[3] > 0, 'The native Picture frame must have positive dimensions')
    return result


def midpoint(rect):
    return [flt(float(minimum) + float(span) / 2.0, 'Picture frame center') for minimum, span in zip(rect[:2], rect[2:], strict=True)]


def check_class_versions(root, version, image_chain):
    expected = dict(picture_signature(version) + image_chain)
    for record in writer.objects(root):
        for name, item in signature(record.clazz):
            key = name.decode('ascii')
            need(key not in expected or expected[key] == item, 'Picture needs compatible source and destination archived classes')


def embed_picture(raw, image, args, suffix):
    if suffix == '.eps':
        need(args.background_rgb is None, 'A background color applies to transparent raster inputs')
        origin, dimensions = eps_bounds(image)
        natural = dimensions
        raster = eps_payload(image, origin, dimensions)
        image_chain = EPS_CHAIN + DATA_CHAIN
        evidence = {'native_eps_sha256': sha(image)}
        flattened = 0
    elif suffix == '.png':
        dimensions, pixels, flattened = png_rgb(image, args.background_rgb)
        natural = dimensions
        raster = bitmap_payload(rgb_tiff(*dimensions, pixels))
        image_chain = BITMAP_CHAIN
        evidence = {'pixel_sha256': sha(pixels)}
    else:
        dimensions, pixels, flattened, rates = external_tiff(image, args.background_rgb)
        natural = [px * 72 * denominator / numerator for px, (numerator, denominator) in zip(dimensions, rates, strict=True)]
        try:
            matches_native = tiff_rgb(image) == (dimensions, pixels)
        except (ValueError, KeyError, IndexError, struct.error):
            matches_native = False
        payload = image if matches_native else rgb_tiff(*dimensions, pixels, rates)
        raster = bitmap_payload(payload)
        image_chain = BITMAP_CHAIN
        evidence = {'pixel_sha256': sha(pixels), 'native_tiff_sha256': sha(payload)}

    root, stream, models, existing = pictures(raw)
    geometry = display_frame(args.frame.model_dump(exclude_none=True), natural) if args.frame else None
    native_size = [flt(size, 'Picture natural size') for size in natural]
    counts = incoming_counts(root)
    before = writer.fingerprint(root)
    undo = []

    def replace(group, values):
        undo.append((group, group.values))
        group.values = values

    if args.graphic_id is None:
        version = 0 if root.clazz.version == 1 else 1
        check_class_versions(root, version, image_chain)
        owner = root.contents[2]
        need(counts[id(owner.value)] == 1 and writer.kind(owner.value) == 'NSMutableArray',
             'The worksheet must own a native mutable graphic array')
        mid = max((model.contents[0].value for model in models), default=-1) + 1
        need(mid < 2**31, 'The worksheet has no free Graphic ID after its existing graphics')
        center = midpoint(geometry)
        groups = [('i', [mid]), ('f', [0.0]), ('f', [center[0]]), ('f', [center[1]]), ('i', [0]), ('i', [0])]
        if version == 1:
            groups.append(('@', [None]))
        groups.extend([('@', [raster]), ('ff', native_size), ('ffff', geometry)])
        if version == 1:
            groups.append(('i', [1]))
        picture = obj(picture_signature(version), groups)
        model_array = writer.GenericArchivedObject(owner.value.clazz)
        writer.set_elements(model_array, [*models, picture])
        replace(owner, [model_array])
        operation = 'insert'
    else:
        mid = args.graphic_id
        picture = existing.get(mid)
        need(picture is not None and counts[id(picture)] == 1, 'Select one standalone existing native Picture')
        version = picture.clazz.version
        check_class_versions(root, version, image_chain)
        bitmap_index, original_index, frame_index = picture_slots(picture)
        need(writer.kind(picture.contents[bitmap_index].value) in ('NSBitmapImageRep', 'NSEPSImageRep'),
             'Existing native Picture has no reviewed image representation')
        replace(picture.contents[bitmap_index], [raster])
        replace(picture.contents[original_index], native_size)
        if geometry is not None:
            replace(picture.contents[frame_index], geometry)
            for slot, value in zip((2, 3), midpoint(geometry), strict=True):
                replace(picture.contents[slot], [value])
        if version == 1:
            replace(picture.contents[10], [1])
        operation = 'replace'

    result = inspect_picture(picture)
    output = writer.dump_verified(root, stream)
    for group, values in reversed(undo):
        group.values = values
    need(writer.fingerprint(root) == before, 'An unrelated native field or reference changed')
    saved = pictures(output)[3][mid]
    need(inspect_picture(saved) == result and all(result[key] == value for key, value in evidence.items()),
         'Native Picture readback differs')
    return output, {'operation': operation, 'transparent_pixels_composited': flattened, **result,
                    'fresh_archive_reload_verified': True, 'original_object_graph_preserved_outside_edits': True}


def embed_png(raw, image, args):
    return embed_picture(raw, image, args, '.png')


class PictureTools(ArchiveTools):
    def source(self, spec, *extensions):
        path = self.path(spec.path)
        if path.suffix.casefold() not in extensions:
            raise APIError('NATIVE_PICTURE_EXTENSION', f'Use a source with extension {" or ".join(extensions)}')
        data = self.secure_bytes(path)
        if sha(data) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'Picture source differs from the requested SHA-256')
        return path, data

    def inspect(self, args):
        _, raw = self.source(args.worksheet, '.opentrack')
        try:
            return {'worksheet_sha256': sha(raw), **inspect_picture(pictures(raw)[3][args.graphic_id])}
        except (ValueError, AttributeError, IndexError, KeyError, TypeError, OverflowError, struct.error) as exc:
            raise APIError('NATIVE_PICTURE_INVALID', str(exc)[:500]) from exc

    def embed(self, args):
        legacy_png = isinstance(args, EmbedPNG)
        source, raw = self.source(args.worksheet, '.opentrack')
        external, image = (self.source(args.png, '.png') if legacy_png
                           else self.source(args.image, '.png', '.tif', '.tiff', '.eps'))
        try:
            output, data = embed_picture(raw, image, args, external.suffix.casefold())
        except (ValueError, AttributeError, IndexError, KeyError, TypeError, OverflowError, struct.error, zlib.error) as exc:
            raise APIError('NATIVE_PICTURE_INVALID', str(exc)[:500]) from exc
        source_hash_key = 'input_png_sha256' if legacy_png else 'input_image_sha256'
        result = {'saved': False, 'preview_only': args.preview_only, 'worksheet_sha256': sha(raw), source_hash_key: sha(image),
                  'output_sha256': sha(output), 'output_bytes': len(output), **data}
        if args.preview_only:
            if self.secure_bytes(source) != raw or self.secure_bytes(external) != image:
                raise APIError('SOURCE_CHANGED', 'A Picture input changed during preview')
            return result
        if self.path(args.target_path).suffix.casefold() != '.opentrack':
            raise APIError('NATIVE_PICTURE_EXTENSION', 'Use a fresh .opentrack worksheet target')
        if len(output) > 20 * 1024 * 1024:
            raise APIError('ARCHIVE_SIZE', 'Generated worksheet exceeds 20 MiB')
        return self.save_copy(source, raw, output, result, args.target_path, additional_inputs={external: image},
                              validate_output=pictures)


def tool_definitions(root):
    api = PictureTools(root)
    return [('opentrack_inspect_saved_worksheet_bitmap', 'Inspect a native editable Picture, image payload and frame.',
             InspectPicture, api.inspect),
            ('opentrack_embed_saved_worksheet_png', 'Embed or replace an external PNG as a native editable Picture '
             'in a fresh .opentrack worksheet. Save the checked RGB bitmap and existing worksheet layout.',
             EmbedPNG, api.embed, False, False),
            ('opentrack_embed_saved_worksheet_picture', 'Embed or replace a PNG, TIFF or EPS native worksheet Picture. '
             'Keep EPS vector bytes and TIFF physical scale. Save to a fresh .opentrack file.',
             EmbedPicture, api.embed, False, False)]
