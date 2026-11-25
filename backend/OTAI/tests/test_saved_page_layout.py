import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.saved_page_layout import (
    EditPageLayout, PageLayoutTools, describe_page, edit_page, worksheet_page,
)
from opentrack_ai.current_archive.saved_plot_tools import DOC_ENC
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.native_signal_routes import arr, obj, string
from test_saved_plot import values


def worksheet(version):
    fields = {1: DOC_ENC[:14], 3: DOC_ENC[:19], 4: DOC_ENC}[version]
    slots = {0: [17], 2: [arr()], 9: [0., 0., 800., 600.], 14: [10., 20., 30., 40.],
             15: [0, 2, 0], 16: [595., 842.], 17: [string('A4')]}
    return writer.dump_verified(obj([('OTDocument', version), ('NSObject', 0)], values(fields, slots)))


def request(raw, **changes):
    return EditPageLayout(
        worksheet={'path': 'OTAI/workspaces/PageLayout/original.opentrack', 'sha256': sha(raw)},
        **changes,
    )


@pytest.mark.parametrize('version', [3, 4])
def test_resize_orientation_and_independent_pagination(version):
    raw = worksheet(version)
    output, before, after = edit_page(raw, request(raw,
        orientation='landscape', horizontal_pagination='fit', vertical_pagination='clip',
        margins_pt={'left': 17, 'right': 24, 'bottom': 31, 'top': 38},
        paper={'name': None, 'portrait_width_pt': 600, 'portrait_height_pt': 900},
    ))
    cold, _ = worksheet_page(output)
    assert before['paper_name'] == 'A4' and before['paper_size_pt'] == [595, 842]
    assert after == describe_page(cold) == {
        'document_version': version, 'paper_name': None, 'paper_size_pt': [900, 600],
        'orientation': 'landscape', 'horizontal_pagination': 'fit', 'vertical_pagination': 'clip',
        'margins_pt': {'left': 17, 'right': 24, 'bottom': 31, 'top': 38},
    }
    assert cold.contents[9].values == [0, 0, 800, 600]
    changed_again, _, page = edit_page(output, request(output, orientation='portrait'))
    assert page['paper_size_pt'] == [600, 900]
    assert edit_page(changed_again, request(changed_again, orientation='portrait'))[0] == changed_again


def test_legacy_archive_and_invalid_margins_are_rejected():
    legacy = worksheet(1)
    with pytest.raises(ValueError, match='OTDocument3/4'):
        edit_page(legacy, request(legacy, orientation='portrait'))
    raw = worksheet(4)
    with pytest.raises(ValueError, match='positive area'):
        edit_page(raw, request(raw, margins_pt={'left': 300, 'right': 300, 'bottom': 1, 'top': 2}))


def test_write_function_reopens_fresh_target_and_keeps_input(tmp_path):
    raw = worksheet(4)
    args = request(raw, orientation='landscape', target_path='OTAI/workspaces/PageLayout/out.opentrack')
    source = tmp_path / args.worksheet.path
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    target = tmp_path / args.target_path
    tool = PageLayoutTools(tmp_path)
    preview = tool.edit(args)
    assert not target.exists() and preview['after']['paper_size_pt'] == [842, 595]
    receipt = tool.edit(args.model_copy(update={'preview_only': False}))
    assert receipt['saved'] and receipt['after'] == preview['after']
    assert sha(target.read_bytes()) == preview['output_sha256']
    assert source.read_bytes() == raw
