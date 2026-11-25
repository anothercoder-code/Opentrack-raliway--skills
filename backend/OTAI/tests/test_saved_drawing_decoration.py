"""Verify the original OTLineModel diagonal flag through native save and readback."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.saved_geometry_tools import DrawingStyle
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_cross_document_route_native_edit import fixture
from test_saved_geometry import apply


MODEL_ID = 100000


def shape_case(kind='OTLineModel', angle=0.0, flags=3):
    docs, catalog = fixture()
    root, version = writer.load_next_compatible(docs['A'])
    shape = native.obj([(kind, 0), ('OTResizeModel', 0), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [MODEL_ID]), ('f', [angle]), ('f', [35.0]), ('f', [20.0]), ('i', [0]), ('i', [0]), ('@', [None]),
        ('if', [flags, 1.5]), ('ff', [33.0, 17.0]), ('ff', [55.0, 25.0]), ('@', [None]), ('@', [None]),
    ])
    graphics = root.contents[2].value
    writer.set_elements(graphics, [*writer.elements(graphics), shape])
    return {**docs, 'A': writer.dump_verified(root, version)}, catalog


def edit(docs, catalog, **style):
    style = DrawingStyle.model_validate(style).model_dump(exclude_unset=True)
    return apply(docs, catalog, {
        'action': 'edit_decoration', 'graphic_id': MODEL_ID,
        'delta_x': 0, 'delta_y': 0, 'text': None, 'drawing_style': style,
    })


@pytest.mark.parametrize('flags, flipped, expected', [(2, True, 3), (3, False, 2), (1, False, 0), (0, True, 1)])
def test_flip_line_preserves_filled_flag_stroke_and_frame_origin(flags, flipped, expected):
    docs, catalog = shape_case(flags=flags)
    after, report = edit(docs, catalog, line_flipped=flipped, height_points=26)
    line = after.model(('A', MODEL_ID))
    assert line.contents[1].value == 0 and line.contents[8].values == [33, 17]
    assert line.contents[7].values == [expected, 1.5] and line.contents[9].values == [55, 31]
    assert report['drawing_style_after']['flipped'] is flipped
    assert report['drawing_style_after']['filled'] is bool(flags & 2)
    assert report['destination_catalog_unchanged'] and report['movement_count_checked'] > 0


def test_omitting_diagonal_selection_preserves_the_existing_native_flag():
    docs, catalog = shape_case(flags=1)
    result, _ = edit(docs, catalog, width_points=65, line_width_points=3.5)
    assert result.model(('A', MODEL_ID)).contents[7].values == [1, 3.5]


@pytest.mark.parametrize('kind, angle', [('OTRectModel', 0), ('OTCircleModel', 0), ('OTLineModel', 90)])
def test_explicit_diagonal_selection_rejects_other_shapes_and_rotated_frame(kind, angle):
    docs, catalog = shape_case(kind, angle)
    with pytest.raises(ValueError, match='unrotated standalone native Line'):
        edit(docs, catalog, line_flipped=False)


@pytest.mark.parametrize('kind', ['OTRectModel', 'OTCircleModel', 'OTLineModel'])
def test_size_guard_for_unverified_rotated_frames_is_unchanged(kind):
    docs, catalog = shape_case(kind, 90)
    with pytest.raises(ValueError, match='Size changes require an unrotated drawing'):
        edit(docs, catalog, width_points=40)


def test_diagonal_selection_rejects_non_boolean_input():
    with pytest.raises(ValueError, match='valid boolean'):
        DrawingStyle.model_validate({'line_flipped': 1})

