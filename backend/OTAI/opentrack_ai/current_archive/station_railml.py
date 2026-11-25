"""The standalone OpenTrack 1.7.6 RailML 2.2 Station catalog exchange."""

from xml.etree import ElementTree as ET
from xml.parsers import expat

from ..errors import APIError
from ..railml_values import NAMESPACE, REAL, int_text, native_id, xml_text


IDENTITY_FIELDS = ('code', 'abbrevation', 'name', 'description')
OMITTED_FIELDS = ('altitude_m', 'station_number', 'company_id', 'department_id', 'coord_x_m',
                  'coord_y_m', 'station_type', 'timing_point')


def text_supported(value):
    return all(' ' <= char <= '~' or '\u00a0' <= char <= '\u00ff' or char in '\u201c\u201e'
               for char in value)


def checked_caption(value):
    if not text_supported(value):
        raise ValueError('RailML 2.2 Station captions require printable ASCII, Latin-1 or original smart quotes')
    return xml_text(value)


def _root(raw):
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(namespace_separator='}')
    depth = 0

    def expanded(tag):
        return '{' + tag if '}' in tag else tag

    def start(tag, attrs):
        nonlocal depth
        depth += 1
        if depth > 48:
            raise ValueError('RailML 2.2 Station XML nesting exceeds 48 levels')
        builder.start(expanded(tag), {expanded(key): value for key, value in attrs.items()})

    def end(tag):
        nonlocal depth
        builder.end(expanded(tag))
        depth -= 1

    def doctype(*_):
        raise ValueError('RailML 2.2 Station XML does not allow a DTD')

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler, parser.StartDoctypeDeclHandler = builder.data, doctype
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(raw, True)
    return builder.close()


def _single(node, tag, *, deep=False):
    candidates = list(node.iter(tag)) if deep else node.findall(tag)
    if len(candidates) > 1:
        raise ValueError(f'Duplicate RailML Station element {tag.rsplit("}", 1)[-1]}')
    return candidates[0] if candidates else None


def _coordinate(value, limit):
    if value != value.strip() or not REAL.fullmatch(value):
        raise ValueError('RailML geoCoord requires two valid numbers separated by one space')
    numeric = float(value)
    if not -limit <= numeric <= limit:
        raise ValueError(f'RailML Station coordinate outside ±{limit}: {value!r}')
    return '0.000000' if numeric == 0 else value


def parse(raw):
    document = _root(raw)
    namespace = '{' + NAMESPACE + '}'
    prefix = namespace if document.tag == namespace + 'railml' else ''
    if document.tag != prefix + 'railml' or document.get('version') != '2.2':
        raise ValueError('Expected a RailML 2.2 station catalog')
    infrastructure = _single(document, prefix + 'infrastructure')
    if infrastructure is None or infrastructure.get('version', '2.2') != '2.2':
        raise ValueError('Expected one RailML 2.2 infrastructure section for the station catalog')
    points = _single(infrastructure, prefix + 'operationControlPoints')
    if points is None:
        raise ValueError('RailML 2.2 station catalog has no operationControlPoints')
    ignored = {child.tag.rsplit('}', 1)[-1] for child in infrastructure if child is not points}
    ignored.update(child.tag.rsplit('}', 1)[-1] for child in document
                   if child is not infrastructure and child.tag != prefix + 'metadata')
    records = []
    for point in points:
        if point.tag != prefix + 'ocp':
            raise ValueError('Expected only RailML ocp records in operationControlPoints')
        attrs = point.attrib
        ignored.update('ocp/@' + field for field in attrs if field not in IDENTITY_FIELDS)
        # code always wins. The original spelling is abbrevation. name supplies
        # a missing sign and supplies the caption until description replaces it.
        sign = next((attrs[key] for key in IDENTITY_FIELDS[:3] if key in attrs), '')
        name = attrs.get('description', attrs.get('name', ''))
        if not sign.strip() or not text_supported(sign) or not text_supported(name):
            raise ValueError('RailML ocp requires a nonempty Station sign and audited printable captions')
        record = {'sign': sign, 'name': name}
        geo = _single(point, prefix + 'geoCoord', deep=True)
        if geo is not None and 'coord' in geo.attrib:
            coordinate_pair = geo.attrib['coord'].split(' ')
            if len(coordinate_pair) != 2:
                raise ValueError('RailML geoCoord requires latitude and longitude separated by one space')
            latitude, longitude = coordinate_pair
            record.update(latitude=_coordinate(latitude, 90), longitude=_coordinate(longitude, 180))
        tsi = _single(point, prefix + 'tsi', deep=True)
        if tsi is not None and 'country' in tsi.attrib:
            try:
                record['company_id'] = int_text(tsi.attrib['country'])
            except APIError as exc:
                raise ValueError('RailML tsi country exceeds native signed 32-bit company ID') from exc
        for child in point.iter():
            if child is point:
                continue
            tag = child.tag.rsplit('}', 1)[-1]
            if child is geo or child is tsi:
                field = 'coord' if child is geo else 'country'
                ignored.update(tag + '/@' + key for key in child.attrib if key != field)
            else:
                ignored.add(tag)
        records.append(record)
    return records, sorted(ignored)


def render(records, basename):
    lines = ['<?xml version="1.0" encoding="ISO-8859-1"?>',
             f'<railml version="2.2" xmlns="{NAMESPACE}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
             f' xsi:schemaLocation="{NAMESPACE} http://schemas.railml.org/2013/railML-2.2/railML.xsd">',
             '\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
             '\t\t<dc:source>OTAI - original OpenTrack 1.7 RailML layout</dc:source>',
             '\t</metadata>',
             f'\t<infrastructure id="{native_id("infrastructure-" + basename)}" version="2.2">',
             '\t\t<operationControlPoints>']
    expected, identifiers, skipped = [], set(), []
    for record in records:
        sign = checked_caption(record['sign'])
        name = checked_caption(record['name'])
        identifier = native_id('ocp-' + record['sign'])
        if identifier in identifiers:
            raise ValueError(f'Original RailML normalization produces duplicate OCP ID {identifier!r}')
        identifiers.add(identifier)
        leaf = f'\t\t\t<ocp id="{identifier}" abbrevation="{sign}" code="{sign}" name="{sign}" description="{name}"'
        projected = {'sign': record['sign'], 'name': record['name']}
        latitude, longitude = record['latitude'], record['longitude']
        if latitude or longitude:
            try:
                projected.update(latitude=_coordinate(latitude, 90), longitude=_coordinate(longitude, 180))
            except ValueError:
                skipped.append(record['sign'])
        if 'latitude' in projected:
            lines.extend((leaf + '>', f'\t\t\t\t<geoCoord coord="{latitude} {longitude}"/>', '\t\t\t</ocp>'))
        else:
            lines.append(leaf + '/>')
        expected.append(projected)
    lines.extend(('\t\t</operationControlPoints>', '\t</infrastructure>', '</railml>'))
    return ('\n'.join(lines) + '\n').encode('ascii'), expected, skipped
