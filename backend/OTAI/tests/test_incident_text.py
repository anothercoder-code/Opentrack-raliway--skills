import pytest

from opentrack_ai.current_archive import incident_text as text


def test_older_and_current_native_rows_keep_empty_columns_and_default_fields():
    head = ['1', 'Route', 'Route slowdown', 'Field check', '', 'A', '4', '8',
            '0', '08:01:00', '0', '08:15:00', '40.5']
    tail = ['1', '83.5', '', '', '', '', '1', '', '', '', '', '', '', '1', '15', '25', '0', '0']
    raw = ('// Incidents (Text)\r\n' + '\t'.join(head) + '\r\n' +
           '\t'.join([*head[:2], 'Periodic route', *head[3:], *tail]) + '\r\n').encode()
    basic, current = map(text.to_item, text.rows(raw))
    assert basic['probability_percentage'] == 100
    assert basic['array_id'] == 8 and basic['start_end_id'] == 4
    assert basic['comment'] == 'Field check'
    assert current['head_only'] and current['probability_percentage'] == 83.5
    assert current['periodic'] == dict(occupied1_s=15, free1_s=25, occupied2_s=0, free2_s=0)


def test_text_refuses_missing_operating_values_and_damaged_rows():
    common = ['1', 'Signal Headway', 'Missing limit', '', '', 'A', '1#2', '',
              '0', '08:01:00', '0', '08:15:00', '0']
    original = '\t'.join(common).encode('ascii')
    with pytest.raises(ValueError, match='omits the headway'):
        text.to_item(text.rows(original)[0])
    with pytest.raises(ValueError, match='column count'):
        text.rows(original + b'\t')
    with pytest.raises(ValueError, match='repeated incident'):
        text.rows(original + b'\n' + original)
