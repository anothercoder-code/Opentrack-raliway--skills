import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.saved_plot_tools import (
    DOC_ENC, GRAPHIC_FIELDS, PLOT_FIELDS, RESIZE_FIELDS, EditPlot, EditPlotSeries, PlotTools, ReadPlot,
    describe, edit_archive, edit_series_archive, load_worksheet, plot_fields,
)
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.native_signal_routes import arr, obj, string


def values(encodings, overrides):
    empty = {'i': 0, 'f': 0.0, '@': None}
    return [(encoding, overrides.get(index, [empty[char] for char in encoding]))
            for index, encoding in enumerate(encodings)]


def point(x, y):
    return obj([('OTPlotPoint', 0), ('NSObject', 0)], [('ff', [x, y])])


def worksheet(version, *, shared=False, update_flags=4):
    start, end = point(0.0, 0.0), point(5.0, 75.0)
    color = obj([('NSColor', 0), ('NSObject', 0)], [('c', [3]), ('ff', [0.5, 1.0])])
    series = obj([('OTPlot', 1), ('NSObject', 0)], values(['@', '@', 'ffff', 'fi', '@', '@', 'ii'], {
        0: [arr([start, end])], 1: [string('OT_100.vs')], 2: [0.0, 0.0, 5.0, 75.0],
        3: [2.0, 0], 4: [color], 5: [string('100')], 6: [9, update_flags],
    }))
    fields = GRAPHIC_FIELDS + ['@'] + RESIZE_FIELDS

    def plot(mid):
        prefix = [('OTPlotModel', version), ('OTResizeModel', 0), ('OTGraphicModel', 1), ('NSObject', 0)]
        tail = values(PLOT_FIELDS, {0: [arr([series])], 1: [arr()], 2: [arr()], 3: [start], 4: [end],
            7: [1.0, 10.0], 9: [1, 0], 10: [arr()], 11: [192 if version == 4 else 0],
            13: [string('Time')], 14: [string('[km/h]')]})
        return obj(prefix, [*values(fields, {0: [mid]}), *tail])

    return writer.dump_verified(obj([('OTDocument', 4), ('NSObject', 0)],
        values(DOC_ENC, {0: [17], 2: [arr([plot(48), plot(64)] if shared else [plot(48)])]})))


def test_plot_axis_changes_keep_actual_data_points_and_recompute_native_increments():
    raw = worksheet(4)
    changes = {'x_title': 'Seconds', 'y_title': 'Speed (km/h)', 'x_range': {'minimum': 0, 'maximum': 600},
               'y_range': {'minimum': 0, 'maximum': 300}, 'x_grid': True, 'show_y_legend': False}
    series = [{'index': 0, 'expected_name': 'OT_100.vs', 'changes': {'name': 'Speed trace', 'line_width': 3.5}}]
    output, report = edit_archive(raw, 48, changes, series)
    model = load_worksheet(output)[2][48]
    fields = plot_fields(model)
    stored = describe(model)
    assert stored == report['after']
    assert stored['axes']['show_y_legend'] is False and stored['axes']['show_x_legend'] is True
    assert stored['axes']['x_grid'] is True and stored['axes']['x_title'] == 'Seconds'
    assert report['before']['axis_increments'] == [1.0, 10.0]
    assert stored['axis_increments'] == [1.0, 100.0]
    assert stored['series'] == [{'index': 0, 'name': 'Speed trace', 'line_width': 3.5, 'point_count': 2,
                                'run_updates': {'plot_type': 9, 'course_id': '100', 'allows_overwrite_data': False,
                                                'overwrite_data': False, 'allows_plot_online': True,
                                                'plot_online': False}}]
    curve, = catalogs.array(fields['series'].value)
    original_points = catalogs.array(curve.contents[0].value)
    assert [point.contents[0].values for point in original_points] == [[0, 0], [5, 75]]
    assert original_points[0] is not fields['minimum'].value
    assert catalogs.text(curve.contents[5].value) == '100' and curve.contents[6].values == [9, 4]


def test_line_run_update_switches_follow_native_setters():
    line = {'index': 0, 'expected_name': 'OT_100.vs'}
    raw = worksheet(4, update_flags=5)
    enabled, report = edit_archive(raw, 48, {}, [{**line, 'changes': {'plot_online': True}}])
    assert report['after']['series'][0]['run_updates']['overwrite_data']
    assert report['after']['series'][0]['run_updates']['plot_online']
    offline, report = edit_archive(enabled, 48, {}, [{**line, 'changes': {'plot_online': False}}])
    assert report['after']['series'][0]['run_updates']['overwrite_data']
    assert not report['after']['series'][0]['run_updates']['plot_online']
    stopped, report = edit_archive(enabled, 48, {}, [{**line, 'changes': {'overwrite_data': False}}])
    assert not report['after']['series'][0]['run_updates']['overwrite_data']
    assert not report['after']['series'][0]['run_updates']['plot_online']
    assert stopped == raw
    assert offline != raw
    with pytest.raises(ValueError, match='does not allow overwriting'):
        edit_archive(worksheet(4), 48, {}, [{**line, 'changes': {'plot_online': True}}])
    with pytest.raises(ValueError, match='requires overwriting'):
        edit_archive(raw, 48, {}, [{**line, 'changes': {'overwrite_data': False, 'plot_online': True}}])


def test_older_plot_grid_and_caption_do_not_emit_ignored_legend_visibility():
    raw = worksheet(3)
    output, _ = edit_archive(raw, 48, {'x_grid': True, 'y_title': 'Raw speed'}, [])
    fresh = describe(load_worksheet(output)[2][48])
    assert fresh['axes']['x_grid'] and fresh['axes']['show_x_legend'] and fresh['axes']['show_y_legend']
    with pytest.raises(ValueError, match='PlotModel4'):
        edit_archive(raw, 48, {'show_y_legend': False}, [])


def test_plot_rejects_native_float_collapse_and_ambiguous_series():
    with pytest.raises(ValueError, match='binary32 precision'):
        edit_archive(worksheet(4), 48, {'x_range': {'minimum': 10**11, 'maximum': 10**11 + 1}}, [])
    edit = {'index': 0, 'expected_name': 'OT_100.vs', 'changes': {'line_width': 4}}
    with pytest.raises(ValueError, match='Shared Plot series'):
        edit_archive(worksheet(4, shared=True), 48, {}, [edit])
    with pytest.raises(ValueError, match='series name differs'):
        edit_archive(worksheet(4), 48, {}, [{**edit, 'expected_name': 'other'}])


def test_normal_plot_preview_publish_and_readback(tmp_path):
    location = tmp_path / 'OTAI/workspaces/NativePlot'
    location.mkdir(parents=True)
    source, target = location / 'old.opentrack', location / 'edited.opentrack'
    raw = worksheet(4)
    source.write_bytes(raw)
    bound = {'path': source.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}
    args = EditPlot(source=bound, plot_id=48, axes={'y_detail_grid': True}, target_path=target.relative_to(tmp_path).as_posix())
    tools = PlotTools(tmp_path)
    assert tools.inspect(ReadPlot(source=bound))['plots'][0]['plot_id'] == 48
    preview = tools.edit(args)
    assert not preview['saved'] and not target.exists()
    result = tools.edit(args.model_copy(update={'preview_only': False}))
    assert result['saved'] and result['output_sha256'] == preview['output_sha256'] == sha(target.read_bytes())
    assert source.read_bytes() == raw


def test_line_actions_use_frozen_donor_and_progressive_output_ordinals(tmp_path):
    project = tmp_path / 'OTAI/workspaces/NativePlot'
    project.mkdir(parents=True)
    source, target = project / 'orig.opentrack', project / 'edited.opentrack'
    blob = worksheet(4)
    source.write_bytes(blob)
    operations = [
        {'action': 'insert_existing_series', 'index': 0, 'name': 'Reference copy',
         'donor': {'plot_id': 48, 'index': 0, 'expected_name': 'OT_100.vs'}},
        {'action': 'delete_series', 'index': 1, 'expected_name': 'OT_100.vs'},
        {'action': 'insert_existing_series', 'index': 1, 'name': 'Second copy',
         'donor': {'plot_id': 48, 'index': 0, 'expected_name': 'OT_100.vs'}},
    ]
    api = PlotTools(tmp_path)
    args = EditPlotSeries(source={'path': source.relative_to(tmp_path).as_posix(), 'sha256': sha(blob)},
                          plot_id=48, operations=operations, viewport='fit_line_data',
                          target_path=target.relative_to(tmp_path).as_posix())
    preview = api.edit_series(args)
    assert not target.exists() and preview['after']['axes']['x_range'] == {'minimum': 0.0, 'maximum': 600.0}
    saved = api.edit_series(args.model_copy(update={'preview_only': False}))
    assert saved['saved'] and saved['output_sha256'] == preview['output_sha256'] == sha(target.read_bytes())
    assert source.read_bytes() == blob
    fields = plot_fields(load_worksheet(target.read_bytes())[2][48])
    first, second = catalogs.array(fields['series'].value)
    assert [catalogs.text(row.contents[1].value) for row in (first, second)] == ['Reference copy', 'Second copy']
    assert first.contents[6].values == second.contents[6].values == [9, 4]
    assert writer.fingerprint(first.contents[0].value) == writer.fingerprint(second.contents[0].value)
    assert first is not second and first.contents[0].value is not second.contents[0].value


def test_delete_last_line_preserves_view_and_fit_requires_saved_line_data():
    old = worksheet(4)
    operations = [{'action': 'delete_series', 'index': 0, 'expected_name': 'OT_100.vs'}]
    _, receipt = edit_series_archive(old, 48, operations, 'preserve', {})
    assert receipt['after']['series'] == []
    assert receipt['before']['axes'] == receipt['after']['axes']
    with pytest.raises(ValueError, match='nonempty saved line data'):
        edit_series_archive(old, 48, operations, 'fit_line_data', {})


def test_external_live_series_requires_original_scope_and_matching_axes():
    original = worksheet(4)
    root, stream, plots = load_worksheet(original)
    fields = plot_fields(plots[48])
    donor = {'action': 'insert_existing_series', 'index': 0,
             'donor': {'worksheet': {'path': 'external'}, 'plot_id': 48, 'index': 0, 'expected_name': 'OT_100.vs'}}
    series, = catalogs.array(fields['series'].value)
    series.contents[6].values[1] = 15
    external = writer.dump_verified(root, stream)
    with pytest.raises(ValueError, match='Active online'):
        edit_series_archive(original, 48, [donor], 'preserve', {'external': external})
    fields['x_title'].value = string('Different unit')
    with pytest.raises(ValueError, match='axis types and captions'):
        edit_series_archive(original, 48, [donor], 'preserve', {'external': writer.dump_verified(root, stream)})
