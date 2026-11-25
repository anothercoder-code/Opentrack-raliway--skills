"""Same-parent prepared replacement with no overwrite of an unheld name."""

import ctypes
import uuid

from ..errors import APIError
from . import windows_io
from .tools import sha
from .windows_publish import _check_blob, _parent, _rename_outcome


def ensure(condition, message):
    if not condition:
        raise APIError('SCOPED_REPLACEMENT_REFUSED', message)


def _file_identity(state):
    return {'volume': state[0], 'file_id': state[1].hex()}


def _read(writer, handle):
    if not writer.seek(handle, 0, None, 0):
        writer.api.failure('SetFilePointerEx(scoped read)')
    return windows_io._read_chunks(writer.api, handle, windows_io.MAX_ARCHIVE_BYTES)


def _security(handle):
    function = ctypes.WinDLL('advapi32', use_last_error=True).GetKernelObjectSecurity
    function.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    function.restype = ctypes.c_int
    size = ctypes.c_uint32()
    function(handle, 7, None, 0, ctypes.byref(size))
    ensure(0 < size.value <= 65536, 'Could not read the native file owner, group and DACL')
    buffer = ctypes.create_string_buffer(size.value)
    ensure(function(handle, 7, buffer, len(buffer), ctypes.byref(size)), 'Could not verify native file security')
    return buffer.raw[:size.value]


def _ordinary(writer, handle, state):
    ensure(not state[5] & ~(0x20 | 0x80), 'Scoped replacement requires ordinary archive file attributes')
    stream = ctypes.create_string_buffer(4096)
    if not writer.api.info(handle, 7, stream, len(stream)):
        writer.api.failure('GetFileInformationByHandleEx(FileStreamInfo)')
    next_entry = int.from_bytes(stream.raw[:4], 'little')
    name_length = int.from_bytes(stream.raw[4:8], 'little')
    simple_name = '::$DATA'.encode('utf-16-le')
    ensure(next_entry == 0 and name_length == len(simple_name) and stream.raw[24:24 + name_length] == simple_name,
           'Scoped replacement will not discard alternate native file streams')


def _where(writer, handle, old, new):
    return new if _rename_outcome(writer, handle, new, old, False) else old


def inspect_current(root, path):
    with _parent(root, path) as (writer, parent, name, target, volume, _):
        handle = writer.open(name, parent, missing_ok=True)
        if handle is None:
            return None
        try:
            snapshot = writer.api.snapshot(handle, target, False, volume)
            data = _read(writer, handle)
            ensure(writer.api.snapshot(handle, target, False, volume) == snapshot,
                   'The worksheet changed while reading its native file identity')
            return _file_identity(snapshot), sha(data)
        finally:
            writer.close(handle)


def retained_siblings(root, path, rotation):
    with _parent(root, path) as (writer, parent, _, _, _, _):
        return [rotation[key] for key in ('original_sibling', 'staged_sibling')
                if writer.exists(parent, rotation[key])]


def replace_verified(root, path, before, after, *, authorize, journal, expected_identity=None):
    """Switch an exact held file and return both identities. Journal runs before the first rename."""
    _check_blob(before)
    _check_blob(after)
    ensure(before != after and before and after, 'Supply two distinct nonempty archive images')
    token = uuid.uuid4().hex
    with _parent(root, path) as (writer, parent, name, target, volume, verify_parent):
        original = writer.open(name, parent, remove=True, read_security=True)
        stage = None
        temporary = target.parent / f'.otai-worksheet-{token}-staged'
        backup = target.parent / f'.otai-worksheet-{token}-original'
        old_location, new_location = target, temporary
        names_ambiguous = False
        try:
            original_snapshot = writer.api.snapshot(original, target, False, volume)
            original_id = _file_identity(original_snapshot)
            ensure(expected_identity is None or original_id == expected_identity, 'The current worksheet has a different native file identity')
            ensure(_read(writer, original) == before, 'The held worksheet differs from its reviewed raw bytes')
            _ordinary(writer, original, original_snapshot)
            stage = writer.open(temporary.name, parent, create=True, writing=True, remove=True, read_security=True)
            writer.write_bytes(stage, after)
            stage_snapshot = writer.api.snapshot(stage, temporary, False, volume)
            new_id = _file_identity(stage_snapshot)
            _ordinary(writer, stage, stage_snapshot)
            ensure(_security(original) == _security(stage), 'Staged file owner, group or access list differs from the original')
            rotation = {'original_identity': original_id, 'replacement_identity': new_id,
                        'original_sibling': backup.name, 'staged_sibling': temporary.name}
            receipt = journal(rotation)
            authorize()
            verify_parent()
            ensure(writer.api.snapshot(original, target, False, volume) == original_snapshot
                   and _read(writer, original) == before, 'The held worksheet changed before replacement')
            try:
                writer.rename(original, parent, backup.name)
                old_location = backup
                writer.rename(stage, parent, name)
                new_location = target
                final = writer.api.snapshot(stage, target, False, volume)
                ensure(_file_identity(final) == new_id and _read(writer, stage) == after,
                       'The installed native worksheet differs from its verified staged file')
                authorize()
                verify_parent()
            except Exception as failure:
                try:
                    old_location = _where(writer, original, target, backup)
                    new_location = _where(writer, stage, temporary, target)
                    if new_location == target:
                        writer.rename(stage, parent, temporary.name)
                        new_location = temporary
                    if old_location == backup:
                        writer.rename(original, parent, name)
                        old_location = target
                    ensure(_file_identity(writer.api.snapshot(original, target, False, volume)) == original_id
                           and _read(writer, original) == before, 'Restored worksheet did not match its original identity and bytes')
                except Exception as recovery:
                    names_ambiguous = True
                    raise APIError('SCOPED_REPLACEMENT_RECOVERY_REQUIRED', 'Retained recovery journal and sibling files after an interrupted replacement',
                                   {'worksheet': str(target), 'rotation': rotation, 'journal': receipt,
                                    'failure': str(failure)[:300], 'recovery_failure': str(recovery)[:300]}) from failure
                raise APIError('SCOPED_REPLACEMENT_RESTORED', 'Replacement aborted and the original file was restored',
                               {'journal': receipt, 'failure': str(failure)[:300]}) from failure
            try:
                writer.delete(original)
            except Exception as failure:
                raise APIError('SCOPED_REPLACEMENT_CLEANUP_REQUIRED', 'Replacement is installed and the original sibling requires reviewed cleanup',
                               {'journal': receipt, 'rotation': rotation}) from failure
            return {**rotation, 'journal': receipt, 'before_sha256': sha(before), 'after_sha256': sha(after),
                    'verified': True, 'same_path': True, 'atomic_single_rename_steps': True,
                    'namespace_gap_possible': True, 'directory_entry_power_loss_durability_verified': False}
        finally:
            try:
                if stage is not None and new_location == temporary and not names_ambiguous:
                    writer.api.snapshot(stage, temporary, False, volume)
                    writer.delete(stage)
            finally:
                writer.close_all([handle for handle in (original, stage) if handle is not None])


def recover_vacant_name(root, path, before, after, rotation, *, authorize):
    """Recover only a vacant target with the exact retained preimage and owned staging file."""
    with _parent(root, path) as (writer, parent, name, target, volume, verify_parent):
        ensure(not writer.exists(parent, name), 'Interrupted recovery requires a vacant target name')
        original = writer.open(rotation['original_sibling'], parent, remove=True)
        stage = None
        try:
            stage = writer.open(rotation['staged_sibling'], parent, remove=True, missing_ok=True)
            former = target.parent / rotation['original_sibling']
            state = writer.api.snapshot(original, former, False, volume)
            _ordinary(writer, original, state)
            ensure(_file_identity(state) == rotation['original_identity'] and _read(writer, original) == before,
                   'Retained original sibling differs from the journal')
            if stage is not None:
                staged = target.parent / rotation['staged_sibling']
                state = writer.api.snapshot(stage, staged, False, volume)
                _ordinary(writer, stage, state)
                ensure(_file_identity(state) == rotation['replacement_identity'] and _read(writer, stage) == after,
                       'Retained staging sibling differs from the journal')
            authorize()
            verify_parent()
            writer.rename(original, parent, name)
            state = writer.api.snapshot(original, target, False, volume)
            ensure(_file_identity(state) == rotation['original_identity'] and _read(writer, original) == before,
                   'Recovered worksheet does not match its reviewed original')
            if stage is not None:
                writer.delete(stage)
            return {'recovered': True, 'restored_sha256': sha(before), 'original_file_identity_preserved': True}
        finally:
            writer.close_all([handle for handle in (original, stage) if handle is not None])
