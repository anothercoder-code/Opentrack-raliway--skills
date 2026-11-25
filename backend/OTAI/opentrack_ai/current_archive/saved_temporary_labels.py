"""Native standalone temporary signal-name labels and their lifecycle."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr

from ..errors import APIError
from . import catalogs, writer
from .bundle_tools import Source
from .graph_references import incoming_counts
from .multi_document.core import layout, need
from .next_tools import Ordinal, Save
from .path_functions import array_like
from .route_factory import SIGNAL
from .saved_plot_tools import load_worksheet
from .saved_rich_labels import describe_rtf, encode_native_color
from .tools import ArchiveTools, Input, sha
from .zero_generation.native_signal_routes import obj
from .zero_generation.topology import flt


GRAPHIC_CHAIN = [('OTGraphicModel', 1), ('NSObject', 0)]
GRAPHIC_FIELDS = ['i', 'f', 'f', 'f', 'i', 'i']
LABEL_FIELDS = ['@', 'ffff', '@', 'iii', '@', '@']
LABEL_CHAIN = [('OTLabelModel', 1), *GRAPHIC_CHAIN]
DATA_CHAIN = [('NSMutableData', 0), ('NSData', 0), ('NSObject', 0)]


class CreateSignalNames(Input):
    action: Literal['create_signal_name_labels']
    signal_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=2048)] | None = None
    font_face: Annotated[StrictStr, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}$')] = 'Helvetica'


class SetTemporary(Input):
    action: Literal['set_temporary_label']
    graphic_id: Ordinal
    expected_temporary: StrictBool
    temporary: StrictBool


class RemoveTemporary(Input):
    action: Literal['remove_temporary_labels']


class EditTemporaryLabels(Save):
    worksheet: Source
    operation: Annotated[CreateSignalNames | SetTemporary | RemoveTemporary, Field(discriminator='action')]


def signal_center(signal):
    fields = signal.contents
    signal_type, _, side = fields[8].values
    flags = fields[9].values[2]
    if flags & 8:
        icon_width = icon_height = symbol_width = 0
    else:
        need(signal_type in (1, 2), 'Signal icon placement is verified for ordinary main and combined signals')
        # Stock images are 72 dpi. Only width changes between virtual and lamp icons.
        icon_width = (9 if flags & 2 else 14) + (5 if signal_type == 2 else 0)
        icon_height = 7
        symbol_width = 7 if flags & 4 else 0
    reach = (icon_width + symbol_width) / 2
    x, y, along_x, along_y = [fields[index].value for index in (2, 3, 4, 5)]
    offsets = {
        (1, 0): (reach + 2, 10 if side == 0 else -12),
        (2, 0): (-reach - 1, -11 if side == 0 else 11),
        (0, 3): (-11 if side == 0 else 11, reach + 1),
        (0, 4): (11 if side == 0 else -11, -reach),
    }
    need((along_x, along_y) in offsets, 'A named Signal must have a reviewed horizontal or vertical orientation')
    dx, dy = offsets[along_x, along_y]
    return [float(x) + dx, float(y) + dy]


def rtf_name(name, font):
    raw = name.encode('cp1252')
    need(len(raw) <= 1024 and all(byte >= 32 and byte != 127 for byte in raw),
         'Signal name must fit the native printable one-line label format')
    escaped = bytearray()
    for byte in raw:
        if byte >= 128:
            escaped.extend(f"\\'{byte:02x}".encode('ascii'))
        else:
            if byte in b'\\{}':
                escaped.append(ord('\\'))
            escaped.append(byte)
    return (b'{\\rtf0\\ansi{\\fonttbl\\f0\\fswiss ' + font.encode('ascii')
            + b';}\n\\pard\\tx560\\ql\\qnatural\n\n\\f0\\fs12 \\cf0 ' + escaped + b'}\n')


def new_label(mid, center, text, font):
    rtf = rtf_name(text, font)
    data = obj(DATA_CHAIN, [('i', [len(rtf)]), (f'[{len(rtf)}c]', [writer.Array(rtf)])])
    x, y = center
    # The original view uses the stored center and lays out text using the installed font.
    width, height = max(18, len(text) * 6 + 22), 20
    return obj(LABEL_CHAIN, [
        ('i', [mid]), ('f', [0.0]), ('f', [flt(x, 'Label x')]), ('f', [flt(y, 'Label y')]),
        ('i', [0]), ('i', [0]), ('@', [None]), ('@', [data]),
        ('ffff', [flt(x - width / 2, 'Label frame x'), flt(y - height / 2, 'Label frame y'),
                  float(width), float(height)]),
        ('@', [None]), ('iii', [0, 1, 1]),
        ('@', [encode_native_color([0, 0, 0])]), ('@', [encode_native_color([170, 170, 170])]),
    ])


def label_index(model):
    graphic = model.clazz.superclass.version
    need(graphic in (0, 1), 'Unreviewed native Label graphic ancestry')
    fields = GRAPHIC_FIELDS + (['@'] if graphic else []) + LABEL_FIELDS
    layout(model, [('OTLabelModel', 1), ('OTGraphicModel', graphic), ('NSObject', 0)], fields)
    return 6 + graphic


def owned_label(model, counts):
    base = label_index(model)
    need(counts[id(model)] == 1 and (base == 6 or model.contents[6].value is None)
         and model.contents[base + 2].value is None and model.contents[base + 3].values[2] in (0, 1),
         'An attached or simulation Label needs its owning editor')
    return model.contents[base + 3].values


def create_names(models, selection, max_id):
    signals = {model.contents[0].value: model for model in models if writer.kind(model) == 'OTSignalModel'}
    if selection.signal_ids is not None:
        ids = set(selection.signal_ids)
        need(len(ids) == len(selection.signal_ids) and ids <= signals.keys(), 'Select distinct saved Signal graphic IDs')
        signals = {mid: model for mid, model in signals.items() if mid in ids}

    additions, records = [], []
    for mid, entry in signals.items():
        # Pre-1.7 Signal versions do not necessarily have signalName.
        if entry.clazz.version != 11 and selection.signal_ids is None:
            continue
        layout(entry, [('OTSignalModel', 11), *GRAPHIC_CHAIN], SIGNAL)
        field = entry.contents[13].value
        name = writer.string(field) if field is not None else ''
        if not name:
            continue
        center = signal_center(entry)
        label_id = max_id + len(additions) + 1
        need(label_id < 2**31, 'Graphic ID exhausted')
        label = new_label(label_id, center, name, selection.font_face)
        additions.append(label)
        records.append({'signal_id': mid, 'label_id': label_id, 'signal_name': name,
                        'center_xy': [float(label.contents[index].value) for index in (2, 3)]})
    return additions, records


def edit_labels(raw, operation):
    root, stream, _ = load_worksheet(raw)
    models = catalogs.array(root.contents[2].value)
    id_map = {model.contents[0].value: model for model in models}
    before_graph = writer.fingerprint(root)
    replace = root.contents[2]
    counts = incoming_counts(root)
    added, removed, changed = [], [], []

    if isinstance(operation, CreateSignalNames):
        need(root.clazz.version in (3, 4), 'Creation needs a reviewed ordinary OTDocument3/4 worksheet')
        additions, added = create_names(models, operation, max(id_map, default=-1))
        if additions:
            need(counts[id(replace.value)] == 1, 'Shared worksheet graphic list cannot be replaced')
            replace.value = array_like(replace.value, [*models, *additions])
    elif isinstance(operation, SetTemporary):
        selected = id_map.get(operation.graphic_id)
        need(selected is not None and writer.kind(selected) == 'OTLabelModel', 'Select a native Label graphic')
        flags = owned_label(selected, counts)
        need(flags[1] in (0, 1) and bool(flags[1]) == operation.expected_temporary,
             'Native Label temporary status differs from the reviewed state')
        flags[1] = int(operation.temporary)
        if operation.temporary != operation.expected_temporary:
            changed = [{'label_id': operation.graphic_id, 'temporary': operation.temporary}]
    else:
        for mid, model in id_map.items():
            if writer.kind(model) != 'OTLabelModel' or model.clazz.version < 1:
                continue
            base = label_index(model)
            if model.contents[base + 3].values[1] == 1:
                owned_label(model, counts)
                removed.append(mid)
        if removed:
            need(counts[id(replace.value)] == 1, 'Shared worksheet graphic list cannot be replaced')
            excluded = set(removed)
            replace.value = array_like(replace.value, [model for mid, model in id_map.items() if mid not in excluded])

    summary = {'created': added, 'removed_label_ids': removed, 'changed': changed}
    if not (added or removed or changed):
        return raw, summary
    output = writer.dump_verified(root, stream)
    cold, _, _ = load_worksheet(output)
    cold_models = catalogs.array(cold.contents[2].value)
    cold_ids = {model.contents[0].value: model for model in cold_models}
    if added:
        for row in added:
            model = cold_ids[row['label_id']]
            base = label_index(model)
            rtf = model.contents[base].value.contents[1].value.elements
            runs = describe_rtf(rtf)['runs']
            need(''.join(run['text'] for run in runs) == row['signal_name']
                 and all(run['size_half_points'] == 12 for run in runs)
                 and model.contents[base + 3].values[1] == 1
                 and [model.contents[index].value for index in (2, 3)] == row['center_xy'],
                 'Native temporary Signal label differs on readback')
        added_ids = {row['label_id'] for row in added}
        field = cold.contents[2]
        field.value = array_like(field.value, [model for mid, model in cold_ids.items() if mid not in added_ids])
        need(writer.fingerprint(cold) == before_graph, 'Original worksheet changed outside added Signal labels')
    elif changed:
        stored = cold_ids[operation.graphic_id]
        base = label_index(stored)
        flags = stored.contents[base + 3].values
        need(flags[1] == int(operation.temporary), 'Native temporary flag differs on readback')
        flags[1] = int(operation.expected_temporary)
        need(writer.fingerprint(cold) == before_graph, 'Original worksheet changed outside the selected flag')
    else:
        need(not set(removed) & cold_ids.keys(), 'Temporary Label still present on readback')
    return output, summary


class TemporaryLabelsTools(ArchiveTools):
    def edit(self, args):
        source = self.path(args.worksheet.path)
        if source.suffix.casefold() != '.opentrack':
            raise APIError('TEMPORARY_LABEL_SOURCE', 'An ordinary .opentrack worksheet is required')
        raw = self.secure_bytes(source)
        if sha(raw) != args.worksheet.sha256:
            raise APIError('SOURCE_CHANGED', 'Worksheet differs from its requested SHA-256')
        try:
            output, summary = edit_labels(raw, args.operation)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
            raise APIError('TEMPORARY_LABEL_INVALID', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'source_sha256': sha(raw),
                  'output_sha256': sha(output), 'fresh_archive_reload_verified': True, **summary}
        if args.preview_only:
            if self.secure_bytes(source) != raw:
                raise APIError('SOURCE_CHANGED', 'Worksheet changed during preview')
            return result
        if self.path(args.target_path).suffix.casefold() != '.opentrack':
            raise APIError('TEMPORARY_LABEL_TARGET', 'Use a fresh .opentrack worksheet target')
        if len(output) > 20 * 1024 * 1024:
            raise APIError('ARCHIVE_SIZE', 'Generated worksheet exceeds 20 MiB')
        return self.save_copy(source, raw, output, result, args.target_path, validate_output=load_worksheet)


def tool_definitions(root):
    tools = TemporaryLabelsTools(root)
    return [('opentrack_edit_saved_temporary_labels',
             'Create native temporary Signal-name labels, set a standalone Label temporary or permanent, '
             'or remove temporary Labels from the worksheet. Preserve operational objects.',
             EditTemporaryLabels, tools.edit, False, False)]
