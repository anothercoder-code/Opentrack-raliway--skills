"""Typed, filesystem-free original timetable text <-> JSON conversion."""
import hashlib
import json
from typing import Literal
from pydantic import Field, model_validator
from .errors import APIError
from .models import Input, NewCourseId, TimetableStop
from .timetable_text_core import parse_text, render

MAX_BYTES = 2_000_000


class ExchangeRow(TimetableStop):
    course_id: NewCourseId
    index: int = Field(ge=0, strict=True)


class ExchangeDocument(Input):
    schema_version: Literal['otai.timetable-text.v1'] = 'otai.timetable-text.v1'
    format: Literal['opentrack_17', 'opentrack_16'] = 'opentrack_17'
    rows: list[ExchangeRow] = Field(min_length=1, max_length=10000)
    source_text: str | None = Field(default=None, max_length=MAX_BYTES)

    @model_validator(mode='after')
    def unique(self):
        ids = [(r.course_id, r.index) for r in self.rows]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate Course/stationIndex record.')
        if sum(len(r.connections) for r in self.rows) > 10000:
            raise ValueError('At most 10000 connections.')
        return self


class DecodeTimetableText(Input):
    content: str = Field(max_length=MAX_BYTES)
    preserve_source: bool = True


class EncodeTimetableText(Input):
    document: ExchangeDocument
    format: Literal['opentrack_17', 'opentrack_16'] | None = None
    preserve_source: bool = True


def _rows(content):
    rows, _, version = parse_text(content)
    return [ExchangeRow(course_id=cid, index=index, **stop.model_dump())
            for (cid, index), stop in rows.items()], version


def _warnings(content):
    """Legacy importer ignores bits 4/8; never hide that semantic loss."""
    warnings = []
    in_connections = False
    import re
    for n, line in enumerate(content.splitlines(), 1):
        if re.match(r'^//\s*Connections\b', line.lstrip(), re.I):
            in_connections = True
        if in_connections and line.strip() and not line.lstrip().startswith('//'):
            bits = int(line.split('\t')[-1]) & 12
            if bits:
                warnings.append({'line': n, 'omitted': ['ignored_connection_bits_4_8'], 'value': bits})
    return warnings


def decode_timetable_text(args):
    if not isinstance(args, DecodeTimetableText):
        args = DecodeTimetableText.model_validate(args)
    rows, version = _rows(args.content)
    doc = ExchangeDocument(format=version, rows=rows,
                           source_text=args.content if args.preserve_source else None)
    return {'document': doc.model_dump(mode='json'),
            'representability_warnings': _warnings(args.content),
            'native_application_started': False}


def _clock(value):
    return 'HH:MM:SS' if value is None else f'{value//3600:02}:{value//60%60:02}:{value%60:02}'


def _catalog_row(row):
    data = row.model_dump()
    data.update(key=f'{row.course_id}#{row.index}',
                arrival=row.arrival or 'HH:MM:SS', departure=row.departure or 'HH:MM:SS',
                actual_arrival='HH:MM:SS', actual_departure='HH:MM:SS',
                interval_reference_course_id=row.interval_reference_course_id or '0')
    for c in data['connections']:
        c.update(target_station_sign=c['target_station_sign'] or '',
                 minimum_wait=_clock(c.pop('minimum_wait_s')),
                 maximum_wait=_clock(c.pop('maximum_wait_s')))
    return data


def encode_timetable_text(args):
    if not isinstance(args, EncodeTimetableText):
        args = EncodeTimetableText.model_validate(args)
    doc = args.document
    version = args.format or doc.format
    content, warnings = render([_catalog_row(r) for r in doc.rows], version)
    source_preserved = False
    if args.preserve_source and doc.source_text is not None:
        source_rows, source_version = _rows(doc.source_text)
        if source_version == version and source_rows == doc.rows:
            content = doc.source_text
            warnings = _warnings(content)
            source_preserved = True
        else:
            warnings.append({'omitted': ['source_comments_whitespace_numeric_spelling'],
                             'reason': 'Edited data or changed output format uses the canonical original-column writer.'})
            warnings.extend(_warnings(doc.source_text))
    raw = content.encode('utf-8')  
    if len(raw) > MAX_BYTES:
        raise APIError('TIMETABLE_EXCHANGE_SIZE', 'Rendered exchange exceeds 2 MB.')
    
    parse_text(content)
    return {'content': content, 'format': version, 'sha256': hashlib.sha256(raw).hexdigest(),
            'byte_count': len(raw), 'source_preserved': source_preserved,
            'representability_warnings': warnings, 'native_application_started': False}


def tool_definitions():
    return [
        {'name': 'opentrack_decode_timetable_text', 'description': 'Parse original 16/8 or legacy 14/7 timetable TSV into typed editable JSON; no archive/native execution.', 'inputSchema': DecodeTimetableText.model_json_schema()},
        {'name': 'opentrack_encode_timetable_text', 'description': 'Generate original timetable TSV from typed editable JSON with explicit loss warnings; no archive/native execution.', 'inputSchema': EncodeTimetableText.model_json_schema()},
    ]


def dispatch(name, arguments):
    handlers = {'opentrack_decode_timetable_text': decode_timetable_text,
                'opentrack_encode_timetable_text': encode_timetable_text}
    if name not in handlers:
        raise APIError('UNKNOWN_TOOL', 'Unknown pure timetable text tool.', name)
    return handlers[name](arguments)


def registry_definitions():
    """Existing Registry tuple shape; handlers require no Service/project."""
    definitions = tool_definitions()
    return [
        (definitions[0]['name'], definitions[0]['description'], DecodeTimetableText, decode_timetable_text),
        (definitions[1]['name'], definitions[1]['description'], EncodeTimetableText, encode_timetable_text),
    ]
