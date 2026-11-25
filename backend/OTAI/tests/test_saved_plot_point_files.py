import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.occupation_plot_files import saved_points
from opentrack_ai.current_archive.plot_point_files import read_point_data, read_points
from opentrack_ai.current_archive.saved_plot_tools import (
    CreatePlot, PlotTools, create_plot_archive, edit_series_archive, load_worksheet, plot_fields,
)
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError
from test_saved_plot import worksheet


def test_multiple_external_y_columns_as_independent_native_series():
    clock = b'// Type    : OT_TimeXPlot\n// Desc.   : OT_vt\n// y-Legend: [km/h]\n20 1 2\n150 8\n200 4 12\n'
    data = read_point_data(clock, 'OT_A1.vt')
    assert data.captions == ('Time', '[km/h]')
    assert data.columns == (((20, 1), (150, 8), (200, 4)), ((20, 2), (200, 12)))
    operation = {'action': 'insert_external_series', 'index': 1, 'source': {'path': 'OT_A1.vt'}}
    output, status = edit_series_archive(worksheet(4), 48, [operation], 'preserve', {}, {'OT_A1.vt': clock})
    assert status['before']['axes'] == status['after']['axes']
    fields = plot_fields(load_worksheet(output)[2][48])
    old, first, second = catalogs.array(fields['series'].value)
    assert read_points(old) == [(0, 0), (5, 75)]
    assert [read_points(row) for row in (first, second)] == [list(column) for column in data.columns]
    assert first.contents[2].values == [20, 1, 200, 8]
    assert second.contents[2].values == [20, 2, 200, 12]
    assert first.contents[6].values == [5, 5] and writer.string(first.contents[5].value) == 'A1'
    assert fields['data_minimum'].value.contents[0].values == [0, 0]
    assert fields['data_maximum'].value.contents[0].values == [200, 75]
    with pytest.raises(ValueError, match='same native axis types'):
        edit_series_archive(worksheet(4), 48, [operation], 'preserve', {}, {'OT_A1.vt': b'2 4\n3 5\n'})


def test_create_blank_plot_and_load_a_constant_line_without_collapsing_axes():
    original = worksheet(4)
    request = CreatePlot(source={'path': 'input.opentrack', 'sha256': sha(original)},
                         frame={'x': 100, 'y': 50, 'width': 300, 'height': 200})
    blank, result = create_plot_archive(original, request, {})
    assert result['frame_xywh'] == [100, 50, 300, 200] and result['plot']['series'] == []
    blank_root, _, plots = load_worksheet(blank)
    new = plots[49]
    assert [new.contents[i].values for i in range(7, 10)] == [[1, 1], [100, 50], [300, 200]]
    assert writer.fingerprint(plots[48]) == writer.fingerprint(load_worksheet(original)[2][48])
    table = b'// Type: OT_Plot\n0 5\n10 5\n'
    request = CreatePlot(source=request.source,
                         frame=request.frame, point_files=[{'source': {'path': 'flat.txt', 'sha256': sha(table)}}])
    filled, result = create_plot_archive(original, request, {'flat.txt': table})
    stored = load_worksheet(filled)[2][49]
    assert result['plot']['axes']['y_range'] == {'minimum': 4.0, 'maximum': 6.0}
    assert result['plot']['axes']['x_title'] == ''
    assert read_points(catalogs.array(plot_fields(stored)['series'].value)[0]) == [(0, 5), (10, 5)]
    assert blank_root.clazz.version == 4


def test_bad_plot_text_and_native_specialized_modes_are_rejected():
    with pytest.raises(ValueError, match='one to five numeric Y'):
        read_point_data(b'0 nan\n', 'bad.txt')
    with pytest.raises(ValueError, match='numeric line Plot file'):
        read_point_data(b'// Type: OT_BarYPlot\n1 2\n', 'bars.txt')
    with pytest.raises(ValueError, match='Conflicting Plot header'):
        read_point_data(b'// Type: OT_Plot\n// Type: OT_TimeXPlot\n1 2\n', 'conflict.txt')


def test_create_native_occupation_plot_preserves_timed_state_transitions_and_display_option():
    original = worksheet(4)
    occ = (
        b'// Produced by OpenTrack: 2026-11-24\n// Desc.   : OT_occ\n'
        b'100\tRDG_P9\tSR\tRDG09\n112\tRDG_P9\tEP\tRDG09\n-1\tRDG_P9\tSO\tRDG09\n'
        b'140\tRDG_P9\tEO\tRDG09\n150\tRDG_P9\tER\tRDG09\n'
    )
    name = 'OT_Occ_RDG_P9.occ'
    request = CreatePlot(source={'path': 'input.opentrack', 'sha256': sha(original)},
                         frame={'x': 0, 'y': 0, 'width': 320, 'height': 250},
                         occupation_files=[{'source': {'path': name, 'sha256': sha(occ)},
                                            'show_reservations': False}])
    output, receipt = create_plot_archive(original, request, {name: occ})
    assert receipt['plot']['axis_types'] == [1, 0]
    assert receipt['operations'][0]['untimed_events_omitted'] == 1
    assert receipt['plot']['occupation_series'] == [
        {'name': 'RDG P9', 'point_count': 4, 'time_bounds_s': [100.0, 150.0], 'show_reservations': False}]
    record, = catalogs.array(plot_fields(load_worksheet(output)[2][49])['occupation_series'].value)
    assert saved_points(record) == ((100.0, 1, 'RDG09'), (112.0, 7, 'RDG09'),
                                    (140.0, 3, 'RDG09'), (150.0, 4, 'RDG09'))
    assert [record.contents[i].value for i in (5, 6)] == [2, 43]
    with pytest.raises(ValueError, match='one occupation resource'):
        create_plot_archive(original, request, {name: occ.replace(b'150\tRDG_P9', b'150\tRDG_P10')})


def test_tunnel_result_uses_native_tunnel_axis_and_clears_y_legend():
    table = b'// Type : OT_Plot\n// Desc.   : OT_tunnel\n// x-Legend: [km]\n// y-Legend: none\n0 0\n5 1\n'
    original = worksheet(4)
    request = CreatePlot(
        source={'path': 'input.opentrack', 'sha256': sha(original)},
        frame={'x': 0, 'y': 0, 'width': 320, 'height': 250},
        point_files=[{'source': {'path': 'OT_A1.tunnel', 'sha256': sha(table)}}],
    )
    result, receipt = create_plot_archive(original, request, {'OT_A1.tunnel': table})
    assert receipt['plot']['axis_types'] == [0, 2]
    assert receipt['plot']['axes']['x_title'] == '[km]' and receipt['plot']['axes']['y_title'] == ''
    stored = load_worksheet(result)[2][receipt['plot']['plot_id']]
    line, = catalogs.array(plot_fields(stored)['series'].value)
    assert read_points(line) == [(0, 0), (5, 1)]


def test_blank_legacy_plot_fits_first_external_curve_and_reports_old_line_metadata():
    raw = worksheet(4, shared=True)
    root, stream, plots = load_worksheet(raw)
    empty, legacy = plot_fields(plots[48]), plot_fields(plots[64])
    original_series, = catalogs.array(legacy['series'].value)
    original_series.clazz = writer.Class(b'OTPlot', 0, original_series.clazz.superclass)
    del original_series.contents[5:]
    writer.set_elements(empty['series'].value, [])
    empty['maximum'].value = empty['minimum'].value
    raw = writer.dump_verified(root, stream)
    file = b'// Type: OT_TimeXPlot\n// Desc.   : OT_vt\n1000 5\n1200 5\n'
    action = {'action': 'insert_external_series', 'index': 0, 'source': {'path': 'OT_F1.vt'}}
    preview, receipt = edit_series_archive(raw, 48, [action], 'preserve', {}, {'OT_F1.vt': file}, fit_empty=True)
    assert receipt['viewport'] == 'fit_line_data'
    assert receipt['after']['axes']['x_range'] == {'minimum': 600, 'maximum': 1200}
    assert receipt['after']['axes']['y_range'] == {'minimum': 4, 'maximum': 6}
    assert receipt['operations'][0]['archived_line_version'] == 0
    assert receipt['operations'][0]['saved_course_and_options'] is None
    fields = plot_fields(load_worksheet(preview)[2][48])
    record, = catalogs.array(fields['series'].value)
    assert record.clazz.version == 0 and read_points(record) == [(1000, 5), (1200, 5)]


def test_create_plot_fails_when_the_external_file_no_longer_matches_sha(tmp_path):
    project = tmp_path / 'OTAI/workspaces/NativePlot'
    project.mkdir(parents=True)
    source, table = project / 'original.opentrack', project / 'input.txt'
    raw = worksheet(4)
    source.write_bytes(raw)
    table.write_bytes(b'0 3\n1 5\n')
    request = CreatePlot(
        source={'path': source.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)},
        frame={'x': 0, 'y': 0, 'width': 320, 'height': 250},
        point_files=[{'source': {'path': table.relative_to(tmp_path).as_posix(), 'sha256': sha(b'0 3\n1 5\n')}}],
    )
    tool = PlotTools(tmp_path)
    assert tool.create(request)['plot']['series'][0]['point_count'] == 2
    table.write_bytes(b'0 3\n1 6\n')
    with pytest.raises(APIError, match='differs from its requested SHA-256'):
        tool.create(request)
