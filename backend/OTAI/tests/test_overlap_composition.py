"""Persist a single local Overlap built from exact existing saved segments."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from opentrack_ai.current_archive import path_functions as paths, writer
from opentrack_ai.current_archive.current_shunting_workflow import core
from opentrack_ai.current_archive.current_shunting_workflow.structure import edit_structure
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.overlap_composition_tools import ComposeOverlap, OverlapComposition, compose_overlap
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from test_itinerary_native_edit import schematic_document


def fixture():
    network = generate.spec()
    network['vertices'] = [generate.vertex(name, i * 100) for i, name in enumerate('ABCDE')]
    prototype = network['edges'][0]
    network['edges'] = [{**prototype, 'key': a + b, 'from': [a, 1], 'to': [b, 0]}
                        for a, b in ('AB', 'BC', 'CD', 'DE')]
    data, pairs = schematic_document(network, [('A', 0), ('B', 0)])
    ends = {name: pair[0] for name, pair in pairs.items()}
    data, result = native.build_route(data, name='A-B', end_ids=[ends['A'], ends['B']], description='',
                                     release_groups='global', reserve_previous=False)
    route = {field: result[field] for field in ('array_id', 'start_id')}
    route['name'] = 'A-B'
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    settings = {'description': '', 'speed_kmh': 30, 'release_time_s': 7, 'reservation_time_s': 0}
    segments = []
    for name in ('BC', 'CD', 'DE'):
        data, receipt = edit_structure({'Line': data}, catalog, 'Line', 'create',
                                       {**settings, 'name': name, 'end_ids': [ends[key] for key in name]})
        segments.append({field: receipt['details'][field] for field in ('name', 'array_id', 'start_id')})
    return data, catalog, route, ends, segments, {**settings, 'name': 'Combined'}


def test_continuity_and_route_terminal_required():
    data, catalog, route, _, (first, second, third), settings = fixture()
    with pytest.raises(ValueError, match='same directional End'):
        compose_overlap({'Line': data}, catalog, 'Line', route, [first, third], settings)
    with pytest.raises(ValueError, match='terminal End'):
        compose_overlap({'Line': data}, catalog, 'Line', route, [second, third], settings)


def test_publish_composed_native_overlap():
    data, catalog, route, ends, segments, settings = fixture()
    with TemporaryDirectory(prefix='compose-', dir=Path(__file__).resolve().parent) as work:
        root = Path(work)
        folder = root / 'OTProjects' / 'Line'
        folder.mkdir(parents=True)

        def write(name, value):
            source = folder / name
            source.write_bytes(value)
            return {'path': source.relative_to(root).as_posix(), 'sha256': sha(value)}

        request = ComposeOverlap(
            project_run=write('Line.run', b'Infrastructure Document#Line.opentrack#\nDestInfoFile#Line.dest#\n'),
            documents={'Line': write('Line.opentrack', data)}, target_document='Line',
            dest_catalog=write('Line.dest', catalog), route=route, segments=segments, **settings,
            preview_only=False, target_path='OTProjects/Line/output.opentrack',
        )
        receipt = OverlapComposition(root).compose(request)
        assert receipt['saved'] and receipt['change_report']['original_segments_preserved']
        assert (folder / 'Line.opentrack').read_bytes() == data
        raw = (folder / 'output.opentrack').read_bytes()
        model, _, _, rows = core.load(raw)
        target = paths.select(model, 'OTRoute', **route)
        assert paths.string(target.contents[7].value) == 'Combined'
        assert target.contents[9].value == ends['B']
        overlap = next(core.detail(row) for row in rows if core.identity(row[0])['name'] == 'Combined')
        assert overlap['end_ids'] == [ends[key] for key in 'BCDE']
        assert overlap['release_time_s'] == 7
        assert len(rows) == 4
