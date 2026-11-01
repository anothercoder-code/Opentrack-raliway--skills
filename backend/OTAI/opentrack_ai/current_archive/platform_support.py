"""Fail-closed diagnostics for existing descriptor-relative archive filesystem IO.

Capability reporting is not a platform certification or a publication approval.
There is deliberately no Path.read_bytes/open fallback on unsupported systems.
"""
import os
from ..errors import APIError

def filesystem_capabilities():
    if os.name=='nt':
        from .windows_io import availability
        from .windows_publish import availability as write_availability
        available,missing=availability()
        write_available,write_missing=write_availability()
        return {'os_name':os.name,'secure_read_available':available,
                'save_copy_primitives_available':available and write_available,'read_missing':missing,
                'write_missing':missing+write_missing,
                'native_windows_verified':False,'publication_approved':False,
                'reader_backend':'windows_x64_handle_relative_local_ntfs',
                'writer_backend':'windows_x64_handle_relative_ntfs_noreplace',
                'nested_project_publication_available':available and write_available,
                'complete_project_inventory_available':available,
                'directory_fd_operations_available':False,
                'scope':'Local NTFS secure_bytes reads, complete native-handle project inventory, fresh-copy saves and single/station-document nested project publication; per-path native checks apply. POSIX parent_fd and Linux incremental bundle publishers remain separate. Native runtime acceptance is project-specific.'}
    dirfd = getattr(os, 'supports_dir_fd', set())
    nofollow = getattr(os, 'supports_follow_symlinks', set())
    read_missing = []
    for flag in ('O_DIRECTORY', 'O_NOFOLLOW'):
        if not hasattr(os, flag):
            read_missing.append('os.'+flag)
    if os.open not in dirfd:
        read_missing.append('os.open(dir_fd)')
    
    
    
    if os.name != 'posix':
        read_missing.append('POSIX directory-descriptor implementation')
    write_missing = list(read_missing)
    for name in ('stat', 'unlink', 'link'):
        if getattr(os,name) not in dirfd:
            write_missing.append('os.'+name+'(dir_fd)')
    for name in ('stat', 'link'):
        if getattr(os,name) not in nofollow:
            write_missing.append('os.'+name+'(follow_symlinks=False)')
    return {'os_name':os.name,'secure_read_available':not read_missing,
            'save_copy_primitives_available':not write_missing,
            'read_missing':read_missing,'write_missing':write_missing,
            'native_windows_verified':False,'publication_approved':False,
            'reader_backend':'posix_directory_descriptors',
            'directory_fd_operations_available':not read_missing,
            'complete_project_inventory_available':not read_missing,
            'scope':'existing ArchiveTools descriptor IO only; no bundle publisher certification'}

def require_secure_filesystem(operation):
    if operation not in ('read','save_copy'):
        raise ValueError('Unknown filesystem capability operation')
    report = filesystem_capabilities()
    available = report['secure_read_available'] if operation=='read' else report['save_copy_primitives_available']
    if not available:
        raise APIError('UNSUPPORTED_SECURE_FILESYSTEM',
            'This platform lacks the existing secure archive '+operation+' implementation; no unsafe filesystem fallback is enabled.',
            {'operation':operation,**report})
    return report
