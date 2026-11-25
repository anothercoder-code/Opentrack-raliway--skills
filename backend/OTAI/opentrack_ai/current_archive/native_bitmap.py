"""Bounded PNG input and the native uncompressed RGB TIFF bitmap payload."""

from fractions import Fraction
import struct
import zlib


PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
TIFF_MAGIC = b'II*\x00'
MAX_PIXELS = 2_000_000
MAX_SIDE = 4096
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def png_chunks(raw):
    require(raw.startswith(PNG_MAGIC), 'Expected a PNG signature')
    offset = len(PNG_MAGIC)
    while offset < len(raw):
        require(offset + 12 <= len(raw), 'Truncated PNG chunk')
        size, kind = struct.unpack_from('>I4s', raw, offset)
        end = offset + 8 + size
        require(end + 4 <= len(raw), 'Truncated PNG chunk payload')
        wanted, = struct.unpack_from('>I', raw, end)
        require(zlib.crc32(raw[offset + 4:end]) == wanted, 'PNG chunk checksum differs')
        offset = end + 4
        yield kind, raw[end - size:end]
        if kind == b'IEND':
            require(size == 0 and offset == len(raw), 'Unexpected extra PNG content')
            return
    raise ValueError('Missing PNG end marker')


def paeth(left, above, upper_left):
    estimate = left + above - upper_left
    a, b, c = (abs(estimate - value) for value in (left, above, upper_left))
    if a <= b and a <= c:
        return left
    return above if b <= c else upper_left


def png_rows(buffer, width, channels):
    span = width * channels
    previous = bytes(span)
    for offset in range(0, len(buffer), span + 1):
        method = buffer[offset]
        row = bytearray(buffer[offset + 1:offset + span + 1])
        require(method <= 4, 'Unsupported PNG scanline filter')
        if method != 0:
            for i, value in enumerate(row):
                left = row[i - channels] if i >= channels else 0
                above = previous[i]
                upper_left = previous[i - channels] if i >= channels else 0
                if method == 1:
                    prediction = left
                elif method == 2:
                    prediction = above
                elif method == 3:
                    prediction = (left + above) // 2
                else:
                    prediction = paeth(left, above, upper_left)
                row[i] = (value + prediction) & 255
        yield row
        previous = row


def rgb_pixels(rows, kind, palette_blob, transparency, background, *, format_name='PNG'):
    if kind == 2 and transparency is None:
        return b''.join(rows), 0
    palette = [tuple(palette_blob[i:i + 3]) for i in range(0, len(palette_blob), 3)] if palette_blob else []
    key = struct.unpack('>H' if kind == 0 else '>3H', transparency) if transparency is not None and kind in (0, 2) else None
    stride = CHANNELS[kind]
    result, flattened = bytearray(), 0
    for row in rows:
        for i in range(0, len(row), stride):
            sample = tuple(row[i:i + stride])
            if kind == 3:
                index = sample[0]
                require(index < len(palette), 'PNG index is outside the installed palette')
                color = palette[index]
                alpha = transparency[index] if transparency is not None and index < len(transparency) else 255
            else:
                color = (sample[0],) * 3 if kind in (0, 4) else sample[:3]
                alpha = sample[-1] if kind in (4, 6) else (0 if sample == key else 255)
            if alpha != 255:
                require(background is not None, f'Transparent {format_name} requires an explicit RGB background')
                color = tuple((value * alpha + backdrop * (255 - alpha) + 127) // 255
                              for value, backdrop in zip(color, background, strict=True))
                flattened += 1
            result.extend(color)
    return bytes(result), flattened


def png_rgb(raw, background):
    chunks = png_chunks(raw)
    kind, header = next(chunks)
    require(kind == b'IHDR' and len(header) == 13, 'Expected the leading PNG image header')
    width, height, depth, kind, compression, filter_method, interlace = struct.unpack('>IIBBBBB', header)
    require(0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE and width * height <= MAX_PIXELS,
            'PNG dimensions exceed supported input bounds')
    require(depth == 8 and kind in CHANNELS and compression == filter_method == interlace == 0,
            'Use noninterlaced standard 8-bit grayscale, indexed, RGB or RGBA PNG')
    palette, transparency, compressed, data_closed = None, None, bytearray(), False
    for chunk, data in chunks:
        if chunk == b'IDAT':
            require(not data_closed, 'PNG data chunks are not consecutive')
            compressed.extend(data)
            continue
        data_closed |= bool(compressed)
        if chunk == b'PLTE':
            require(not data_closed and palette is None and 0 < len(data) <= 768 and len(data) % 3 == 0,
                    'Invalid PNG palette')
            palette = data
        elif chunk == b'tRNS':
            require(not data_closed and transparency is None and kind in (0, 2, 3), 'Invalid PNG transparency table')
            expected = {0: 2, 2: 6}.get(kind)
            require(len(data) == expected if expected else palette is not None and 0 < len(data) <= len(palette) // 3,
                    'Invalid PNG transparency table size')
            transparency = data
        else:
            require(chunk == b'IEND' or (chunk[0] & 32 and chunk not in (b'acTL', b'fcTL', b'fdAT')),
                    'Unsupported critical or animated PNG chunk')
    require(compressed and (kind != 3 or palette is not None), 'PNG image data or indexed palette is absent')
    channels = CHANNELS[kind]
    size = height * (1 + width * channels)
    inflater = zlib.decompressobj()
    decoded = inflater.decompress(bytes(compressed), size + 1)
    require(len(decoded) == size and inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail,
            'PNG decompressed content differs from the declared dimensions')
    pixels, flattened = rgb_pixels(png_rows(decoded, width, channels), kind, palette, transparency, background)
    return (width, height), pixels, flattened


def rgb_tiff(width, height, pixels, resolution=((720000, 10000), (720000, 10000))):
    require(len(pixels) == width * height * 3 and 0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE,
            'RGB pixel length differs from the declared image size')
    offset = 8 + len(pixels) + len(pixels) % 2
    extras = offset + 2 + 12 * 12 + 4
    entries = [(256, 3, 1, width), (257, 3, 1, height), (258, 3, 3, extras),
               (259, 3, 1, 1), (262, 3, 1, 2), (273, 4, 1, 8), (277, 3, 1, 3),
               (279, 4, 1, len(pixels)), (282, 5, 1, extras + 6), (283, 5, 1, extras + 14),
               (284, 3, 1, 1), (296, 3, 1, 2)]
    directory = struct.pack('<H', len(entries)) + b''.join(struct.pack('<HHII', *entry) for entry in entries)
    native_resolution = struct.pack('<IHHHIIII', 0, 8, 8, 8, *resolution[0], *resolution[1])
    return TIFF_MAGIC + struct.pack('<I', offset) + pixels + b'\0' * (len(pixels) % 2) + directory + native_resolution


def tiff_rgb(raw):
    """Independently read the one-strip native subset used by the writer."""
    require(raw.startswith(TIFF_MAGIC) and len(raw) >= 10, 'Expected native little-endian TIFF')
    offset, = struct.unpack_from('<I', raw, 4)
    require(8 <= offset <= len(raw) - 6, 'Invalid native TIFF directory offset')
    count, = struct.unpack_from('<H', raw, offset)
    require(0 < count <= 64 and offset + 6 + count * 12 <= len(raw), 'Invalid native TIFF directory')
    tags = {tag: (dtype, n, value) for tag, dtype, n, value in struct.iter_unpack(
        '<HHII', raw[offset + 2:offset + 2 + count * 12])}
    require(len(tags) == count and tags.get(259) == (3, 1, 1) and tags.get(262) == (3, 1, 2)
            and tags.get(277) == (3, 1, 3) and tags.get(284) == (3, 1, 1), 'Unexpected native TIFF pixel format')
    width, height = (tags[tag][2] for tag in (256, 257))
    start, length = (tags[tag][2] for tag in (273, 279))
    bits = tags[258][2]
    require(0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE and tags[258][:2] == (3, 3)
            and bits + 6 <= len(raw) and struct.unpack_from('<HHH', raw, bits) == (8, 8, 8)
            and start >= 8 and length == width * height * 3 and start + length <= offset,
            'Unexpected native TIFF pixel row or strip layout')
    return (width, height), raw[start:start + length]


def packbits_strip(raw, size):
    output = bytearray()
    pos = 0
    while pos < len(raw):
        run = raw[pos]
        pos += 1
        if run <= 127:
            count = run + 1
            require(pos + count <= len(raw) and len(output) + count <= size, 'Invalid TIFF PackBits literal run')
            output.extend(raw[pos:pos + count])
            pos += count
        elif run != 128:
            count = 257 - run
            require(pos < len(raw) and len(output) + count <= size, 'Invalid TIFF PackBits repeat run')
            output.extend(raw[pos:pos + 1] * count)
            pos += 1
    require(len(output) == size, 'TIFF PackBits strip differs from its declared length')
    return output


def lzw_strip(raw, size):
    """TIFF MSB-first LZW with early code-width changes."""
    pos, pending, bit_count = 0, 0, 0
    output = bytearray()
    clear, end = 256, 257
    table, width, previous = [], 9, None
    while True:
        while bit_count < width and pos < len(raw):
            pending = (pending << 8) | raw[pos]
            pos += 1
            bit_count += 8
        require(bit_count >= width, 'Missing TIFF LZW end code')
        bit_count -= width
        code = pending >> bit_count
        pending &= (1 << bit_count) - 1
        if code == clear:
            table = [bytes([value]) for value in range(256)] + [b'', b'']
            width, previous = 9, None
            continue
        require(table, 'Missing initial TIFF LZW clear code')
        if code == end:
            require(len(output) == size and not pending and pos == len(raw), 'Unexpected TIFF LZW strip length or padding')
            return output
        require(code < len(table) or (code == len(table) and previous is not None and len(table) < 4096),
                'Invalid TIFF LZW dictionary reference')
        value = table[code] if code < len(table) else previous + previous[:1]
        require(value and len(output) + len(value) <= size, 'TIFF LZW expansion exceeds the declared strip')
        output.extend(value)
        if previous is not None and len(table) < 4096:
            table.append(previous + value[:1])
            if len(table) == (1 << width) - 1 and width < 12:
                width += 1
        previous = value


def decode_tiff_strip(blob, size, compression):
    if compression == 1:
        require(len(blob) == size, 'Uncompressed TIFF strip differs from its declared length')
        return bytearray(blob)
    if compression == 32773:
        return packbits_strip(blob, size)
    if compression == 5:
        return lzw_strip(blob, size)
    inflater = zlib.decompressobj()
    pixels = inflater.decompress(blob, size + 1)
    require(len(pixels) == size and inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data,
            'TIFF Deflate strip differs from its declared length')
    return bytearray(pixels)


def external_tiff(raw, background):
    """Read a bounded, single strip-based TIFF and preserve its physical point size."""
    require(len(raw) >= 14 and raw[:4] in (TIFF_MAGIC, b'MM\x00*'), 'Expected a classic TIFF image')
    endian = '<' if raw[:2] == b'II' else '>'
    directory, = struct.unpack_from(endian + 'I', raw, 4)
    require(8 <= directory <= len(raw) - 6, 'Invalid TIFF directory offset')
    count, = struct.unpack_from(endian + 'H', raw, directory)
    end = directory + 2 + 12 * count
    require(0 < count <= 128 and end + 4 <= len(raw), 'Invalid TIFF directory')
    require(struct.unpack_from(endian + 'I', raw, end)[0] == 0, 'Use a single-image TIFF')
    entries = {}
    for offset in range(directory + 2, end, 12):
        tag, kind, length = struct.unpack_from(endian + 'HHI', raw, offset)
        require(tag not in entries, 'Duplicate TIFF tag')
        entries[tag] = kind, length, offset + 8
    require(330 not in entries, 'Use a single-image TIFF without SubIFDs')

    def values(tag, allowed_types, maximum):
        kind, length, offset = entries[tag]
        require(kind in allowed_types and 0 < length <= maximum, f'Invalid TIFF tag {tag}')
        size, fmt = {3: (2, 'H'), 4: (4, 'I'), 5: (8, 'II')}[kind]
        total = size * length
        if total > 4:
            offset, = struct.unpack_from(endian + 'I', raw, offset)
            require(8 <= offset and offset + total <= len(raw), f'Missing TIFF tag {tag} data')
        return struct.unpack_from(endian + fmt * length, raw, offset)

    def scalar(tag, default=None):
        if tag not in entries:
            require(default is not None, f'Missing TIFF tag {tag}')
            return default
        return values(tag, (3, 4), 1)[0]

    width, height = scalar(256), scalar(257)
    require(0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE and width * height <= MAX_PIXELS,
            'TIFF dimensions exceed supported input bounds')
    compression, photometric, samples, predictor = scalar(259, 1), scalar(262), scalar(277, 1), scalar(317, 1)
    require(compression in (1, 5, 8, 32946, 32773) and scalar(284, 1) == 1 and scalar(274, 1) == 1
            and scalar(266, 1) == 1 and predictor in (1, 2) and 324 not in entries,
            'Use an upright interleaved TIFF with strips and uncompressed, LZW, Deflate or PackBits encoding')
    alpha = values(338, (3,), 1)[0] if 338 in entries else 0
    require(photometric in (0, 1, 2) and alpha in (0, 2)
            and samples == (3 if photometric == 2 else 1) + bool(alpha)
            and values(258, (3,), 4) == (8,) * samples,
            'Use 8-bit grayscale or RGB TIFF with optional unassociated alpha')
    rows_per_strip = scalar(278, height)
    require(rows_per_strip > 0, 'Invalid TIFF rows per strip')
    strips = (height + rows_per_strip - 1) // rows_per_strip
    require(273 in entries and 279 in entries, 'Missing TIFF strip layout')
    offsets, lengths = values(273, (3, 4), strips), values(279, (3, 4), strips)
    require(len(offsets) == len(lengths) == strips, 'Incomplete TIFF strip layout')
    bounds = sorted((offset, offset + length) for offset, length in zip(offsets, lengths, strict=True))
    require(all(8 <= start < stop <= len(raw) and (stop <= directory or start >= end + 4)
                for start, stop in bounds) and all(a[1] <= b[0] for a, b in zip(bounds, bounds[1:])),
            'TIFF strips overlap or exceed the input')
    row_stride, pixels = width * samples, bytearray()
    for index, (offset, length) in enumerate(zip(offsets, lengths, strict=True)):
        rows = min(rows_per_strip, height - index * rows_per_strip)
        band = decode_tiff_strip(raw[offset:offset + length], row_stride * rows, compression)
        if predictor == 2:
            for row in range(0, len(band), row_stride):
                for pos in range(row + samples, row + row_stride):
                    band[pos] = (band[pos] + band[pos - samples]) & 255
        pixels.extend(band)
    if photometric == 0:
        for pos in range(0, len(pixels), samples):
            pixels[pos] = 255 - pixels[pos]
    colors = (6 if alpha else 2) if photometric == 2 else (4 if alpha else 0)
    rgb, flattened = rgb_pixels((pixels,), colors, None, None, background, format_name='TIFF')

    unit = scalar(296, 2 if 282 in entries or 283 in entries else 1)
    require(unit in (1, 2, 3), 'Unknown TIFF resolution unit')
    rates = []
    for tag in (282, 283):
        if unit != 1 and tag in entries:
            numerator, denominator = values(tag, (5,), 1)
            require(numerator and denominator, 'TIFF resolution must be positive')
            rate = Fraction(numerator, denominator) * (Fraction(254, 100) if unit == 3 else 1)
            rate = rate.limit_denominator(10000)
        else:
            rate = Fraction(72)
        require(Fraction(1, 10) <= rate <= 100000, 'TIFF resolution is outside supported bounds')
        rates.append(rate)
    return (width, height), rgb, flattened, tuple((rate.numerator, rate.denominator) for rate in rates)
