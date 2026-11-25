"""Original OpenTrack 1.7 geographic and Swiss-grid station exports."""

from xml.etree import ElementTree as ET

from ..railml_values import REAL, double_prefix, xml_text


NAMESPACE = 'http://earth.google.com/kml/2.0'
PREFIX = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="{NAMESPACE}">
<Folder>
\t<ScreenOverlay>
\t<name>OpenTrack Logo</name>
\t<Icon>
\t<href>http://www.opentrack.ch/google/opentrack.gif</href>
\t</Icon>
\t<overlayXY x="0" y="1" xunits="fraction" yunits="fraction"/>
\t<screenXY x="0" y="1" xunits="fraction" yunits="fraction"/>
\t<size x="0" y="0" xunits="fraction" yunits="fraction"/>
\t</ScreenOverlay>

\t<name>OpenTrack Stations</name>
\t<visibility>0</visibility>
\t<open>1</open>
\t<Folder>
\t<name>RailML Stations</name>
\t<visibility>1</visibility>
\t<open>0</open>
'''
PLACEMARK = '''\t<Placemark>
\t\t<name>{name}</name>
\t\t<Style>
\t\t\t<IconStyle>
\t\t\t<Icon>
\t\t\t<x>96</x>
\t\t\t<y>160</y>
\t\t\t<w>48</w>
\t\t\t<h>48</h>
\t\t\t<href>http://www.opentrack.ch/google/train.gif</href>
\t\t\t</Icon>
\t\t\t</IconStyle>
\t\t</Style>
\t\t<Point>
\t\t<Style><LineStyle><width>2</width></LineStyle></Style>
\t\t\t<extrude>0</extrude>
\t\t\t<tesselate>1</tesselate>
\t\t\t<altitudeMode>relativeToGround</altitudeMode>
\t\t\t<coordinates>{coordinates}</coordinates>
\t\t</Point>
\t</Placemark>
'''
SUFFIX = '\t</Folder>\n</Folder>\n</kml>\n'


def ch1903(x, y):
    """OpenTrack's two polynomial conversions from the Swiss LV03 grid."""
    easting, northing = (x - 600000.0) / 1000000.0, (y - 200000.0) / 1000000.0
    longitude = (easting * 0.791484 * northing + easting * 4.728982 + 2.6779094
                 + easting * 0.1306 * northing * northing - easting * 0.0436 * easting * easting)
    latitude = (northing * 3.238372 + 16.9023892 - easting * 0.270978 * easting
                - northing * 0.002582 * northing - easting * 0.0447 * easting * northing
                - northing * 0.014 * northing * northing)
    return longitude * 100.0 / 36.0, latitude * 100.0 / 36.0


def station_point(row, swiss_grid):
    if swiss_grid:
        x, y = row['coord_x_m'], row['coord_y_m']
        if x > 0 and y > 0:
            return ch1903(x, y), None
        return None, None
    longitude, latitude = row['longitude'], row['latitude']
    if not longitude or not latitude:
        return None, None
    x, y = double_prefix(longitude), double_prefix(latitude)
    if not (-180 <= x <= 180 and -90 <= y <= 90):
        return None, None
    numeric_text = all((match := REAL.match(value)) is not None and match[0].strip() == value.strip()
                       for value in (longitude, latitude))
    return (x, y), None if numeric_text else 'original_coordinate_text_parsed_as_number_prefix'


def export(entries, basename, *, swiss_grid):
    parts, expected, included, skipped, warnings = [PREFIX], [], [], [], []
    for row in sorted(entries, key=lambda item: item['name']):
        point, warning = station_point(row, swiss_grid)
        if point is None:
            skipped.append(row['sign'])
            continue
        longitude, latitude = point
        if warning is not None or not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            warnings.append({'station_sign': row['sign'], 'reason': warning or 'original_swiss_projection_out_of_range'})
        coordinates = f'{longitude:.5f}, {latitude:.5f}, 0'
        name = '' if not row['name'] else xml_text(row['name'])
        parts.append(PLACEMARK.format(name=name, coordinates=coordinates))
        expected.append((row['name'].replace('\r\n', '\n').replace('\r', '\n'), coordinates))
        included.append(row['sign'])
    parts.append(SUFFIX)
    raw = ''.join(parts).encode('utf-8')
    ns = {'k': NAMESPACE}
    points = ET.fromstring(raw).findall('k:Folder/k:Folder/k:Placemark', ns)
    fresh = [(point.findtext('k:name', namespaces=ns), point.findtext('k:Point/k:coordinates', namespaces=ns))
             for point in points]
    if fresh != expected:
        raise ValueError('Station KML coordinates or captions differ on XML readback')
    return {f'{basename}.kml': raw}, {'station_count': len(expected), 'selected_count': len(entries),
                                     'coordinate_source': 'ch1903' if swiss_grid else 'longitude_latitude',
                                     'exported_station_signs': included, 'skipped_station_signs': skipped,
                                     'coordinate_warnings': warnings, 'omitted_fields': [
                                         'sign', 'station_number', 'station_type', 'company_id', 'department_id',
                                         'altitude_m', 'timing_point'],
                                     'native_import_ignores': []}
