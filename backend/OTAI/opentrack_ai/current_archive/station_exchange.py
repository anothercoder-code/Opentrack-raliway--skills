"""Original station interchange and bounded OTStation saved-record writes."""

import re
import struct
from collections import Counter
from xml.etree import ElementTree as ET
from xml.parsers import expat

from . import catalogs, station_railml, writer
from .course_factories import dictionary
from .graph_references import incoming_counts
from .zero_generation.native_signal_routes import obj, string


SLOTS = {
    'sign': (1, 0), 'name': (2, 0), 'altitude_m': (3, 0),
    'station_number': (4, 0), 'company_id': (4, 1), 'department_id': (4, 2),
    'coord_x_m': (5, 0), 'coord_y_m': (5, 1), 'station_type': (6, 0),
    'timing_point': (7, 0), 'longitude': (8, 0), 'latitude': (9, 0),
}
DEFAULTS = {
    'sign': '', 'name': '', 'altitude_m': 0, 'station_number': 0, 'company_id': 0,
    'department_id': 0, 'coord_x_m': 0, 'coord_y_m': 0, 'station_type': '',
    'timing_point': 1, 'longitude': '', 'latitude': '',
}
STATION_LAYOUT = catalogs.LAYOUTS['OTStation'][1]
STATION_LAYOUT_LENGTH = (6, 7, 8, 10)
TSV = ('company_id', 'department_id', 'station_number', 'reserved', 'coord_x_m', 'coord_y_m',
       'longitude', 'latitude', 'altitude_m', 'sign', 'name', 'station_type')
TSV_HEADER = ('// Stations (Text)\n// Type    : OT_Text\n// Desc.   : OT_sta_text\n'
              '// companyID, companyDeptID, stationID, resID,\n'
              '// x-Coord, y-Coord, longtitude, latitude, altitude,\n'
              '// stationSign, stationName, stationType\n')
XML_FIELDS = {
    'stationID': 'sign', 'stationName': 'name', 'stationCompanyData_ID': 'company_id',
    'stationCompanyData_DepartmentID': 'department_id', 'stationGeoData_xCoordinate': 'coord_x_m',
    'stationGeoData_yCoordinate': 'coord_y_m', 'stationGeoData_altitude': 'altitude_m',
}
XML_UNSUPPORTED = frozenset(('stationData_Type', 'stationData_NumberOfTracks',
                             'stationGeoData_longitude', 'stationGeoData_latitude'))
GEO = ('stationGeoData_xCoordinate', 'stationGeoData_yCoordinate', 'stationGeoData_altitude')
XML_CONTAINERS = {
    'stationEntry': ('stationID', 'stationName', 'stationData', 'stationCompanyData', 'stationGeoData'),
    'stationData': ('stationData_OpenTrack',),
    'stationData_OpenTrack': ('stationData_Type', 'stationData_NumberOfTracks'),
    'stationCompanyData': ('stationCompanyData_OpenTrack',),
    'stationCompanyData_OpenTrack': ('stationCompanyData_ID', 'stationCompanyData_DepartmentID'),
    'stationGeoData': ('stationGeoData_CH_XYA', 'stationGeoData_D_XYA', 'stationGeoData_World_LLA'),
    'stationGeoData_CH_XYA': GEO, 'stationGeoData_D_XYA': GEO,
    'stationGeoData_World_LLA': ('stationGeoData_longitude', 'stationGeoData_latitude', GEO[-1]),
}
DTD = '''<!ELEMENT stations (stationEntry*) >
<!ATTLIST stations title CDATA #IMPLIED application CDATA #IMPLIED date CDATA #IMPLIED comment CDATA #IMPLIED >
<!ELEMENT stationEntry (stationID, stationName, stationData?, stationCompanyData?, stationGeoData?)>
<!ELEMENT stationID (#PCDATA)>
<!ELEMENT stationName (#PCDATA)>
<!ELEMENT stationData (stationData_OpenTrack?)>
<!ELEMENT stationData_OpenTrack (stationData_Type?, stationData_NumberOfTracks?)>
<!ELEMENT stationCompanyData (stationCompanyData_OpenTrack?)>
<!ELEMENT stationCompanyData_OpenTrack (stationCompanyData_ID?, stationCompanyData_DepartmentID?)>
<!ELEMENT stationGeoData (stationGeoData_CH_XYA? | stationGeoData_D_XYA? | stationGeoData_World_LLA?)>
<!ELEMENT stationGeoData_CH_XYA (stationGeoData_xCoordinate?, stationGeoData_yCoordinate?, stationGeoData_altitude?)>
<!ELEMENT stationGeoData_D_XYA (stationGeoData_xCoordinate?, stationGeoData_yCoordinate?, stationGeoData_altitude?)>
<!ELEMENT stationGeoData_World_LLA (stationGeoData_longitude?, stationGeoData_latitude?, stationGeoData_altitude?)>
<!ELEMENT stationData_Type (#PCDATA)>
<!ELEMENT stationData_NumberOfTracks (#PCDATA)>
<!ELEMENT stationGeoData_xCoordinate (#PCDATA)>
<!ELEMENT stationGeoData_yCoordinate (#PCDATA)>
<!ELEMENT stationGeoData_altitude (#PCDATA)>
<!ELEMENT stationGeoData_longitude (#PCDATA)>
<!ELEMENT stationGeoData_latitude (#PCDATA)>
<!ELEMENT stationCompanyData_ID (#PCDATA)>
<!ELEMENT stationCompanyData_DepartmentID (#PCDATA)>
'''.encode('ascii')


def integer(value):
    if not re.fullmatch(r'[+-]?[0-9]{1,10}', value.strip()):
        raise ValueError(f'Expected signed 32-bit integer, found {value!r}')
    number = int(value)
    if not -(2**31) <= number < 2**31:
        raise ValueError(f'Station integer outside 32-bit range: {value!r}')
    return number


def geographic(value, limit):
    if not value:
        return 0.0
    if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', value.strip()):
        raise ValueError(f'Invalid station coordinate {value!r}')
    number = float(value)
    if not -limit <= number <= limit:
        raise ValueError(f'Station coordinate outside ±{limit}: {value!r}')
    return struct.unpack('f', struct.pack('f', number))[0]


def tsv_entries(raw):
    text = raw.decode('ascii').replace('\r\n', '\n')
    entries, ignored = [], set()
    for index, line in enumerate(text.split('\n'), 1):
        if len(line) > 1022:
            raise ValueError(f'Station text line {index} exceeds the original 1024-byte buffer')
        if not line or line.startswith('//'):
            continue
        if any(ord(ch) < 32 and ch != '\t' or ord(ch) > 126 for ch in line):
            raise ValueError(f'Invalid text byte on station line {index}')
        fields = line.split('\t')
        if len(fields) not in (11, 12):
            raise ValueError(f'Station text line {index} requires 11 or 12 tab-separated fields')
        entry = dict(zip(TSV, fields))
        if entry.pop('reserved') not in ('', '0'):
            ignored.add('resID')
        for field in entry:
            if isinstance(DEFAULTS[field], int):
                entry[field] = integer(entry[field]) if entry[field].strip() else 0
        if not all((geographic(entry['longitude'], 180), geographic(entry['latitude'], 90))):
            if entry['longitude'] or entry['latitude']:
                ignored.update(('longitude', 'latitude'))
            del entry['longitude'], entry['latitude']
        entries.append(entry)
    return entries, sorted(ignored)


def xml_entries(raw):
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(encoding='UTF-8')
    depth = 0

    def start(tag, attributes):
        nonlocal depth
        depth += 1
        if depth > 6:
            raise ValueError('Station XML exceeds the native field nesting')
        builder.start(tag, attributes)

    def end(tag):
        nonlocal depth
        builder.end(tag)
        depth -= 1

    def doctype(name, system_id, public_id, internal):
        if name != 'stations' or public_id is not None or internal or not re.fullmatch(
                r'[A-Za-z0-9_. -]+\.dtd', system_id or ''):
            raise ValueError('Station XML permits only an inert local original station DTD declaration')

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = builder.data
    parser.StartDoctypeDeclHandler = doctype
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(raw, True)
    root = builder.close()
    if root.tag != 'stations' or set(root.attrib) - {'title', 'application', 'date', 'comment'}:
        raise ValueError('Expected original OpenTrack <stations> XML')
    ignored = set()

    def fields(node, row):
        if node.attrib:
            raise ValueError(f'Unexpected attributes on {node.tag}')
        if node.tag in XML_CONTAINERS:
            tags = [child.tag for child in node]
            if (set(tags) - set(XML_CONTAINERS[node.tag]) or len(tags) != len(set(tags))
                    or (node.tag == 'stationGeoData' and len(tags) > 1)
                    or (node.text or '').strip() or any((child.tail or '').strip() for child in node)):
                raise ValueError(f'Unexpected or duplicate field in {node.tag}')
            for child in node:
                fields(child, row)
        elif len(node):
            raise ValueError(f'Expected text field {node.tag}')
        elif node.tag in XML_UNSUPPORTED:
            ignored.add(node.tag)
        else:
            field = XML_FIELDS[node.tag]
            value = node.text or ''
            row[field] = integer(value) if isinstance(DEFAULTS[field], int) and value.strip() else (
                0 if isinstance(DEFAULTS[field], int) else value)

    if (root.text or '').strip() or any(node.tag != 'stationEntry' or (node.tail or '').strip() for node in root):
        raise ValueError('Expected only stationEntry records')
    entries = []
    for node in root:
        row = {}
        fields(node, row)
        if not {'sign', 'name'} <= row.keys():
            raise ValueError('stationEntry requires stationID and stationName')
        entries.append(row)
    return entries, sorted(ignored)


def read_exchange(raw, format, *, allow_empty=False):
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('Station exchange text exceeds 8 MiB')
    readers = {'opentrack_text': tsv_entries, 'opentrack_xml': xml_entries, 'railml_2_2': station_railml.parse}
    entries, ignored = readers[format](raw)
    signs = {row['sign'] for row in entries}
    if (not entries and not allow_empty or len(entries) > 10000 or len(signs) != len(entries)
            or any(not sign.strip() for sign in signs)):
        raise ValueError('Expected up to 10000 unique, nonempty station signs')
    return entries, ignored


def read_catalog(raw, *, mutable=False):
    root, version = writer.load_next_compatible(raw)
    rows = catalogs.station_items(root) if mutable else dictionary(root)
    values = {}
    for sign, record in rows.items():
        if writer.kind(record) != 'OTStation' or record.clazz.version not in (0, 1, 2, 3):
            raise ValueError(f'Unrecognized saved Station version for {sign!r}')
        layout = STATION_LAYOUT[:STATION_LAYOUT_LENGTH[record.clazz.version]]
        catalogs.shape(record, 'OTStation', record.clazz.version, layout)
        if catalogs.text(record.contents[1].value) != sign or not sign:
            raise ValueError('Station dictionary key/sign mismatch')
        row = DEFAULTS.copy()
        for field, (group, slot) in SLOTS.items():
            if group < len(layout):
                value = record.contents[group].values[slot]
                if field == 'timing_point' and record.clazz.version == 2:
                    value = int(value > 0)
                row[field] = writer.string(value) or '' if layout[group] == '@' else value
        values[sign] = row
    return root, version, rows, values


def current_class():
    return writer.Class(b'OTStation', 3, writer.Class(b'NSObject', 0))


def upgrade_record(record, current, empty):
    version = record.clazz.version
    if version == 3:
        return
    # Native decoder 0x664724 supplies these fields. Encoder 0x664904 always writes marker 17.
    if version == 0:
        record.contents.append(writer.TypedValue(b'@', empty))
    if version < 2:
        record.contents.append(writer.TypedValue(b'i', 1))
    else:
        record.contents[7].value = int(record.contents[7].value > 0)
    record.contents.extend(writer.TypedValue(b'@', empty) for _ in range(2))
    record.contents[0].value = 17
    record.clazz = current


def editable_catalog(raw):
    root, version, stations, values = read_catalog(raw)
    counts = incoming_counts(root)
    if counts[id(root)] or any(station.clazz.version == 3 and station.contents[0].value not in (15, 17)
                              for station in stations.values()):
        raise ValueError('Expected an independently owned Station catalog with reviewed current records')
    migrated = Counter(str(station.clazz.version) for station in stations.values() if station.clazz.version < 3)
    if migrated:
        current, empty = current_class(), string('')
        for station in stations.values():
            upgrade_record(station, current, empty)
    return root, version, stations, values, counts, dict(migrated)


def finish_records(root, version, expected):
    root.contents[0].value = len(expected)
    output = writer.dump_verified(root, version)
    if read_catalog(output, mutable=True)[3] != expected:
        raise ValueError('Saved station field reload differs from the exchange plan')
    return output


def apply_records(raw, entries, format, existing, *, require_existing=False):
    root, version, records, before, counts, migrated = editable_catalog(raw)
    if require_existing and any(entry['sign'] not in before for entry in entries):
        raise ValueError('Select only exact existing station signs')
    expected = before.copy()
    created, updated, preserved = [], [], []
    for entry in entries:
        sign = entry['sign']
        if sign in records:
            if existing == 'reject':
                raise ValueError(f'Existing Station {sign!r} requires explicit collision handling')
            if existing == 'preserve':
                preserved.append(sign)
                continue
            record = records[sign]
            if counts[id(record)] != 1:
                raise ValueError(f'Shared Station object {sign!r} cannot be updated independently')
            base = DEFAULTS if format in ('opentrack_xml', 'railml_2_2') and existing == 'replace' else before[sign]
            updated.append(sign)
        else:
            record = obj([('OTStation', 3), ('NSObject', 0)], zip(STATION_LAYOUT,
                         ([17], [string(sign)], [None], [0], [0, 0, 0], [0, 0], [None], [1], [None], [None])))
            root.contents.extend((writer.TypedValue(b'@', record.contents[1].value), writer.TypedValue(b'@', record)))
            base = DEFAULTS
            created.append(sign)
        values = {**base, **entry}
        expected[sign] = values
        for field, value in values.items():
            if field == 'sign' or (sign in before and value == before[sign][field]):
                continue
            group, slot = SLOTS[field]
            if isinstance(value, str):
                railml_caption = (format == 'railml_2_2' and field == 'name' and station_railml.text_supported(value))
                if not railml_caption and not re.fullmatch(r'[ -~]*', value):
                    raise ValueError(f'New native {field} must be printable ASCII at {sign!r}')
                value = string(value)
            record.contents[group].values[slot] = value
        railml_sign = format == 'railml_2_2' and station_railml.text_supported(sign)
        if sign not in before and not railml_sign and not re.fullmatch(r'[ -~]*', sign):
            raise ValueError(f'New native station sign must be printable ASCII: {sign!r}')
    output = finish_records(root, version, expected)
    return output, {'created': created, 'updated': updated, 'preserved': preserved, 'station_count': len(expected),
                    'migrated_target_versions': migrated}


def import_station_objects(raw, donor_blob, signs, existing):
    root, version, stations, expected, counts, migrated = editable_catalog(raw)
    donor, _, source_stations, source_fields = read_catalog(donor_blob)
    if not signs or len(signs) != len(set(signs)) or set(signs) - source_stations.keys():
        raise ValueError('Select unique exact station signs from the donor archive')
    source_keys = {catalogs.text(group.value): group.value for group in donor.contents[1::2]}
    current, empty = current_class(), string('')
    created, replaced, preserved, source_versions = [], [], [], {}
    for sign in signs:
        source = source_stations[sign]
        source_versions[sign] = source.clazz.version
        if source.clazz.version == 3 and source.contents[0].value not in (15, 17):
            raise ValueError(f'Unsupported current Station marker at {sign!r}')
        if sign in stations:
            if existing == 'reject':
                raise ValueError(f'Existing Station {sign!r} requires explicit collision handling')
            if existing == 'preserve':
                preserved.append(sign)
                continue
            target = stations[sign]
            if counts[id(target)] != 1:
                raise ValueError(f'Shared Station object {sign!r} cannot be updated independently')
            upgrade_record(source, current, empty)
            # Keep the destination Station object, its key and its stationSign reference.
            target.contents[2:] = source.contents[2:]
            replaced.append(sign)
        else:
            upgrade_record(source, current, empty)
            root.contents.extend((writer.TypedValue(b'@', source_keys[sign]), writer.TypedValue(b'@', source)))
            created.append(sign)
        expected[sign] = source_fields[sign]
    output = finish_records(root, version, expected)
    return output, {'created': created, 'updated': replaced, 'preserved': preserved, 'station_count': len(expected),
                    'migrated_target_versions': migrated, 'selected_donor_versions': source_versions}


def export_catalog(raw, format, basename, signs):
    _, _, _, rows = read_catalog(raw)
    if signs and (len(set(signs)) != len(signs) or set(signs) - rows.keys()):
        raise ValueError('Use unique exact saved station signs')
    if format in ('google_earth', 'google_earth_ch'):
        from . import station_kml

        return station_kml.export([rows[sign] for sign in signs or rows], basename,
                                  swiss_grid=format == 'google_earth_ch')
    entries = [rows[sign] for sign in signs or sorted(rows)]
    extra = {}
    if format == 'railml_2_2':
        blob, projected, skipped = station_railml.render(entries, basename)
        members = {f'{basename}.xml': blob}
        omitted = list(station_railml.OMITTED_FIELDS)
        extra = {'coordinate_pairs_omitted': skipped}
    elif format == 'opentrack_text':
        lines = ['\t'.join(str(row.get(field, 0)) for field in TSV) for row in entries]
        members = {f'{basename}.txt': (TSV_HEADER + '\n'.join(lines) + '\n').encode('ascii')}
        omitted = ['timing_point']
    else:
        root = ET.Element('stations', {'title': 'RailML stations', 'application': 'OpenTrack'})
        for row in sorted(entries, key=lambda x: (x['name'].casefold(), x['sign'])):
            leaf = ET.SubElement(root, 'stationEntry')
            for tag in ('stationID', 'stationName'):
                ET.SubElement(leaf, tag).text = row[XML_FIELDS[tag]]
            company = ET.SubElement(ET.SubElement(leaf, 'stationCompanyData'), 'stationCompanyData_OpenTrack')
            geography = ET.SubElement(ET.SubElement(leaf, 'stationGeoData'), 'stationGeoData_CH_XYA')
            for parent, tags in ((company, XML_CONTAINERS['stationCompanyData_OpenTrack']), (geography, GEO)):
                for tag in tags:
                    ET.SubElement(parent, tag).text = str(row[XML_FIELDS[tag]])
        ET.indent(root, space='\t')
        prefix = f'<?xml version="1.0"?>\n<?xml-stylesheet?>\n<!DOCTYPE stations SYSTEM "{basename}.dtd">\n'
        members = {f'{basename}.xml': prefix.encode('ascii') + ET.tostring(root, encoding='utf-8') + b'\n',
                   f'{basename}.dtd': DTD}
        omitted = ['station_number', 'station_type', 'timing_point', 'longitude', 'latitude']
    decoded, ignored = read_exchange(next(iter(members.values())), format, allow_empty=True)
    if len(decoded) != len(entries) or {r['sign'] for r in decoded} != {r['sign'] for r in entries}:
        raise ValueError('Station export lost or changed a station sign on local readback')
    source = {row['sign']: row for row in (projected if format == 'railml_2_2' else entries)}
    if any(value != source[row['sign']][field] for row in decoded for field, value in row.items()):
        raise ValueError('Station export failed representable-field readback')
    return members, {'station_count': len(entries), 'omitted_fields': omitted, 'native_import_ignores': ignored, **extra}
