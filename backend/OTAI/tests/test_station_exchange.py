"""Original station exchange fields, native graph identity and production publication."""

import os

import pytest

from opentrack_ai.current_archive import station_exchange as ex, writer
from opentrack_ai.current_archive.bundle_tools import Source
from opentrack_ai.current_archive.station_exchange_tools import (
    EditStations, ExportStations, ImportStationArchive, ImportStations, StationExchangeTools, StationFields,
)
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.native_signal_routes import obj, string
from opentrack_ai.current_archive.zero_operations.station_binding import dictionary
from opentrack_ai.errors import APIError


def station(sign='AAA', version=3, name='Alpha & West', xy=(123, 456), coordinates=('7.25', '47.5'), timing=0):
    slots = [('i', [15 if version == 3 else 1]), ('@', [string(sign)]), ('@', [string(name)]),
             ('i', [32]), ('iii', [11, 7, 9]), ('ii', list(xy)), ('@', [string('Passenger')]),
             ('i', [timing]), ('@', [string(coordinates[0])]), ('@', [string(coordinates[1])])]
    return obj([('OTStation', version), ('NSObject', 0)], slots[:[6, 7, 8, 10][version]])


def catalog(version=3, name='Alpha & West', xy=(123, 456), coordinates=('7.25', '47.5')):
    return writer.dump_verified(dictionary([('AAA', station(version=version, name=name, xy=xy, coordinates=coordinates))]))


def xml(body):
    return ('<?xml version="1.0"?><!DOCTYPE stations SYSTEM "Original stations.dtd">'
            '<stations application="OpenTrack">' + body + '</stations>').encode('utf-8')


def test_text_roundtrip_updates_original_fields_and_preserves_timing_station():
    native = catalog()
    blobs, receipt = ex.export_catalog(native, 'opentrack_text', 'Stations', [])
    assert receipt['omitted_fields'] == ['timing_point']
    text = blobs['Stations.txt']
    assert b'7\t9\t11\t0\t123\t456\t7.25\t47.5\t32\tAAA\tAlpha & West\tPassenger\n' in text
    edited = text.replace(b'Alpha & West\tPassenger', b'Alpha platform\tFreight')
    edited += b'0\t0\t11\t3\t-12\t23\t0\t50\t-9\tBBB\tBeta\n'
    entries, ignored = ex.read_exchange(edited, 'opentrack_text')
    assert ignored == ['latitude', 'longitude', 'resID']
    output, report = ex.apply_records(native, entries, 'opentrack_text', 'replace')
    _, _, records, rows = ex.read_catalog(output, mutable=True)
    assert report['updated'] == ['AAA'] and report['created'] == ['BBB']
    assert records['AAA'].contents[0].value == 15
    assert records['BBB'].contents[0].value == 17
    assert rows['AAA']['timing_point'] == 0 and rows['AAA']['station_type'] == 'Freight'
    assert (rows['BBB']['altitude_m'], rows['BBB']['longitude'], rows['BBB']['timing_point']) == (-9, '', 1)


def test_xml_update_and_native_replace_have_distinct_omitted_field_semantics():
    incoming = xml('<stationEntry><stationID>AAA</stationID><stationName>Alpha &amp; North</stationName>'
                   '<stationData><stationData_OpenTrack><stationData_Type>Ignored type</stationData_Type>'
                   '</stationData_OpenTrack></stationData>'
                   '<stationGeoData><stationGeoData_D_XYA><stationGeoData_altitude>52</stationGeoData_altitude>'
                   '</stationGeoData_D_XYA></stationGeoData></stationEntry>')
    rows, ignored = ex.read_exchange(incoming, 'opentrack_xml')
    assert ignored == ['stationData_Type']
    original = catalog()
    with pytest.raises(ValueError, match='explicit collision handling'):
        ex.apply_records(original, rows, 'opentrack_xml', 'reject')
    untouched, report = ex.apply_records(original, rows, 'opentrack_xml', 'preserve')
    assert report['preserved'] == ['AAA']
    assert ex.read_catalog(untouched)[3] == ex.read_catalog(original)[3]
    update, _ = ex.apply_records(original, rows, 'opentrack_xml', 'update')
    replace, _ = ex.apply_records(original, rows, 'opentrack_xml', 'replace')
    updated = ex.read_catalog(update)[3]['AAA']
    replaced = ex.read_catalog(replace)[3]['AAA']
    assert (updated['name'], updated['altitude_m'], updated['station_number'], updated['timing_point']) == (
        'Alpha & North', 52, 11, 0,
    )
    assert (replaced['name'], replaced['altitude_m'], replaced['station_number'], replaced['timing_point']) == (
        'Alpha & North', 52, 0, 1,
    )
    assert (replaced['longitude'], replaced['company_id'], replaced['coord_x_m']) == ('', 0, 0)


def test_original_older_station_shape_can_export_as_utf8_xml():
    outputs, stats = ex.export_catalog(catalog(version=0, name='Saignelégier & West'), 'opentrack_xml', 'Swiss', [])
    assert set(outputs) == {'Swiss.xml', 'Swiss.dtd'}
    assert b'<!DOCTYPE stations SYSTEM "Swiss.dtd">' in outputs['Swiss.xml']
    assert b'<!ELEMENT stationEntry' in outputs['Swiss.dtd']
    assert b'Saignel\xc3\xa9gier &amp; West' in outputs['Swiss.xml']
    assert stats['station_count'] == 1 and 'station_number' in stats['omitted_fields']


def railml(points, extra=''):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<railml version="2.2" xmlns="http://www.railml.org/schemas/2013">'
            '<infrastructure version="2.2"><operationControlPoints>' + points +
            '</operationControlPoints>' + extra + '</infrastructure></railml>').encode('utf-8')


def test_railml_station_original_callbacks_and_native_collision_modes():
    source = railml(
        '<ocp id="opaque" code="AAA" name="Wrong caption" abbrevation="IGN" '
        'description="Saignel&#233;gier &amp; West"><geoCoord coord="0 -7.25"/>'
        '<propOther><tsi country="41suffix"/></propOther><propOperational operationalType="station"/></ocp>'
        '<ocp abbrevation="BBB" name="Biel/Bienne" />'
        '<ocp abbreviation="ignored" name="CCC"><tsi country="CH"/></ocp>', '<tracks/>',
    )
    entries, ignored = ex.read_exchange(source, 'railml_2_2')
    assert ignored == ['ocp/@abbreviation', 'ocp/@id', 'propOperational', 'propOther', 'tracks']
    assert entries == [
        {'sign': 'AAA', 'name': 'Saignelégier & West', 'latitude': '0.000000',
         'longitude': '-7.25', 'company_id': 41},
        {'sign': 'BBB', 'name': 'Biel/Bienne'}, {'sign': 'CCC', 'name': 'CCC', 'company_id': 0},
    ]
    original = catalog()
    absent, _ = ex.apply_records(original, entries, 'railml_2_2', 'preserve')
    update, _ = ex.apply_records(original, entries, 'railml_2_2', 'update')
    replacement, _ = ex.apply_records(original, entries, 'railml_2_2', 'replace')
    absent_rows = ex.read_catalog(absent)[3]
    assert absent_rows['AAA'] == ex.read_catalog(original)[3]['AAA']
    assert absent_rows['BBB']['name'] == 'Biel/Bienne' and absent_rows['CCC']['company_id'] == 0
    updated = ex.read_catalog(update)[3]['AAA']
    replaced = ex.read_catalog(replacement)[3]['AAA']
    assert all(updated[key] == replaced[key] == value for key, value in entries[0].items())
    assert (updated['station_number'], updated['station_type'], updated['timing_point']) == (11, 'Passenger', 0)
    assert (replaced['station_number'], replaced['station_type'], replaced['timing_point']) == (0, '', 1)


def test_railml_station_export_native_dialect_and_coordinate_scope():
    source = catalog(name='Saignelégier & West', coordinates=('7.25', '-0'))
    members, receipt = ex.export_catalog(source, 'railml_2_2', 'Station.Locations', ['AAA'])
    document = members['Station.Locations.xml']
    assert document.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
    assert b'<infrastructure id="infrastructure-Station.Locations" version="2.2">' in document
    assert b'id="ocp-AAA" abbrevation="AAA" code="AAA" name="AAA" description="Saignel&#233;gier &#38; West"' in document
    assert b'<geoCoord coord="-0 7.25"/>' in document
    entries, _ = ex.read_exchange(document, 'railml_2_2')
    assert entries == [{'sign': 'AAA', 'name': 'Saignelégier & West', 'latitude': '0.000000', 'longitude': '7.25'}]
    assert receipt['coordinate_pairs_omitted'] == [] and 'company_id' in receipt['omitted_fields']
    missing, receipt = ex.export_catalog(catalog(coordinates=('', '47.5')), 'railml_2_2', 'Stations', [])
    assert b'geoCoord' not in missing['Stations.xml'] and receipt['coordinate_pairs_omitted'] == ['AAA']


@pytest.mark.parametrize(('blob', 'message'), [
    (railml('<ocp code="AAA"/><ocp code="AAA"/>'), 'unique'),
    (railml('<ocp code="AAA"><geoCoord coord="47  7"/></ocp>'), 'one space'),
    (railml('<ocp code="AAA"><geoCoord coord="91 7"/></ocp>'), 'outside'),
    (railml('<ocp code="AAA"><tsi country="2147483648"/></ocp>'), '32-bit'),
    (railml('<ocp code="AAA"><geoCoord coord="47 7"/><geoCoord coord="48 8"/></ocp>'), 'Duplicate'),
    (railml('<ocp code="" name="AAA"/>'), 'nonempty'),
    (railml('<ocp code="AAA" description="車站"/>'), 'audited printable'),
    (railml('<ocp code="AAA"/>').replace(b'version="2.2"', b'version="2.1"'), '2.2'),
    (b'<!DOCTYPE railml SYSTEM "http://example.test/rail.dtd"><railml version="2.2"/>', 'does not allow a DTD'),
])
def test_railml_station_import_rejects_ambiguous_or_unsupported_inputs(blob, message):
    with pytest.raises(ValueError, match=message):
        ex.read_exchange(blob, 'railml_2_2')


@pytest.mark.parametrize(('version', 'stored_timing', 'timing'), [(0, 0, 1), (1, 0, 1), (2, -2, 0), (2, 3, 1)])
def test_legacy_edit_upgrades_native_defaults_and_preserves_graph_links(version, stored_timing, timing):
    a = station(version=version, timing=stored_timing)
    b = station('BBB', version=version, timing=stored_timing)
    b.contents[2].value = a.contents[2].value
    root = dictionary([('AAA', a), ('BBB', b)])
    root.contents[1].value = a.contents[1].value
    old = writer.dump_verified(root)
    new, report = ex.apply_records(old, [{'sign': 'AAA', 'altitude_m': -12}], None, 'update', require_existing=True)
    root, _, rows, values = ex.read_catalog(new, mutable=True)
    assert report['migrated_target_versions'] == {str(version): 2}
    assert all(record.clazz.version == 3 and record.contents[0].value == 17 for record in rows.values())
    assert (values['AAA']['altitude_m'], values['BBB']['altitude_m']) == (-12, 32)
    assert values['BBB']['station_type'] == ('Passenger' if version else '')
    assert values['BBB']['timing_point'] == timing
    assert values['BBB']['longitude'] == values['BBB']['latitude'] == ''
    assert root.contents[1].value is rows['AAA'].contents[1].value
    assert root.contents[3].value is not rows['BBB'].contents[1].value
    assert rows['AAA'].contents[2].value is rows['BBB'].contents[2].value
    assert rows['AAA'].contents[8].value is rows['BBB'].contents[9].value


def test_import_selected_native_archive_preserves_actual_cross_record_references(tmp_path):
    project = tmp_path / 'OTAI/workspaces/StationArchive'
    project.mkdir(parents=True)
    base = project / 'base.stations'
    donor_file = project / 'donor.stations'
    base.write_bytes(catalog())
    a = station(version=0, name='Genève & West')
    b = station('BBB', version=0)
    b.contents[2].value = a.contents[2].value
    donor = dictionary([('AAA', a), ('BBB', b), ('ZZZ', station('ZZZ', version=0))])
    donor.contents[3].value = b.contents[1].value
    source_bytes = writer.dump_verified(donor)
    donor_file.write_bytes(source_bytes)
    args = ImportStationArchive(stations={'path': 'OTAI/workspaces/StationArchive/base.stations',
                                         'sha256': sha(base.read_bytes())},
                                donor_stations={'path': 'OTAI/workspaces/StationArchive/donor.stations',
                                                'sha256': sha(source_bytes)},
                                station_signs=['BBB', 'AAA'], existing='replace',
                                target_path='OTAI/workspaces/StationArchive/merged.stations')
    api = StationExchangeTools(tmp_path)
    preview = api.import_station_archive(args)
    receipt = api.import_station_archive(args.model_copy(update={'preview_only': False}))
    assert receipt['saved'] and receipt['output_sha256'] == preview['output_sha256']
    assert receipt['selected_donor_versions'] == {'BBB': 0, 'AAA': 0}
    assert receipt['created'] == ['BBB'] and receipt['updated'] == ['AAA']
    root, _, rows, values = ex.read_catalog((project / 'merged.stations').read_bytes(), mutable=True)
    assert set(values) == {'AAA', 'BBB'} and values['AAA']['name'] == values['BBB']['name'] == 'Genève & West'
    assert rows['AAA'].contents[0].value == 15 and rows['BBB'].contents[0].value == 17
    assert root.contents[1].value is not rows['AAA'].contents[1].value
    assert root.contents[3].value is rows['BBB'].contents[1].value
    assert rows['AAA'].contents[2].value is rows['BBB'].contents[2].value
    assert donor_file.read_bytes() == source_bytes
    with pytest.raises(APIError, match='explicit collision'):
        api.import_station_archive(args.model_copy(update={'existing': 'reject'}))


def test_google_earth_modes_keep_original_axes_caption_and_coordinate_sources():
    archive = catalog(name='Légier & West', xy=(600000, 200000), coordinates=('0', '-90'))
    files, results = ex.export_catalog(archive, 'google_earth', 'Geography', ['AAA'])
    assert set(files) == {'Geography.kml'}
    assert b'<kml xmlns="http://earth.google.com/kml/2.0">' in files['Geography.kml']
    assert b'<name>L&#233;gier &#38; West</name>' in files['Geography.kml']
    assert b'<coordinates>0.00000, -90.00000, 0</coordinates>' in files['Geography.kml']
    assert results['exported_station_signs'] == ['AAA'] and results['coordinate_warnings'] == []
    legacy = catalog(version=0, xy=(600000, 200000))
    files, results = ex.export_catalog(legacy, 'google_earth_ch', 'Swiss', [])
    assert b'<coordinates>7.43864, 46.95108, 0</coordinates>' in files['Swiss.kml']
    assert results['coordinate_source'] == 'ch1903' and results['station_count'] == 1
    _, skipped = ex.export_catalog(legacy, 'google_earth', 'Swiss', [])
    assert skipped['station_count'] == 0 and skipped['skipped_station_signs'] == ['AAA']


def test_kml_reports_non_numeric_suffix_and_skips_out_of_range():
    partial = catalog(coordinates=('7.25rest', '47.5'))
    files, result = ex.export_catalog(partial, 'google_earth', 'Swiss', [])
    assert b'7.25000, 47.50000, 0' in files['Swiss.kml']
    assert result['coordinate_warnings'][0]['station_sign'] == 'AAA'
    outside = catalog(coordinates=('181', '47.5'))
    _, result = ex.export_catalog(outside, 'google_earth', 'Swiss', [])
    assert result['skipped_station_signs'] == ['AAA']


def test_station_metadata_writes_zero_longitude_and_preserves_sign(tmp_path):
    project = tmp_path / 'OTAI/workspaces/StationMetadata'
    project.mkdir(parents=True)
    source = project / 'base.stations'
    target = project / 'edited.stations'
    data = catalog()
    source.write_bytes(data)
    args = EditStations(
        stations={'path': source.relative_to(tmp_path).as_posix(), 'sha256': sha(data)},
        edits=[{'sign': 'AAA', 'changes': {'longitude': '0', 'timing_point': True, 'coord_x_m': 600000}}],
        target_path=target.relative_to(tmp_path).as_posix(),
    )
    api = StationExchangeTools(tmp_path)
    preview = api.edit_stations(args)
    saved = api.edit_stations(args.model_copy(update={'preview_only': False}))
    assert saved['fresh_archive_reload_verified'] and saved['output_sha256'] == preview['output_sha256']
    _, _, _, rows = ex.read_catalog(target.read_bytes())
    assert (rows['AAA']['longitude'], rows['AAA']['latitude'], rows['AAA']['timing_point']) == ('0', '47.5', 1)
    assert rows['AAA']['coord_x_m'] == 600000 and rows['AAA']['name'] == 'Alpha & West'
    assert source.read_bytes() == data


def test_station_metadata_requires_valid_coordinates_and_existing_station(tmp_path):
    project = tmp_path / 'OTAI/workspaces/StationMeta'
    project.mkdir(parents=True)
    data = catalog()
    (project / 'base.stations').write_bytes(data)
    with pytest.raises(ValueError, match='outside'):
        StationFields(latitude='91')
    with pytest.raises(ValueError, match='explicit'):
        StationFields(longitude=None)
    args = EditStations(
        stations={'path': 'OTAI/workspaces/StationMeta/base.stations', 'sha256': sha(data)},
        edits=[{'sign': 'Absent', 'changes': {'longitude': ''}}],
    )
    with pytest.raises(APIError, match='existing station'):
        StationExchangeTools(tmp_path).edit_stations(args)


@pytest.mark.parametrize(('raw', 'format', 'message'), [
    (b'<!DOCTYPE stations SYSTEM "https://host/native.dtd"><stations/>', 'opentrack_xml', 'inert local'),
    (b'<!DOCTYPE stations [<!ENTITY x "station">]><stations/>', 'opentrack_xml', 'inert local'),
    (xml('<stationEntry><stationID>AAA</stationID><stationID>BBB</stationID><stationName>A</stationName>'
         '</stationEntry>'), 'opentrack_xml', 'duplicate field'),
    (b'0\t0\t0\t0\t0\t0\t0\t0\t0\tAAA\tName\n' * 2, 'opentrack_text', 'unique'),
    (b'0\t0\t0\t0\t0\t0\t0\t0\t0\tAAA\t' + b'N' * 1024, 'opentrack_text', '1024-byte'),
], ids=['external-dtd', 'entities', 'duplicate-xml-field', 'duplicate-station-sign', 'original-buffer'])
def test_exchange_rejects_ambiguous_or_unreadable_original_inputs(raw, format, message):
    with pytest.raises(ValueError, match=message):
        ex.read_exchange(raw, format)


def test_preview_save_and_check_selected_run_binding(tmp_path):
    if not tmp_path.as_posix().isascii():
        pytest.skip('Original .run path fields require an ASCII --basetemp')
    project = tmp_path / 'OTAI/workspaces/StationExchange'
    project.mkdir(parents=True)
    api = StationExchangeTools(tmp_path)

    def source(filename, content):
        path = project / filename
        path.write_bytes(content)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(content)}

    data = catalog()
    native = source('source.stations', data)
    run = source('source.run', f'StationFile#{(project / "source.stations").as_posix()}#\n'.encode('ascii'))
    wrong = source('alternate.run', f'StationFile#{(project / "alternate.stations").as_posix()}#\n'.encode('ascii'))
    tsv = source('update.tsv', b'1\t2\t3\t0\t5\t6\t\t\t9\tAAA\tAlpha\tLocal\n')
    target = (project / 'output.stations').relative_to(tmp_path).as_posix()
    args = ImportStations(stations=native, project_run=run, exchange_file=tsv, existing='update',
                          format='opentrack_text', target_path=target)
    with pytest.raises(APIError, match='StationFile'):
        api.import_stations(args.model_copy(update={'project_run': Source(**wrong)}))
    preview = api.import_stations(args)
    assert preview['project_run_sha256'] == run['sha256'] and not (project / 'output.stations').exists()
    saved = api.import_stations(args.model_copy(update={'preview_only': False}))
    assert saved['saved'] and saved['output_sha256'] == preview['output_sha256']
    assert (project / 'source.stations').read_bytes() == data
    if os.name == 'nt':
        export = ExportStations(stations=native, format='opentrack_xml', preview_only=False,
                                target_directory=(project / 'Exchange').relative_to(tmp_path).as_posix())
        output = api.export_stations(export)
        assert output['post_commit_verified'] and set(output['member_sha256']) == {'Stations.xml', 'Stations.dtd'}
        assert (project / 'Exchange/Stations.xml').is_file()
        geo = api.export_stations(export.model_copy(update={
            'format': 'google_earth', 'target_directory': (project / 'Geographic').relative_to(tmp_path).as_posix(),
        }))
        assert geo['post_commit_verified'] and geo['selected_count'] == 1
        assert b'7.25000, 47.50000, 0' in (project / 'Geographic/Stations.kml').read_bytes()

        xml_output = api.export_stations(export.model_copy(update={
            'format': 'railml_2_2', 'target_directory': (project / 'RailML').relative_to(tmp_path).as_posix(),
        }))
        assert xml_output['post_commit_verified'] and set(xml_output['member_sha256']) == {'Stations.xml'}
    inputs = source('select.railml', railml('<ocp code="AAA"/><ocp code="BBB" description="Genève"/>'))
    selective = args.model_copy(update={
        'format': 'railml_2_2', 'exchange_file': Source(**inputs), 'station_signs': ['BBB'],
        'target_path': (project / 'selective.stations').relative_to(tmp_path).as_posix(), 'preview_only': False,
    })
    with pytest.raises(APIError, match='unique exact'):
        api.import_stations(selective.model_copy(update={'station_signs': ['BBB', 'BBB']}))
    imported = api.import_stations(selective)
    assert imported['saved'] and imported['created'] == ['BBB'] and not imported['updated']
    assert ex.read_catalog((project / 'selective.stations').read_bytes())[3]['BBB']['name'] == 'Genève'
