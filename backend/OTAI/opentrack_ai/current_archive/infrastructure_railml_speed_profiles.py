"""Verify a complete direct RailML 2.2 ETCS speed exchange before relabeling GModel slots."""

from collections import defaultdict
import re

from . import course_factories, route_factory, writer
from .infrastructure_railml import railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_facilities import measurement, require


LIMIT = re.compile(r'(?:0|[1-9][0-9]{0,3})')


def source_speed_edges(raw, profiles):
    """Read direct complete category vectors in original bridge discovery order."""
    _, tracks = railml_tracks(railml_tree(raw))
    categories = tuple(map(str, profiles.values()))
    result = defaultdict(list)
    for track in tracks:
        speeds = defaultdict(dict)
        code = track.get('name') or track.get('id')
        boundaries = [track.findall(tag('trackTopology', name)) for name in ('trackBegin', 'trackEnd')]
        require(all(len(pair) == 1 for pair in boundaries), f'Track {code!r} requires one entry and one exit')
        begin, end = (measurement(pair[0], 'pos') for pair in boundaries)
        for change in track.findall(tag('trackElements', 'speedChanges', 'speedChange')):
            category = change.get('etcsTrainCategory', '')
            direction = change.get('dir')
            value = change.get('vMax', '')
            require(direction in ('up', 'down') and category in categories
                    and set(change.attrib) <= {'id', 'pos', 'dir', 'vMax', 'etcsTrainCategory', 'name', 'description'}
                    and LIMIT.fullmatch(value) is not None and int(value) <= 1000 and not len(change),
                    'Explicit speed_profiles expects direct ordered ETCS speedChange rows with whole km/h limits')
            position = measurement(change, 'pos')
            at = speeds[(direction, position)]
            require(category not in at, 'RailML directional speed profile repeats an ETCS category at a boundary')
            at[category] = int(value)
        require(speeds and all(tuple(vector) == categories for vector in speeds.values()),
                'Each RailML speed boundary must specify every ETCS category in the explicit mapping order')
        starts = sorted(position for direction, position in speeds if direction == 'up')
        finishes = sorted(position for direction, position in speeds if direction == 'down')
        require(starts and finishes and starts[0] == begin and finishes[-1] == end
                and starts[1:] == finishes[:-1] and len(starts) == len(finishes),
                'Both RailML speed directions must completely cover the same contiguous physical spans')
        for start, finish in zip(starts, finishes):
            length = finish - start
            require(length == int(length) and length > 0, 'Complete speed-profile spans require whole positive metres')
            result[code].append((int(length), tuple(speeds['up', start].values()), tuple(speeds['down', finish].values())))
    return dict(result)


def verify_native_speed_edges(document, profiles, expected):
    root, _ = writer.load_next_compatible(document)
    models, _ = route_factory.document(root)
    observed = defaultdict(list)
    for model in models:
        if writer.kind(model) != 'OTEdgeModel':
            continue
        name = writer.string(model.contents[19].value)
        limits = course_factories.dictionary(model.contents[16].value)
        require(tuple(limits) == tuple(profiles), 'Native saved Edge speed keys are inconsistent with the explicit mapping')
        up, down = (tuple(limits[key].contents[slot].value for key in profiles) for slot in (1, 2))
        observed[name].append((model.contents[9].values[1], up, down))
    require(observed == expected, 'One or more complete native Edge speed vectors differ from the RailML source')
    edge_count = sum(len(spans) for spans in observed.values())
    return {'edge_count': edge_count, 'directional_value_count': 2 * len(profiles) * edge_count}
