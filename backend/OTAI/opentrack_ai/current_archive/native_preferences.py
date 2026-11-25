"""Portable text accepted by the original Info > Preferences importer."""

import re

from . import runfile_parameters
from .prepare_contract import auxiliary
from .zero_operations.run_bundle import CATALOG_KEYS, root_path


SET_KEYS = {'Document Set Name', 'Document Set Document'}
DOCUMENT_KEYS = {'Infrastructure Document', 'Train Diagram Document'}
DAY_KEYS = rb'(Start|Stop|Break) Day Offset'
SET_NAME = r'[A-Za-z0-9][A-Za-z0-9 _-]{0,79}'
SCALAR_KEYS = {key.decode('ascii') for key in (*runfile_parameters.WRITABLE, *runfile_parameters.OPTIONS)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse(data):
    """Original exports use blank day-zero cells. Keep their meaning as zero."""
    require(type(data) is bytes and 0 < len(data) <= 1048576, 'Expected native Preferences text up to 1 MiB')
    zeroes = []

    def zero(match):
        key = match[1]
        zeroes.append(key.decode('ascii'))
        return key + b'#0#'

    normalized = re.sub(rb'(?m)^(' + DAY_KEYS + rb')##(?=\r?$)', zero, data)
    rows = auxiliary.records(normalized)
    return rows, zeroes


def document_sets(rows):
    declared = {value for key, value, _ in rows if key in DOCUMENT_KEYS}
    set_members = {value for key, value, _ in rows if key == 'Document Set Document'}
    return auxiliary.set_bindings(rows, declared | set_members)['groups']


def settings(rows):
    return {key: value for key, value, _ in rows if key in SCALAR_KEYS}


def inspect(data):
    rows, zeroes = parse(data)
    values = settings(rows)
    docs = [{'kind': key, 'path': value} for key, value, _ in rows if key in DOCUMENT_KEYS]
    declared = {item['path'].replace('\\', '/').casefold() for item in docs}
    sets = document_sets(rows)
    for group in sets:
        group['outside_declared_documents'] = [path for path in group['documents']
                                              if path.replace('\\', '/').casefold() not in declared]
    catalog_keys = {*CATALOG_KEYS.values(), 'OutputPath'}
    return {'scalar_preferences': values, 'catalog_and_output_paths': {key: value for key, value, _ in rows if key in catalog_keys},
            'documents': docs, 'document_sets': sets, 'native_blank_day_offsets': zeroes}


def transferable(data, fields):
    rows, _ = parse(data)
    source = settings(rows)
    require(len(fields) == len(set(fields)) and set(fields) <= source.keys(),
            'Each selected scalar preference must appear exactly once in the imported profile')
    return {key: source[key] for key in fields}


def declared_document_paths(rows):
    result = {}
    for key, value, _ in rows:
        if key not in DOCUMENT_KEYS:
            continue
        canonical = root_path(value, 'windows')
        require(canonical.casefold() not in result, 'Aliased native Preferences document path')
        result[canonical.casefold()] = (key, value)
    return result


def encode_sets(sets, rows, newline):
    declared = declared_document_paths(rows)
    seen = set()
    output = []
    for group in sets:
        name = group['name']
        require(isinstance(name, str) and re.fullmatch(SET_NAME, name) and name == name.strip()
                and name.casefold() not in seen, 'Use a distinct and output-safe native Document Set name')
        seen.add(name.casefold())
        output.append(f'Document Set Name#{name}#'.encode('ascii') + newline)
        members = [value.replace('\\', '/').casefold() for value in group['documents']]
        require(members and len(members) == len(set(members)) and set(members) <= declared.keys(),
                'Each Document Set needs distinct documents in the base profile declarations')
        for member in members:
            _, raw = declared[member]
            output.append(f'Document Set Document#{raw}#'.encode('ascii') + newline)
    return output


def edit(data, changes, sets):
    rows, zeroes = parse(data)
    saved_sets = document_sets(rows)
    before = settings(rows)
    scalar_source = b''.join(raw for key, _, raw in rows if key not in SET_KEYS)
    restricted = {key.encode('ascii'): value.encode('ascii') for key, value in changes.items()}
    scalar_output = runfile_parameters.edit_runfile(scalar_source, restricted)
    if sets is None:
        retained = iter(auxiliary.records(scalar_output))
        output = b''.join(raw if key in SET_KEYS else next(retained)[2] for key, _, raw in rows)
        output += b''.join(raw for _, _, raw in retained)
    else:
        newline = b'\r\n' if b'\r\n' in data else b'\n'
        new_sets = encode_sets(sets, rows, newline)
        heading = b'' if not new_sets or b'// Document Sets' in scalar_output else b'// Document Sets' + newline
        output = scalar_output + heading + b''.join(new_sets)
    fresh, _ = parse(output)
    require(settings(fresh) == before | changes, 'Native scalar preference readback differs')
    preserve = lambda records: [(key, value) for key, value, _ in records if key and key not in SCALAR_KEYS | SET_KEYS]
    require(preserve(fresh) == preserve(rows), 'Existing catalogs, documents, or incident bindings changed')
    groups = document_sets(fresh)
    if sets is None:
        require(groups == saved_sets, 'Unselected Document Sets changed')
    else:
        expected = [(group['name'], [value.replace('\\', '/').casefold() for value in group['documents']]) for group in sets]
        actual = [(group['name'], [value.replace('\\', '/').casefold() for value in group['documents']]) for group in groups]
        require(actual == expected, 'Native Document Set readback differs')
    return output, {'changes': {key: {'before': before.get(key), 'after': value} for key, value in changes.items()},
                    'document_sets': groups, 'normalized_day_zero_fields': zeroes,
                    'catalogs_documents_incidents_preserved': True, 'native_application_started': False}
