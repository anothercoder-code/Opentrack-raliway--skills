"""Edit the native RTF0 runs and appearance of standalone worksheet Labels."""

from dataclasses import dataclass, replace
import math
import re
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import catalogs, writer
from .bundle_tools import Source
from .graph_references import incoming_counts
from .multi_document.core import layout, need
from .next_tools import Ordinal, Save
from .saved_plot_tools import load_worksheet
from .tools import ArchiveTools, Input, sha
from .zero_generation.native_signal_routes import obj
from .zero_generation.topology import flt


RTF_LIMIT = 65536
DOCUMENT = re.compile(rb'(?P<prefix>\{\\rtf0\\ansi\{\\fonttbl(?P<fonts>[^{}\r\n]+)\}'
                      rb'(?P<colors>\{\\colortbl(?P<palette>[^{}\r\n]*)\})?'
                      rb'\r?\n\\pard(?P<paragraph>[^{}\r\n]*)\r?\n\r?\n)'
                      rb'(?P<body>[\s\S]*)(?P<suffix>\}\r?\n)\Z')
WORD = re.compile(rb'\\([a-z]+)(-?[0-9]+)? ?')
FONT = re.compile(rb'\\f([0-9]+)(?=\\| )')
FONT_ENTRY = re.compile(rb'\\f([0-9]+)\\f(swiss|roman|modern|nil) ([^;{}\\\r\n]{1,80});')
COLOR = re.compile(rb'\\red([0-9]{1,3})\\green([0-9]{1,3})\\blue([0-9]{1,3});')
LINE_BREAK = re.compile(rb'\\(?:par(?=\\| |[\r\n]|$) ?|\r?\n)')
PARAGRAPH = re.compile(rb'\\q(natural|[lcrj])(?=\\| |$) ?')
ALIGNMENTS = {'left': b'l', 'center': b'c', 'right': b'r', 'justified': b'j'}
ANCHORS = {'left': 1, 'center': 0, 'right': 2}
HalfPointSize = Annotated[StrictInt, Field(ge=2, le=288)]
RichText = Annotated[StrictStr, Field(min_length=1, max_length=1024, pattern=r'^[ -~]*$')]
RGBChannel = Annotated[StrictInt, Field(ge=0, le=255)]
RGB = Annotated[list[RGBChannel], Field(min_length=3, max_length=3)]
LabelCoordinate = Annotated[StrictInt | StrictFloat, Field(ge=-1e6, le=1e6, allow_inf_nan=False)]
LabelDimension = Annotated[StrictInt | StrictFloat, Field(gt=0, le=100000, allow_inf_nan=False)]
RTF1_START = re.compile(rb'\{\\rtf1\\ansi((?:\\(?:ansicpg1252|deff[0-9]+|uc1|deflang[0-9]+)\s*)*)\s*')
RTF1_FONT = re.compile(rb'\{\\f([0-9]+)\\f(swiss|roman|modern|nil)'
                       rb'(?:\\fcharset0)?(?:\\fprq[0-2])? ([^;{}\\\r\n]{1,80});\}\s*')
RTF_CHARACTER = re.compile(rb"\\(?:[{}\\]|'[0-9a-fA-F]{2})|[ -~\x80-\xff]")


class LabelFont(Input):
    face: Annotated[StrictStr, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}$')]
    family: Literal['swiss', 'roman', 'modern', 'nil'] | None = None


class Fragment(Input):
    text: RichText
    bold: StrictBool | None = None
    size_half_points: HalfPointSize | None = None
    font: LabelFont | None = None
    text_rgb: RGB | None = Field(
        default=None, description='Stored run color. The original label view applies its model foreground to all runs.')
    paragraph_break_before: StrictBool = False


class RunEdit(Input):
    index: Ordinal
    expected_text: Annotated[StrictStr, Field(max_length=RTF_LIMIT)]
    replace_with: Annotated[list[Fragment], Field(min_length=1, max_length=64)]


class ReadLabel(Input):
    worksheet: Source
    graphic_id: Ordinal


class Appearance(Input):
    resize_anchor: Literal['left', 'center', 'right'] | None = None
    paragraph_alignment: Literal['left', 'center', 'right', 'justified'] | None = None
    font: LabelFont | None = None
    text_rgb: RGB | None = None
    background_rgb: RGB | None = None
    draws_background: StrictBool | None = None

    @model_validator(mode='after')
    def explicit(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Supply one or more explicit, non-null Label appearance changes')
        return self


class EditLabel(Save, ReadLabel):
    edits: Annotated[list[RunEdit], Field(max_length=128)] = Field(default_factory=list)
    appearance: Appearance | None = None

    @model_validator(mode='after')
    def unique_edits(self):
        if len({edit.index for edit in self.edits}) != len(self.edits):
            raise ValueError('Select each original rich-text run at most once')
        if not (self.edits or self.appearance):
            raise ValueError('Supply rich-text run edits or label appearance changes')
        return self


class ExternalLabelFrame(Input):
    x: LabelCoordinate
    y: LabelCoordinate
    width: LabelDimension
    height: LabelDimension


class ImportRTF(Save):
    worksheet: Source
    rtf: Source
    graphic_id: Ordinal | None = None
    frame: ExternalLabelFrame | None = None
    appearance: Appearance | None = None

    @model_validator(mode='after')
    def frame_contract(self):
        if (self.graphic_id is None) == (self.frame is None):
            raise ValueError('Choose an explicit frame for a new Label or select the existing Label ID')
        return self


@dataclass(frozen=True)
class Style:
    font: int
    bold: bool
    size: int
    color: int = 0


@dataclass(frozen=True)
class Run:
    start: int
    end: int
    text: str
    style: Style
    paragraph: int


def color_palette(payload):
    if payload is None:
        return [None]
    need(payload.startswith(b';'), 'Expected the native RTF0 automatic color slot')
    colors, cursor = [None], 1
    while cursor < len(payload):
        match = COLOR.match(payload, cursor)
        need(match is not None, 'Unsupported native RTF0 color table entry')
        channels = tuple(map(int, match.groups()))
        need(max(channels) <= 255, 'Invalid native RTF0 color component')
        colors.append(channels)
        cursor = match.end()
    return colors


def font_entries(table):
    matches = list(FONT_ENTRY.finditer(table))
    need(b''.join(match[0] for match in matches) == table,
         'Editing native RTF0 font declarations requires a flat font table')
    fonts = {int(match[1]): (match[2], match[3]) for match in matches}
    need(len(fonts) == len(matches) and fonts, 'Invalid or repeated native RTF0 font index')
    return fonts


def fragment_font(font, fonts, original_index):
    wanted_face = font.face.encode('ascii')
    wanted_family = font.family.encode('ascii') if font.family else fonts[original_index][0]
    for index, (family, face) in fonts.items():
        if family == wanted_family and face.lower() == wanted_face.lower():
            return index
    index = max(fonts) + 1
    fonts[index] = wanted_family, wanted_face
    return index


def control_style(token, raw, font, bold, size, color, fonts, color_count):
    number = int(raw) if raw is not None else None
    if token == b'f' and number in fonts:
        font = number
    elif token == b'fs' and number is not None and 1 <= number <= 512:
        size = number
    elif token == b'b' and number in (None, 0, 1):
        bold = number != 0
    elif token == b'cf' and number is not None and 0 <= number < color_count:
        color = number
    else:
        raise ValueError('Unsupported native RTF0 run formatting control')
    return font, bold, size, color


def parse_rtf(raw, color_commands=None):
    need(len(raw) <= RTF_LIMIT, 'Native label text exceeds the supported size')
    envelope = DOCUMENT.fullmatch(raw)
    need(envelope is not None, 'Expected the native RTF0 label envelope')
    prefix, font_table, palette, body, suffix = envelope.group('prefix', 'fonts', 'palette', 'body', 'suffix')
    fonts = {int(index) for index in FONT.findall(font_table)}
    need(fonts, 'No declared native RTF0 font')
    colors = color_palette(palette)
    out, fragments = [], []
    font, bold, size, color = None, False, None, 0
    pos, run_start, paragraph = 0, 0, 0
    # Some older native label donors have AppKit marker bytes before the text.
    while pos < len(body):
        line_break = LINE_BREAK.match(body, pos)
        token = WORD.match(body, pos)
        if line_break or token or body[pos] in (10, 13):
            if fragments:
                out.append(Run(run_start, pos, ''.join(fragments), Style(font, bold, size, color), paragraph))
                fragments = []
            if line_break:
                paragraph += 1
                pos = line_break.end()
            elif token:
                if color_commands is not None and token[1] == b'cf':
                    color_commands.append(token.span())
                font, bold, size, color = control_style(*token.groups(), font, bold, size, color, fonts, len(colors))
                pos = token.end()
            else:
                pos += 1
            continue
        if not out and not fragments and body[pos:pos + 2] == b'\x08\x08':
            pos += 2
            continue
        need(font is not None and size is not None, 'Native label text needs explicit font and point size')
        if not fragments:
            run_start = pos
        if body[pos:pos + 1] == b'\\':
            escaped = body[pos + 1:pos + 2]
            if escaped in (b'\\', b'{', b'}'):
                fragments.append(escaped.decode('ascii'))
                pos += 2
            else:
                pair = body[pos + 2:pos + 4]
                need(escaped == b"'" and re.fullmatch(rb'[0-9a-fA-F]{2}', pair), 'Unsupported native RTF0 escape')
                fragments.append(bytes([int(pair, 16)]).decode('cp1252'))
                pos += 4
        else:
            byte = body[pos]
            need(byte >= 32 and byte != 127 and byte not in (123, 125), 'Unsupported native RTF0 text or nested group')
            fragments.append(bytes([byte]).decode('cp1252'))
            pos += 1
    if fragments:
        out.append(Run(run_start, len(body), ''.join(fragments), Style(font, bold, size, color), paragraph))
    need(out, 'Native rich-text label has no editable run')
    return prefix, body, suffix, out


def rtf1_tables(raw):
    start = RTF1_START.match(raw)
    need(start is not None, 'Use RTF0 or ANSI Windows-1252 RTF1 using the reviewed text controls')
    position = start.end()
    need(raw.startswith(b'{\\fonttbl', position), 'RTF1 requires a font table')
    position += len(b'{\\fonttbl')
    while raw[position:position + 1] in (b' ', b'\r', b'\n', b'\t'):
        position += 1
    entries = []
    while (match := RTF1_FONT.match(raw, position)) is not None:
        entries.append(b'\\f' + match[1] + b'\\f' + match[2] + b' ' + match[3] + b';')
        position = match.end()
    if not entries:
        end = raw.find(b'}', position)
        need(end >= position, 'Unclosed RTF1 font table')
        entries = [raw[position:end]]
        position = end
    need(raw[position:position + 1] == b'}', 'Unsupported RTF1 font declaration')
    fonts = b''.join(entries)
    indexed_fonts = font_entries(fonts)
    tail = raw[position + 1:]
    palette = None
    next_group = tail.lstrip()
    if next_group.startswith(b'{\\colortbl'):
        end = next_group.find(b'}')
        need(end >= 0, 'Unclosed RTF1 color table')
        palette = next_group[len(b'{\\colortbl'):end]
        color_palette(palette)
        tail = next_group[end + 1:]
    defaults = re.findall(rb'\\deff([0-9]+)', start[1])
    need(len(defaults) <= 1, 'RTF1 declares more than one default font')
    default = int(defaults[0]) if defaults else 0
    need(default in indexed_fonts, 'The RTF1 default font is unlisted')
    need(tail.endswith(b'}'), 'Unclosed RTF1 document')
    return fonts, indexed_fonts, palette, default, tail[:-1].lstrip(b'\r\n')


def external_label_rtf(raw):
    need(0 < len(raw) <= RTF_LIMIT, 'External rich text exceeds the supported size')
    stripped = raw.strip()
    if stripped.startswith(b'{\\rtf0'):
        candidate = raw if DOCUMENT.fullmatch(raw) else stripped + b'\n'
        prefix = DOCUMENT.fullmatch(candidate)
        need(prefix is not None, 'Expected the reviewed native RTF0 envelope')
        font_entries(prefix['fonts'])
        need(re.fullmatch(rb'(?:\\(?:tx[0-9]+|q(?:natural|[lcrj])) ?)*', prefix['paragraph']),
             'Unsupported external RTF0 paragraph setting')
        parse_rtf(candidate)
        return candidate, 'rtf0'

    fonts, indexed_fonts, palette, default, body = rtf1_tables(stripped)
    color_count = len(color_palette(palette))
    normal = Style(default, False, 24)
    style, alignment = normal, b'l'
    scope, seen_alignments, runs = [], set(), []
    position, paragraph = 0, 0
    while position < len(body):
        byte = body[position:position + 1]
        if byte == b'{':
            need(len(scope) < 32, 'External RTF group nesting exceeds supported bounds')
            scope.append((style, alignment))
            position += 1
            continue
        if byte == b'}':
            need(scope, 'Unmatched external RTF group close')
            style, alignment = scope.pop()
            position += 1
            continue
        if byte in (b'\r', b'\n'):
            position += 1
            continue
        token = WORD.match(body, position)
        if token:
            name, value = token.groups()
            position = token.end()
            if name in (b'f', b'fs', b'b', b'cf'):
                style = Style(*control_style(name, value, style.font, style.bold, style.size, style.color,
                                             indexed_fonts, color_count))
            elif name == b'par' and value is None:
                paragraph += 1
            elif name == b'pard' and value is None:
                alignment = b'l'
            elif name in (b'ql', b'qc', b'qr', b'qj') and value is None:
                alignment = name[-1:]
            elif name == b'plain' and value is None:
                style = normal
            elif name == b'viewkind' and value == b'4':
                pass
            else:
                raise ValueError(f'Unsupported external RTF1 control {name.decode("ascii")}')
            continue
        character = RTF_CHARACTER.match(body, position)
        need(character is not None and character[0] != b'\\', 'Unsupported external RTF character')
        position = character.end()
        value = character[0]
        if value.startswith(b"\\'"):
            value = bytes([int(value[2:], 16)])
        elif value.startswith(b'\\'):
            value = value[1:]
        text = value.decode('cp1252')
        need(text.isprintable(), 'External RTF contains a nonprintable character')
        seen_alignments.add(alignment)
        if runs and runs[-1][1:] == (style, paragraph):
            runs[-1][0].append(text)
        else:
            runs.append(([text], style, paragraph))
    need(not scope and runs and len(seen_alignments) == 1, 'RTF1 needs complete groups and one shared paragraph alignment')
    out = [b'{\\rtf0\\ansi{\\fonttbl' + fonts + b'}']
    if palette is not None:
        out.append(b'{\\colortbl' + palette + b'}')
    out.append(b'\n\\pard\\q' + next(iter(seen_alignments)) + b'\n\n')
    before, previous_paragraph = Style(-1, False, -1), 0
    last_paragraph = paragraph
    expected = []
    for fragments, styled, paragraph in runs:
        words = ''.join(fragments)
        expected.append((words, styled, paragraph))
        out.append(b'\\par ' * (paragraph - previous_paragraph))
        out.append(controls(before, styled))
        out.append(b''.join(f"\\'{char:02x}".encode('ascii') if char >= 128 else
                            (b'\\' if char in b'{}\\' else b'') + bytes([char]) for char in words.encode('cp1252')))
        before, previous_paragraph = styled, paragraph
    out.extend((b'\\par ' * (last_paragraph - previous_paragraph), b'}\n'))
    candidate = b''.join(out)
    found = parse_rtf(candidate)[3]
    need(normalized((run.text, run.style, run.paragraph) for run in found) == normalized(expected),
         'External rich-text conversion changed text or formatting')
    return candidate, 'rtf1'


def controls(before, after):
    result = []
    if before.font != after.font:
        result.append(b'\\f%d' % after.font)
    if before.bold != after.bold:
        result.append(b'\\b' if after.bold else b'\\b0')
    if before.size != after.size:
        result.append(f'\\fs{after.size}'.encode('ascii'))
    if before.color != after.color:
        result.append(b'\\cf%d' % after.color)
    return b''.join(result) + b' ' if result else b''


def quote_text(text):
    return re.sub(rb'([{}\\])', rb'\\\1', text.encode('ascii'))


def normalized(runs):
    merged = []
    for text, style, paragraph in runs:
        if merged and merged[-1][1:] == (style, paragraph):
            merged[-1] = (merged[-1][0] + text, style, paragraph)
        else:
            merged.append((text, style, paragraph))
    return merged


def revise_rtf(raw, edits):
    prefix, body, suffix, runs = parse_rtf(raw)
    envelope = DOCUMENT.fullmatch(raw)
    fonts = font_entries(envelope['fonts']) if any(fragment.font for edit in edits for fragment in edit.replace_with) else {}
    colors = color_palette(envelope['palette'])
    font_count, color_count = len(fonts), len(colors)
    selections = {edit.index: edit for edit in edits}
    need(len(selections) == len(edits) and all(index < len(runs) for index in selections), 'Unknown or duplicate rich-text run')
    sections, expected = [], []
    cursor, added_paragraphs = 0, 0
    for index, run in enumerate(runs):
        sections.append(body[cursor:run.start])
        cursor = run.end
        edit = selections.get(index)
        if edit is None:
            sections.append(body[run.start:run.end])
            expected.append((run.text, run.style, run.paragraph + added_paragraphs))
            continue
        need(edit.expected_text == run.text, 'Selected rich-text run differs from its expected text')
        active = run.style
        for fragment in edit.replace_with:
            if fragment.paragraph_break_before:
                sections.append(b'\\par\n')
                added_paragraphs += 1
            font = run.style.font if fragment.font is None else fragment_font(fragment.font, fonts, run.style.font)
            color = run.style.color
            if fragment.text_rgb is not None:
                rgb = tuple(fragment.text_rgb)
                if rgb not in colors:
                    colors.append(rgb)
                color = colors.index(rgb)
            style = Style(font, run.style.bold if fragment.bold is None else fragment.bold,
                          run.style.size if fragment.size_half_points is None else fragment.size_half_points,
                          color)
            sections.extend((controls(active, style), quote_text(fragment.text)))
            expected.append((fragment.text, style, run.paragraph + added_paragraphs))
            active = style
        if run.end < len(body):
            sections.append(controls(active, run.style))
    updates = []
    if len(fonts) != font_count:
        # New declarations follow existing entries with the same AppKit RTF0 layout.
        new_fonts = list(fonts.items())[font_count:]
        insert = envelope.end('fonts')
        updates.append((insert, insert, b''.join(b'\\f%d\\f%s %s;' % (index, family, face)
                                                 for index, (family, face) in new_fonts)))
    if len(colors) != color_count:
        new_colors = b''.join(b'\\red%d\\green%d\\blue%d;' % color for color in colors[color_count:])
        if envelope['palette'] is None:
            insert = envelope.end('fonts') + 1
            updates.append((insert, insert, b'{\\colortbl;' + new_colors + b'}'))
        else:
            insert = envelope.end('palette')
            updates.append((insert, insert, new_colors))
    candidate = b''.join([replace_spans(prefix, updates), *sections, body[cursor:], suffix])
    parsed = parse_rtf(candidate)
    need(normalized((run.text, run.style, run.paragraph) for run in parsed[3]) == normalized(expected),
         'Edited native RTF styles or paragraphs differ on readback')
    return candidate


def replace_spans(source, updates):
    for start, end, value in sorted(updates, reverse=True):
        source = source[:start] + value + source[end:]
    return source


def label_record(raw, graphic_id):
    root, version, _ = load_worksheet(raw)
    labels = {item.contents[0].value: item for item in catalogs.array(root.contents[2].value)
              if writer.kind(item) == 'OTLabelModel'}
    model = labels.get(graphic_id)
    need(model is not None and incoming_counts(root)[id(model)] == 1, 'Select an independently owned native Label')
    graphic = model.clazz.superclass.version
    need(graphic in (0, 1), 'Unrecognized native Label graphic ancestry')
    extra = ['@'] if graphic else []
    layout(model, [('OTLabelModel', 1), ('OTGraphicModel', graphic), ('NSObject', 0)],
           ['i', 'f', 'f', 'f', 'i', 'i', *extra, '@', 'ffff', '@', 'iii', '@', '@'])
    index = 6 + graphic
    need((not graphic or model.contents[6].value is None) and model.contents[index + 2].value is None
         and model.contents[index + 3].values[1] == 0 and model.contents[index + 3].values[2] in (0, 1),
         'Temporary, simulation or dependency-bound Labels need their owning editor')
    stored = model.contents[index].value
    name = writer.kind(stored)
    need(name in ('NSData', 'NSMutableData'), 'Expected native Label RTF bytes in NSData')
    size = stored.contents[0].value
    need(type(size) is int and 0 < size <= RTF_LIMIT, 'Invalid native Label byte count')
    lineage = ([('NSMutableData', 0)] if name == 'NSMutableData' else []) + [('NSData', 0), ('NSObject', 0)]
    layout(stored, lineage, ['i', f'[{size}c]'])
    payload = stored.contents[1].value
    need(isinstance(payload, writer.Array) and isinstance(payload.elements, bytes) and len(payload.elements) == size,
         'Malformed native Label RTF bytes')
    return root, version, model, index, payload.elements


def describe_rtf(raw):
    runs = parse_rtf(raw)[3]
    envelope = DOCUMENT.fullmatch(raw)
    palette = color_palette(envelope['palette'])
    multiline = any(run.paragraph for run in runs)
    return {'rtf_sha256': sha(raw),
            'fonts': [{'index': int(match[1]), 'family': match[2].decode('ascii'), 'face': match[3].decode('cp1252')}
                      for match in FONT_ENTRY.finditer(envelope['fonts'])],
            'runs': [{'index': index, 'text': run.text, 'font_index': run.style.font,
                      'bold': run.style.bold, 'size_half_points': run.style.size,
                      **({'paragraph': run.paragraph} if multiline else {}),
                      **({'text_rgb': list(palette[run.style.color])} if run.style.color else {})}
                     for index, run in enumerate(runs)]}


def edit_rtf_appearance(raw, appearance):
    color_tokens = []
    _, body, _, runs = parse_rtf(raw, color_tokens)
    envelope = DOCUMENT.fullmatch(raw)
    updates = []
    if appearance.font is not None:
        font = FONT_ENTRY.fullmatch(envelope['fonts'])
        need(font is not None, 'Whole-label font editing requires one declared native RTF0 face')
        family = font[2] if appearance.font.family is None else appearance.font.family.encode('ascii')
        replacement = b'\\f%s\\f%s %s;' % (font[1], family, appearance.font.face.encode('ascii'))
        updates.append((*envelope.span('fonts'), replacement))
    if appearance.paragraph_alignment is not None:
        paragraph = PARAGRAPH.sub(b'', envelope['paragraph'])
        replacement = paragraph + b'\\q' + ALIGNMENTS[appearance.paragraph_alignment]
        updates.append((*envelope.span('paragraph'), replacement))
    if appearance.text_rgb is not None:
        palette = b'{\\colortbl;\\red%d\\green%d\\blue%d;}' % tuple(appearance.text_rgb)
        after_fonts = envelope.end('fonts') + 1
        start, end = envelope.span('colors') if envelope['colors'] is not None else (after_fonts, after_fonts)
        updates.append((start, end, palette))
        body_start = envelope.start('body')
        for start, end in color_tokens:
            replacement = b'\\cf1 ' if body[end - 1:end] == b' ' else b'\\cf1'
            updates.append((body_start + start, body_start + end, replacement))
        if not any(end <= runs[0].start for _, end in color_tokens):
            first_text = body_start + runs[0].start
            updates.append((first_text, first_text, b'\\cf1 '))
    candidate = replace_spans(raw, updates)
    expected = [(run.text, replace(run.style, color=1) if appearance.text_rgb is not None else run.style,
                 run.paragraph) for run in runs]
    readback = parse_rtf(candidate)[3]
    need(normalized((run.text, run.style, run.paragraph) for run in readback) == normalized(expected),
         'Native RTF0 body changed outside the requested appearance')
    return candidate


def native_color(value):
    if value is None:
        return None
    chain = [('NSColor', 0), ('NSObject', 0)]
    if writer.kind(value) != 'NSColor' or not value.contents or value.contents[0].value not in (1, 3):
        return {'encoding': 'unsupported'}
    layout(value, chain, ['c', 'ffff'] if value.contents[0].value == 1 else ['c', 'ff'])
    color_space, channels = value.contents[0].value, value.contents[1].values
    need(color_space in (1, 3) and all(math.isfinite(channel) and 0 <= channel <= 1 for channel in channels),
         'Unsupported native Label NSColor')
    rgb = channels[:3] if color_space == 1 else [channels[0]] * 3
    return {'rgb': [round(channel * 255) for channel in rgb], 'alpha': channels[-1]}


def encode_native_color(rgb):
    return obj([('NSColor', 0), ('NSObject', 0)], [('c', [1]),
        ('ffff', [*(flt(channel / 255, 'Label color component') for channel in rgb), flt(1, 'Label alpha')])])


def describe_appearance(model, index, raw):
    envelope = DOCUMENT.fullmatch(raw) if raw is not None else None
    need(raw is None or envelope is not None, 'Expected the native RTF0 label envelope')
    font = FONT_ENTRY.fullmatch(envelope['fonts']) if envelope else None
    alignments = PARAGRAPH.findall(envelope['paragraph']) if envelope else ()
    alignment = next((token for token in reversed(alignments) if token != b'natural'), None)
    anchor, _, flags = model.contents[index + 3].values
    return {'resize_anchor': next((name for name, value in ANCHORS.items() if value == anchor), None),
            'paragraph_alignment': next((name for name, value in ALIGNMENTS.items() if value == alignment), None),
            'font': {'face': font[3].decode('cp1252'), 'family': font[2].decode('ascii')} if font else None,
            'text_color': native_color(model.contents[index + 4].value),
            'background_color': native_color(model.contents[index + 5].value),
            'draws_background': bool(flags & 1)}


def edit_archive(raw, graphic_id, edits, appearance=None, *, replacement_rtf=None):
    need(not (appearance and appearance.font and any(fragment.font for edit in edits for fragment in edit.replace_with)),
         'Choose whole-label or per-run font changes in one request')
    need(not (appearance and appearance.text_rgb and any(fragment.text_rgb for edit in edits for fragment in edit.replace_with)),
         'Choose whole-label or per-run foreground changes in one request')
    root, version, model, index, original = label_record(raw, graphic_id)
    styled = replacement_rtf if replacement_rtf is not None else (revise_rtf(original, edits) if edits else original)
    try:
        before_text = describe_rtf(original)
    except ValueError:
        if replacement_rtf is None:
            raise
        before_text = {'rtf_sha256': sha(original), 'prior_format_outside_inspection': True}
    before_appearance = describe_appearance(model, index, original if 'runs' in before_text else None)
    before = writer.fingerprint(root)
    changed = []
    fields = model.contents

    def change(slot, element, value):
        values = fields[slot].values
        changed.append((values, element, values[element]))
        values[element] = value

    if appearance is not None:
        styled = edit_rtf_appearance(styled, appearance)
        if appearance.resize_anchor is not None:
            change(index + 3, 0, ANCHORS[appearance.resize_anchor])
        if appearance.draws_background is not None:
            change(index + 3, 2, int(appearance.draws_background))
        if appearance.text_rgb is not None:
            change(index + 4, 0, encode_native_color(appearance.text_rgb))
        if appearance.background_rgb is not None:
            change(index + 5, 0, encode_native_color(appearance.background_rgb))
    if styled != original:
        change(index, 0, writer.GenericArchivedObject(fields[index].value.clazz,
            contents=[writer.TypedValue(b'i', len(styled)),
                      writer.TypedValue(f'[{len(styled)}c]'.encode('ascii'), writer.Array(styled))]))
    after_appearance = describe_appearance(model, index, styled)
    output = writer.dump_verified(root, version)
    model_fields_changed = any(values is not fields[index].values for values, _, _ in changed)
    for values, element, previous in reversed(changed):
        values[element] = previous
    need(writer.fingerprint(root) == before, 'An unrelated worksheet field or reference changed')
    _, _, verified, verified_index, verified_rtf = label_record(output, graphic_id)
    need(verified_rtf == styled and describe_appearance(verified, verified_index, verified_rtf) == after_appearance,
         'Native rich-text Label differs after archive readback')
    return output, {'graphic_id': graphic_id, 'before': before_text, 'after': describe_rtf(styled),
                    'appearance_before': before_appearance, 'appearance_after': after_appearance,
                    'frame_xywh': list(fields[index + 1].values), 'fresh_archive_reload_verified': True,
                    'original_object_graph_preserved_outside_rtf': not model_fields_changed,
                    'original_object_graph_preserved_outside_selected_label_fields': True}


def add_imported_label(raw, rtf, frame, appearance):
    root, stream, _ = load_worksheet(raw)
    before = writer.fingerprint(root)
    owner = root.contents[2]
    items = catalogs.array(owner.value)
    model_id = max((item.contents[0].value for item in items), default=-1) + 1
    need(model_id < 2**31 and writer.kind(owner.value) == 'NSMutableArray'
         and incoming_counts(root)[id(owner.value)] == 1, 'Expected a privately owned worksheet with a free graphic ID')
    graphic = 0 if root.clazz.version == 1 else 1
    x, y, width, height = [flt(getattr(frame, key), 'Label frame') for key in ('x', 'y', 'width', 'height')]
    need(0 < width <= 100000 and 0 < height <= 100000, 'Label dimensions must remain in native frame bounds')
    center = (flt(x + width / 2, 'Label center x'), flt(y + height / 2, 'Label center y'))
    rtf = edit_rtf_appearance(rtf, appearance) if appearance is not None else rtf
    encoded = obj([('NSData', 0), ('NSObject', 0)],
                  [('i', [len(rtf)]), (f'[{len(rtf)}c]', [writer.Array(rtf)])])
    anchor = ANCHORS[appearance.resize_anchor] if appearance and appearance.resize_anchor else 1
    description = describe_rtf(rtf)
    colors = {tuple(run.get('text_rgb', [0, 0, 0])) for run in description['runs']}
    foreground = appearance.text_rgb if appearance and appearance.text_rgb else (
        next(iter(colors)) if len(colors) == 1 else [0, 0, 0])
    background = appearance.background_rgb if appearance and appearance.background_rgb else [255, 255, 255]
    filled = int(bool(appearance and appearance.draws_background))
    groups = [('i', [model_id]), ('f', [0.0]), ('f', [center[0]]), ('f', [center[1]]), ('i', [0]), ('i', [0])]
    if graphic:
        groups.append(('@', [None]))
    groups.extend([('@', [encoded]), ('ffff', [x, y, width, height]), ('@', [None]), ('iii', [anchor, 0, filled]),
                   ('@', [encode_native_color(foreground)]), ('@', [encode_native_color(background)])])
    model = obj([('OTLabelModel', 1), ('OTGraphicModel', graphic), ('NSObject', 0)], groups)
    new_array = writer.GenericArchivedObject(owner.value.clazz)
    writer.set_elements(new_array, [*items, model])
    owner.value = new_array
    output = writer.dump_verified(root, stream)
    check, _, restored, index, found = label_record(output, model_id)
    need(found == rtf and restored.contents[index + 1].values == [x, y, width, height],
         'New native rich-text Label differs after archive readback')
    reloaded_items = catalogs.array(check.contents[2].value)
    writer.set_elements(check.contents[2].value, [item for item in reloaded_items if item is not restored])
    need(writer.fingerprint(check) == before, 'An unrelated worksheet field or reference changed')
    return output, {'graphic_id': model_id, 'after': description,
                    'appearance_after': describe_appearance(restored, index, found),
                    'frame_xywh': [x, y, width, height], 'fresh_archive_reload_verified': True,
                    'original_object_graph_preserved_outside_selected_label_fields': True}


class RichLabels(ArchiveTools):
    def source(self, spec, suffix='.opentrack'):
        path = self.path(spec.path)
        if path.suffix.casefold() != suffix:
            raise APIError('NATIVE_RTF_SOURCE', f'Use a source with extension {suffix}')
        raw = self.secure_bytes(path)
        if sha(raw) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'Rich-text source differs from its requested SHA-256')
        return path, raw

    def inspect(self, args):
        _, raw = self.source(args.worksheet)
        try:
            _, _, model, index, rtf = label_record(raw, args.graphic_id)
            return {'source_sha256': sha(raw), 'graphic_id': args.graphic_id,
                    'frame_xywh': list(model.contents[index + 1].values),
                    'appearance': describe_appearance(model, index, rtf), **describe_rtf(rtf)}
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_RTF_INVALID', str(exc)[:500]) from exc

    def edit(self, args):
        source, raw = self.source(args.worksheet)
        try:
            output, report = edit_archive(raw, args.graphic_id, args.edits, args.appearance)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_RTF_INVALID', str(exc)[:500]) from exc
        return self.finish(source, raw, output, report, args)

    def import_rtf(self, args):
        source, raw = self.source(args.worksheet)
        path, external = self.source(args.rtf, '.rtf')
        try:
            rtf, encoding = external_label_rtf(external)
            if args.graphic_id is None:
                output, report = add_imported_label(raw, rtf, args.frame, args.appearance)
            else:
                output, report = edit_archive(raw, args.graphic_id, (), args.appearance, replacement_rtf=rtf)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_RTF_INVALID', str(exc)[:500]) from exc
        report.update(input_rtf_sha256=sha(external), input_format=encoding,
                      operation='insert' if args.graphic_id is None else 'replace')
        return self.finish(source, raw, output, report, args, additional_inputs={path: external})

    def finish(self, source, raw, output, report, args, *, additional_inputs=None):
        result = {'saved': False, 'preview_only': args.preview_only, 'source_sha256': sha(raw),
                  'output_sha256': sha(output), 'output_bytes': len(output), **report}
        if args.preview_only:
            if any(self.secure_bytes(path) != content for path, content in {source: raw, **(additional_inputs or {})}.items()):
                raise APIError('SOURCE_CHANGED', 'Rich-text source changed during preview')
            return result
        if self.path(args.target_path).suffix.casefold() != '.opentrack':
            raise APIError('NATIVE_RTF_TARGET', 'Use a fresh .opentrack worksheet target')
        if len(output) > 20 * 1024 * 1024:
            raise APIError('ARCHIVE_SIZE', 'Generated worksheet exceeds 20 MiB')
        return self.save_copy(source, raw, output, result, args.target_path, additional_inputs=additional_inputs,
                              validate_output=lambda data: label_record(data, report['graphic_id']))


def tool_definitions(root):
    api = RichLabels(root)
    return [('opentrack_inspect_saved_worksheet_rich_label', 'Inspect native rich-text Label runs and appearance.',
             ReadLabel, api.inspect),
            ('opentrack_edit_saved_worksheet_rich_label', 'Edit native RTF0 paragraphs, run formatting, and '
             'standalone Label alignment, foreground and background. Preserve other worksheet graphics.',
             EditLabel, api.edit, False, False),
            ('opentrack_import_saved_worksheet_rich_label', 'Insert or replace a native editable standalone Label '
             'from an external RTF0 or reviewed ANSI RTF1 text file.',
             ImportRTF, api.import_rtf, False, False)]
