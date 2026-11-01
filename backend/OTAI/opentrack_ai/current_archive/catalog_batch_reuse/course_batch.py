"""Narrow current catalog reuse of original OperationalData.update_courses.

The operation method below is a static, AST-identical copy of the wave6 source.
No runtime source loading/exec, Project, migration, Definitions, or graph.
Only acceleration_percent, delayed_acceleration_percent and comment are public.
Percentages accept exact integer 50..100: reject (do not silently clamp) outside
native C's clamp domain. Delayed acceleration is NOT a braking percentage.

Object-level apply mutates a caller-owned transaction graph; callers must perform
whole-batch prevalidation, alias scope checks, and atomic serialization. This
module performs current shape and actual catalog reference checks, not topology.
"""
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.course_factories import itinerary_names
from opentrack_ai.errors import APIError
from opentrack_ai.models import UpdateCourses

ALLOWED_FIELDS = frozenset({'acceleration_percent', 'delayed_acceleration_percent', 'comment'})

def put(obj,index,value): obj.contents[index].values[0]=value

SOURCE_PROVENANCE = {'course_records': {'sha256': '1222b5a1f9a175389d37a0574a8b45b0651bb73ebdb94e0e396594eb15dfe540', 'definitions': ['SPACING_CODES', 'COURSE_LENGTHS', 'COURSE_ENCODINGS', 'COURSE_SCALARS', 'COURSE_STRINGS', 'course_version', 'course_record']}, 'drafts': {'sha256': 'f31718ff32779290499f2f871051a69eb916fe2a8438721959a802526843bfe6', 'definitions': ['text', 'set_text']}, 'generation': {'sha256': 'd492550d9e344f66835515afbd261e4da7d81681d580a82dd723bcaf970b8e40', 'definitions': ['OperationalData.update_courses'], 'method_ast_sha256': '5fb3e6120539f0844f2a9cac5627580ed8ed40189fcf1260cae3f04946101759'}}

SPACING_CODES = {'discrete': 0, 'moving': 2, 'moving_cbtc': 3}

COURSE_LENGTHS = {0: 5, 1: 6, 2: 7, 3: 7, 4: 8, 5: 9, 6: 10, 7: 11, 8: 12, 9: 13, 10: 14, 11: 15}

COURSE_ENCODINGS = [[b'@'], [b'f'], [b'@'], [b'@'], [b'@'], [b'i'], [b'i'], [b'f', b'f'], [b'i'], [b'i'], [b'@'], [b'@'], [b'f', b'f'], [b'@'], [b'@']]

COURSE_SCALARS = {'enabled': (5, 0), 'acceleration_percent': (6, 0), 'delayed_acceleration_percent': (9, 0), 'output_offset_m': (7, 0), 'additional_reservation_time_s': (12, 0), 'additional_release_time_s': (12, 1)}

COURSE_STRINGS = {'train': 3, 'speed_type': 4, 'description': 10, 'comment': 11, 'train_number': 13, 'course_type': 14}

def course_version(obj):
    version = obj.clazz.version
    if w.kind(obj) != 'OTCourse' or version not in COURSE_LENGTHS or len(obj.contents) != COURSE_LENGTHS[version] or any((group.encodings != enc for group, enc in zip(obj.contents, COURSE_ENCODINGS))):
        raise APIError('COURSE_SCHEMA', 'Course class version or typed groups differ from the audited original v0-v11 contract.', version)
    return version

def course_record(obj):
    version = course_version(obj)
    itineraries = [w.string(item) for item in w.elements(obj.contents[2].value)] if obj.contents[2].value else []
    acceleration = obj.contents[6].value if version >= 2 else 100
    code = obj.contents[8].value if version >= 5 else 0
    return {'course_id': w.string(obj.contents[0].value), 'train': w.string(obj.contents[3].value), 'itineraries': itineraries, 'itinerary_preferences': [{'itinerary': name, 'priority': index + 1} for index, name in enumerate(itineraries)], 'enabled': obj.contents[5].value > 0 if version >= 1 else True, 'speed_type': w.string(obj.contents[4].value), 'description': w.string(obj.contents[10].value) if version >= 7 else '', 'comment': w.string(obj.contents[11].value) if version >= 8 else '', 'train_number': w.string(obj.contents[13].value) if version >= 10 else '', 'course_type': w.string(obj.contents[14].value) if version >= 11 else '', 'acceleration_percent': acceleration, 'delayed_acceleration_percent': obj.contents[9].value if version >= 6 else acceleration, 'entering_speed_kmh': obj.contents[1].value * 3.6, 'output_offset_m': obj.contents[7].values[0] if version >= 4 else 0.0, 'spacing_mode_code': code, 'spacing_mode': next((name for name, value in SPACING_CODES.items() if value == code), None), 'additional_reservation_time_s': obj.contents[12].values[0] if version >= 9 else 0.0, 'additional_release_time_s': obj.contents[12].values[1] if version >= 9 else 0.0, 'archive_class_version': version}

def text(template, value):
    value.encode('ascii')
    sample = next((o for o in w.objects(template) if w.kind(o) == 'NSString'))
    return w.ar.GenericArchivedObject(sample.clazz, None, [w.ar.TypedValue(b'+', value.encode('ascii'))])

def set_text(obj, index, value):
    obj.contents[index].values[0] = text(obj, value)

def validate_spec(spec):
    if type(spec) is not dict:
        raise ValueError('Course update must be a dictionary')
    unknown=set(spec)-ALLOWED_FIELDS-{'kind','course_ids'}
    if unknown: raise ValueError('Unknown/unsupported Course fields: '+repr(sorted(unknown)))
    for key in ('acceleration_percent','delayed_acceleration_percent'):
        if key in spec and (type(spec[key]) is not int or not 50<=spec[key]<=100):
            raise ValueError(key+' must be an exact integer 50..100; no implicit C clamp')
    if 'comment' in spec and type(spec['comment']) is not str:
        raise ValueError('comment must be explicit ASCII text, not null')
    
    
    return UpdateCourses.model_validate(spec)


class CurrentCourses:
    def __init__(self,context):
        self.p=context
        self.course_update_targets=0

    def prepare_courses(self):
        
        items=c.course_items(self.p.data['courses'])
        trains={c.text(o.contents[0].value) for o in c.train_items(self.p.data['trains'])}
        destinations=itinerary_names(self.p.data['dest'])
        for obj in items:
            identity=c.text(obj.contents[0].value)
            if identity in ('0','-1'): raise ValueError('Reserved Course identity')
            for index in (0,3,4,10,11,13,14): c.text(obj.contents[index].value)
            if c.text(obj.contents[3].value) not in trains:
                raise APIError('VEHICLE_BINDING','Course references missing exact formation.',identity)
            names=[c.text(o) for o in c.array(obj.contents[2].value)]
            if len(names)!=len(set(names)) or not set(names)<=destinations:
                raise APIError('ITINERARY_BINDING','Course has duplicate/missing exact itinerary.',identity)

    def course_bindings(self,train=None,itineraries=None):
        
        
        if train is not None or itineraries is not None:
            raise ValueError('Binding changes are outside current Course batch scope')

    def update_courses(self, args):
        self.course_update_targets += len(args.course_ids)
        if self.course_update_targets > 10000:
            raise APIError('GENERATION_SIZE', 'One draft supports at most 10000 requested Course update targets.')
        self.prepare_courses()
        items = self.p.courses()
        lookup = {w.string(obj.contents[0].value): obj for obj in items}
        if len(lookup) != len(items):
            raise APIError('DUPLICATE_COURSE_ID', 'Course IDs are ambiguous in the selected catalog.')
        missing = [cid for cid in args.course_ids if cid not in lookup]
        if missing:
            raise APIError('COURSE_NOT_FOUND', 'Selected Courses do not exist.', {'course_ids': missing[:50], 'count': len(missing)})
        self.course_bindings(args.train, args.itineraries)
        changes = []
        fields = args.model_fields_set - {'kind', 'course_ids', 'invert_enabled'}
        if args.invert_enabled:
            fields = fields | {'enabled'}
        for cid in args.course_ids:
            obj = lookup[cid]
            before = course_record(obj)
            for field, (index, position) in COURSE_SCALARS.items():
                value = getattr(args, field)
                if value is not None:
                    obj.contents[index].values[position] = int(value) if field == 'enabled' else value
            for field, index in COURSE_STRINGS.items():
                value = getattr(args, field)
                if value is not None:
                    set_text(obj, index, value)
            if args.entering_speed_kmh is not None:
                put(obj, 1, args.entering_speed_kmh / 3.6)
            if args.spacing_mode is not None:
                put(obj, 8, SPACING_CODES[args.spacing_mode])
            if args.invert_enabled:
                put(obj, 5, int(not before['enabled']))
            names = list(args.itineraries) if args.itineraries is not None else list(before['itineraries'])
            if args.itinerary_move is not None:
                move = args.itinerary_move
                if names.count(move.name) != 1:
                    raise APIError('ITINERARY_ORDER', 'Move requires exactly one matching Itinerary in every selected Course.', {'course_id': cid, 'itinerary': move.name})
                names.remove(move.name)
                names.insert(min(move.priority - 1, len(names)), move.name)
            if args.itineraries is not None or args.itinerary_move is not None:
                put(obj, 2, self.d.array([text(obj, name) for name in names]))
            after = course_record(obj)
            keys = fields - {'itinerary_move'} | ({'itineraries', 'itinerary_preferences'} if args.itinerary_move or args.itineraries is not None else set())
            changes.append({'course_id': cid, 'fields': {field: {'before': before[field], 'after': after[field]} for field in sorted(keys) if before[field] != after[field]}})
        return {'courses_updated': len(changes), 'courses_changed': sum((bool(row['fields']) for row in changes)), 'course_ids': list(args.course_ids), 'course_changes': changes, 'timetable_rows_changed': 0}


def apply(context,spec):
    """Apply one strict operation to caller-owned current catalog transaction.

    context.data must contain real courses, trains and dest roots and context.courses()
    must return the same original Course graph nodes (not reconstructed records).
    """
    args=validate_spec(spec)
    expected=c.course_items(context.data['courses'])
    actual=context.courses()
    if len(actual)!=len(expected) or any(a is not b for a,b in zip(actual,expected)):
        raise ValueError('Current context courses accessor must preserve graph identity')
    return CurrentCourses(context).update_courses(args)
