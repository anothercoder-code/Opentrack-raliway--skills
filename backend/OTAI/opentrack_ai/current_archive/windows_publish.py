"""Windows x64/local NTFS fresh-file and whole-directory publication.

All opens/creates are native, one component relative to retained directory
handles. No ordinary pathname IO, ACL mutation, replacement, or volume flush.
Members are FlushFileBuffers'd before an atomic no-replace rename. Windows does
not promise a POSIX directory-fsync equivalent here: power-loss directory-entry
durability is explicitly not certified. After rename, creation handles close and
the published objects are freshly opened, identity checked and actually read.

https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers
https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile
"""
import ctypes
from contextlib import contextmanager
import hashlib
import ntpath
from pathlib import Path, PureWindowsPath
import sys
import uuid

from ..errors import APIError
from . import windows_io as rd

DELETE = 0x00010000
FILE_LIST_DIRECTORY = 1
FILE_CREATE = 2
FILE_SHARE_WRITE = 2
FILE_ATTRIBUTE_DIRECTORY = 0x10
NOT_FOUND = {0xc0000034, 0xc000003a}


class FILE_RENAME_INFO(ctypes.Structure):
    _fields_ = [('ReplaceIfExists', ctypes.c_ubyte), ('RootDirectory', ctypes.c_void_p),
                ('FileNameLength', ctypes.c_uint32), ('FileName', ctypes.c_wchar * 1)]


def _error(code, message, **details):
    raise APIError(code, message, details or None)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


class _Writer:
    def __init__(self):
        self.api = rd._api()
        if FILE_RENAME_INFO.FileName.offset != 20 or ctypes.sizeof(FILE_RENAME_INFO) != 24:
            _error('UNSUPPORTED_SECURE_FILESYSTEM', 'Unexpected Windows rename ABI')
        self.write = self.api.kernel.WriteFile
        self.write.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        self.write.restype = ctypes.c_int
        self.flush = self.api.kernel.FlushFileBuffers
        self.flush.argtypes = [ctypes.c_void_p]
        self.flush.restype = ctypes.c_int
        self.seek = self.api.kernel.SetFilePointerEx
        self.seek.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint32]
        self.seek.restype = ctypes.c_int
        self.set_info = self.api.kernel.SetFileInformationByHandle
        self.set_info.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.set_info.restype = ctypes.c_int
        self.set_native = self.api.ntdll.NtSetInformationFile
        self.set_native.argtypes = [ctypes.c_void_p,ctypes.POINTER(rd.IO_STATUS_BLOCK),
                                   ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int]
        self.set_native.restype = ctypes.c_int32

    def open(self, name, parent=None, *, directory=False, create=False,
             remove=False, writing=False, listing=False, share=rd.FILE_SHARE_READ,
             missing_ok=False):
        if parent is not None:
            rd._component(name)
        encoded = name.encode('utf-16-le')
        if len(encoded) > 65532:
            _error('ARCHIVE_PATH', 'Native component exceeds UNICODE_STRING capacity')
        buffer = ctypes.create_unicode_buffer(name)
        unicode = rd.UNICODE_STRING(len(encoded), len(encoded)+2, ctypes.cast(buffer, ctypes.c_void_p))
        attrs = rd.OBJECT_ATTRIBUTES(ctypes.sizeof(rd.OBJECT_ATTRIBUTES), parent,
                                     ctypes.pointer(unicode), rd.OBJ_CASE_INSENSITIVE, None, None)
        desired = rd.FILE_READ_ATTRIBUTES | rd.SYNCHRONIZE
        desired |= (FILE_LIST_DIRECTORY if listing else 0) if directory else rd.FILE_READ_DATA
        if remove:
            desired |= DELETE
        if writing:
            desired |= 0x40000000  
        options = rd.FILE_OPEN_REPARSE_POINT | rd.FILE_SYNCHRONOUS_IO_NONALERT
        options |= rd.FILE_DIRECTORY_FILE if directory else rd.FILE_NON_DIRECTORY_FILE
        handle, ios = ctypes.c_void_p(), rd.IO_STATUS_BLOCK()
        status = self.api.create(ctypes.byref(handle), desired, ctypes.byref(attrs), ctypes.byref(ios),
                                 None, 0, share, FILE_CREATE if create else rd.FILE_OPEN,
                                 options, None, 0)
        if status != 0 or not handle.value or ios.StatusOrPointer or ios.Information != (2 if create else 1):
            if handle.value:
                self.close(handle.value)
            if missing_ok and status & 0xffffffff in NOT_FOUND:
                return None
            if status & 0xffffffff == 0xc0000035:
                _error('TARGET_EXISTS', 'Target exists; nothing was replaced')
            self.api.failure('NtCreateFile(publication)', self.api.status_error(status), status)
        return handle.value

    def close(self, handle):
        if handle is not None and not self.api.close(handle):
            _error('ARCHIVE_HANDLE_CLEANUP', 'Native publication handle could not close', winerror=ctypes.get_last_error())

    def close_all(self, handles):
        errors = []
        for handle in reversed(handles):
            try:
                self.close(handle)
            except Exception as error:
                errors.append(str(error))
        handles.clear()
        if errors:
            _error('ARCHIVE_HANDLE_CLEANUP', 'Some native publication handles could not close', errors=errors)

    def exists(self, parent, name):
        
        encoded = name.encode('utf-16-le'); buffer = ctypes.create_unicode_buffer(name)
        unicode = rd.UNICODE_STRING(len(encoded),len(encoded)+2,ctypes.cast(buffer,ctypes.c_void_p))
        attrs = rd.OBJECT_ATTRIBUTES(ctypes.sizeof(rd.OBJECT_ATTRIBUTES),parent,ctypes.pointer(unicode),rd.OBJ_CASE_INSENSITIVE,None,None)
        handle, ios = ctypes.c_void_p(), rd.IO_STATUS_BLOCK()
        status = self.api.create(ctypes.byref(handle),rd.FILE_READ_ATTRIBUTES|rd.SYNCHRONIZE,
                                 ctypes.byref(attrs),ctypes.byref(ios),None,0,7,rd.FILE_OPEN,
                                 rd.FILE_OPEN_REPARSE_POINT|rd.FILE_SYNCHRONOUS_IO_NONALERT,None,0)
        if handle.value:
            self.close(handle.value)
        if status == 0:
            return True
        if status & 0xffffffff in NOT_FOUND:
            return False
        if status & 0xffffffff == 0xc0000043:  
            return True
        self.api.failure('NtCreateFile(target existence)',self.api.status_error(status),status)

    def write_bytes(self, handle, output):
        offset = 0
        while offset < len(output):
            chunk = output[offset:offset+1024*1024]
            buffer, written = ctypes.create_string_buffer(chunk), ctypes.c_uint32()
            if not self.write(handle,buffer,len(chunk),ctypes.byref(written),None):
                self.api.failure('WriteFile')
            if not 0 < written.value <= len(chunk):
                _error('CURRENT_ARCHIVE_VERIFY', 'Native WriteFile did not make valid progress')
            offset += written.value
        if not self.flush(handle):
            self.api.failure('FlushFileBuffers')
        if not self.seek(handle,0,None,0):
            self.api.failure('SetFilePointerEx')
        if rd._read_chunks(self.api,handle,rd.MAX_ARCHIVE_BYTES) != output:
            _error('CURRENT_ARCHIVE_VERIFY', 'Flushed native staging bytes differ')

    def rename(self, handle, parent, name):
        rd._component(name)
        encoded = name.encode('utf-16-le')
        buffer = ctypes.create_string_buffer(max(ctypes.sizeof(FILE_RENAME_INFO),20+len(encoded)+2))
        value = FILE_RENAME_INFO.from_buffer(buffer)
        value.ReplaceIfExists = 0
        
        
        
        value.RootDirectory = None
        value.FileNameLength = len(encoded)
        ctypes.memmove(ctypes.addressof(buffer)+20,encoded,len(encoded))
        ios=rd.IO_STATUS_BLOCK()
        status=self.set_native(handle,ctypes.byref(ios),buffer,len(buffer),10)
        if status!=0 or ios.StatusOrPointer:
            error=self.api.status_error(status)
            if error in (80,183) or self.exists(parent,name):
                _error('TARGET_EXISTS', 'Target exists; atomic rename replaced nothing')
            self.api.failure('NtSetInformationFile(FileRenameInformation)',error,status)

    def delete(self, handle):
        value = ctypes.c_ubyte(1)
        if not self.set_info(handle,4,ctypes.byref(value),ctypes.sizeof(value)):
            self.api.failure('SetFileInformationByHandle(FileDispositionInfo)')

    def entries(self, handle):
        
        first, names = True, []
        while True:
            buffer = ctypes.create_string_buffer(65536)
            if not self.api.info(handle,11 if first else 10,buffer,len(buffer)):
                error = ctypes.get_last_error()
                if error == 18:  
                    return names
                self.api.failure('GetFileInformationByHandleEx(directory)',error)
            first, offset = False, 0
            while True:
                raw = buffer.raw
                next_offset = int.from_bytes(raw[offset:offset+4],'little')
                attrs = int.from_bytes(raw[offset+56:offset+60],'little')
                length = int.from_bytes(raw[offset+60:offset+64],'little')
                if length % 2 or length > 510 or offset+104+length > len(raw):
                    _error('CURRENT_ARCHIVE_VERIFY','Malformed native directory information')
                name = raw[offset+104:offset+104+length].decode('utf-16-le')
                if name not in ('.','..'):
                    rd._component(name)
                    if attrs & rd.FILE_ATTRIBUTE_REPARSE_POINT:
                        _error('ARCHIVE_REPARSE_POINT','Publication tree contains a reparse point')
                    names.append((name,bool(attrs & FILE_ATTRIBUTE_DIRECTORY)))
                    if len(names)>256:
                        _error('ARCHIVE_SIZE','Publication tree directory inventory exceeds bound')
                if not next_offset:
                    break
                if next_offset < 104+length or next_offset % 8 or offset+next_offset+104 > len(raw):
                    _error('CURRENT_ARCHIVE_VERIFY','Invalid native directory record chain')
                offset += next_offset


def availability():
    supported, missing = rd.availability()
    if not supported:
        return supported, missing
    try:
        _Writer()
    except (APIError,OSError,AttributeError) as error:
        return False, ['Windows native publication API/ABI: '+str(error)]
    return True, []


def _identity(state):
    return state[:2]


def _directory_anchor(state):
    
    
    return tuple(state[index] for index in (0,1,2,5,8,9,10,11,12))


@contextmanager
def _parent(root, target, transaction=None):
    root,target = rd.validate_scoped_path(root,target)
    writer,handles,states = _Writer(),[],[]
    try:
        drive=target.drive+'\\'
        if writer.api.drive_type(drive)!=rd.DRIVE_FIXED:
            _error('UNSUPPORTED_SECURE_FILESYSTEM','Publication requires a fixed local NTFS volume')
        handle=writer.open('\\??\\'+drive,directory=True,share=3)
        handles.append(handle);path=PureWindowsPath(drive)
        state=writer.api.snapshot(handle,path,True);volume=state[0]
        writer.api.check_volume(handle);states.append((handle,path,_directory_anchor(state)))
        for part in target.parts[1:-1]:
            handle=writer.open(part,handle,directory=True,share=3)
            handles.append(handle);path=path/part
            state=writer.api.snapshot(handle,path,True,volume)
            states.append((handle,path,_directory_anchor(state)))
        def verify():
            for handle,path,before in states:
                if _directory_anchor(writer.api.snapshot(handle,path,True,volume))!=before:
                    _error('SOURCE_CHANGED','A retained publication parent changed identity or path')
        verify()
        try:
            yield writer,handles[-1],target.name,target,volume,verify
            verify()
        except Exception as error:
            if transaction and transaction.get('committed') and getattr(error,'code',None) not in ('ARCHIVE_COMMITTED_POSTCHECK_FAILED','BUNDLE_COMMITTED_POSTCHECK_FAILED'):
                _postcommit(error,target.relative_to(root),transaction['expected'],transaction['bundle'])
            raise
    finally:
        try:
            writer.close_all(handles)
        except Exception as error:
            if transaction and transaction.get('committed'):
                _postcommit(error,target.relative_to(root),transaction['expected'],transaction['bundle'])
            raise


def _postcommit(error, target, expected, bundle):
    code='BUNDLE_COMMITTED_POSTCHECK_FAILED' if bundle else 'ARCHIVE_COMMITTED_POSTCHECK_FAILED'
    raise APIError(code,'A fresh target was committed but a later verification failed; inspect it and do not overwrite or claim rollback.',
                   {'commit_completed':True,'post_commit_verification':False,
                    'target_directory' if bundle else 'target_path':str(target),
                    'expected_members_sha256' if bundle else 'expected_sha256':expected,
                    'cause_code':getattr(error,'code',None),'reason':str(error)[:500]}) from error


def _check_blob(output):
    if type(output) is not bytes:
        _error('ARCHIVE_TYPE','Publication members must be exact bytes')
    if len(output)>rd.MAX_ARCHIVE_BYTES:
        _error('ARCHIVE_SIZE','A publication member exceeds 20 MiB')


def _rename_outcome(writer,handle,target,stage,bundle):
    """Resolve an interrupted/exceptional rename through the still-owned handle.

    Never delete a handle after an attempted rename unless its actual name is
    proven to remain the staging name. An indeterminate result is preserved.
    """
    try:
        actual=writer.api.name(handle)
    except Exception as error:
        raise APIError('PUBLICATION_COMMIT_OUTCOME_UNCERTAIN','Rename was attempted but its handle name cannot be verified; inspect target and staging without overwriting either.',
                       {'commit_completed':None,'commit_attempted':True,'target':str(target),'staging':str(stage),'bundle':bundle}) from error
    normalize=lambda value:ntpath.normcase('\\\\?\\'+str(value)).rstrip('\\')
    if actual==normalize(target):return True
    if actual==normalize(stage):return False
    _error('PUBLICATION_COMMIT_OUTCOME_UNCERTAIN','Rename handle has an unexpected name; neither target nor staging is removed',
           commit_completed=None,commit_attempted=True,target=str(target),staging=str(stage),bundle=bundle)


def save_copy(root,target,output,*,recheck,validate_output,scope_check=None):
    _check_blob(output);validate_output(output);recheck()
    if scope_check:scope_check()
    expected=_sha(output);committed=False
    transaction={'committed':False,'expected':expected,'bundle':False}
    with _parent(root,target,transaction) as (writer,parent,name,target,volume,verify_parent):
        relative=target.relative_to(PureWindowsPath(root))
        if writer.exists(parent,name):
            _error('TARGET_EXISTS','Target exists; nothing was overwritten')
        temporary='.opentrack-file-'+uuid.uuid4().hex
        handle=None;identity=None;attempted=False
        try:
            handle=writer.open(temporary,parent,create=True,writing=True,remove=True)
            identity=_identity(writer.api.snapshot(handle,target.parent/temporary,False,volume))
            writer.write_bytes(handle,output)
            recheck();verify_parent()
            if scope_check:scope_check()
            attempted=True;writer.rename(handle,parent,name);committed=True;transaction['committed']=True
            writer.close(handle);handle=None
            handle=writer.open(name,parent)
            state=writer.api.snapshot(handle,target,False,volume)
            if _identity(state)!=identity:
                _error('TARGET_CHANGED','Committed archive identity differs from staging')
            actual=rd._read_chunks(writer.api,handle,rd.MAX_ARCHIVE_BYTES)
            if actual!=output:
                _error('CURRENT_ARCHIVE_VERIFY','Committed archive bytes differ from expected')
            validate_output(actual);recheck()
            if scope_check:scope_check(Path(target))
            if writer.api.snapshot(handle,target,False,volume)!=state:
                _error('TARGET_CHANGED','Committed archive changed during postcheck')
            verify_parent();writer.close(handle);handle=None
        except Exception as error:
            if attempted and not committed:
                committed=_rename_outcome(writer,handle,target,target.parent/temporary,False)
                transaction['committed']=committed
            if committed:
                _postcommit(error,relative,expected,False)
            if handle is not None:
                try:
                    if _identity(writer.api.snapshot(handle,target.parent/temporary,False,volume))!=identity:
                        _error('TARGET_CHANGED','Owned staging archive identity changed')
                    writer.delete(handle)
                except Exception as cleanup_error:
                    raise APIError('ARCHIVE_PRECOMMIT_CLEANUP_FAILED','No final target was committed; owned staging cleanup failed',
                                   {'commit_completed':False,'temporary_name':temporary,'cause_code':getattr(error,'code',None),'cleanup_reason':str(cleanup_error)}) from error
            raise
        finally:
            writer.close(handle)
    return {'saved':True,'commit_completed':True,'target_path':str(relative),'source_unchanged':True,
            'atomic_no_replace':True,'post_commit_verified':True,'all_input_hashes_rechecked':True,
            'output_sha256':expected,'member_buffers_flushed':True,'directory_entry_power_loss_durability_verified':False}


def _member_plan(members,empty_directories):
    if not isinstance(members,dict) or not 1<=len(members)<=128:
        _error('ARCHIVE_SIZE','Project publication requires 1..128 exact member files')
    files,dirs,folded={},set(),set()
    for name,blob in members.items():
        _check_blob(blob)
        if not isinstance(name,str) or '\\' in name or any(part in ('','.','..') for part in name.split('/')):
            _error('ARCHIVE_PATH','Bundle member names must use plain relative slash-separated components')
        path=PureWindowsPath(name)
        if path.drive or path.root or len(path.parts)>8:
            _error('ARCHIVE_PATH','Bundle member path is not a bounded relative path')
        for part in path.parts:rd._component(part)
        normalized='/'.join(path.parts)
        if normalized.casefold() in folded:
            _error('ARCHIVE_PATH','Bundle member names collide case-insensitively')
        folded.add(normalized.casefold());files[normalized]=blob
        dirs.update('/'.join(path.parts[:i]) for i in range(1,len(path.parts)))
    empty=set()
    for name in empty_directories:
        if not isinstance(name,str) or '\\' in name or any(part in ('','.','..') for part in name.split('/')):
            _error('ARCHIVE_PATH','Empty directory path is not relative and unambiguous')
        path=PureWindowsPath(name)
        if path.drive or path.root or len(path.parts)>8:
            _error('ARCHIVE_PATH','Empty directory path is not bounded')
        for part in path.parts:rd._component(part)
        normalized='/'.join(path.parts);empty.add(normalized)
        dirs.update('/'.join(path.parts[:i]) for i in range(1,len(path.parts)+1))
    all_dirs={name.casefold() for name in dirs}
    if folded & all_dirs or len(all_dirs)!=len(dirs) or any(any(f.casefold().startswith(d.casefold()+'/') for f in files) for d in empty):
        _error('ARCHIVE_PATH','Bundle file/directory names overlap or collide')
    if sum(map(len,files.values()))>100*1024*1024 or len(dirs)>128:
        _error('ARCHIVE_SIZE','Bundle exceeds its bounded size or directory count')
    return files,dirs,empty


def _scan(writer,top,target,volume,files,dirs,identities,validate_bundle,after_validation=None):
    handles=[];snapshots=[];actual={};seen_files=set();seen_dirs=set()
    def walk(handle,prefix,path):
        state=writer.api.snapshot(handle,path,True,volume)
        if _identity(state)!=identities[prefix]:
            _error('TARGET_CHANGED','Published directory identity differs from staged directory',member=prefix)
        snapshots.append((handle,path,True,state))
        for name,directory in writer.entries(handle):
            key=prefix+'/'+name if prefix else name
            if directory:
                if key not in dirs:
                    _error('CURRENT_ARCHIVE_VERIFY','Unexpected directory in publication',member=key)
                seen_dirs.add(key)
                child=writer.open(name,handle,directory=True,listing=True)
                handles.append(child);walk(child,key,path/name)
            else:
                if key not in files:
                    _error('CURRENT_ARCHIVE_VERIFY','Unexpected file in publication',member=key)
                seen_files.add(key);child=writer.open(name,handle)
                handles.append(child);before=writer.api.snapshot(child,path/name,False,volume)
                if _identity(before)!=identities[key]:
                    _error('TARGET_CHANGED','Published file identity differs from staged member',member=key)
                value=rd._read_chunks(writer.api,child,rd.MAX_ARCHIVE_BYTES)
                if value!=files[key]:
                    _error('CURRENT_ARCHIVE_VERIFY','Published member bytes differ',member=key)
                actual[key]=value;snapshots.append((child,path/name,False,before))
    try:
        walk(top,'',target)
        if seen_files!=set(files) or seen_dirs!=dirs:
            _error('CURRENT_ARCHIVE_VERIFY','Publication inventory does not exactly match expected members')
        validate_bundle(actual)
        if after_validation:after_validation()
        for handle,path,directory,before in snapshots:
            if writer.api.snapshot(handle,path,directory,volume)!=before:
                _error('TARGET_CHANGED','Publication changed during readback',member=str(path))
        return actual
    finally:
        writer.close_all(handles)


def _cleanup_tree(writer,top,stage,volume,files,dirs,identities):
    
    
    opened={'':top};owned=[]
    try:
        for directory in sorted(dirs,key=lambda p:(p.count('/'),p)):
            parent,name=directory.rsplit('/',1) if '/' in directory else ('',directory)
            handle=writer.open(name,opened[parent],directory=True,listing=True,remove=True)
            owned.append(handle);opened[directory]=handle
            if _identity(writer.api.snapshot(handle,stage/directory,True,volume))!=identities[directory]:
                _error('TARGET_CHANGED','Cleanup refuses a replaced staging directory')
        for name in files:
            if name not in identities:continue
            parent,leaf=name.rsplit('/',1) if '/' in name else ('',name)
            handle=writer.open(leaf,opened[parent],remove=True)
            try:
                if _identity(writer.api.snapshot(handle,stage/name,False,volume))!=identities[name]:
                    _error('TARGET_CHANGED','Cleanup refuses a replaced staging member')
                writer.delete(handle)
            finally:writer.close(handle)
        for directory in sorted(dirs,key=lambda p:(p.count('/'),p),reverse=True):
            writer.delete(opened[directory]);writer.close(opened[directory]);owned.remove(opened[directory])
        if _identity(writer.api.snapshot(top,stage,True,volume))!=identities['']:
            _error('TARGET_CHANGED','Cleanup refuses replaced staging root')
        writer.delete(top)
    finally:writer.close_all(owned)


def publish_project(root,target_directory,members,*,recheck,validate_bundle,empty_directories=('output',),scope_check=None):
    files,dirs,empty=_member_plan(members,empty_directories)
    validate_bundle(dict(files));recheck()
    if scope_check:scope_check()
    hashes={name:_sha(blob) for name,blob in files.items()};committed=False
    transaction={'committed':False,'expected':hashes,'bundle':True}
    with _parent(root,target_directory,transaction) as (writer,parent,name,target,volume,verify_parent):
        relative=target.relative_to(PureWindowsPath(root))
        if writer.exists(parent,name):
            _error('TARGET_EXISTS','Target directory exists; nothing was overwritten')
        temporary='.opentrack-project-'+uuid.uuid4().hex;stage=target.parent/temporary
        top=None;directories={};child_handles=[];identities={};created_files=[];created_dirs=set();attempted=False
        try:
            top=writer.open(temporary,parent,directory=True,listing=True,create=True,remove=True)
            identities['']=_identity(writer.api.snapshot(top,stage,True,volume));directories['']=top
            for directory in sorted(dirs,key=lambda p:(p.count('/'),p)):
                prefix,leaf=directory.rsplit('/',1) if '/' in directory else ('',directory)
                handle=writer.open(leaf,directories[prefix],directory=True,listing=True,create=True,remove=True)
                child_handles.append(handle);directories[directory]=handle;created_dirs.add(directory)
                identities[directory]=_identity(writer.api.snapshot(handle,stage/directory,True,volume))
            for member,blob in files.items():
                prefix,leaf=member.rsplit('/',1) if '/' in member else ('',member)
                handle=writer.open(leaf,directories[prefix],create=True,writing=True,remove=True)
                try:
                    identities[member]=_identity(writer.api.snapshot(handle,stage/member,False,volume));created_files.append(member)
                    writer.write_bytes(handle,blob)
                finally:writer.close(handle)
            
            writer.close_all(child_handles)
            _scan(writer,top,stage,volume,files,dirs,identities,validate_bundle)
            recheck();verify_parent()
            if scope_check:scope_check()
            attempted=True;writer.rename(top,parent,name);committed=True;transaction['committed']=True
            writer.close(top);top=None
            top=writer.open(name,parent,directory=True,listing=True)
            def postcheck():
                recheck()
                if scope_check:scope_check(Path(target))
                verify_parent()
            _scan(writer,top,target,volume,files,dirs,identities,validate_bundle,postcheck)
            writer.close(top);top=None
        except Exception as error:
            if attempted and not committed:
                committed=_rename_outcome(writer,top,target,stage,True)
                transaction['committed']=committed
            if committed:
                _postcommit(error,relative,hashes,True)
            writer.close_all(child_handles)
            if top is not None:
                try:
                    _cleanup_tree(writer,top,stage,volume,created_files,created_dirs,identities)
                except Exception as cleanup_error:
                    raise APIError('BUNDLE_PRECOMMIT_CLEANUP_FAILED','No final target committed; staging cleanup refused or failed',
                                   {'commit_completed':False,'staging_directory':str(stage.relative_to(PureWindowsPath(root))),
                                    'cause_code':getattr(error,'code',None),'cleanup_reason':str(cleanup_error)}) from error
            raise
        finally:
            writer.close_all(child_handles);writer.close(top)
    return {'saved':True,'commit_completed':True,'target_directory':str(relative),'member_sha256':hashes,
            'empty_directories':sorted(empty),'atomic_no_replace':True,'post_commit_verified':True,
            'all_input_hashes_rechecked':True,'member_buffers_flushed':True,'directory_entry_power_loss_durability_verified':False}
