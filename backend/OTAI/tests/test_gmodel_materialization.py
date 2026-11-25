"""Guard the GModel-to-binary turnout direction, identity and publication."""

import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.gmodel_materialization import materialize
from opentrack_ai.current_archive.infrastructure_railml_tools import InfrastructureRailMLTools, MaterializeGModel
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha

from test_itinerary_native_edit import schematic_document
from test_saved_geometry import shapes_for


TURNOUT = b'''{
  RootObject = { isa = OTDocument; graphicArray = (WestCap, West, Near, Far, Main, MainCap, Branch, BranchCap,
       LeadEdge, BranchEdge, MainEdge, G0, G1, G2, G3, G4); };
  WestCap = { isa = OTConnModel; identification = 1; idOfRelated = 2; align_x = 1; origin_x = 5; origin_y = 20;
             blockEnd = "-1"; blockTopo = ""; element = G0; };
  West = { isa = OTEndModel; identification = 2; idOfRelated = 1; align_x = 2; origin_x = 5; origin_y = 20;
          element = G1; firstEdge = LeadEdge; };
  Near = { isa = OTEndModel; identification = 3; idOfRelated = 4; align_x = 1; origin_x = 50; origin_y = 20;
          element = G1; firstEdge = LeadEdge; };
  Far = { isa = OTEndModel; identification = 4; idOfRelated = 3; align_x = 2; origin_x = 50; origin_y = 20;
         element = G2; firstEdge = MainEdge; secondEdge = BranchEdge; anInfo = 1; switchTime = 4.5; };
  Main = { isa = OTEndModel; identification = 5; idOfRelated = 6; align_x = 1; origin_x = 120; origin_y = 20;
          element = G2; firstEdge = MainEdge; };
  MainCap = { isa = OTConnModel; identification = 6; idOfRelated = 5; align_x = 2; origin_x = 120; origin_y = 20;
             blockEnd = "-1"; blockTopo = ""; element = G3; };
  Branch = { isa = OTEndModel; identification = 7; idOfRelated = 8; align_x = 1; origin_x = 115; origin_y = 60;
            element = G2; firstEdge = BranchEdge; locality = 1234; };
  BranchCap = { isa = OTConnModel; identification = 8; idOfRelated = 7; align_x = 2; origin_x = 115; origin_y = 60;
               blockEnd = "-1"; blockTopo = ""; element = G4; };
  LeadEdge = { isa = OTEdgeModel; identification = 9; end1 = West; end2 = Near; length = 150; trackName = "Line A"; };
  BranchEdge = { isa = OTEdgeModel; identification = 11; end1 = Far; end2 = Branch; length = 450;
                gradient = -2.5; trackName = "Branch"; lineName = "nil"; speedDict = Speeds; };
  MainEdge = { isa = OTEdgeModel; identification = 10; end1 = Far; end2 = Main; length = 150; trackName = "Line A"; };
  Speeds = { isa = NSMutableDictionary; elements = { "0" = Limited; }; };
  Limited = { isa = OTSpeed; trainType = "0"; speed12 = 60; speed21 = 40; };
  G0 = { isa = OTElement; identification = 12; ends = (WestCap); };
  G1 = { isa = OTElement; identification = 13; ends = (West, Near); };
  G2 = { isa = OTElement; identification = 14; ends = (Far, Main, Branch); };
  G3 = { isa = OTElement; identification = 15; ends = (MainCap); };
  G4 = { isa = OTElement; identification = 16; ends = (BranchCap); };
  TopLevelObjects = (RootObject); Version = 1;
}'''
FALLBACK = [{'train_type': '0', 'speed12_kmh': 80, 'speed21_kmh': 70}]


def donors():
    template, _ = schematic_document(generate.spec(), [])
    root, version = writer.load_next_compatible(template)
    root.contents[9].values = [0.0, 0.0, 300.0, 150.0]
    return writer.dump_verified(root, version), shapes_for(template)


def test_materializes_both_turnout_slots_independent_of_source_edge_order():
    output, receipt = materialize(TURNOUT, *donors(), FALLBACK)
    assert receipt['topology']['edges'] == 3 and receipt['total_track_length_m'] == 750
    assert receipt['topology']['safety_elements'] == 5
    assert receipt['fallback_speed_edge_ids'] == [9, 10]
    assert receipt['normalized_terminal_end_ids'] == [1, 6, 8]
    _, models = route_factory.document(writer.load_next_compatible(output)[0])
    point = models[receipt['end_ids']['4']]
    main, branch = [point.contents[slot].value for slot in (9, 10)]
    assert main.contents[0].value == receipt['edge_ids']['10']
    assert branch.contents[0].value == receipt['edge_ids']['11']
    assert point.contents[21].value == 4.5 and point.contents[22].value == 1
    assert branch.contents[9].values[1:4] == [450, 0.0, -2.5]
    assert writer.string(branch.contents[20].value) == 'nil'


def test_materializes_original_bridge_speed_dictionary_keys_archived_as_nsstring_references():
    original = TURNOUT.replace(b'\"0\" = Limited;', b'Object23 = Limited;')
    original = original.replace(b'Limited = {', b'Object23 = { isa = NSString; string = 0; }; Limited = {')
    expected, _ = materialize(TURNOUT, *donors(), FALLBACK)
    actual, _ = materialize(original, *donors(), FALLBACK)
    assert actual == expected
    with pytest.raises(ValueError, match='Unsupported GModel OTSpeed record'):
        materialize(original.replace(b'string = 0;', b'string = 1;'), *donors(), FALLBACK)


@pytest.mark.parametrize(('data', 'fallback', 'message'), [
    (TURNOUT, [], 'explicit fallback_speeds'),
    (TURNOUT.replace(b'blockTopo = ""', b'blockTopo = "OtherWorksheet"', 1), FALLBACK, 'active GModel connector'),
    (TURNOUT.replace(b'secondEdge = BranchEdge', b'secondEdge = LeadEdge'), FALLBACK, 'Nonreciprocal GModel Edge'),
    (TURNOUT.replace(b'isa = OTEdgeModel; identification = 11', b'isa = OTSignalModel; identification = 11'), FALLBACK,
     'unreviewed GModel classes'),
], ids=['missing-speeds', 'live-connector', 'invalid-turnout-slot', 'active-object'])
def test_rejects_unsupported_source_semantics(data, fallback, message):
    with pytest.raises(ValueError, match=message):
        materialize(data, *donors(), fallback)


def test_fresh_archive_publication_checks_all_source_hashes(tmp_path):
    work = tmp_path / 'OTAI/workspaces/Materialize'
    work.mkdir(parents=True)
    source = {}
    header, shapes = donors()
    for name, filename, data in [('gmodel', 'Workshop.plist', TURNOUT), ('header_document', 'Header', header),
                                 ('shapes', 'Shapes', shapes)]:
        path = work / filename
        path.write_bytes(data)
        source[name] = {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}
    target = work / 'Workshop.opentrack'
    args = MaterializeGModel(**source, fallback_speeds=FALLBACK, target_path=target.relative_to(tmp_path).as_posix())
    tool = InfrastructureRailMLTools(tmp_path)
    preview = tool.materialize(args)
    assert not target.exists() and preview['geometry_readback_verified']
    result = tool.materialize(args.model_copy(update={'preview_only': False}))
    assert result['saved'] and result['all_input_hashes_rechecked']
    assert sha(target.read_bytes()) == preview['output_sha256'] == result['output_sha256']
