from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import native_itinerary_import_tools as transfer, path_functions
from opentrack_ai.current_archive.itinerary_lifecycle_tools import _definitions
from test_itinerary_native_edit import fixture, with_margin


def state(root, *, margin=False):
    worksheet, catalog = 'OTDocuments/Line.opentrack', 'OTData/Line.dest'
    docs, data, paths, refs = fixture(f'{root}/{worksheet}')
    if margin:
        docs['Line'] = with_margin(docs['Line'])
        docs['Line'], _ = path_functions.set_description(docs['Line'], 'OTDest', 'Service', 'Donor notes')
    return {'documents': docs, 'document_paths': paths, 'document_members': {'Line': worksheet},
            'root': root, 'run': b'run', 'roles': {'dest': catalog},
            'files': {catalog: data, worksheet: docs['Line']}}, refs


def parameters(refs, **fields):
    return SimpleNamespace(station_mapping={}, itineraries=[
        transfer.Selection(source_name='Service', target_name='Imported', target_paths=refs, **fields)])


def test_import_materializes_both_archive_members_and_keeps_margins(monkeypatch):
    donor, source_refs = state('D:/Donor', margin=True)
    target, target_refs = state('D:/Target')
    monkeypatch.setattr(transfer.preflight, 'check', lambda *_: {'passed_static_subset': True, 'errors': []})
    changed, report = transfer.apply_import(target, donor, parameters(target_refs[2:]))
    assert set(changed) == {'OTDocuments/Line.opentrack', 'OTData/Line.dest'}
    item, = report['imported_itineraries']
    assert item['source_paths'] == source_refs[:2]
    assert item['target_paths'] == target_refs[2:]
    assert item['safety_margins'] == [{'position_m': 100.0, 'safety_margin_m': 5.0}]
    assert item['description'] == 'Donor notes'
    after = transfer.read_project({**target, 'files': {**target['files'], **changed},
                                   'documents': {'Line': changed['OTDocuments/Line.opentrack']}})
    assert set(_definitions(after)) == {'Service', 'Imported'}
    assert _definitions(transfer.read_project(donor)).keys() == {'Service'}


def test_changed_mileage_needs_explicit_safe_margin_coordinates(monkeypatch):
    donor, _ = state('D:/Donor', margin=True)
    target, refs = state('D:/Target')
    monkeypatch.setattr(transfer.preflight, 'check', lambda *_: {'passed_static_subset': True, 'errors': []})
    with pytest.raises(ValueError, match='explicit target safety_margins'):
        transfer.apply_import(target, donor, parameters(refs[:1]))
    with pytest.raises(ValueError, match='within target geometry'):
        transfer.apply_import(target, donor, parameters(refs[:1], safety_margins=[
            {'position_m': 1001, 'safety_margin_m': 4}]))
    _, report = transfer.apply_import(target, donor, parameters(refs[:1], safety_margins=[]))
    assert report['imported_itineraries'][0]['safety_margins'] == []
