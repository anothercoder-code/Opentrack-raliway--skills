"""Native publication common to explicitly mapped timetable exchanges."""

from collections import defaultdict
from typing import Literal

from ..errors import APIError
from .bundle_tools import Source
from .graph_references import incoming_counts
from .multi_document_tools import Inventory
from .operating_plan_edit import apply_row_fields, need, text
from .operating_plan_edit_tools import OperatingPlanEditTools, operating_candidate
from .project_candidate_publication import ProjectSave
from .tools import sha


SECONDS_PER_DAY = 86400
UNDEFINED = 'HH:MM:SS'
SOURCE_LIMIT = 2_000_000


class BoundTimetableInput(ProjectSave):
    source_project: Inventory
    exchange: Source
    endpoint_clocks: Literal['preserve', 'mirror_for_run'] = 'preserve'


def clock(value):
    if value is None:
        return UNDEFINED, 0
    day, second = divmod(value, SECONDS_PER_DAY)
    return f'{second // 3600:02}:{second // 60 % 60:02}:{second % 60:02}', day


def clock_fields(arrival, departure):
    fields = {}
    for name, value in [('arrival', arrival), ('departure', departure)]:
        fields[name], fields[name + '_day_offset'] = clock(value)
    return fields


def grouped_native_rows(plan):
    by_course, by_visit = defaultdict(list), defaultdict(int)
    for row in plan.rows().values():
        owner, station = text(row, 1), text(row, 5)
        by_course[owner].append(row)
        by_visit[owner, station] += 1
    return by_course, by_visit


def bind_rows(plan, selection, parsed):
    need(selection.keys() <= parsed.keys() and set(selection.values()) <= plan.courses().keys(),
         'Every selected source service and native Course must already exist exactly once')
    return incoming_counts(plan.table)


def apply_bound_visit(row, references, course, station, index, source_line, fields, endpoint_policy, final_index):
    need(text(row, 5) == station and row.contents[3].value == index and references[id(row)] == 1,
         f'Source line {source_line} does not match native {course}#{index} station or row ownership')
    need(text(row, 2) in ('', '0', '-1', None), f'Mapped native {course}#{index} derives its clocks from an interval reference')
    report = {'row_index': index, 'station_sign': station}
    if endpoint_policy == 'mirror_for_run':
        pair = None
        if index == 0 and fields['arrival'] == UNDEFINED and fields['departure'] != UNDEFINED:
            pair = 'arrival', 'departure'
        elif index == final_index and fields['departure'] == UNDEFINED and fields['arrival'] != UNDEFINED:
            pair = 'departure', 'arrival'
        if pair:
            target, source = pair
            fields[target] = fields[source]
            fields[target + '_day_offset'] = fields[source + '_day_offset']
            report['mirrored_endpoint_clock'] = target
    apply_row_fields(row, fields)
    return {**report, **fields}


class BoundTimetableExchangeTools(OperatingPlanEditTools):
    def publish_exchange(self, args, parser, transform, error_code, label):
        state = self.load_operating_project(args)
        source = self.path(args.exchange.path)
        raw = self.secure_bytes(source)
        if sha(raw) != args.exchange.sha256:
            raise APIError('SOURCE_CHANGED', f'{label} input differs from its requested SHA-256')
        try:
            parsed = parser(raw)
            changed, report = operating_candidate(state, args.source_project.run_file,
                                                  lambda plan: transform(plan, *parsed, args))
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            raise APIError(error_code, str(exc)[:700]) from exc
        state['inputs'][source] = raw
        return self.publish_operating_increment(args, state, changed, {**report, 'exchange_source': args.exchange.model_dump()})
