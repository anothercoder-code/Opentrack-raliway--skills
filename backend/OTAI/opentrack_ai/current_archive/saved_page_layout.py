"""Read and write the native worksheet fields used by Page Layout."""

import math
from typing import Annotated, Literal

from pydantic import Field, StrictFloat, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import writer
from .bundle_tools import Source
from .multi_document.core import layout, need
from .next_tools import Save
from .tools import ArchiveTools, Input, sha
from .zero_generation.native_signal_routes import string
from .zero_generation.topology import DOC_ENC, flt


ORIENTATIONS = ('portrait', 'landscape')
PAGINATION = ('automatic', 'fit', 'clip')
MARGINS = ('left', 'right', 'bottom', 'top')
PRINT_FIELDS = slice(14, 18)
MarginValue = Annotated[StrictInt | StrictFloat, Field(ge=0, le=500000, allow_inf_nan=False)]
PaperDimension = Annotated[StrictInt | StrictFloat, Field(gt=0, le=500000, allow_inf_nan=False)]
PaperName = Annotated[StrictStr, Field(min_length=1, max_length=120, pattern=r'^[ -~]+$')]


class InspectPageLayout(Input):
    worksheet: Source


class PrintMargins(Input):
    left: MarginValue
    right: MarginValue
    bottom: MarginValue
    top: MarginValue


class Paper(Input):
    name: PaperName | None
    portrait_width_pt: PaperDimension
    portrait_height_pt: PaperDimension

    @model_validator(mode='after')
    def portrait_dimensions(self):
        if self.portrait_width_pt > self.portrait_height_pt:
            raise ValueError('Supply unrotated portrait paper dimensions')
        return self


class EditPageLayout(Save, InspectPageLayout):
    margins_pt: PrintMargins | None = None
    orientation: Literal['portrait', 'landscape'] | None = None
    horizontal_pagination: Literal['automatic', 'fit', 'clip'] | None = None
    vertical_pagination: Literal['automatic', 'fit', 'clip'] | None = None
    paper: Paper | None = None

    @model_validator(mode='after')
    def explicit_change(self):
        fields = {'margins_pt', 'orientation', 'horizontal_pagination', 'vertical_pagination', 'paper'}
        changes = fields & self.model_fields_set
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError('Supply one or more explicit non-null page settings')
        return self


def worksheet_page(raw):
    root, stream = writer.load_next_compatible(raw)
    version = root.clazz.version
    need(version in (3, 4), 'Page Layout uses the reviewed OTDocument3/4 print fields')
    layout(root, [('OTDocument', version), ('NSObject', 0)],
           DOC_ENC[:19] if version == 3 else DOC_ENC)
    return root, stream


def describe_page(root):
    margin, setup, paper_size, name = root.contents[PRINT_FIELDS]
    orientation, horizontal, vertical = setup.values
    need(0 <= orientation < len(ORIENTATIONS) and
         0 <= horizontal < len(PAGINATION) and 0 <= vertical < len(PAGINATION),
         'Unrecognized native orientation or pagination code')
    need(all(math.isfinite(value) for value in [*margin.values, *paper_size.values]),
         'Non-finite native Page Layout value')
    return {
        'document_version': root.clazz.version,
        'margins_pt': dict(zip(MARGINS, map(float, margin.values))),
        'orientation': ORIENTATIONS[orientation],
        'horizontal_pagination': PAGINATION[horizontal],
        'vertical_pagination': PAGINATION[vertical],
        'paper_name': None if name.value is None else writer.string(name.value),
        'paper_size_pt': [float(value) for value in paper_size.values],
    }


def edit_page(raw, args):
    root, stream = worksheet_page(raw)
    before = describe_page(root)
    margin, setup, paper_size, name = root.contents[PRINT_FIELDS]

    if args.margins_pt is not None:
        margin.values[:] = [flt(getattr(args.margins_pt, key), 'Page margin') for key in MARGINS]
    if args.horizontal_pagination is not None:
        setup.values[1] = PAGINATION.index(args.horizontal_pagination)
    if args.vertical_pagination is not None:
        setup.values[2] = PAGINATION.index(args.vertical_pagination)

    orientation = ORIENTATIONS.index(args.orientation) if args.orientation is not None else setup.values[0]
    if args.paper is not None:
        portrait = [flt(args.paper.portrait_width_pt, 'Paper width'),
                    flt(args.paper.portrait_height_pt, 'Paper height')]
        paper_size.values[:] = portrait[::-1] if orientation else portrait
        if args.paper.name != before['paper_name']:
            name.value = string(args.paper.name) if args.paper.name is not None else None
    elif setup.values[0] != orientation:
        paper_size.values.reverse()
    setup.values[0] = orientation

    after = describe_page(root)
    if before == after:
        return raw, before, after
    if any(after[key] != before[key] for key in ('margins_pt', 'paper_size_pt')):
        left, right, bottom, top = margin.values
        width, height = paper_size.values
        need(min(left, right, bottom, top) >= 0 and width > left + right and height > bottom + top,
             'Page margins must leave a positive area within the stored paper size')

    output = writer.dump_verified(root, stream)
    cold, _ = worksheet_page(output)
    need(describe_page(cold) == after, 'Saved Page Layout differs on readback')
    del root.contents[PRINT_FIELDS]
    del cold.contents[PRINT_FIELDS]
    need(writer.fingerprint(cold) == writer.fingerprint(root),
         'A field outside the native Page Layout changed')
    return output, before, after


class PageLayoutTools(ArchiveTools):
    def source(self, spec):
        path = self.path(spec.path)
        if path.suffix.casefold() != '.opentrack':
            raise APIError('PAGE_LAYOUT_SOURCE', 'An ordinary .opentrack worksheet is required')
        raw = self.secure_bytes(path)
        if sha(raw) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'Worksheet differs from its requested SHA-256')
        return path, raw

    @staticmethod
    def check_page(raw):
        try:
            return describe_page(worksheet_page(raw)[0])
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise APIError('PAGE_LAYOUT_INVALID', str(exc)[:500]) from exc

    def inspect(self, args):
        _, raw = self.source(args.worksheet)
        return {'source_sha256': sha(raw), **self.check_page(raw)}

    def edit(self, args):
        source, raw = self.source(args.worksheet)
        try:
            output, before, after = edit_page(raw, args)
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise APIError('PAGE_LAYOUT_INVALID', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'source_sha256': sha(raw),
                  'output_sha256': sha(output), 'before': before, 'after': after,
                  'non_print_fields_preserved': True, 'fresh_archive_reload_verified': True}
        if args.preview_only:
            if self.secure_bytes(source) != raw:
                raise APIError('SOURCE_CHANGED', 'Worksheet changed during preview')
            return result
        if self.path(args.target_path).suffix.casefold() != '.opentrack':
            raise APIError('PAGE_LAYOUT_TARGET', 'Use a fresh .opentrack worksheet target')
        if len(output) > 20 * 1024 * 1024:
            raise APIError('ARCHIVE_SIZE', 'Generated worksheet exceeds 20 MiB')
        return self.save_copy(source, raw, output, result, args.target_path, validate_output=self.check_page)


def tool_definitions(root):
    tools = PageLayoutTools(root)
    return [
        ('opentrack_inspect_saved_page_layout',
         'Read native worksheet paper size, orientation, margins and horizontal and vertical pagination.',
         InspectPageLayout, tools.inspect),
        ('opentrack_edit_saved_page_layout',
         'Save revised native worksheet Page Layout and pagination without changing the worksheet canvas or model graph.',
         EditPageLayout, tools.edit, False, False),
    ]
