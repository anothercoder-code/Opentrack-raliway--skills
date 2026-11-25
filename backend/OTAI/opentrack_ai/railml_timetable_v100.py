"""The original OpenTrack RailML 1.00 timetable's direct train/entry XML."""

from collections import defaultdict
from decimal import Decimal
import re
from xml.etree import ElementTree as ET
from xml.parsers import expat


MAX_BYTES = 2_000_000
MAX_ROWS = 10_000
XSI = 'http://www.w3.org/2000/10/XMLSchema-instance'
HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!-- edited with OpenTrack (http://www.opentrack.ch) -->\n'
NATIVE_FOOTER = b'\n\t</timetable>\n</railml>\n'
ENTRY_CLOCKS = ('arrival', 'departure')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_tree(blob):
    need(type(blob) is bytes and 0 < len(blob) <= MAX_BYTES, 'RailML timetable requires one bounded nonempty XML file')
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(namespace_separator='}')
    depth = elements = 0

    def start(name, attrs):
        nonlocal depth, elements
        depth += 1
        elements += 1
        need(depth <= 20 and elements <= 60000 and len(attrs) <= 64 and all(len(v) <= 4096 for v in attrs.values()),
             'Legacy timetable XML exceeds its structural bounds')
        builder.start(name, attrs)

    def end(name):
        nonlocal depth
        depth -= 1
        builder.end(name)

    def reject_dtd(*_):
        raise ValueError('Legacy RailML timetable must omit DTD declarations')

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.StartDoctypeDeclHandler = reject_dtd
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(blob, True)
    return builder.close()


def legacy_tree(blob, *, recover_original_footer=False):
    recovered = False
    try:
        root = bounded_tree(blob)
    except expat.ExpatError as exc:
        is_native_prefix = blob.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n', 2).startswith(HEADER.encode())
        if (not recover_original_footer or not is_native_prefix or not blob.rstrip().endswith(b'</train>') or
                exc.code != expat.errors.codes[expat.errors.XML_ERROR_NO_ELEMENTS]):
            raise ValueError(f'Malformed RailML 1.00 XML: {exc}') from exc
        try:
            root = bounded_tree(blob + NATIVE_FOOTER)
        except expat.ExpatError as recovery_error:
            raise ValueError(f'Original footer did not complete the RailML document: {recovery_error}') from recovery_error
        recovered = True
    need(root.tag == 'railml' and 'version' not in root.attrib and len(root) == 1 and
         root[0].tag == 'timetable' and root[0].get('version') == '1.00',
         'Expected original RailML with one direct <timetable version="1.00">')
    if recovered:
        need(root.get(XSI + '}noNamespaceSchemaLocation') == 'timetable.xsd' and
             all(train.tag == 'train' and train.get('dataSource') == 'opentrack' for train in root[0]),
             'Footer recovery requires original OpenTrack train records and header')
    return root[0], recovered


def clock(row, field, *, scope):
    actual = field
    if scope == 'published':
        actual = 'published' + field.title()
        if actual not in row:
            return None
    value = row.get(actual)
    day = row.get(field + 'Day', '0')
    need(re.fullmatch(r'[0-9]{1,3}', day) is not None and int(day) <= 366,
         f'Legacy RailML {field} day offset must be 0–366')
    if value is None:
        need(int(day) == 0, f'Legacy RailML undefined {field} cannot carry a day offset')
        return 'HH:MM:SS', 0, None
    match = re.fullmatch(r'([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])(?:\.0+)?', value)
    need(match is not None, f'Legacy RailML {actual} requires a canonical whole-second clock')
    h, m, s = map(int, match.groups())
    return value[:8], int(day), int(day)*86400 + h*3600 + m*60 + s


def duration(value, label, *, limit=86400):
    match = re.fullmatch(r'PT([0-9]{1,7}(?:\.[0-9]{1,9})?)S', value or '')
    need(match is not None, f'Original RailML {label} requires nonnegative PT…S seconds')
    seconds = Decimal(match[1])
    need(seconds <= limit, f'Original RailML {label} exceeds the supported range')
    return seconds


def wait_seconds(value):
    if value in (None, '', 'HH:MM:SS'):
        return -1
    match = re.fullmatch(r'([01][0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]|60))?', value)
    need(match is not None, 'Unsupported stored legacy connection clock')
    hours, minutes, seconds = match.groups()
    return int(hours)*3600 + int(minutes)*60 + int(seconds or '0') % 60


def train_index(table):
    trains = defaultdict(list)
    count = 0
    for train in table:
        need(train.tag == 'train' and train.get('trainID') and train.get('type') in ('planned', 'calculated'),
             'Legacy RailML expects direct train records with trainID and planned/calculated type')
        trains[train.get('trainID'), train.get('type')].append(train)
        count += sum(len(group) for group in train if group.tag == 'timetableentries')
    need(trains and count <= MAX_ROWS*2, 'Missing train records or legacy timetable exceeds archive row limit')
    return trains


def entries(train):
    need(len(train) == 1 and train[0].tag == 'timetableentries' and len(train[0]),
         'Selected legacy train needs one populated timetableentries group')
    for entry in train[0]:
        need(entry.tag == 'entry' and entry.get('posID') and entry.get('type') in (None, 'stop', 'pass'),
             'Selected legacy entry needs posID and optional stop/pass type')
        need(all(child.tag in ('composition', 'connection') for child in entry), 'Unknown selected legacy entry child record')
    return list(train[0])
