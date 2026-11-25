"""RailML 2.2 multiple-direction ETCS limits and original bridge slot identity."""

from xml.etree import ElementTree as ET

from pydantic import ValidationError
import pytest

from opentrack_ai.current_archive import infrastructure_railml_tools
from opentrack_ai.current_archive.gmodel_materialization import edge_speeds
from opentrack_ai.current_archive.infrastructure_railml import railml_path as tag, railml_tree
from opentrack_ai.current_archive.infrastructure_railml_speed_profiles import source_speed_edges, verify_native_speed_edges
from opentrack_ai.current_archive.infrastructure_railml_tools import ExportGeometry, InfrastructureRailMLTools, MaterializeGModel
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document
from test_railml_geometry_export import physical, place, trace
from opentrack_ai.current_archive.tools import sha


PROFILES = [{'native_train_type': '0', 'etcs_train_category': 3}, {'native_train_type': '1', 'etcs_train_category': 7}]
MAP = {'0': 3, '1': 7}


def candidate(tmp_path, reverse=False):
    spec = generate.spec()
    spec['edges'][0].update(track_name='Main', equal_speed=False,
                           speeds=[dict(train_type='0', speed12_kmh=45, speed21_kmh=31),
                                   dict(train_type='1', speed12_kmh=81, speed21_kmh=57),
                                   dict(train_type='2', speed12_kmh=100, speed21_kmh=91)])
    data, vertices = schematic_document(spec, [])
    edge_id = physical(data)[0][0]
    start = vertices['right'][0] if reverse else vertices['left'][1]
    role = place(tmp_path, 'C.opentrack', data, [trace('T', (edge_id, start))])
    args = {'documents': [role], 'speed_profiles': PROFILES, 'preview_only': False,
            'target_path': 'OTAI/workspaces/geometry/Multiprofile.railml'}
    return data, args


def test_both_directions_use_schema_etcs_categories_without_legacy_references(tmp_path):
    data, args = candidate(tmp_path, reverse=True)
    service = InfrastructureRailMLTools(tmp_path)
    saved = service.export_geometry(ExportGeometry(**args))
    assert saved['output_inventory']['total_track_length_m'] == 1000
    assert saved['selected_speed_profiles'] == MAP
    assert saved['omitted_native_fields']['unselected_speed_categories']['sample'] == ['2']
    xml = (tmp_path/args['target_path']).read_bytes()
    limits = [item.attrib for item in railml_tree(xml).iter(tag('speedChange'))]
    assert [(x['dir'], x['pos'], x['etcsTrainCategory'], x['vMax']) for x in limits] == [
        ('up','0','3','31'), ('up','0','7','57'), ('down','1000','3','45'), ('down','1000','7','81')]
    assert all('profileRef' not in row for row in limits)
    assert source_speed_edges(xml, MAP) == {'Main': [(1000,(31,57),(45,81))]}
    with pytest.raises(ValueError, match='speed keys are inconsistent'):
        verify_native_speed_edges(data, MAP, source_speed_edges(xml, MAP))


@pytest.mark.parametrize(('invalid', 'error'), [
    ('missing', 'every ETCS category'),
    ('reordered', 'in the explicit mapping order'),
    ('pointer', 'expects direct ordered ETCS'),
    ('duplicate', 'repeats an ETCS category'),
    ('different_span', 'same contiguous physical spans'),
])
def test_speed_source_requires_complete_ordered_physical_coverage(tmp_path, invalid, error):
    _, args = candidate(tmp_path)
    InfrastructureRailMLTools(tmp_path).export_geometry(ExportGeometry(**args))
    xml = railml_tree((tmp_path/args['target_path']).read_bytes())
    entries = next(xml.iter(tag('speedChanges')))
    if invalid == 'missing':
        entries.remove(entries[1])
    if invalid == 'duplicate':
        entries[1].set('etcsTrainCategory','3')
    if invalid == 'reordered':
        original = entries[1]
        entries.remove(original)
        entries.insert(0, original)
    if invalid == 'pointer':
        entries[0].set('profileRef','Legacy')
    if invalid == 'different_span':
        for row in list(entries)[-2:]:
            row.set('pos', '900')
    with pytest.raises(ValueError, match=error):
        source_speed_edges(ET.tostring(xml), MAP)


def test_bridge_compact_gmodel_slots_use_the_explicit_source_order():
    model = {
        'dict': {'isa': 'NSMutableDictionary', 'elements': {'Object1': 'R1', 'Object0': 'R0'}},
        'Object1': {'isa': 'NSString', 'string': '1'},
        'Object0': {'isa': 'NSString', 'string': '0'},
        'R1': {'isa': 'OTSpeed', 'trainType': '1', 'speed12': '78', 'speed21': '72'},
        'R0': {'isa': 'OTSpeed', 'trainType': '0', 'speed12': '41', 'speed21': '39'},
    }
    found, fallback = edge_speeds(model, {'speedDict': 'dict'}, [], {'slow': 9, 'fast': 4})
    assert found == [{'train_type':'slow','speed12_kmh':41,'speed21_kmh':39},
                     {'train_type':'fast','speed12_kmh':78,'speed21_kmh':72}]
    assert not fallback
    with pytest.raises(ValueError, match='missing from a GModel Edge'):
        edge_speeds(model, {}, [], MAP)


def test_materialization_rejects_source_and_gmodel_that_do_not_replay(tmp_path, monkeypatch):
    _, args = candidate(tmp_path)
    service = InfrastructureRailMLTools(tmp_path)
    service.export_geometry(ExportGeometry(**args))
    work = (tmp_path / args['target_path']).parent

    def bind(path):
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(path.read_bytes())}

    input_spec = {}
    for role, filename in [('gmodel','Other.plist'),('header_document','Header'),('shapes','Shapes')]:
        path = work / filename
        path.write_bytes(b'a different member')
        input_spec[role] = bind(path)
    with pytest.raises(ValidationError, match='requires its original SHA-bound railml_speed_source'):
        MaterializeGModel(**input_spec, speed_profiles=PROFILES)
    input_spec['railml_speed_source'] = bind(tmp_path / args['target_path'])
    monkeypatch.setattr(infrastructure_railml_tools, 'java_executable', lambda: 'original-java')
    monkeypatch.setattr(infrastructure_railml_tools, 'bridge_resource', lambda _: b'original-jar')
    monkeypatch.setattr(infrastructure_railml_tools, 'bridge_convert', lambda *_: (b'replay', {}))
    with pytest.raises(APIError, match='differs from the official bridge replay'):
        service.materialize(MaterializeGModel(**input_spec, speed_profiles=PROFILES))


@pytest.mark.parametrize('bad', [
    [{'native_train_type': '1', 'etcs_train_category': 16}],
    [{'native_train_type': '0', 'etcs_train_category': 3}, {'native_train_type': '1', 'etcs_train_category': 3}],
])
def test_speed_profile_mappings_follow_the_official_integer_category_range_and_are_unique(tmp_path, bad):
    _, args = candidate(tmp_path)
    with pytest.raises(ValidationError):
        ExportGeometry(**{**args, 'speed_profiles':bad})
