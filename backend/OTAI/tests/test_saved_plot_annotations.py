import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.saved_plot_tools import (
    CreatePlot, EditPlot, PlotTools, ReadPlot, create_plot_archive, edit_archive, load_worksheet, plot_fields,
)
from opentrack_ai.current_archive.tools import sha
from test_saved_plot import worksheet


BARS = [{'name': 'Signed binned delay', 'color_rgb': [24, 46, 80], 'outline_width': 2,
         'points': [{'value': -5.5, 'course_id': 'E1', 'station_sign': 'WEST', 'time_s': 3600},
                    {'value': 0}, {'value': 9.25, 'course_id': 'E2'}]}]
MARKERS = {'x': [[{'name': 'West', 'point': [1, -5.5], 'kind': 'station', 'angle_deg': 90},
                  {'name': 'MS', 'point': [2, 0], 'kind': 'signal'}]],
           'y': [[{'name': 'Baseline', 'point': [0, 0]}]]}


def source(data):
    return {'path': 'input.opentrack', 'sha256': sha(data)}


def create_request(raw):
    return CreatePlot(source=source(raw), frame={'x': 40, 'y': 35, 'width': 450, 'height': 300},
                      bar_series=BARS, axis_marker_groups=MARKERS)


def test_native_bar_plot_constructs_ordered_points_and_original_marker_wire_format():
    raw = worksheet(4)
    output, receipt = create_plot_archive(raw, create_request(raw), {})
    root, stream, plots = load_worksheet(output)
    generated = plots[receipt['plot']['plot_id']]
    fields = plot_fields(generated)
    (bars,) = catalogs.array(fields['bars'].value)
    assert (writer.kind(bars), bars.clazz.superclass.name, bars.clazz.superclass.version) == ('OTBarPlot', b'OTPlot', 1)
    assert bars.contents[6].values == [0, 0] and bars.contents[2].values == [1, -5.5, 3, 9.25]
    points = catalogs.array(bars.contents[0].value)
    assert all(writer.kind(point) == 'OTBarPoint' and point.clazz.version == 1 for point in points)
    assert [point.contents[0].values for point in points] == [[1, -5.5], [2, 0], [3, 9.25]]
    assert [writer.string(point.contents[2].value) for point in points] == ['E1', '', 'E2']
    assert [point.contents[4].value for point in points] == [3600, -1, -1]
    (group,) = catalogs.array(fields['x_markers'].value)
    station, signal = catalogs.array(group)
    assert station.contents[0].values == [1084227584, 90]
    assert signal.contents[0].values == [1082130432, 0]
    assert receipt['plot']['axis_marker_groups']['x'][0][0]['kind'] == 'station'
    assert receipt['plot']['bar_series'][0]['color_rgb'] == [24, 46, 80]
    assert fields['data_minimum'].value.contents[0].values == [0, -5.5]
    assert fields['data_maximum'].value.contents[0].values == [4, 9.25]
    writer.set_elements(root.contents[2].value, [plots[48]])
    assert writer.dump_verified(root, stream) == raw


def test_native_marker_group_and_bar_lifecycle_preserve_unselected_objects(tmp_path):
    project = tmp_path / 'OTAI/workspaces/PlotAnnotations'
    project.mkdir(parents=True)
    input_path, output_path = project / 'source.opentrack', project / 'revised.opentrack'
    raw, _ = create_plot_archive(worksheet(4), create_request(worksheet(4)), {})
    input_path.write_bytes(raw)
    tools = PlotTools(tmp_path)
    source_binding = {'path': input_path.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}
    plots = tools.inspect(ReadPlot(source=source_binding, include_bar_points=True))['plots']
    (_, chart) = plots
    assert chart['bar_series'][0]['points'][0] == {
        'category': 1, 'value': -5.5, 'type': 0, 'course_id': 'E1', 'station_sign': 'WEST', 'time_s': 3600,
    }
    request = EditPlot(source={'path': input_path.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}, plot_id=49,
                       bars={'series': []}, axis_marker_groups={'x': []},
                       target_path=output_path.relative_to(tmp_path).as_posix())
    preview = tools.edit(request)
    assert not preview['saved'] and not output_path.exists()
    saved = tools.edit(request.model_copy(update={'preview_only': False}))
    assert saved['saved'] and saved['output_sha256'] == preview['output_sha256'] == sha(output_path.read_bytes())
    assert input_path.read_bytes() == raw
    assert 'bar_series' not in saved['after'] and saved['after']['axis_marker_groups'] == {'y': saved['before']['axis_marker_groups']['y']}
    assert saved['after']['axes'] == saved['before']['axes']


def test_axis_marker_write_does_not_modify_line_payload_or_active_bars():
    old = worksheet(4)
    args = EditPlot(source=source(old), plot_id=48, axis_marker_groups={'x': MARKERS['x']})
    updated, _ = edit_archive(old, 48, {}, [], axis_marker_groups=args.axis_marker_groups)
    original_line, saved_line = (plot_fields(load_worksheet(data)[2][48])['series'].value for data in (old, updated))
    assert writer.dump_verified(saved_line) == writer.dump_verified(original_line)

    active, _ = create_plot_archive(old, create_request(old), {})
    root, version, plots = load_worksheet(active)
    (bar,) = catalogs.array(plot_fields(plots[49])['bars'].value)
    bar.contents[6].values[:] = [36, 15]
    active = writer.dump_verified(root, version)
    args = EditPlot(source=source(active), plot_id=49, bars={'series': []})
    with pytest.raises(ValueError, match='offline bars without native simulation update bindings'):
        edit_archive(active, 49, {}, [], bars=args.bars)


def test_creation_refuses_combining_bar_points_with_native_line_inputs():
    raw = worksheet(4)
    request = create_request(raw).model_dump()
    request['point_files'] = [{'source': {'path': 'line.txt', 'sha256': '0' * 64}}]
    with pytest.raises(ValueError, match='Choose one data family'):
        CreatePlot.model_validate(request)


def test_zero_outline_uses_native_no_outline_setting():
    raw = worksheet(4)
    spec = create_request(raw)
    spec.bar_series[0].outline_width = 0
    output, receipt = create_plot_archive(raw, spec, {})
    fields = plot_fields(load_worksheet(output)[2][receipt['plot']['plot_id']])
    (bars,) = catalogs.array(fields['bars'].value)
    assert bars.contents[3].values[0] == 0


def delay_chart(raw, plot_id):
    root, stream, plots = load_worksheet(raw)
    fields = plot_fields(plots[plot_id])
    (series,) = catalogs.array(fields['bars'].value)
    return root, stream, fields, series


def test_runtime_delay_writes_exact_stock_seed_and_pauses_without_replacing_data():
    raw = worksheet(4)
    spec = CreatePlot(source=source(raw), frame={'x': 40, 'y': 35, 'width': 450, 'height': 300},
                      runtime_delay_bar=True)
    online, receipt = create_plot_archive(raw, spec, {})
    plot_id = receipt['plot']['plot_id']
    root, stream, fields, series = delay_chart(online, plot_id)
    assert series.contents[5].value is None and series.contents[6].values == [36, 15]
    assert series.contents[2].values == [0, 0, 0, 0] and series.contents[3].values == [1, 0]
    assert fields['data_minimum'].value is fields['data_maximum'].value is None
    (seed,) = catalogs.array(series.contents[0].value)
    assert seed.contents[0].values == [0, 0] and seed.contents[1].value == 0
    assert writer.string(seed.contents[2].value) == '0' and seed.contents[3].value is None and seed.contents[4].value == 0
    assert receipt['plot']['axis_marker_groups']['x'] == [[{
        'name': '', 'point': [0, 0], 'kind': 'text', 'native_type_raw': 0, 'angle_deg': 90,
        'color_rgb': [0, 0, 0],
    }]]
    assert receipt['plot']['axes']['y_title'] == 's'
    assert receipt['plot']['bar_series'][0]['run_updates']['course_scope'] == 'all_active_simulation_courses'
    seed.contents[0].values[:] = [1, 129]
    series.contents[2].values[:] = [1, 129, 1, 129]
    edited_online = writer.dump_verified(root, stream)
    paused, receipt = edit_archive(edited_online, plot_id, {}, [], runtime_delay_bar=False)
    assert receipt['before']['bar_series'][0]['run_flags'] == 15
    assert receipt['after']['bar_series'][0]['run_flags'] == 5
    assert not receipt['after']['bar_series'][0]['run_updates']['overwrite_data']
    assert delay_chart(paused, plot_id)[3].contents[6].values == [36, 5]
    resumed, _ = edit_archive(paused, plot_id, {}, [], runtime_delay_bar=True)
    assert resumed == edited_online


def test_runtime_delay_can_activate_blank_chart_and_refuses_offline_replacement():
    raw = worksheet(4)
    spec = CreatePlot(source=source(raw), frame={'x': 40, 'y': 35, 'width': 450, 'height': 300})
    blank, receipt = create_plot_archive(raw, spec, {})
    plot_id = receipt['plot']['plot_id']
    chart, receipt = edit_archive(blank, plot_id, {}, [], runtime_delay_bar=True)
    assert delay_chart(chart, plot_id)[3].contents[6].values == [36, 15]
    assert receipt['after']['axes']['y_title'] == 's'
    assert receipt['after']['axes']['x_range'] == receipt['before']['axes']['x_range']
    offline, receipt = create_plot_archive(raw, create_request(raw), {})
    plot_id = receipt['plot']['plot_id']
    with pytest.raises(ValueError, match='outside the reviewed global actual-delay binding'):
        edit_archive(offline, plot_id, {}, [], runtime_delay_bar=True)
    with pytest.raises(ValueError, match='runtime delay update owns X-axis marker groups'):
        EditPlot(source=source(chart), plot_id=plot_id, runtime_delay_bar=True, axis_marker_groups={'x': []})
