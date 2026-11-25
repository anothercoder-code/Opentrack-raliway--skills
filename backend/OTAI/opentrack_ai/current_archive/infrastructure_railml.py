"""Read back the original RailML bridge's worksheet exchange objects."""

from collections import Counter
import math
import re
from xml.etree import ElementTree as ET
from xml.parsers import expat


RAILML_NAMESPACE = 'http://www.railml.org/schemas/2013'
RAILML_TAG = f'{{{RAILML_NAMESPACE}}}'
MAX_MEMBER_BYTES = 20 * 1024 * 1024
TOKEN = re.compile(r'\s+|(?:/\*.*?\*/|//[^\r\n]*)|([{}()=;,]|"(?:\\.|[^"\\])*"|<[\da-fA-F\s]*>|[^\s{}()=;,"<>]+)', re.DOTALL)


def finite(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid {label}: {value!r}') from exc
    if not math.isfinite(result):
        raise ValueError(f'Non-finite {label}: {value!r}')
    return result


def railml_tree(raw):
    if not 0 < len(raw) <= MAX_MEMBER_BYTES:
        raise ValueError('Expected nonempty bounded RailML XML')
    parser = expat.ParserCreate(namespace_separator='}')
    builder = ET.TreeBuilder()
    depth = 0
    elements = 0

    def qname(name):
        return '{' + name if '}' in name else name

    def start(name, attributes):
        nonlocal depth, elements
        depth += 1
        elements += 1
        if depth > 64 or elements > 250000 or len(attributes) > 128:
            raise ValueError('RailML bridge input exceeds XML structure limits')
        builder.start(qname(name), {qname(key): value for key, value in attributes.items()})

    def end(name):
        nonlocal depth
        builder.end(qname(name))
        depth -= 1

    def no_dtd(*_):
        raise ValueError('RailML bridge XML must omit all DTD declarations')

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = builder.data
    parser.StartDoctypeDeclHandler = no_dtd
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(raw, True)
    root = builder.close()
    if root.tag != RAILML_TAG + 'railml' or root.get('version') != '2.2':
        raise ValueError('Expected RailML 2.2 with its original 2013 namespace')
    return root


def railml_path(*names):
    return '/'.join(RAILML_TAG + name for name in names)


def railml_tracks(root):
    infra = root.findall(railml_path('infrastructure'))
    if len(infra) != 1:
        raise ValueError('RailML bridge requires exactly one infrastructure group')
    tracks = infra[0].findall(railml_path('tracks', 'track'))
    if not tracks or len({track.get('id') for track in tracks}) != len(tracks) or any(not t.get('id') for t in tracks):
        raise ValueError('Expected unique RailML infrastructure track IDs')
    return infra[0], tracks


def railml_inventory(raw):
    root = railml_tree(raw)
    infra, tracks = railml_tracks(root)
    tag = railml_path
    lengths = []
    for track in tracks:
        begin, end = (track.findall(tag('trackTopology', name)) for name in ('trackBegin', 'trackEnd'))
        if len(begin) != 1 or len(end) != 1:
            raise ValueError(f'Track {track.get("id")!r} requires a begin and an end')
        length = finite(end[0].get('pos'), 'track end position') - finite(begin[0].get('pos'), 'track begin position')
        if not math.isfinite(length) or length <= 0:
            raise ValueError(f'Track {track.get("id")!r} needs a positive finite length')
        lengths.append(length)
    links = {}
    for connection in infra.iter(tag('connection')):
        code, target = connection.get('id'), connection.get('ref')
        if not code or code in links or not target or target == code:
            raise ValueError('Expected unique and explicit RailML connection IDs and references')
        links[code] = target
    unmatched = sorted(code for code, target in links.items() if links.get(target) != code)
    return {'format': 'railml_2_2', 'track_count': len(tracks), 'total_track_length_m': math.fsum(lengths),
            'track_length_sample_m': lengths[:20], 'reciprocal_connection_pairs': (len(links) - len(unmatched)) // 2,
            'unmatched_connection_count': len(unmatched), 'unmatched_connection_sample': unmatched[:20],
            'switch_count': sum(1 for _ in infra.iter(tag('switch'))),
            'signal_count': sum(1 for _ in infra.iter(tag('signal'))),
            'position_count': sum(1 for _ in root.iter(tag('position')))}


def plist_tokens(text):
    index = 0
    while index < len(text):
        match = TOKEN.match(text, index)
        if match is None:
            raise ValueError(f'Invalid native property list at character {index}')
        index = match.end()
        if match.group(1) is not None:
            yield match.group(1)


class QuotedString(str):
    """Distinguish a literal quoted value from the unquoted OpenStep nil token."""


def scalar(token):
    if token is None or token in ('{', '}', '(', ')', ';', '=', ',') or token.startswith('<'):
        raise ValueError('Expected a native property-list scalar')
    return QuotedString(token[1:-1]) if token.startswith('"') else token


class PropertyList:
    def __init__(self, text):
        self.tokens = iter(plist_tokens(text))
        self.token = next(self.tokens, None)

    def take(self, expected=None):
        token = self.token
        if token is None or (expected is not None and token != expected):
            raise ValueError(f'Expected {expected or "native data"}, found {token!r}')
        self.token = next(self.tokens, None)
        return token

    def value(self, depth=0):
        if depth > 64:
            raise ValueError('Native GModel property list exceeds 64 levels')
        if self.token == '{':
            self.take('{')
            values = {}
            while self.token != '}':
                key = scalar(self.take())
                if key in values:
                    raise ValueError(f'Duplicate native property-list key {key!r}')
                self.take('=')
                values[key] = self.value(depth + 1)
                self.take(';')
            self.take('}')
            return values
        if self.token == '(':
            self.take('(')
            values = []
            while self.token != ')':
                values.append(self.value(depth + 1))
                if self.token != ')':
                    self.take(',')
            self.take(')')
            return values
        token = self.take()
        return token if token.startswith('<') else scalar(token)


def archive_list(model, reference):
    if isinstance(reference, str):
        container = model.get(reference)
        reference = container.get('elements') if isinstance(container, dict) else None
    if not isinstance(reference, list) or any(not isinstance(key, str) for key in reference):
        raise ValueError('Expected a native GModel reference list')
    return reference


def gmodel_graph(raw):
    if not 0 < len(raw) <= MAX_MEMBER_BYTES or b'\0' in raw:
        raise ValueError('Expected original bounded ASCII GModel property list')
    parser = PropertyList(raw.decode('utf-8-sig'))
    model = parser.value()
    if parser.token is not None or not isinstance(model, dict) or model.get('Version') != '1':
        raise ValueError('Expected one original GModel property list v1')
    doc = model.get('RootObject')
    if not isinstance(doc, dict) or doc.get('isa') != 'OTDocument':
        raise ValueError('GModel root must be an OTDocument worksheet')
    reference = archive_list(model, doc.get('graphicArray'))
    if len(set(reference)) != len(reference):
        raise ValueError('Duplicate graphic reference in GModel')
    graphics = {key: model.get(key) for key in reference}
    if any(not isinstance(item, dict) or not isinstance(item.get('isa'), str) for item in graphics.values()):
        raise ValueError('Unresolved GModel graphic object')
    return model, doc, graphics


def gmodel_inventory(raw):
    model, _, graphics = gmodel_graph(raw)
    classes = Counter(item['isa'] for item in graphics.values())
    ends = {key: row for key, row in graphics.items() if row['isa'] in ('OTEndModel', 'OTConnModel')}
    junctions = sum(len(archive_list(model, row.get('ends'))) >= 3
                    for row in graphics.values() if row['isa'] == 'OTElement')
    edge_ends = {}
    edges = []
    for row in graphics.values():
        if row['isa'] != 'OTEdgeModel':
            continue
        pair = (row.get('end1'), row.get('end2'))
        if pair[0] == pair[1] or any(not isinstance(key, str) or key not in ends for key in pair):
            raise ValueError('Unresolved GModel edge end reference')
        length = finite(row.get('length'), 'GModel edge length')
        if length <= 0:
            raise ValueError('Expected positive GModel edge length')
        for key in pair:
            edge_ends.setdefault(key, []).append(len(edges))
        edges.append(length)
    if not edges:
        raise ValueError('GModel worksheet contains no tracks')
    ids = {row.get('identification'): key for key, row in ends.items()}
    if len(ids) != len(ends) or None in ids:
        raise ValueError('Expected unique native end IDs')
    internal_pairs = set()
    for key, node in ends.items():
        related = ids.get(node.get('idOfRelated'))
        if related != key and key in edge_ends and related in edge_ends and ends[related].get('idOfRelated') == node['identification']:
            internal_pairs.add(tuple(sorted((key, related))))
    coords = [(finite(row.get('origin_x'), 'GModel end X'), finite(row.get('origin_y'), 'GModel end Y'))
              for row in ends.values() if 'origin_x' in row and 'origin_y' in row]
    bounds = None if not coords else [min(x for x, _ in coords), min(y for _, y in coords),
                                       max(x for x, _ in coords), max(y for _, y in coords)]
    return {'format': 'opentrack_gmodel', 'object_counts': dict(sorted(classes.items())), 'edge_count': len(edges),
            'total_edge_length_m': math.fsum(edges), 'edge_length_sample_m': edges[:20],
            'reciprocal_interior_end_pairs': len(internal_pairs), 'junction_element_count': junctions, 'end_bounds': bounds}
