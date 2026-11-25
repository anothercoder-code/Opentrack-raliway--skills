"""Original bridge inputs, graph readback and the original success marker."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive.infrastructure_railml import gmodel_inventory, railml_inventory
from opentrack_ai.current_archive import infrastructure_railml_tools as tools
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError


XML = b'''<railml xmlns="http://www.railml.org/schemas/2013" version="2.2">
  <infrastructure id="one"><tracks>
    <track id="one-track"><trackTopology>
      <trackBegin id="one-a" pos="0"><openEnd id="outside"/></trackBegin>
      <trackEnd id="one-b" pos="300"><connection id="join-one" ref="join-two"/></trackEnd>
    </trackTopology></track>
    <track id="two-track"><trackTopology>
      <trackBegin id="two-a" pos="0"><connection id="join-two" ref="join-one"/></trackBegin>
      <trackEnd id="two-b" pos="450"><openEnd id="other"/></trackEnd>
    </trackTopology></track>
  </tracks></infrastructure>
</railml>'''

GMODEL = b'''// Native worksheet property list
{
  RootObject = { isa = OTDocument; graphicArray = (OneA, OneB, TwoA, TwoB, EdgeOne, EdgeTwo); };
  OneA = { isa = OTEndModel; identification = 2; idOfRelated = 1; origin_x = 0; origin_y = 10; };
  OneB = { isa = OTEndModel; identification = 3; idOfRelated = 7; origin_x = 100; origin_y = 10; };
  TwoA = { isa = OTEndModel; identification = 7; idOfRelated = 3; origin_x = 100; origin_y = 10; };
  TwoB = { isa = OTEndModel; identification = 8; idOfRelated = 9; origin_x = 300; origin_y = 10; };
  EdgeOne = { isa = OTEdgeModel; identification = 4; length = 300; end1 = OneA; end2 = OneB; };
  EdgeTwo = { isa = OTEdgeModel; identification = 10; length = 450; end1 = TwoA; end2 = TwoB; };
  TopLevelObjects = (RootObject);
  Version = 1;
}
'''


def test_gmodel_readback_summarizes_actual_lengths_and_reciprocal_endpoints():
    rail = railml_inventory(XML)
    native = gmodel_inventory(GMODEL)
    assert rail['track_length_sample_m'] == native['edge_length_sample_m'] == [300.0, 450.0]
    assert rail['reciprocal_connection_pairs'] == native['reciprocal_interior_end_pairs'] == 1
    assert native['end_bounds'] == [0.0, 10.0, 300.0, 10.0]


def test_gmodel_resolves_archived_graphic_array_objects():
    raw = GMODEL.replace(b'graphicArray = (OneA, OneB, TwoA, TwoB, EdgeOne, EdgeTwo)', b'graphicArray = Members')
    raw = raw.replace(b'  Version = 1;', b'  Members = { isa = NSMutableArray; '
                     b'elements = (OneA, OneB, TwoA, TwoB, EdgeOne, EdgeTwo); };\n  Version = 1;')
    assert gmodel_inventory(raw) == gmodel_inventory(GMODEL)


def test_gmodel_distinguishes_a_three_end_junction():
    raw = GMODEL.replace(b'TwoB, EdgeOne, EdgeTwo);', b'TwoB, EdgeOne, EdgeTwo, Turnout);')
    raw = raw.replace(b'  Version = 1;', b'  Turnout = { isa = OTElement; ends = BranchEnds; };\n'
                     b'  BranchEnds = { isa = NSMutableArray; elements = (OneA, OneB, TwoA); };\n  Version = 1;')
    assert gmodel_inventory(raw)['junction_element_count'] == 1


@pytest.mark.parametrize(('raw','read','message'), [
    (b'<!DOCTYPE railml SYSTEM "somewhere.dtd">' + XML, railml_inventory, 'omit all DTD'),
    (XML.replace(b'pos="300"', b'pos="NaN"'), railml_inventory, 'Non-finite'),
    (GMODEL.replace(b'end2 = OneB', b'end2 = Absent'), gmodel_inventory, 'Unresolved GModel edge'),
], ids=['external-dtd', 'non-finite', 'dangling-end'])
def test_infrastructure_shape_errors_are_explicit(raw, read, message):
    with pytest.raises(ValueError, match=message):
        read(raw)


def test_zero_exit_code_without_ok_marker_does_not_publish(monkeypatch):
    jar = b'Mock JAR for subprocess tests only'
    monkeypatch.setattr(tools, 'BRIDGE_SHA256', sha(jar))

    def failed(args, cwd, stderr, **_):
        assert args[-3:] == ['r2p', 'candidate.xml', 'candidate.plist']
        assert (Path(cwd) / 'candidate.xml').read_bytes() == XML
        (Path(cwd) / 'candidate.plist').write_bytes(GMODEL)
        stderr.write(b'java.lang.IllegalArgumentException: NaN not supported\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tools.subprocess, 'run', failed)
    with pytest.raises(APIError) as err:
        tools.bridge_convert(Path('java.exe'), jar, 'r2p', 'candidate.xml', XML, 'candidate.plist')
    assert err.value.code == 'RAILML_BRIDGE_FAILED'
    assert err.value.details['process_exit_code'] == 0


def test_bridge_refuses_a_different_jar_before_starting_java(monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail('Unexpected Java launch')

    monkeypatch.setattr(tools.subprocess, 'run', unexpected)
    with pytest.raises(APIError, match='verified original bridge'):
        tools.bridge_convert(Path('java.exe'), b'different JAR', 'r2p', 'candidate.xml', XML, 'candidate.plist')
