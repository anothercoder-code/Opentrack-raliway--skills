import pytest

from opentrack_ai.current_archive import native_preferences as prefs


@pytest.fixture
def exported():
    return (b'// OpenTrack Preferences Export / Run-File\r\n'
            b'Start Day Offset##\r\nStart Time#10:20:00#\r\n'
            b'Stop Day Offset##\r\nStop Time#10:30:00#\r\nBreak Day Offset##\r\nBreak Time#HH:MM:SS#\r\n'
            b'Step#0.2#\r\nDelay Scenario#0#\r\n'
            b'CourseFile#D:/rail/OTData/demo.courses#\r\n'
            b'Infrastructure Document#D:\\rail\\OTDocuments\\A.opentrack#\r\n'
            b'Train Diagram Document#D:/rail/OTDocuments/Local.otsimcor#\r\n'
            b'Incident#Reduce speed at A#\r\n// Document Sets\r\n'
            b'Document Set Name#Existing#\r\nDocument Set Document#D:/rail/OTDocuments/A.opentrack#\r\n'
            b'Document Set Name#Earlier Set#\r\nDocument Set Document#D:/Elsewhere/Old.opentrack#\r\n')


def test_read_original_day_zero_cells_and_saved_documents_outside_active_view(exported):
    result = prefs.inspect(exported)
    assert result['native_blank_day_offsets'] == ['Start Day Offset', 'Stop Day Offset', 'Break Day Offset']
    assert result['scalar_preferences']['Start Day Offset'] == '0'
    assert result['document_sets'] == [
        {'name': 'Existing', 'documents': ['D:/rail/OTDocuments/A.opentrack'], 'outside_declared_documents': []},
        {'name': 'Earlier Set', 'documents': ['D:/Elsewhere/Old.opentrack'],
         'outside_declared_documents': ['D:/Elsewhere/Old.opentrack']},
    ]


def test_write_native_set_order_and_scalar_changes_preserving_bindings(exported):
    sets = [{'name': 'Train graphs', 'documents': ['D:/rail/OTDocuments/Local.otsimcor', 'D:/rail/OTDocuments/A.opentrack']},
            {'name': 'Infrastructure', 'documents': ['D:/rail/OTDocuments/A.opentrack']}]
    output, report = prefs.edit(exported, {'Label Size': 'XL', 'Delay Scenario': '-1'}, sets)
    assert 'Delay Scenario#-1#' in output.decode('ascii')
    assert report['changes']['Delay Scenario'] == {'before': '0', 'after': '-1'}
    assert report['document_sets'] == [
        {'name': sets[0]['name'], 'documents': ['D:/rail/OTDocuments/Local.otsimcor', r'D:\rail\OTDocuments\A.opentrack']},
        {'name': sets[1]['name'], 'documents': [r'D:\rail\OTDocuments\A.opentrack']},
    ]
    assert b'Incident#Reduce speed at A#\r\n' in output
    assert b'CourseFile#D:/rail/OTData/demo.courses#\r\n' in output
    assert b'\n' not in output.replace(b'\r\n', b'')


def test_transfer_only_selected_settings_and_keep_existing_sets(exported):
    donor = exported.replace(b'Step#0.2#', b'Step#0.5#').replace(b'Train Diagram Document', b'Infrastructure Document')
    copied = prefs.transferable(donor, ['Step'])
    assert copied == {'Step': '0.5'}
    updated, _ = prefs.edit(exported, copied | {'Delay Format': 'M:SS'}, None)
    assert prefs.inspect(updated)['document_sets'] == prefs.inspect(exported)['document_sets']
    assert prefs.inspect(updated)['documents'] == prefs.inspect(exported)['documents']
    with pytest.raises(ValueError, match='selected scalar preference'):
        prefs.transferable(donor, ['Step', 'Step'])


@pytest.mark.parametrize(('requested', 'message'), [
    ([{'name': 'New', 'documents': ['D:/Elsewhere/Old.opentrack']}], 'base profile declarations'),
    ([{'name': 'New', 'documents': ['D:/rail/OTDocuments/A.opentrack', 'd:/RAIL/OTDocuments/A.opentrack']}], 'distinct documents'),
    ([{'name': 'Incident Set', 'documents': ['D:/rail/OTDocuments/A.opentrack']}], 'whole-line token collision'),
])
def test_refuse_unbound_aliased_or_colliding_native_document_sets(exported, requested, message):
    with pytest.raises(ValueError, match=message):
        prefs.edit(exported, {}, requested)
