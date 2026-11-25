"""Render the original RailML 1.00 timetable format from selected saved rows."""

from collections import defaultdict
from xml.sax.saxutils import quoteattr

from .errors import APIError
from .models import RailMLTimetableOptions
from .railml_timetable_v100 import ENTRY_CLOCKS, HEADER, MAX_BYTES, MAX_ROWS, XSI, clock, duration, legacy_tree, train_index, wait_seconds


# Stock 1.7 0x546250 uses this date-only literal for the OTT menu without a date.
OTT_DEFAULT_OPERATING_DATE = '2007-01-01'


def element(indent, tag, values=None, close=False):
    attrs = ''.join(' '+key+'='+quoteattr(str(value)) for key, value in (values or {}).items())
    return '\t'*indent + '<' + tag + attrs + ('/>' if close else '>')


def station_label(value, options):
    if options is None:
        return value
    if options.uppercase:
        if not value.isascii():
            raise ValueError('Legacy uppercase station rule requires ASCII identity')
        value = value.upper()
    if len(value) >= options.replace_first:
        value = options.first_string + value[options.replace_first:]
    if len(value) >= options.replace_last:
        value = value[:len(value)-options.replace_last] + options.last_string
    return value.rstrip(' ') or value[:1]


def render_legacy_railml(rows, services, stations, args, *, ott=False):
    options = args.railml or RailMLTimetableOptions()
    calculated_date = options.metadata_date
    if ott:
        calculated_date = calculated_date.rstrip(' ') if calculated_date else OTT_DEFAULT_OPERATING_DATE
    warnings, selected, skipped = [], {}, []
    groups = defaultdict(list)
    for row in rows:
        groups[row['course_id']].append(row)
    if len(rows) > MAX_ROWS or sum(len(row['connections']) for row in rows) > MAX_ROWS:
        raise APIError('TIMETABLE_RAILML_100_SIZE', 'Legacy timetable export exceeds the row or connection scope')
    for cid, data in groups.items():
        if any(row['index'] != i or row['last_index'] != len(data)-1 for i, row in enumerate(data)):
            raise APIError('TIMETABLE_RAILML_100_INDEX', 'Legacy export requires complete contiguous saved rows', cid)
        if options.only_active and not services.get(cid, {}).get('enabled', False):
            skipped.append({'course_id': cid, 'reason': 'inactive_or_missing_definition'})
            continue
        included = [row for row in data if not options.existing_stations_only or row['station_sign'] in stations]
        if included:
            selected[cid] = included
        else:
            skipped.append({'course_id': cid, 'reason': 'no_existing_station'})
        if len(included) != len(data):
            warnings.append({'kind': 'NATIVE_EXISTING_STATION_FILTER_REMOVED_ROWS', 'course_id': cid,
                             'removed': len(data)-len(included)})

    lines = [f'<railml xmlns:xsi="{XSI}" xsi:noNamespaceSchemaLocation="timetable.xsd">',
             element(1, 'timetable', {'version': '1.00'})]
    emitted = {'planned_trains': 0, 'calculated_trains': 0, 'entry_count': 0, 'connections': 0}
    planned = options.planned or options.published or not options.calculated
    calculated = options.calculated and args.saved_actual == 'as_valid'
    if options.calculated and not calculated:
        warnings.append({'kind': 'NATIVE_ACTUAL_VALIDITY_UNAVAILABLE', 'scope': 'calculated'})
    if options.published:
        warnings.append({'kind': 'PUBLISHED_REUSES_SAVED_PLANNED_CLOCKS'})
    if calculated:
        warnings.append({'kind': 'SAVED_ACTUAL_STRINGS_ASSUMED_VALID'})
    if options.dataset_name is not None:
        warnings.append({'kind': 'NATIVE_RAILML_100_DATASET_NAME_UNREPRESENTED'})

    def train(cid, items, scope):
        course = services.get(cid, {})
        if not course:
            warnings.append({'kind': 'MISSING_COURSE_DEFINITION', 'course_id': cid})
        attrs = {'trainID': cid}
        interval = items[0]['interval_reference_course_id']
        if interval not in (None, '', '0', '-1'):
            attrs['intervalGroupID'] = interval
        for field, name in (('course_type', 'kind'), ('train_number', 'trainNumber'), ('comment', 'remarks'),
                            ('description', 'description')):
            if course.get(field):
                attrs[name] = course[field]
        attrs.update(type=scope, dataSource='opentrack')
        if scope == 'calculated' and calculated_date:
            attrs['dataDateTime'] = calculated_date
        lines.append(element(2, 'train', attrs))
        lines.append(element(3, 'timetableentries'))
        emitted[scope+'_trains'] += 1
        for index, row in enumerate(items):
            position = station_label(row['station_sign'], options.station_filter)
            entry = {'posID': position}
            if scope == 'planned' and row['track_id']:
                entry.update(trackID=row['track_id'], trackInfo=row['track_id'])
            for kind in ENTRY_CLOCKS:
                field = ('actual_' if scope == 'calculated' else '') + kind
                value, day = row[field], row[field+'_day_offset']
                if value not in (None, '', 'HH:MM:SS'):
                    entry[kind] = value+'.0'
                    if scope == 'planned' and options.published:
                        entry['published'+kind.title()] = value+'.0'
                    if day:
                        entry[kind+'Day'] = str(day)
                elif day:
                    warnings.append({'kind': 'UNDEFINED_CLOCK_DAY_OMITTED', 'key': row['key'], 'clock': field})
                clock(entry, kind, scope='scheduled')
            if scope == 'planned':
                for source, key in (('dwell_raw', 'minStopTime'), ('mean_delay_raw', 'meanDelayDeparture')):
                    value = row[source] or '0'
                    amount = duration('PT'+value+'S', key)
                    if amount:
                        entry[key] = 'PT'+value+'S'
            entry['type'] = 'stop' if row['stop_at_station'] else 'pass'
            lines.append(element(4, 'entry', entry))
            emitted['entry_count'] += 1
            if index == 0 and course.get('train'):
                lines.append(element(5, 'composition', {'compID': course['train']}, close=True))
            if scope == 'planned':
                for conn in row['connections']:
                    target = conn['target_course_id']
                    if options.only_active and not services.get(target, {}).get('enabled', False):
                        warnings.append({'kind': 'NATIVE_INACTIVE_CONNECTION_OMITTED', 'key': row['key'], 'target': target})
                        continue
                    minimum, maximum = [wait_seconds(conn[key]) for key in ('minimum_wait', 'maximum_wait')]
                    cattrs = {'trainID': target, 'minConnTime': f'PT{max(0, minimum)}S'}
                    if maximum > 0:
                        cattrs['maxConnTime'] = f'PT{maximum}S'
                    cattrs['connOperation'] = ('none', 'join', 'split', 'meet')[int(conn['join'])+2*int(conn['split'])]
                    lines.append(element(5, 'connection', cattrs, close=True))
                    emitted['connections'] += 1
                    warnings.append({'kind': 'LEGACY_CONNECTION_AUXILIARY_FIELDS_NOT_REPRESENTED', 'key': row['key'],
                                     'target': target})
            lines.append(element(4, '/entry'))
        lines.extend((element(3, '/timetableentries'), element(2, '/train')))

    for cid, items in selected.items():
        if planned:
            train(cid, items, 'planned')
    if calculated:
        for cid, items in selected.items():
            known = [row for row in items if any(row['actual_'+key] not in (None, '', 'HH:MM:SS') for key in ENTRY_CLOCKS)]
            if known:
                train(cid, known, 'calculated')
    lines.extend((element(1, '/timetable'), '</railml>'))
    content = HEADER+'\n'.join(lines)+'\n'
    payload = content.encode('utf-8')
    if len(payload) > MAX_BYTES:
        raise APIError('TIMETABLE_RAILML_100_SIZE', 'Legacy timetable XML exceeds 2 MB')
    document, _ = legacy_tree(payload)
    if len(document):
        train_index(document)
    warnings.append({'kind': 'NATIVE_RAILML_100_OMISSIONS', 'fields': [
        'Course routes/itineraries, prepared vehicle properties and interval offsets',
        'Timing-station flag, distribution name, load changes and actual validity',
    ]})
    return content, warnings, {**emitted, 'rows': emitted['entry_count'], 'courses': len(selected),
                               'skipped_courses': skipped, 'railml_options': options.model_dump(),
                               'saved_actual': args.saved_actual, 'native_actual_validity_verified': False,
                               'xsd_validation_performed': False, 'external_resources_resolved': False}
