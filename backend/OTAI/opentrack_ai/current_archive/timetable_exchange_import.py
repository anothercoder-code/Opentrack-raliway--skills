"""OpenTrack TSV/XML exchange into current, bound native operating archives."""

from collections import Counter
from typing import Annotated, Literal

from pydantic import Field, StrictBool

from ..errors import APIError
from ..timetable_text_core import parse_text
from ..timetable_xml import NativeXMLParser
from . import catalogs as c, course_factories as cf
from .bundle_tools import Source
from .multi_document_tools import Inventory
from .native_connections import LAYOUT, connection, wait
from .operating_plan_edit import apply_row_fields, dictionary_replace, need, row_key, set_sequence, text
from .operating_plan_edit_tools import Id, Index, OperatingPlanEditTools, operating_candidate
from .project_candidate_publication import ProjectSave
from .tools import Input, sha
from .zero_generation.native_signal_routes import obj, string


MAX_EXCHANGE_BYTES = 2_000_000


class RowTemplate(Input):
    course_id: Id
    index: Index


class ImportTimetableExchange(ProjectSave):
    source_project: Inventory
    exchange: Source
    format: Literal['opentrack_text', 'opentrack_xml']
    existing: Literal['reject', 'replace', 'merge'] = 'reject'
    row_template: RowTemplate
    new_course_templates: Annotated[dict[Id, Id], Field(max_length=1000)] = Field(default_factory=dict)
    connection_attribute_order: Literal['require_unambiguous', 'place_then_time_type', 'time_type_then_place'] = 'require_unambiguous'
    import_xml_actual: StrictBool = False


def _native_connection(owner, station, fields):
    flags = int(fields['join']) | (2 * int(fields['split'])) | fields['location']
    groups = [[string(value) if value is not None else None] for value in
              (owner, fields['target_course_id'], station, fields['minimum_wait'])]
    groups.extend(([flags], [string(fields['maximum_wait']) if fields['maximum_wait'] is not None else None],
                   [string(fields['target_station_sign'] or station)], [fields['time_reference_type']],
                   [float(fields['dispatching_distance_km'])]))
    return connection(obj([('OTConnection', 6), ('NSObject', 0)], list(zip(LAYOUT, groups))))


def _read_exchange(content, args):
    if args.format == 'opentrack_text':
        need(not args.import_xml_actual and args.connection_attribute_order == 'require_unambiguous',
             'XML options only apply to proprietary XML input')
        parsed, _, version = parse_text(content)
        rows = {}
        for key, model in parsed.items():
            fields = model.model_dump(exclude={'connections'})
            fields['connections'] = [
                {
                    'target_course_id': spec.target_course_id, 'target_station_sign': spec.target_station_sign,
                    'minimum_wait': wait(spec.minimum_wait_s),
                    'maximum_wait': wait(spec.maximum_wait_s) if spec.maximum_wait_s is not None else 'HH:MM:SS',
                    'join': spec.join, 'split': spec.split, 'location': 4 if spec.entry_connection else 8 if spec.dispo_connection else 0,
                    'time_reference_type': spec.time_reference_type, 'dispatching_distance_km': spec.dispatching_distance_km,
                    'record_has_time_reference': version == 'opentrack_17',
                } for spec in model.connections
            ]
            rows[key] = fields
        return rows, version, []
    parsed, warnings = NativeXMLParser(args.connection_attribute_order).parse(content)
    need(parsed, 'No proprietary XML timetable rows to import')
    for row in parsed.values():
        row['dwell_s'] = float(row.pop('dwell') or '0')
        row['mean_delay_s'] = float(row.pop('mean_delay') or '0')
        need(0 <= row['dwell_s'] <= 86400 and 0 <= row['mean_delay_s'] <= 1000000, 'Negative or unbounded dwell or delay')
        for item in row['connections']:
            item['dispatching_distance_km'] = 0
            item['record_has_time_reference'] = True
    return parsed, 'opentrack_xml', warnings


def _replace_connections(row, previous, incoming, *, merge):
    station, owner = text(row, 5), text(row, 1)
    if not merge:
        set_sequence(row, 9, [_native_connection(owner, station, fields) for fields in incoming])
        return
    outgoing = [connection(item) for item in c.array(previous.contents[9].value)] if previous else []
    seen = set()
    for data in incoming:
        new = _native_connection(owner, station, data)
        key = (text(new, 1), text(new, 6))
        need(key not in seen, 'Duplicate incoming Connection merge identity')
        seen.add(key)
        matches = [index for index, item in enumerate(outgoing) if (text(item, 1), text(item, 6) or station) == key]
        need(len(matches) <= 1, 'Ambiguous native Connection merge identity')
        if not matches:
            outgoing.append(new)
            continue
        existing = outgoing[matches[0]]
        cf.put(new, 8, existing.contents[8].value)
        if not data['record_has_time_reference']:
            cf.put(new, 7, existing.contents[7].value)
        outgoing[matches[0]] = new
    set_sequence(row, 9, outgoing)


def _candidate_row(template, existing, cid, index, fields, version, args):
    station = fields['station_sign']
    if existing is not None and args.existing == 'merge':
        need(text(existing, 5) == station or not c.array(existing.contents[9].value),
             f'Merge cannot silently reassign existing Connections from {cid}#{index} to another station')
    row = cf.clone(existing if existing is not None and args.existing == 'merge' else template)
    cf.settext(row, 1, cid)
    cf.settext(row, 5, station)
    cf.put(row, 3, index)
    values = {key: value for key, value in fields.items()
              if key not in ('station_sign', 'course_id', 'connections') and not key.startswith('actual_')}
    if version == 'opentrack_16' and args.existing == 'merge' and existing is not None:
        values.pop('track_id')
        values.pop('delta_mass_t')
    apply_row_fields(row, values)
    if args.import_xml_actual:
        for key, slot in [('actual_arrival', 13), ('actual_departure', 14)]:
            cf.settext(row, slot, fields[key])
            row.contents[15].values[slot - 11] = fields[key + '_day_offset']
    elif args.existing != 'merge' or existing is None:
        cf.settext(row, 13, 'HH:MM:SS')
        cf.settext(row, 14, 'HH:MM:SS')
        row.contents[15].values[2:] = [0, 0]
    _replace_connections(row, existing, fields['connections'], merge=args.existing == 'merge')
    return row


def import_rows(plan, content, args):
    incoming, version, warnings = _read_exchange(content, args)
    courses = plan.courses()
    ids = dict.fromkeys(cid for cid, _ in incoming)
    missing = set(ids) - courses.keys()
    need(set(args.new_course_templates) == missing, 'Every new Course needs exactly one explicit existing Course template')
    template = plan.row(args.row_template.course_id, args.row_template.index)
    new_courses = []
    for cid in ids:
        if cid not in missing:
            continue
        donor = courses[args.new_course_templates[cid]]
        new = cf.clone(donor)
        cf.settext(new, 0, cid)
        new_courses.append(new)
    if new_courses:
        set_sequence(plan.catalog, 4, [*courses.values(), *new_courses])

    existing = plan.rows()
    counts = {cid: len(plan.course_rows(cid)) for cid in ids}
    need(args.existing != 'reject' or not any(counts.values()), 'Existing rows found; explicitly select replace or merge')
    output = dict(existing) if args.existing == 'merge' else {
        key: row for key, row in existing.items() if text(row, 1) not in ids
    }
    for (cid, index), fields in incoming.items():
        need(fields['station_sign'] in plan.stations, f'Unbound Station in {cid}#{index}')
        key = f'{cid}#{index}'
        previous = existing.get(key)
        output[key] = _candidate_row(template, previous, cid, index, fields, version, args)
    for cid in ids:
        family = [row for row in output.values() if text(row, 1) == cid]
        for row in family:
            if row is existing.get(row_key(row)):
                plan.exclusive(plan.table, row)
            cf.put(row, 4, len(family) - 1)
    before_counts = Counter((text(row, 1), text(row, 5)) for row in existing.values())
    after_counts = Counter((text(row, 1), text(row, 5)) for row in output.values())
    changes = [key for key in before_counts.keys() | after_counts.keys() if before_counts[key] != after_counts[key]]
    for cid, station in changes:
        if before_counts[cid, station] > 1:
            plan.require_unambiguous_visit(cid, station)
    dictionary_replace(plan.table, list(output.items()))
    for cid, station in changes:
        if after_counts[cid, station] > 1:
            plan.require_unambiguous_visit(cid, station)
    plan.changed_course_visits.update(ids)
    return {'format': version, 'existing_policy': args.existing, 'imported_rows': len(incoming),
            'imported_connections': sum(len(row['connections']) for row in incoming.values()),
            'courses_created': sorted(missing), 'xml_warnings': warnings[:200],
            'xml_warning_count': len(warnings), 'actual_results_imported': args.import_xml_actual}


class TimetableExchangeImporter(OperatingPlanEditTools):
    def import_timetable(self, args):
        state = self.load_operating_project(args)
        source = self.path(args.exchange.path)
        raw = self.secure_bytes(source)
        if len(raw) > MAX_EXCHANGE_BYTES or not raw or sha(raw) != args.exchange.sha256:
            raise APIError('TIMETABLE_EXCHANGE_SOURCE', 'Exchange data must be nonempty, up to 2 MB, and match the supplied SHA')
        try:
            content = raw.decode('utf-8-sig')
            changed, report = operating_candidate(state, args.source_project.run_file,
                                                  lambda plan: import_rows(plan, content, args))
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('TIMETABLE_EXCHANGE_INVALID', str(exc)[:700]) from exc
        state['inputs'][source] = raw
        report['exchange_source'] = args.exchange.model_dump()
        return self.publish_operating_increment(args, state, changed, report)


def tool_definitions(root):
    from .falko_timetable import tool_definitions as falko_definitions
    from .fbs_timetable import tool_definitions as fbs_definitions
    from .protim_pif_timetable import tool_definitions as protim_definitions
    from .simu_vii_timetable import tool_definitions as simu_definitions

    service = TimetableExchangeImporter(root)
    return [('opentrack_import_current_timetable_exchange',
             'Import original OpenTrack TSV (1.6/1.7) or proprietary XML to current native Timetable9/Course11. '
             'Checks exact stations, Course definitions or explicit templates, dependent connections and complete inventory. '
             'Can preview or publish fresh current native catalogs without using a legacy editor.',
             ImportTimetableExchange, service.import_timetable, False, False),
             *falko_definitions(root), *fbs_definitions(root), *protim_definitions(root), *simu_definitions(root)]

