import struct
import zlib

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.native_bitmap import PNG_MAGIC, external_tiff, png_rgb, rgb_tiff, tiff_rgb
from opentrack_ai.current_archive.saved_worksheet_images import (
    EmbedPicture, EmbedPNG, InspectPicture, PictureTools, embed_png, eps_bounds, pictures,
)
from opentrack_ai.current_archive.tools import sha
from test_saved_plot import worksheet


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def png(width, height, kind, scanlines, extra=b''):
    header = struct.pack('>IIBBBBB', width, height, 8, kind, 0, 0, 0)
    return PNG_MAGIC + chunk(b'IHDR', header) + extra + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b'')


def spec(path, data):
    return {'path': path, 'sha256': sha(data)}


def test_picture_png_filters_and_native_rgb_tiff_record():
    raw = png(2, 3, 2, bytes([
        0, 10, 20, 30, 45, 50, 55,
        1, 11, 20, 30, 44, 45, 46,
        2, 1, 2, 3, 4, 5, 6,
    ]))
    size, rgb, flattened = png_rgb(raw, None)
    assert size == (2, 3) and flattened == 0
    assert rgb == bytes([10, 20, 30, 45, 50, 55, 11, 20, 30, 55, 65, 76, 12, 22, 33, 59, 70, 82])
    encoded = rgb_tiff(*size, rgb)
    assert encoded[:4] == b'II*\0' and tiff_rgb(encoded) == (size, rgb)


def test_transparency_palette_and_explicit_background():
    indexed = png(2, 1, 3, bytes([0, 0, 1]), chunk(b'PLTE', bytes([255, 0, 0, 0, 0, 255]))
                  + chunk(b'tRNS', bytes([128, 0])))
    with pytest.raises(ValueError, match='explicit RGB background'):
        png_rgb(indexed, None)
    size, pixels, transparent = png_rgb(indexed, (255, 255, 255))
    assert (size, pixels, transparent) == ((2, 1), bytes([255, 127, 127, 255, 255, 255]), 2)
    alpha = png(1, 1, 6, bytes([0, 0, 128, 255, 0]))
    assert png_rgb(alpha, (10, 20, 30)) == ((1, 1), bytes([10, 20, 30]), 1)
    rgb_key = png(1, 1, 2, bytes([0, 1, 2, 3]), chunk(b'tRNS', struct.pack('>HHH', 1, 2, 3)))
    assert png_rgb(rgb_key, (4, 5, 6)) == ((1, 1), bytes([4, 5, 6]), 1)


def test_png_invalid_checksum_or_inflate_bounds():
    raw = png(1, 1, 2, bytes([0, 1, 2, 3]))
    with pytest.raises(ValueError, match='checksum'):
        png_rgb(raw[:-1] + bytes([raw[-1] ^ 1]), None)
    with pytest.raises(ValueError, match='decompressed content'):
        png_rgb(png(1, 1, 2, bytes([0, 1, 2, 3]) * 5), None)
    with pytest.raises(ValueError, match='animated PNG'):
        png_rgb(png(1, 1, 2, bytes([0, 1, 2, 3]), chunk(b'acTL', b'\0' * 8)), None)


def test_native_picture_publication_reread_and_same_id_replacement(tmp_path):
    project = tmp_path / 'OTAI/workspaces/PictureSave'
    project.mkdir(parents=True)
    source = project / 'source.opentrack'
    image = project / 'input.png'
    output = project / 'embedded.opentrack'
    original = worksheet(4)
    color_png = png(2, 1, 2, bytes([0, 5, 11, 13, 17, 23, 29]))
    source.write_bytes(original)
    image.write_bytes(color_png)
    api = PictureTools(tmp_path)
    src = spec(source.relative_to(tmp_path).as_posix(), original)
    image_spec = spec(image.relative_to(tmp_path).as_posix(), color_png)
    args = EmbedPNG(worksheet=src, png=image_spec, frame={'x': 13.5, 'y': 2, 'width': 20},
                    background_rgb=[255, 255, 255], target_path=output.relative_to(tmp_path).as_posix())
    view = api.embed(args)
    assert not output.exists() and view['frame_xywh'] == [13.5, 2, 20, 10]
    saved = api.embed(args.model_copy(update={'preview_only': False}))
    assert saved['saved'] and saved['center_xy'] == [23.5, 7] and saved['output_sha256'] == view['output_sha256']
    embedded = output.read_bytes()
    found = api.inspect(InspectPicture(worksheet=spec(output.relative_to(tmp_path).as_posix(), embedded),
                                       graphic_id=saved['graphic_id']))
    assert found['pixel_sha256'] == sha(bytes([5, 11, 13, 17, 23, 29]))
    new_bitmap = png(1, 1, 0, bytes([0, 11]))
    replacement, result = embed_png(embedded, new_bitmap,
        EmbedPNG(worksheet=src, png=image_spec, graphic_id=saved['graphic_id']))
    assert result['graphic_id'] == saved['graphic_id'] and result['operation'] == 'replace'
    assert result['frame_xywh'] == saved['frame_xywh'] and result['natural_size'] == [1, 1]
    assert result['pixel_sha256'] == sha(bytes([11, 11, 11]))
    assert len(pictures(embedded)[2]) == len(pictures(replacement)[2]) == len(pictures(original)[2]) + 1
    assert writer.fingerprint(pictures(original)[2][0]) == writer.fingerprint(pictures(replacement)[2][0])
    assert source.read_bytes() == original


def test_external_tiff_scale_and_exact_eps_vector_replacement(tmp_path):
    project = tmp_path / 'OTAI/workspaces/PictureImport'
    project.mkdir(parents=True)
    original = worksheet(4)
    pixels = bytes([8, 16, 24, 32, 64, 128] * 4)
    tiff = rgb_tiff(4, 2, pixels, ((144, 1), (72, 1)))
    eps = (b'%!PS-Adobe-3.0 EPSF-3.0\r\n%%BoundingBox: (atend)\r\n%%EndComments\r\n'
           b'%%BeginDocument: inner.eps\r\n%%Trailer\r\n%%BoundingBox: 0 0 4 4\r\n%%EndDocument\r\n'
           b'%%BeginData: 2 ASCII Lines\r\n%%Trailer\r\n%%BoundingBox: 0 0 4 4\r\n%%EndData\r\n'
           b'newpath -2 3 moveto 10 8 lineto stroke\r\n%%Trailer\r\n%%BoundingBox: -2 3 10 8\r\n%%EOF\r\n')

    def write(name, contents):
        path = project / name
        path.write_bytes(contents)
        return spec(path.relative_to(tmp_path).as_posix(), contents)

    config = {'worksheet': write('source.opentrack', original), 'image': write('photo.tiff', tiff),
              'frame': {'x': 11, 'y': 12}, 'preview_only': False,
              'target_path': (project / 'tiff.opentrack').relative_to(tmp_path).as_posix()}
    tool = PictureTools(tmp_path)
    saved = tool.embed(EmbedPicture(**config))
    assert saved['saved'] and saved['dimensions_px'] == [4, 2] and saved['pixel_sha256'] == sha(pixels)
    assert saved['natural_size'] == [2, 2] and saved['frame_xywh'] == [11, 12, 2, 2]
    assert saved['native_tiff_sha256'] == sha(tiff)
    after = (project / 'tiff.opentrack').read_bytes()
    model_id = saved['graphic_id']
    output_path = (project / 'eps.opentrack').relative_to(tmp_path).as_posix()
    replaced = tool.embed(EmbedPicture(worksheet=spec(config['target_path'], after), image=write('plan.eps', eps),
                                       graphic_id=model_id, preview_only=False, target_path=output_path))
    assert replaced['graphic_id'] == model_id and replaced['operation'] == 'replace'
    cold = tool.inspect(InspectPicture(worksheet=spec(output_path, (tmp_path / output_path).read_bytes()), graphic_id=model_id))
    assert cold['representation'] == 'eps' and cold['native_eps_sha256'] == sha(eps)
    assert cold['bounding_box_origin'] == [-2, 3] and cold['natural_size'] == [12, 5]
    assert cold['frame_xywh'] == saved['frame_xywh']
    assert (project / 'source.opentrack').read_bytes() == original
    with pytest.raises(ValueError, match='outer BoundingBox'):
        eps_bounds(eps.replace(b'%%BoundingBox: -2 3 10 8', b'%%Title: missing-boundary'))


def test_external_tiff_rejects_referenced_second_page():
    blob = bytearray(rgb_tiff(1, 1, b'\xff\x00\x80'))
    offset, = struct.unpack_from('<I', blob, 4)
    count, = struct.unpack_from('<H', blob, offset)
    struct.pack_into('<I', blob, offset + 2 + count * 12, offset)
    with pytest.raises(ValueError, match='single-image TIFF'):
        external_tiff(blob, None)
    struct.pack_into('<I', blob, offset + 2 + count * 12, 0)
    struct.pack_into('<HHII', blob, offset + 2 + 11 * 12, 330, 4, 1, offset)
    with pytest.raises(ValueError, match='without SubIFDs'):
        external_tiff(blob, None)
