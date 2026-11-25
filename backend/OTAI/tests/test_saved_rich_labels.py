import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.saved_plot_tools import DOC_ENC
from opentrack_ai.current_archive.saved_rich_labels import (
    Appearance, EditLabel, ImportRTF, ReadLabel, RichLabels, RunEdit, describe_appearance, describe_rtf,
    edit_archive, edit_rtf_appearance, external_label_rtf, label_record, revise_rtf,
)
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.native_signal_routes import arr, obj
from test_saved_plot import values


PREFIX = b'{\\rtf0\\ansi{\\fonttbl\\f0\\fswiss Helvetica;}\n\\pard\\tx560\\ql\\qnatural\n\n'
BASE = PREFIX + b'\\f0\\b\\fs48 \\cf0 Output Example}\n'


def opts(index, expected, *replacements):
    return RunEdit(index=index, expected_text=expected, replace_with=list(replacements))


def stored_label(data):
    storage = obj([('NSMutableData', 0), ('NSData', 0), ('NSObject', 0)],
                  [('i', [len(data)]), (f'[{len(data)}c]', [writer.Array(data)])])
    label = obj([('OTLabelModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], values(
        ['i', 'f', 'f', 'f', 'i', 'i', '@', '@', 'ffff', '@', 'iii', '@', '@'],
        {0: [4], 7: [storage], 8: [11.0, 33.0, 206.0, 42.0], 10: [1, 0, 0]}))
    return writer.dump_verified(obj([('OTDocument', 4), ('NSObject', 0)], values(DOC_ENC, {0: [17], 2: [arr([label])]})))


def test_styled_run_splits_into_native_plain_and_bold_face_sizes():
    adjusted = revise_rtf(BASE, [opts(0, 'Output Example', {'text': 'Output '},
                                      {'text': 'example', 'bold': False, 'size_half_points': 36})])
    assert adjusted == PREFIX + b'\\f0\\b\\fs48 \\cf0 Output \\b0\\fs36 example}\n'
    assert describe_rtf(adjusted)['runs'] == [
        {'index': 0, 'text': 'Output ', 'font_index': 0, 'bold': True, 'size_half_points': 48},
        {'index': 1, 'text': 'example', 'font_index': 0, 'bold': False, 'size_half_points': 36},
    ]


def test_edit_restores_inherited_styles_of_unselected_existing_runs():
    mixed = PREFIX + b"\\f0\\b\\fs48 \\cf0 Title \\b0 first\\cf0 L\\'e9gier}\n"
    adjusted = revise_rtf(mixed, [opts(1, 'first', {'text': 'changed ', 'bold': True, 'size_half_points': 34})])
    assert b"\\b0\\fs48 \\cf0 L\\'e9gier" in adjusted
    resulting = describe_rtf(adjusted)['runs']
    assert resulting[-1]['text'] == 'Légier' and resulting[-1]['bold'] is False
    assert resulting[-1]['size_half_points'] == 48


def test_literal_special_characters_are_quoted_and_unsupported_sources_fail():
    adjusted = revise_rtf(BASE, [opts(0, 'Output Example', {'text': r'Group {A} \b0'})])
    assert describe_rtf(adjusted)['runs'][0]['text'] == r'Group {A} \b0'
    with pytest.raises(ValueError, match='expected text'):
        revise_rtf(BASE, [opts(0, 'Other phrase', {'text': 'Change'})])
    with pytest.raises(ValueError, match='formatting control'):
        revise_rtf(BASE.replace(b'\\fs48', b'\\i\\fs48'), [opts(0, 'Output Example', {'text': 'Change'})])


def test_native_rich_label_save_readback_and_second_edit(tmp_path):
    project = tmp_path / 'OTAI/workspaces/RichLabel'
    project.mkdir(parents=True)
    source, target = project / 'source.opentrack', project / 'styled.opentrack'
    original = stored_label(BASE)
    source.write_bytes(original)
    api = RichLabels(tmp_path)
    binding = {'path': source.relative_to(tmp_path).as_posix(), 'sha256': sha(original)}
    args = EditLabel(worksheet=binding, graphic_id=4, edits=[opts(0, 'Output Example', {'text': 'Output '},
                     {'text': 'view', 'bold': False, 'size_half_points': 36})], target_path=target.relative_to(tmp_path).as_posix())
    before = api.edit(args)
    assert not target.exists() and before['after']['runs'][1]['bold'] is False
    after = api.edit(args.model_copy(update={'preview_only': False}))
    saved = target.read_bytes()
    assert after['saved'] and after['output_sha256'] == before['output_sha256'] == sha(saved)
    inspected = api.inspect(ReadLabel(worksheet={'path': target.relative_to(tmp_path).as_posix(), 'sha256': sha(saved)}, graphic_id=4))
    assert inspected['runs'] == after['after']['runs'] and inspected['frame_xywh'] == [11, 33, 206, 42]
    update = revise_rtf(label_record(saved, 4)[4], [opts(1, 'view', {'text': 'layout'})])
    assert describe_rtf(update)['runs'][1]['text'] == 'layout'
    assert source.read_bytes() == original


def test_external_rtf_import_preserves_multi_style_native_text_on_insert_and_replace(tmp_path):
    work = tmp_path / 'OTAI/workspaces/RichTextImport'
    work.mkdir(parents=True)
    original = stored_label(BASE)
    ansi_rtf = (br"{\rtf1\ansi\ansicpg1252\deff0{\fonttbl{\f0\fswiss\fcharset0 Arial;}{\f1\froman Times New Roman;}}"
               br"{\colortbl;\red20\green60\blue120;}\viewkind4\pard\qc\f0\fs24 Arriv\'e9e {\b voie 9}"
               br"\par\f1\fs20\cf1 Departure\par}")

    def put(name, blob):
        path = work / name
        path.write_bytes(blob)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(blob)}

    api = RichLabels(tmp_path)
    saved_path = (work / 'saved.opentrack').relative_to(tmp_path).as_posix()
    saved = api.import_rtf(ImportRTF(worksheet=put('source.opentrack', original), rtf=put('notice.rtf', ansi_rtf),
                                     frame={'x': 11, 'y': 13, 'width': 150, 'height': 31},
                                     preview_only=False, target_path=saved_path))
    assert saved['saved'] and saved['input_format'] == 'rtf1' and saved['graphic_id'] == 5
    data = (tmp_path / saved_path).read_bytes()
    _, _, graphic, index, rtf0 = label_record(data, 5)
    assert rtf0.endswith(b'\\par }\n') and rtf0.startswith(b'{\\rtf0')
    assert [graphic.contents[slot].value for slot in (2, 3)] == [86, 28.5]
    assert describe_appearance(graphic, index, rtf0)['paragraph_alignment'] == 'center'
    runs = describe_rtf(rtf0)['runs']
    assert [row['text'] for row in runs] == ['Arrivée ', 'voie 9', 'Departure']
    assert (runs[1]['bold'], runs[2]['paragraph'], runs[2]['text_rgb']) == (True, 1, [20, 60, 120])
    assert label_record(data, 4)[4] == BASE
    out = (work / 'replacement.opentrack').relative_to(tmp_path).as_posix()
    revised = api.import_rtf(ImportRTF(worksheet={'path': saved_path, 'sha256': sha(data)},
                                       rtf=put('native.rtf', BASE), graphic_id=5,
                                       preview_only=False, target_path=out))
    assert revised['frame_xywh'] == [11, 13, 150, 31]
    assert label_record((tmp_path / out).read_bytes(), 5)[4] == BASE
    assert (work / 'source.opentrack').read_bytes() == original
    with pytest.raises(ValueError, match='Unsupported external RTF1 control'):
        external_label_rtf(ansi_rtf.replace(b'\\cf1', b'\\pict'))


def test_external_rtf_keeps_leading_space_and_can_replace_legacy_plain_label():
    raw = br'{\rtf1\ansi{\fonttbl{\f0\fswiss Arial;}}  label text }'
    native_rtf, _ = external_label_rtf(raw)
    assert describe_rtf(native_rtf)['runs'][0]['text'] == '  label text '
    old = stored_label(b'legacy unformatted label')
    updated, receipt = edit_archive(old, 4, (), replacement_rtf=native_rtf)
    assert receipt['before']['prior_format_outside_inspection']
    assert receipt['after']['runs'][0]['text'] == '  label text '
    assert label_record(updated, 4)[4] == native_rtf


def test_native_standalone_appearance_roundtrip_and_followup_style_edit():
    source = stored_label(BASE)
    request = Appearance(resize_anchor='right', paragraph_alignment='center', font={'face': 'Arial'},
                         text_rgb=[30, 88, 160], background_rgb=[242, 244, 246], draws_background=True)
    revised, evidence = edit_archive(source, 4, [], request)
    expected = {'resize_anchor': 'right', 'paragraph_alignment': 'center',
        'font': {'face': 'Arial', 'family': 'swiss'}, 'text_color': {'rgb': [30, 88, 160], 'alpha': 1},
        'background_color': {'rgb': [242, 244, 246], 'alpha': 1}, 'draws_background': True}
    assert evidence['appearance_after'] == expected
    assert evidence['appearance_before']['resize_anchor'] == 'left'
    assert evidence['appearance_before']['paragraph_alignment'] == 'left'
    assert evidence['original_object_graph_preserved_outside_rtf'] is False
    assert evidence['original_object_graph_preserved_outside_selected_label_fields'] is True
    root, _, model, index, rtf = label_record(revised, 4)
    assert describe_appearance(model, index, rtf) == expected
    assert model.contents[index + 3].values == [2, 0, 1]
    assert model.contents[index + 4].value.contents[0].value == 1
    assert b'\\pard\\tx560\\qc\n' in rtf
    updated, receipt = edit_archive(revised, 4, [opts(0, 'Output Example', {'text': 'Next', 'bold': False})])
    assert receipt['after']['runs'] == [{'index': 0, 'text': 'Next', 'font_index': 0,
        'bold': False, 'size_half_points': 48, 'text_rgb': [30, 88, 160]}]
    assert receipt['appearance_after'] == expected
    original_root, _, original, original_index, _ = label_record(source, 4)
    for slot in (index, index + 4, index + 5):
        original.contents[slot].value = model.contents[slot].value = None
    model.contents[index + 3].values[:] = original.contents[original_index + 3].values
    assert writer.fingerprint(root) == writer.fingerprint(original_root)
    assert label_record(updated, 4)[4] != rtf


def test_coloring_whole_label_preserves_literal_controls_and_formats():
    source = PREFIX + b'\\f0\\b\\fs48 Literal \\\\cf0 \\b0\\fs28\\cf0 tail}\n'
    revised = edit_rtf_appearance(source, Appearance(text_rgb=[8, 17, 250]))
    assert b'Literal \\\\cf0 ' in revised
    assert describe_rtf(revised)['runs'] == [
        {'index': 0, 'text': r'Literal \cf0 ', 'font_index': 0, 'bold': True, 'size_half_points': 48, 'text_rgb': [8, 17, 250]},
        {'index': 1, 'text': 'tail', 'font_index': 0, 'bold': False, 'size_half_points': 28, 'text_rgb': [8, 17, 250]},
    ]
    tinted = edit_rtf_appearance(revised, Appearance(text_rgb=[190, 60, 99]))
    assert tinted.count(b'\\colortbl') == 1
    assert [run['text_rgb'] for run in describe_rtf(tinted)['runs']] == [[190, 60, 99]] * 2


def test_native_fill_only_keeps_exact_RTF_and_allows_switching_off():
    source = stored_label(BASE)
    revised, evidence = edit_archive(source, 4, [], Appearance(background_rgb=[230, 230, 230], draws_background=True))
    assert label_record(revised, 4)[4] == BASE
    assert evidence['appearance_after']['draws_background']
    reopened, evidence = edit_archive(revised, 4, [], Appearance(draws_background=False))
    assert label_record(reopened, 4)[4] == BASE
    assert evidence['appearance_after']['draws_background'] is False
    assert evidence['appearance_before']['background_color'] == evidence['appearance_after']['background_color']


def test_native_fragments_save_two_paragraphs_with_distinct_fonts_and_colors():
    original = stored_label(BASE.replace(b'Output Example', b'Output Example\\b0 caption'))
    edits = [opts(0, 'Output Example',
        {'text': 'Platform 9', 'font': {'face': 'Arial'}, 'text_rgb': [10, 55, 112]},
        {'text': 'Reading ', 'paragraph_break_before': True,
         'font': {'face': 'Times New Roman', 'family': 'roman'}, 'text_rgb': [112, 55, 10],
         'bold': False, 'size_half_points': 24})]
    revised, receipt = edit_archive(original, 4, edits, Appearance(paragraph_alignment='right'))
    assert receipt['after']['runs'] == [
        {'index': 0, 'text': 'Platform 9', 'font_index': 1, 'bold': True, 'size_half_points': 48,
         'paragraph': 0, 'text_rgb': [10, 55, 112]},
        {'index': 1, 'text': 'Reading ', 'font_index': 2, 'bold': False, 'size_half_points': 24,
         'paragraph': 1, 'text_rgb': [112, 55, 10]},
        {'index': 2, 'text': 'caption', 'font_index': 0, 'bold': False, 'size_half_points': 48, 'paragraph': 1},
    ]
    assert receipt['after']['fonts'] == [
        {'index': 0, 'family': 'swiss', 'face': 'Helvetica'},
        {'index': 1, 'family': 'swiss', 'face': 'Arial'},
        {'index': 2, 'family': 'roman', 'face': 'Times New Roman'},
    ]
    assert b'\\par\n' in label_record(revised, 4)[4]
    reopened, result = edit_archive(revised, 4, [opts(2, 'caption', {
        'text': 'caption revised', 'font': {'face': 'arial'}, 'text_rgb': [10, 55, 112]})])
    assert label_record(reopened, 4)[4].count(b'\\colortbl') == 1
    assert result['after']['fonts'] == receipt['after']['fonts']
    assert result['after']['runs'][-1]['font_index'] == 1
    assert result['after']['runs'][-1]['text_rgb'] == [10, 55, 112]


def test_whole_label_tint_on_multiple_paragraphs_and_conflicting_edits():
    source = BASE.replace(b'Output Example', b'Output Example\\par\nnext line')
    tinted = edit_rtf_appearance(source, Appearance(text_rgb=[8, 17, 250]))
    assert [run['paragraph'] for run in describe_rtf(tinted)['runs']] == [0, 1]
    assert [run['text_rgb'] for run in describe_rtf(tinted)['runs']] == [[8, 17, 250]] * 2
    with pytest.raises(ValueError, match='whole-label or per-run foreground'):
        edit_archive(stored_label(source), 4, [opts(0, 'Output Example', {'text': 'one', 'text_rgb': [8, 8, 8]})],
                     Appearance(text_rgb=[7, 7, 7]))
