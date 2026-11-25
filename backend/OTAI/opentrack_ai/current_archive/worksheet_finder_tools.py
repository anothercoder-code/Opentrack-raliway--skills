"""Original worksheet Finder predicates and signed kilometre-point conflicts."""

from math import isfinite
from pathlib import Path
from struct import pack, unpack
from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr

from ..errors import APIError
from . import route_factory as rf, writer as w
from .bundle_tools import Source
from .next_tools import NextFunctions, Ordinal
from .prepare_contract.auxiliary import records
from .saved_geometry import UNSET_KILOMETRE, _end_shape
from .tools import Input, sha


END_CLASSES = {'OTEndModel', 'OTConnModel'}


class ById(Input):
    kind: Literal['object_id']
    id: Ordinal


class ByName(Input):
    kind: Literal['vertex_name', 'signal_name']
    name: Annotated[StrictStr, Field(min_length=1, max_length=240)]
    match: Literal['exact', 'contains'] = 'exact'


class ByKilometre(Input):
    kind: Literal['kilometre_point']
    kilometre_point: Annotated[float, Field(ge=-100000, le=100000, allow_inf_nan=False)]


class Conflicts(Input):
    kind: Literal['kilometre_conflicts']


Query = Annotated[ById | ByName | ByKilometre | Conflicts, Field(discriminator='kind')]


class WorksheetQuery(Input):
    source: Source
    related_worksheets: list[Source] = Field(default_factory=list, max_length=64)
    project_run: Source | None = None
    query: Query
    offset: Annotated[StrictInt, Field(ge=0)] = 0
    limit: Annotated[StrictInt, Field(ge=1, le=1000)] = 200


def single(value):
    return unpack('<f', pack('<f', value))[0]


def verify_run_membership(run_path, run_data, selected):
    declarations = []
    for key, value, _ in records(run_data):
        if key == 'Infrastructure Document':
            path = Path(value)
            rf.require('..' not in path.parts, 'Run declarations cannot contain parent traversal')
            declarations.append(path if path.is_absolute() else run_path.parent / path)
    declared = set(declarations)
    rf.require(len(declared) == len(declarations) and selected <= declared,
               'Selected worksheets must be the exact paths declared by this run file')


def kilometres(graphs, document, end):
    _end_shape(end)
    point = end.contents[14].value
    rf.require(isfinite(point), 'Invalid saved kilometre point')
    if point != UNSET_KILOMETRE:
        return point
    related = graphs[document].get(end.contents[8].value)
    if related is None:
        return None
    _end_shape(related)
    end_id = end.contents[0].value
    rf.require(related.contents[8].value == end_id, 'Nonreciprocal local directional Ends')
    if w.kind(related) == 'OTConnModel':
        remote_name = w.string(related.contents[25].value)
        if remote_name not in graphs:
            return None
        remote = graphs[remote_name].get(related.contents[26].value)
        rf.require(remote is not None and w.kind(remote) == 'OTConnModel', 'Missing remote connector')
        _end_shape(remote)
        rf.require(w.string(remote.contents[25].value) == document
                   and remote.contents[26].value == related.contents[0].value, 'Nonreciprocal remote connector')
        related = graphs[remote_name].get(remote.contents[8].value)
        rf.require(related is not None, 'Missing End behind remote connector')
        _end_shape(related)
        rf.require(related.contents[8].value == remote.contents[0].value, 'Nonreciprocal remote directional Ends')
    value = related.contents[14].value
    rf.require(isfinite(value), 'Invalid related kilometre point')
    return value


def describe(graphs, document, obj):
    kind = w.kind(obj)
    item = {'id': obj.contents[0].value, 'class': kind}
    if kind in END_CLASSES:
        _end_shape(obj)
        item.update(name=w.string(obj.contents[18].value),
                    kilometre_point=kilometres(graphs, document, obj),
                    position=[obj.contents[2].value, obj.contents[3].value])
    elif kind == 'OTSignalModel':
        rf.layout(obj, kind, 11, rf.SIGNAL, graphic=True)
        end = obj.contents[7].value
        _end_shape(end)
        end_id = end.contents[0].value
        rf.require(end is graphs[document].get(end_id) and end.contents[11].value is obj,
                   'Signal and directional End association is not reciprocal')
        item.update(name=w.string(obj.contents[13].value), end_id=end_id,
                    signal_type=obj.contents[8].values[0],
                    position=[end.contents[2].value, end.contents[3].value])
    return item


def edge_conflict(graphs, document, obj):
    rf.layout(obj, 'OTEdgeModel', 3, rf.EDGE, graphic=True)
    endpoints = [obj.contents[slot].value for slot in (7, 8)]
    for end in endpoints:
        _end_shape(end)
        rf.require(end is graphs[document].get(end.contents[0].value)
                   and obj in [end.contents[slot].value for slot in (9, 10)],
                   'Edge endpoint reference is not reciprocal')
    points = [kilometres(graphs, document, end) for end in endpoints]
    if None in points:
        return None
    # Native 0x6def2c rounds each float32 metre coordinate half away from zero.
    metres = [single(point * 1000) for point in points]
    first, last = [int(value + (0.5 if value >= 0 else -0.5)) for value in metres]
    length = obj.contents[9].values[1]
    difference = last - first
    return {'id': obj.contents[0].value, 'end_ids': [end.contents[0].value for end in endpoints],
            'kilometre_points': points, 'physical_length_m': length,
            'signed_kilometre_length_m': difference, 'discrepancy_m': difference - length,
            'uses_unset_kilometre': UNSET_KILOMETRE in points}


def worksheet_results(graphs, document, query):
    kind = query.kind
    objects = graphs[document]
    if kind == 'object_id':
        obj = objects.get(query.id)
        return ([] if obj is None else [describe(graphs, document, obj)]), []
    hits, unresolved = [], []
    selected_point = single(query.kilometre_point) if kind == 'kilometre_point' else None
    for obj in objects.values():
        model_kind = w.kind(obj)
        if kind == 'kilometre_conflicts' and model_kind == 'OTEdgeModel':
            row = edge_conflict(graphs, document, obj)
            if row is None:
                unresolved.append(obj.contents[0].value)
            elif row['discrepancy_m']:
                hits.append(row)
        elif kind == 'kilometre_point' and model_kind in END_CLASSES:
            row = describe(graphs, document, obj)
            if row['kilometre_point'] is None:
                unresolved.append(row['id'])
            elif row['kilometre_point'] == selected_point:
                hits.append(row)
        elif ((kind == 'vertex_name' and model_kind in END_CLASSES)
              or (kind == 'signal_name' and model_kind == 'OTSignalModel')):
            row = describe(graphs, document, obj)
            name = row['name']
            if name is not None and (query.name == name if query.match == 'exact' else query.name in name):
                hits.append(row)
    return hits, unresolved


class NativeWorksheetFinder(NextFunctions):
    def query(self, args):
        graphs = {}
        selected = set()
        try:
            rf.require(not args.related_worksheets or args.project_run is not None,
                       'Supply the shared project run file to resolve remote worksheets')
            for source in (args.source, *args.related_worksheets):
                path, _, root, _ = self.checked(source)
                rf.require(path.suffix.lower() == '.opentrack' and path.stem not in graphs,
                           'Use separate native worksheets with unique document names')
                _, graphs[path.stem] = rf.document(root)
                selected.add(path)
            if args.project_run is not None:
                run_path = self.path(args.project_run.path)
                rf.require(run_path.suffix.lower() == '.run', 'Select a native .run file')
                run_data = self.secure_bytes(run_path)
                rf.require(sha(run_data) == args.project_run.sha256, 'Selected run has changed')
                verify_run_membership(run_path, run_data, selected)
            document = self.path(args.source.path).stem
            matches, unresolved = worksheet_results(graphs, document, args.query)
            return {'source': args.source.model_dump(), 'document': document,
                    'related_worksheets': [source.model_dump() for source in args.related_worksheets],
                    'project_run': args.project_run.model_dump() if args.project_run is not None else None,
                    'matches': matches[args.offset:args.offset + args.limit],
                    'total_matches': len(matches), 'offset': args.offset,
                    'unresolved_ids': unresolved[:1000], 'unresolved_count': len(unresolved),
                    'read_only': True}
        except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError('NATIVE_FINDER_INVALID', 'Could not query current native worksheet', str(exc)[:500]) from exc


def tool_definitions(root):
    service = NativeWorksheetFinder(root)
    return [('opentrack_query_native_worksheet',
             'Find original worksheet objects by ID, vertex name, signal name or exact kilometre point. '
             'Also audit original signed kilometre point conflicts. Read only.',
             WorksheetQuery, service.query)]
