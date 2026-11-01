"""Read-only, handle-relative archive IO and inventories for Windows x64 / NTFS.

No pathname read fallback, ACL changes, privileged token, or publication lives
here. Every component is opened separately relative to its retained parent
handle, with FILE_OPEN_REPARSE_POINT, and every reparse tag is refused. Sharing
denies data writers and rename/delete access; it does not freeze attributes, so
identity, metadata and normalized handle paths are checked before/after reading.

Microsoft contracts (not a claim of universal Windows/filesystem certification):
https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew
https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_both_dir_info
"""
import ctypes
from contextlib import contextmanager
from functools import lru_cache
import ntpath
import os
from pathlib import PureWindowsPath
import re
import sys

from ..errors import APIError

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
FILE_READ_DATA = 0x0001
FILE_LIST_DIRECTORY = 0x0001
FILE_READ_ATTRIBUTES = 0x0080
SYNCHRONIZE = 0x00100000
FILE_SHARE_READ = 0x0001
FILE_OPEN = 1
FILE_DIRECTORY_FILE = 0x0001
FILE_SYNCHRONOUS_IO_NONALERT = 0x0020
FILE_NON_DIRECTORY_FILE = 0x0040
FILE_OPEN_REPARSE_POINT = 0x00200000
OBJ_CASE_INSENSITIVE = 0x0040
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
FILE_TYPE_DISK = 1
DRIVE_FIXED = 3


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [('Length', ctypes.c_uint16), ('MaximumLength', ctypes.c_uint16),
                ('Buffer', ctypes.c_void_p)]


class OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('Length', ctypes.c_uint32), ('RootDirectory', ctypes.c_void_p),
                ('ObjectName', ctypes.POINTER(UNICODE_STRING)), ('Attributes', ctypes.c_uint32),
                ('SecurityDescriptor', ctypes.c_void_p), ('SecurityQualityOfService', ctypes.c_void_p)]


class IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [('StatusOrPointer', ctypes.c_void_p), ('Information', ctypes.c_size_t)]


class FILE_BASIC_INFO(ctypes.Structure):
    _fields_ = [('CreationTime', ctypes.c_int64), ('LastAccessTime', ctypes.c_int64),
                ('LastWriteTime', ctypes.c_int64), ('ChangeTime', ctypes.c_int64),
                ('FileAttributes', ctypes.c_uint32)]


class FILE_STANDARD_INFO(ctypes.Structure):
    _fields_ = [('AllocationSize', ctypes.c_int64), ('EndOfFile', ctypes.c_int64),
                ('NumberOfLinks', ctypes.c_uint32), ('DeletePending', ctypes.c_ubyte),
                ('Directory', ctypes.c_ubyte)]


class FILE_ID_INFO(ctypes.Structure):
    _fields_ = [('VolumeSerialNumber', ctypes.c_uint64), ('FileId', ctypes.c_ubyte * 16)]


class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [('FileAttributes', ctypes.c_uint32), ('ReparseTag', ctypes.c_uint32)]


def _refuse(code, message, **details):
    raise APIError(code, message, details or None)


def _component(name):
    if (not name or name in ('.', '..') or name[-1:] in ('.', ' ')
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)):
        _refuse('ARCHIVE_PATH', 'Windows archive paths require unambiguous ordinary components')
    reserved = name.split('.')[0].upper()
    if reserved in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or re.fullmatch(r'(?:COM|LPT)[0-9¹²³]', reserved):
        _refuse('ARCHIVE_PATH', 'Windows device names are not archive path components')


def validate_scoped_path(root, path):
    """Lexical validation only: never resolve a reparse point before opening it."""
    root, path = PureWindowsPath(root), PureWindowsPath(path)
    if (not re.fullmatch(r'[A-Za-z]:', root.drive) or root.root != '\\'
            or path.drive.casefold() != root.drive.casefold() or path.root != '\\'):
        _refuse('ARCHIVE_PATH', 'Windows secure reads require a local drive-letter absolute data root')
    for part in (*root.parts[1:], *path.parts[1:]):
        _component(part)
    try:
        relative = path.relative_to(root)
    except ValueError:
        _refuse('PATH_OUTSIDE_SCOPE', 'Archive path is outside the configured data root')
    parts = relative.parts
    allowed = ((len(parts) >= 2 and parts[0].casefold() == 'otprojects') or
               (len(parts) >= 3 and tuple(p.casefold() for p in parts[:2]) == ('otai', 'workspaces')))
    if not allowed:
        _refuse('PATH_OUTSIDE_SCOPE', 'Archive path must remain below OTProjects or OTAI/workspaces')
    return root, path


class _API:
    def __init__(self):
        if sys.platform != 'win32' or os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8:
            _refuse('UNSUPPORTED_SECURE_FILESYSTEM', 'Windows archive reader requires native Windows x64')
        sizes = {UNICODE_STRING: 16, OBJECT_ATTRIBUTES: 48, IO_STATUS_BLOCK: 16,
                 FILE_BASIC_INFO: 40, FILE_STANDARD_INFO: 24, FILE_ID_INFO: 24,
                 FILE_ATTRIBUTE_TAG_INFO: 8}
        if any(ctypes.sizeof(kind) != size for kind, size in sizes.items()):
            _refuse('UNSUPPORTED_SECURE_FILESYSTEM', 'Unexpected Windows native ABI structure size')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.ntdll = ctypes.WinDLL('ntdll', use_last_error=True)
        self.create = self.ntdll.NtCreateFile
        self.create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32,
                                ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(IO_STATUS_BLOCK),
                                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                                ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        self.create.restype = ctypes.c_int32
        self.status_error = self.ntdll.RtlNtStatusToDosError
        self.status_error.argtypes = [ctypes.c_int32]
        self.status_error.restype = ctypes.c_uint32
        self.close = self.kernel.CloseHandle
        self.close.argtypes = [ctypes.c_void_p]
        self.close.restype = ctypes.c_int
        self.info = self.kernel.GetFileInformationByHandleEx
        self.info.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.info.restype = ctypes.c_int
        self.file_type = self.kernel.GetFileType
        self.file_type.argtypes = [ctypes.c_void_p]
        self.file_type.restype = ctypes.c_uint32
        self.final_path = self.kernel.GetFinalPathNameByHandleW
        self.final_path.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
        self.final_path.restype = ctypes.c_uint32
        self.volume = self.kernel.GetVolumeInformationByHandleW
        self.volume.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                               ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p, ctypes.c_uint32]
        self.volume.restype = ctypes.c_int
        self.drive_type = self.kernel.GetDriveTypeW
        self.drive_type.argtypes = [ctypes.c_wchar_p]
        self.drive_type.restype = ctypes.c_uint32
        self.read = self.kernel.ReadFile
        self.read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                             ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        self.read.restype = ctypes.c_int

    def failure(self, operation, error=None, status=None):
        error = ctypes.get_last_error() if error is None else error
        code = 'ARCHIVE_BUSY' if error in (32, 33) else 'ARCHIVE_IO_ERROR'
        _refuse(code, 'Windows secure archive operation failed; no fallback was used',
                operation=operation, winerror=int(error), **({'ntstatus':hex(status & 0xffffffff)} if status is not None else {}))

    def open(self, name, parent=None, directory=False, *, listing=False):
        
        
        
        
        if parent is not None:
            _component(name)
        encoded = name.encode('utf-16-le')
        if len(encoded) > 65532:
            _refuse('ARCHIVE_PATH', 'Windows component exceeds UNICODE_STRING capacity')
        buffer = ctypes.create_unicode_buffer(name)
        unicode = UNICODE_STRING(len(encoded), len(encoded)+2, ctypes.cast(buffer, ctypes.c_void_p))
        attrs = OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES), parent, ctypes.pointer(unicode),
                                  OBJ_CASE_INSENSITIVE, None, None)
        handle, status_block = ctypes.c_void_p(), IO_STATUS_BLOCK()
        
        
        
        rights = FILE_READ_ATTRIBUTES | SYNCHRONIZE
        rights |= (FILE_LIST_DIRECTORY if listing else 0) if directory else FILE_READ_DATA
        options = FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT | (FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE)
        status = self.create(ctypes.byref(handle), rights, ctypes.byref(attrs), ctypes.byref(status_block),
                             None, 0, FILE_SHARE_READ, FILE_OPEN, options, None, 0)
        if status != 0 or not handle.value or status_block.StatusOrPointer or status_block.Information != 1:
            if handle.value and not self.close(handle):
                _refuse('ARCHIVE_HANDLE_CLEANUP', 'A failed Windows archive open could not release its returned handle',
                        operation='CloseHandle', winerror=ctypes.get_last_error(), ntstatus=hex(status & 0xffffffff))
            self.failure('NtCreateFile', self.status_error(status), status)
        return handle.value

    def directory_entries(self, handle, maximum_entries):
        """Restart and exhaust FILE_ID_BOTH_DIR_INFO on the retained handle.

        Record names are length-delimited UTF-16, 8-byte chained, not NUL
        terminated. A fresh restart is used for each independent scan.
        """
        first, names, folded = True, [], set()
        while True:
            buffer = ctypes.create_string_buffer(65536)
            if not self.info(handle, 11 if first else 10, buffer, len(buffer)):
                error = ctypes.get_last_error()
                if error == 18:  
                    return sorted(names)
                self.failure('GetFileInformationByHandleEx(directory)', error)
            first, offset = False, 0
            raw = buffer.raw
            while True:
                if offset + 104 > len(raw):
                    _refuse('PROJECT_INVENTORY', 'Truncated native directory record')
                next_offset = int.from_bytes(raw[offset:offset+4], 'little')
                attrs = int.from_bytes(raw[offset+56:offset+60], 'little')
                length = int.from_bytes(raw[offset+60:offset+64], 'little')
                if not length or length % 2 or length > 510 or offset + 104 + length > len(raw):
                    _refuse('PROJECT_INVENTORY', 'Malformed native directory filename')
                try:
                    name = raw[offset+104:offset+104+length].decode('utf-16-le')
                except UnicodeDecodeError as error:
                    raise APIError('PROJECT_INVENTORY', 'Invalid UTF-16 directory filename') from error
                if name not in ('.', '..'):
                    _component(name)
                    if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
                        _refuse('ARCHIVE_REPARSE_POINT', 'Project inventory contains a reparse point')
                    if attrs & (0x40 | 0x1000 | 0x40000 | 0x400000):
                        _refuse('ARCHIVE_OFFLINE', 'Device, offline or recall-on-access inventory entry refused')
                    if name.casefold() in folded:
                        _refuse('PROJECT_INVENTORY', 'Case-insensitive directory member collision')
                    folded.add(name.casefold())
                    names.append((name, bool(attrs & 0x10)))
                    if len(names) > maximum_entries:
                        _refuse('PROJECT_INVENTORY', 'Directory entry count exceeds project inventory bound')
                if not next_offset:
                    break
                if (next_offset < 104 + length or next_offset % 8
                        or offset + next_offset + 104 > len(raw)):
                    _refuse('PROJECT_INVENTORY', 'Invalid native directory record chain')
                offset += next_offset

    def query(self, handle, info_class, kind):
        result = kind()
        if not self.info(handle, info_class, ctypes.byref(result), ctypes.sizeof(result)):
            self.failure('GetFileInformationByHandleEx')
        return result

    def name(self, handle, flags=0):
        buffer = ctypes.create_unicode_buffer(32768)
        count = self.final_path(handle, buffer, len(buffer), flags)
        if not count:
            self.failure('GetFinalPathNameByHandleW')
        if count >= len(buffer):
            _refuse('ARCHIVE_PATH', 'Normalized Windows handle path exceeds capacity')
        return ntpath.normcase(buffer.value).rstrip('\\')

    def snapshot(self, handle, expected, directory, volume_identity=None):
        if self.file_type(handle) != FILE_TYPE_DISK:
            _refuse('ARCHIVE_NOT_FILE', 'Archive must be a local disk file')
        basic = self.query(handle, 0, FILE_BASIC_INFO)
        standard = self.query(handle, 1, FILE_STANDARD_INFO)
        tag = self.query(handle, 9, FILE_ATTRIBUTE_TAG_INFO)
        identity = self.query(handle, 18, FILE_ID_INFO)
        if basic.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT or tag.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT or tag.ReparseTag:
            _refuse('ARCHIVE_REPARSE_POINT', 'Reparse points are refused at every archive path component')
        if basic.FileAttributes & (0x1000 | 0x40000 | 0x400000):
            _refuse('ARCHIVE_OFFLINE', 'Offline or recall-on-access archive components are refused')
        if bool(standard.Directory) != directory or standard.DeletePending:
            _refuse('ARCHIVE_NOT_FILE', 'Windows archive component has the wrong type or is pending deletion')
        if not directory and standard.NumberOfLinks != 1:
            _refuse('ARCHIVE_HARDLINK', 'Windows archive reads require a single-link regular file')
        actual = self.name(handle)
        if actual != ntpath.normcase('\\\\?\\' + str(expected)).rstrip('\\'):
            _refuse('PATH_OUTSIDE_SCOPE', 'Normalized Windows handle path differs from the authorized lexical path')
        if volume_identity is not None and identity.VolumeSerialNumber != volume_identity:
            _refuse('PATH_OUTSIDE_SCOPE', 'Archive component crossed the retained local volume')
        return (identity.VolumeSerialNumber, bytes(identity.FileId), basic.CreationTime,
                basic.LastWriteTime, basic.ChangeTime, basic.FileAttributes,
                standard.EndOfFile if not directory else 0, standard.NumberOfLinks if not directory else 0,
                bool(standard.DeletePending), bool(standard.Directory), tag.ReparseTag, actual,
                self.name(handle, 1))

    def check_volume(self, handle):
        fs = ctypes.create_unicode_buffer(261)
        if not self.volume(handle, None, 0, None, None, None, fs, len(fs)):
            self.failure('GetVolumeInformationByHandleW')
        if fs.value != 'NTFS':
            _refuse('UNSUPPORTED_SECURE_FILESYSTEM', 'Windows secure archive reads are limited to local NTFS', filesystem=fs.value)


@lru_cache(maxsize=1)
def _api():
    return _API()


def availability():
    if sys.platform != 'win32' or os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8:
        return False, ['native Windows x64 handle-relative reader']
    try:
        _api()
    except (APIError, OSError, AttributeError) as error:
        return False, ['required Windows native API/ABI: ' + str(error)]
    return True, []


def _read_chunks(api, handle, maximum):
    chunks, total = [], 0
    while True:
        size = min(1024 * 1024, maximum + 1 - total)
        buffer, received = ctypes.create_string_buffer(size), ctypes.c_uint32()
        if not api.read(handle, buffer, size, ctypes.byref(received), None):
            api.failure('ReadFile')
        if received.value > size:
            _refuse('ARCHIVE_IO_ERROR', 'Windows ReadFile returned an invalid byte count')
        if not received.value:
            return b''.join(chunks)
        total += received.value
        if total > maximum:
            _refuse('ARCHIVE_SIZE', 'Archive exceeds 20 MiB limit')
        chunks.append(buffer.raw[:received.value])


@contextmanager
def held_file(root, path, maximum=MAX_ARCHIVE_BYTES):
    """Internal native reader context; all handles close on every exception."""
    root, path = validate_scoped_path(root, path)
    api, handles, snapshots = _api(), [], []
    try:
        drive = path.drive + '\\'
        if api.drive_type(drive) != DRIVE_FIXED:
            _refuse('UNSUPPORTED_SECURE_FILESYSTEM', 'Windows archive reader supports fixed local NTFS drives only')
        parent = api.open('\\??\\' + drive, directory=True)
        handles.append(parent)
        current = PureWindowsPath(drive)
        state = api.snapshot(parent, current, True)
        api.check_volume(parent)
        snapshots.append((parent, current, True, state))
        volume = state[0]
        for index, part in enumerate(path.parts[1:]):
            
            
            for handle, expected, directory, before in snapshots:
                if api.snapshot(handle, expected, directory, volume) != before:
                    _refuse('SOURCE_CHANGED', 'A held archive path component changed during reading')
            directory = index < len(path.parts) - 2
            handle = api.open(part, parent, directory)
            handles.append(handle)
            current = current / part
            state = api.snapshot(handle, current, directory, volume)
            snapshots.append((handle, current, directory, state))
            parent = handle
        if snapshots[-1][2]:
            _refuse('ARCHIVE_NOT_FILE', 'Archive must be a regular file')
        if not 0 <= snapshots[-1][3][6] <= maximum:
            _refuse('ARCHIVE_SIZE', 'Archive exceeds 20 MiB limit')
        def verify():
            for handle, expected, directory, before in snapshots:
                if api.snapshot(handle, expected, directory, volume) != before:
                    _refuse('SOURCE_CHANGED', 'A held archive file or directory changed during reading')
        verify()
        yield api, handles[-1], snapshots[-1][3][6], verify
        verify()
    finally:
        primary_error = sys.exception()
        close_errors = []
        for handle in reversed(handles):
            try:
                if not api.close(handle):
                    close_errors.append({'winerror':ctypes.get_last_error()})
            except Exception as error:
                close_errors.append({'reason':str(error)[:200]})
        if close_errors:
            raise APIError('ARCHIVE_HANDLE_CLEANUP', 'Windows archive handles could not all be released; no successful read receipt is returned',
                           {'close_errors':close_errors,'cause_code':getattr(primary_error,'code',None)}) from primary_error


def secure_bytes(root, path, maximum=MAX_ARCHIVE_BYTES):
    with held_file(root, path, maximum) as (api, handle, expected_size, verify):
        blob = _read_chunks(api, handle, maximum)
        verify()
        if len(blob) != expected_size:
            _refuse('SOURCE_CHANGED', 'Archive size changed while its native handle was held')
        return blob


def inventory_names(root, directory, *, maximum_files=2000, maximum_depth=16,
                    maximum_total_bytes=256*1024*1024, maximum_directories=2000):
    """Return a complete bounded source tree inventory without pathname IO.

    All ancestors, directories and files remain held until a second complete
    directory enumeration and metadata/identity verification have succeeded.
    File bytes are not read here: callers must bind and read every returned
    member through secure_bytes, and repeat this inventory around that work.
    """
    limits = (maximum_files, maximum_depth, maximum_total_bytes, maximum_directories)
    if any(type(value) is not int or value < 1 for value in limits):
        _refuse('PROJECT_INVENTORY', 'Positive integer inventory limits required')
    if (maximum_files > 2000 or maximum_depth > 16
            or maximum_total_bytes > 256*1024*1024 or maximum_directories > 2000):
        _refuse('PROJECT_INVENTORY', 'Inventory limits exceed the supported bounded profile')
    root, directory = validate_scoped_path(root, directory)
    api, handles, snapshots, directories, files = _api(), [], [], [], []
    byte_count, directory_count = 0, 0
    try:
        drive = directory.drive + '\\'
        if api.drive_type(drive) != DRIVE_FIXED:
            _refuse('UNSUPPORTED_SECURE_FILESYSTEM', 'Project inventories require a fixed local NTFS drive')
        parent = api.open('\\??\\' + drive, directory=True)
        handles.append(parent)
        current = PureWindowsPath(drive)
        state = api.snapshot(parent, current, True)
        api.check_volume(parent)
        volume = state[0]
        snapshots.append((parent, current, True, state))

        def verify():
            for handle, expected, is_directory, before in snapshots:
                if api.snapshot(handle, expected, is_directory, volume) != before:
                    _refuse('SOURCE_CHANGED', 'A held project inventory component changed')

        for index, part in enumerate(directory.parts[1:]):
            verify()
            listing = index == len(directory.parts) - 2
            parent = api.open(part, parent, directory=True, listing=listing)
            handles.append(parent)
            current = current / part
            state = api.snapshot(parent, current, True, volume)
            snapshots.append((parent, current, True, state))

        def scan(handle, path, prefix, depth):
            nonlocal byte_count, directory_count
            if depth > maximum_depth:
                _refuse('PROJECT_INVENTORY', 'Directory nesting exceeds project inventory bound')
            entries = api.directory_entries(handle, maximum_files + maximum_directories)
            directories.append((handle, entries))
            for name, is_directory in entries:
                relative = prefix + name
                child = api.open(name, handle, directory=is_directory, listing=is_directory)
                handles.append(child)
                before = api.snapshot(child, path/name, is_directory, volume)
                snapshots.append((child, path/name, is_directory, before))
                if is_directory:
                    directory_count += 1
                    if directory_count > maximum_directories:
                        _refuse('PROJECT_INVENTORY', 'Directory count exceeds project inventory bound')
                    scan(child, path/name, relative+'/', depth+1)
                else:
                    files.append(relative)
                    if len(files) > maximum_files:
                        _refuse('PROJECT_INVENTORY', 'File count exceeds project inventory bound')
                    if not 0 <= before[6] <= MAX_ARCHIVE_BYTES:
                        _refuse('ARCHIVE_SIZE', 'An inventory member exceeds the 20 MiB archive limit')
                    byte_count += before[6]
                    if byte_count > maximum_total_bytes:
                        _refuse('PROJECT_SIZE', 'Complete project inventory exceeds its total byte bound')
        scan(parent, directory, '', 0)
        verify()
        for handle, entries in directories:
            if api.directory_entries(handle, maximum_files + maximum_directories) != entries:
                _refuse('PROJECT_INVENTORY_CHANGED', 'Directory membership changed during the complete inventory')
        verify()
        if len({name.casefold() for name in files}) != len(files):
            _refuse('PROJECT_INVENTORY', 'Case-insensitive complete inventory collision')
        return sorted(files)
    finally:
        primary_error = sys.exception()
        close_errors = []
        for handle in reversed(handles):
            try:
                if not api.close(handle):
                    close_errors.append({'winerror':ctypes.get_last_error()})
            except Exception as error:
                close_errors.append({'reason':str(error)[:200]})
        if close_errors:
            raise APIError('ARCHIVE_HANDLE_CLEANUP', 'Project inventory handles could not all be released; no complete inventory is returned',
                           {'close_errors':close_errors,'cause_code':getattr(primary_error,'code',None)}) from primary_error
