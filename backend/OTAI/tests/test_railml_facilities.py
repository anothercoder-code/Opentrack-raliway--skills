"""Explicit RailML 2.2 station, platform, stop post and signal archive mapping."""

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.infrastructure_railml import railml_inventory
from opentrack_ai.current_archive.infrastructure_railml_facilities import project_geometry
from opentrack_ai.current_archive.infrastructure_railml_tools import ApplyFacilities, InfrastructureRailMLTools
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document


XML = b'''<?xml version="1.0"?>
<railml xmlns="http://www.railml.org/schemas/2013" version="2.2">
  <infrastructure id="I"><tracks>
    <track id="T" name="Platform track">
      <trackTopology>
        <trackBegin id="T1" pos="125"><openEnd id="L"/></trackBegin>
        <trackEnd id="T2" pos="425"><openEnd id="R"/></trackEnd>
        <crossSections><crossSection id="C" pos="425" ocpRef="O"/></crossSections>
      </trackTopology>
      <trackElements><platformEdges>
        <platformEdge id="P" pos="125" length="300" dir="up" ocpRef="O" side="left" height="760"/>
      </platformEdges></trackElements>
      <ocsElements>
        <signals><signal id="S" name="Exit1" pos="425" dir="up" type="main" function="exit" sight="450"/></signals>
        <stopPosts><stopPost id="SP" pos="425" dir="up" platformEdgeRef="P" ocpRef="O">
          <signalRef ref="S"/>
        </stopPost></stopPosts>
      </ocsElements>
    </track>
  </tracks><operationControlPoints><ocp id="O" name="Central" code="CTR"/></operationControlPoints></infrastructure>
  <infrastructureVisualizations><visualization id="V" infrastructureRef="I">
    <lineVis ref="line"><trackVis ref="T">
      <trackElementVis ref="T1"><position x="0" y="20"/></trackElementVis>
      <trackElementVis ref="P"><position x="100" y="20"/></trackElementVis>
    </trackVis></lineVis>
  </visualization></infrastructureVisualizations>
</railml>'''


def fixture(tmp_path, xml=XML):
    line = generate.spec()
    line['vertices'] = [generate.vertex(name, i * 100) for i, name in enumerate('ABCD')]
    spec = line['edges'][0]
    line['edges'] = [{**spec, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'track_name': name, 'length_m': length}
                     for a, b, name, length in [('A', 'B', 'West', 120), ('B', 'C', 'Platform track', 300),
                                                 ('C', 'D', 'East', 350)]]
    sheet, ids = schematic_document(line, [('A', 0)])
    _, _, models, _ = native.document(sheet)
    platform = next(model for model in models if writer.kind(model) == 'OTEdgeModel' and model.contents[9].values[1] == 300)
    work = tmp_path / 'OTAI/workspaces/facilities'
    work.mkdir(parents=True)

    def put(name, raw):
        path = work / name
        path.write_bytes(raw)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}

    args = {'railml': put('Base.railml', xml), 'worksheet': put('Worksheet.opentrack', sheet),
            'tracks': [{'track_id': 'T', 'edges': [{'edge_id': platform.contents[0].value, 'start_end_id': ids['B'][1]}]}],
            'signals': [{'signal_id': 'S'}], 'stations': [{'cross_section_id': 'C', 'direction': 'up',
            'platform_edge_id': 'P', 'exit_signal_id': 'S', 'stop_post_id': 'SP'}],
            'target_directory': (work / 'Output').relative_to(tmp_path).as_posix()}
    return InfrastructureRailMLTools(tmp_path), args, ids


@pytest.mark.parametrize('direction', ('up', 'down'))
def test_railml_facilities_archive_operating_track_and_native_signal(tmp_path, direction):
    xml = XML
    if direction == 'down':
        xml = (xml.replace(b' id="P" pos="125"', b' id="P" pos="425"')
               .replace(b' id="C" pos="425"', b' id="C" pos="125"')
               .replace(b'pos="425" dir="up"', b'pos="125" dir="down"').replace(b'dir="up"', b'dir="down"'))
    tool, args, ids = fixture(tmp_path, xml)
    args['stations'][0]['direction'] = direction
    if not tmp_path.as_posix().isascii():
        preview = tool.facilities(ApplyFacilities(**{**args, 'target_directory': None}))
        assert preview['station_readback']['stop_area_count'] == 1
        pytest.skip('Windows native publication requires an ASCII --basetemp')
    preview = tool.facilities(ApplyFacilities(**args))
    assert not (tmp_path / args['target_directory']).exists()
    assert preview['station_readback']['stop_area_count'] == 1
    result = tool.facilities(ApplyFacilities(**args, preview_only=False))
    assert result['saved'] and result['publication']['post_commit_verified']
    assert result['members'] == preview['members']
    assert all(not values for values in result['unselected_facilities'].values())
    expected_entry, expected_stop = (ids['B'], ids['C']) if direction == 'up' else (ids['C'][::-1], ids['B'][::-1])
    assert result['source_station_cross_sections']['C']['entry_end_id'] == expected_entry[0]
    assert result['source_station_cross_sections']['C']['reference_end_id'] == expected_stop[0]
    target = tmp_path / args['target_directory']
    _, _, _, records = native.document((target / 'Worksheet.opentrack').read_bytes())
    regular, reference = [records[key] for key in (expected_entry[0], expected_stop[0])]
    assert (regular.contents[20].value, reference.contents[20].value) == (1, 2)
    assert regular.contents[12].value is reference.contents[12].value
    assert catalogs.text(reference.contents[12].value.contents[7].value) == 'CTR'
    assert catalogs.text(reference.contents[11].value.contents[13].value) == 'Exit1'
    assert reference.contents[11].value.contents[9].values[1] == 450
    assert catalogs.text(records[ids['A'][0]].contents[11].value.contents[13].value) == 'S0'
    assert set(catalogs.station_items(writer.load_next_compatible((target/'FacilityCatalog.stations').read_bytes())[0])) == {'CTR'}


@pytest.mark.parametrize(('old', 'new', 'message'), [
    (b'length="300"', b'length="290"', 'terminate exactly'),
    (b'sight="450"', b'sight="451.5"', 'whole meters'),
    (b'pos="425" dir="up" type="main"', b'pos="424" dir="up" type="main"', 'native Edge boundary'),
    (b'platformEdgeRef="P"', b'platformEdgeRef="other"', 'Selected stop post'),
    (b'function="exit"', b'function="home"', 'platform stopping signal must be a physical main or combined exit signal'),
], ids=('wrong-platform-span', 'fractional-sight', 'inside-edge', 'wrong-stop-owner', 'different-signal-function'))
def test_inconsistent_facility_mapping_fails_before_publication(tmp_path, old, new, message):
    tool, args, _ = fixture(tmp_path, XML.replace(old, new))
    with pytest.raises(APIError, match='(?i)' + message):
        if tmp_path.as_posix().isascii():
            tool.facilities(ApplyFacilities(**args, preview_only=False))
        else:
            tool.facilities(ApplyFacilities(**{**args, 'target_directory': None}))
    assert not (tmp_path / args['target_directory']).exists()


def test_geometry_projection_keeps_track_and_nonfacility_visual_position():
    projection, report = project_geometry(XML)
    assert railml_inventory(projection)['total_track_length_m'] == 300
    assert railml_inventory(projection)['signal_count'] == 0
    assert railml_inventory(projection)['position_count'] == 1
    assert report['removed_facility_ids'] == {'ocp': ['O'], 'crossSection': ['C'], 'platformEdge': ['P'],
                                              'signal': ['S'], 'stopPost': ['SP']}
    connected = XML.replace(b'<track id="T"', b'<track id="T" stationRef="O"')
    with pytest.raises(ValueError, match='Other RailML data still uses projected facility'):
        project_geometry(connected)
