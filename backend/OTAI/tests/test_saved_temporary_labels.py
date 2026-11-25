import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.route_factory import SIGNAL
from opentrack_ai.current_archive.saved_plot_tools import DOC_ENC, load_worksheet
from opentrack_ai.current_archive.saved_temporary_labels import (
    CreateSignalNames, RemoveTemporary, SetTemporary, edit_labels, label_index,
)
from opentrack_ai.current_archive.zero_generation.native_signal_routes import arr, obj, string
from test_saved_plot import values


def signal(number, heading, *, kind=1, flags=0, side=0, name='F'):
    return obj([('OTSignalModel', 11), ('OTGraphicModel', 1), ('NSObject', 0)], values(
        SIGNAL, {0: [number], 2: [100.], 3: [150.], 4: [heading[0]], 5: [heading[1]],
                 8: [kind, 4, side], 9: [2, 0, flags, 0], 13: [string(name)]}))


def worksheet(items):
    root = obj([('OTDocument', 4), ('NSObject', 0)], values(DOC_ENC, {0: [17], 2: [arr(items)]}))
    return writer.dump_verified(root)


def test_signal_centers_escape_names_and_remove_labels_as_one_write():
    original = worksheet([
        signal(4, (1, 0), side=2, name=r'S:força {A}\A'),
        signal(9, (0, 3), kind=2, flags=6),
        signal(10, (2, 0), kind=9, flags=8),
        signal(14, (0, 4), name=''),
    ])
    result, report = edit_labels(original, CreateSignalNames(action='create_signal_name_labels'))
    assert [(row['signal_id'], row['label_id'], row['center_xy']) for row in report['created']] == [
        (4, 15, [109, 138]), (9, 16, [89, 161.5]), (10, 17, [99, 139]),
    ]
    back, removal = edit_labels(result, RemoveTemporary(action='remove_temporary_labels'))
    assert removal['removed_label_ids'] == [15, 16, 17]
    assert writer.fingerprint(load_worksheet(back)[0]) == writer.fingerprint(load_worksheet(original)[0])


def test_explicit_selection_and_convert_temporary_to_permanent():
    original = worksheet([signal(2, (0, 4)), signal(3, (1, 0))])
    result, report = edit_labels(original, CreateSignalNames(action='create_signal_name_labels', signal_ids=[3]))
    assert [item['signal_id'] for item in report['created']] == [3]
    permanent, change = edit_labels(result, SetTemporary(action='set_temporary_label', graphic_id=4,
                                                        expected_temporary=True, temporary=False))
    assert change['changed'] == [{'label_id': 4, 'temporary': False}]
    assert edit_labels(permanent, RemoveTemporary(action='remove_temporary_labels'))[0] == permanent
    root, _, _ = load_worksheet(permanent)
    stored = catalogs.array(root.contents[2].value)[-1]
    assert stored.contents[label_index(stored) + 3].values == [0, 0, 1]
    with pytest.raises(ValueError, match='reviewed state'):
        edit_labels(permanent, SetTemporary(action='set_temporary_label', graphic_id=4,
                                            expected_temporary=True, temporary=False))


def test_invalid_ids_are_rejected_and_unreviewed_visible_glyph_is_reported():
    original = worksheet([signal(5, (1, 0), kind=9)])
    with pytest.raises(ValueError, match='distinct saved Signal'):
        edit_labels(original, CreateSignalNames(action='create_signal_name_labels', signal_ids=[5, 5]))
    with pytest.raises(ValueError, match='ordinary main and combined'):
        edit_labels(original, CreateSignalNames(action='create_signal_name_labels', signal_ids=[5]))
