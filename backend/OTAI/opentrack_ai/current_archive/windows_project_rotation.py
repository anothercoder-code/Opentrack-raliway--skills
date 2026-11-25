"""Rotate an ordered set of held native files through a same-volume recovery vault."""

from contextlib import ExitStack
from dataclasses import dataclass
import ntpath
import uuid

from ..errors import APIError
from .windows_publish import _check_blob, _parent
from .windows_scoped_replace import _file_identity, _ordinary, _read, _security, ensure


@dataclass(frozen=True)
class Parent:
    writer: object
    handle: int
    directory: object
    volume: int
    verify: object

    def path(self, name):
        return self.directory / name


def _parent_of(stack, root, path):
    writer, handle, _, native, volume, verify = stack.enter_context(_parent(root, path))
    return Parent(writer, handle, native.parent, volume, verify)


@dataclass
class Image:
    handle: int
    data: bytes
    identity: dict
    security: bytes


def _open_file(stack, parent, name, data=None, *, create=False, missing=False):
    writer = parent.writer
    handle = writer.open(name, parent.handle, remove=True, read_security=True,
                         create=create, writing=create, missing_ok=missing)
    if handle is None:
        return None
    stack.callback(writer.close, handle)
    try:
        if create:
            writer.write_bytes(handle, data)
        state = writer.api.snapshot(handle, parent.path(name), False, parent.volume)
        _ordinary(writer, handle, state)
        actual = _read(writer, handle)
        ensure(data is None or actual == data, 'Held project member bytes differ from reviewed input')
        return Image(handle, actual, _file_identity(state), _security(handle))
    except Exception:
        if create:
            writer.api.snapshot(handle, parent.path(name), False, parent.volume)
            writer.delete(handle)
        raise


def _hold_dependencies(stack, root, dependencies):
    for path, exact in (dependencies or {}).items():
        parent = _parent_of(stack, root, path)
        writer = parent.writer
        handle = writer.open(path.name, parent.handle)
        stack.callback(writer.close, handle)
        snapshot = writer.api.snapshot(handle, parent.path(path.name), False, parent.volume)
        if _read(writer, handle) != exact or writer.api.snapshot(
                handle, parent.path(path.name), False, parent.volume) != snapshot:
            raise APIError('SOURCE_CHANGED', 'A run-bound dependency changed before the native file switch',
                           path.relative_to(root).as_posix())


def _at(parent, name, image):
    writer = parent.writer
    state = writer.api.snapshot(image.handle, parent.path(name), False, parent.volume)
    _ordinary(writer, image.handle, state)
    ensure(_file_identity(state) == image.identity and _read(writer, image.handle) == image.data
           and _security(image.handle) == image.security, 'Held native image changed during the project operation')


def _move(image, source, old, destination, new):
    ensure(source.volume == destination.volume, 'Project and recovery vault must have one local NTFS volume')
    source.verify()
    destination.verify()
    _at(source, old, image)
    if source.directory == destination.directory:
        source.writer.rename(image.handle, source.handle, new)
    else:
        source.writer.rename_into(image.handle, destination.handle, destination.path(new))
    _at(destination, new, image)


@dataclass
class Row:
    parent: Parent
    target: str
    staged: str
    vault_name: str
    before: Image
    after: Image

    def binding(self):
        return {'stage': self.staged, 'vault_name': self.vault_name,
                'before_identity': self.before.identity, 'after_identity': self.after.identity}

    def restore(self, before_parent, after_parent):
        possible = ((self.parent, self.target), (self.parent, self.staged),
                    (before_parent, self.vault_name), (after_parent, self.vault_name))
        old = _location(self.parent.writer, self.before, possible)
        new = _location(self.parent.writer, self.after, possible)
        ensure(old in (possible[0], possible[2])
               and new in (possible[0], possible[1], possible[3]), 'Unexpected recovery-handle location')
        if new != possible[3]:
            _move(self.after, *new, after_parent, self.vault_name)
        if old != possible[0]:
            _move(self.before, *old, self.parent, self.target)
        _at(self.parent, self.target, self.before)
        _at(after_parent, self.vault_name, self.after)


def _location(writer, image, possible):
    actual = writer.api.name(image.handle)
    for parent, name in possible:
        expected = ntpath.normcase('\\\\?\\' + str(parent.path(name)))
        if actual == expected:
            return parent, name
    raise APIError('SCOPED_REPLACEMENT_REFUSED', 'A held file has an unexpected recovery location')


def _vault(stack, root, vault):
    return tuple(_parent_of(stack, root, vault / folder / 'marker') for folder in ('before-held', 'after-held'))


def _restore_rows(rows, before_parent, after_parent):
    errors = {}
    for row in reversed(rows):
        try:
            row.restore(before_parent, after_parent)
        except Exception as error:
            errors[row.parent.path(row.target).as_posix()] = str(error)[:300]
    return errors


def apply_images(root, entries, vault, *, authorize, journal, dependencies=None):
    """Retain all original and staging handles until the complete switch or compensation."""
    with ExitStack() as stack:
        _hold_dependencies(stack, root, dependencies)
        rows = []
        receipt = None
        try:
            for index, (path, before, after) in enumerate(entries):
                _check_blob(before)
                _check_blob(after)
                ensure(before and after and before != after, 'Each project member must have distinct nonempty images')
                parent = _parent_of(stack, root, path)
                original = _open_file(stack, parent, path.name, before)
                staged = f'.otai-project-{uuid.uuid4().hex}-staged'
                replacement = _open_file(stack, parent, staged, after, create=True)
                rows.append(Row(parent, path.name, staged, f'{index:04d}.native', original, replacement))
                ensure(original.security == replacement.security, 'Staging owner, group or access list differs from the original')
            authorize()
            receipt = journal([row.binding() for row in rows])
        except Exception as error:
            details = getattr(error, 'details', None)
            uncertain = isinstance(details, dict) and details.get('commit_attempted', False)
            committed = isinstance(details, dict) and details.get('commit_completed', False)
            if not (uncertain or committed):
                for row in reversed(rows):
                    _at(row.parent, row.staged, row.after)
                    row.parent.writer.delete(row.after.handle)
            raise

        try:
            before_parent, after_parent = _vault(stack, root, vault)
        except Exception as error:
            raise APIError('PROJECT_FILE_RECOVERY_REQUIRED', 'Journal retained before project switching',
                           {'journal': receipt, 'reason': str(error)[:300]}) from error
        try:
            authorize()
            for row in rows:
                _move(row.before, row.parent, row.target, before_parent, row.vault_name)
                _move(row.after, row.parent, row.staged, row.parent, row.target)
            authorize()
        except Exception as error:
            failures = _restore_rows(rows, before_parent, after_parent)
            code = 'PROJECT_FILE_RECOVERY_REQUIRED' if failures else 'PROJECT_FILE_APPLY_RESTORED'
            message = ('The completed members were restored; review the unresolved files'
                       if failures else 'The application stopped and all original files were restored')
            raise APIError(code, message,
                           {'journal': receipt, 'reason': str(error)[:300], 'unresolved': failures}) from error
        return receipt


def _recover_row(stack, root, entry, before_parent, after_parent):
    path, old_data, new_data, binding = entry
    parent = _parent_of(stack, root, path)
    staged, vault_name = binding['stage'], binding['vault_name']
    locations = [(parent, path.name), (parent, staged), (before_parent, vault_name), (after_parent, vault_name)]
    images = [_open_file(stack, place, name, missing=True) for place, name in locations]
    old = [image for image in (images[0], images[2]) if image is not None
           and image.identity == binding['before_identity'] and image.data == old_data]
    new = [image for image in (images[0], images[1], images[3]) if image is not None
           and image.identity == binding['after_identity'] and image.data == new_data]
    ensure(len(old) == len(new) == 1 and sum(image is not None for image in images) == 2,
           'Recovery cannot prove both owned identities and exact bytes at their reserved locations')
    return Row(parent, path.name, staged, vault_name, old[0], new[0])


def recover_images(root, entries, vault, *, authorize, dependencies=None):
    """Verify the entire closed set, then restore original identities in reverse order."""
    with ExitStack() as stack:
        _hold_dependencies(stack, root, dependencies)
        before_parent, after_parent = _vault(stack, root, vault)
        rows = [_recover_row(stack, root, entry, before_parent, after_parent) for entry in entries]
        authorize()
        failures = _restore_rows(rows, before_parent, after_parent)
        if failures:
            raise APIError('PROJECT_FILE_RECOVERY_REQUIRED', 'Retry only with the exact retained journal and owned files',
                           {'unresolved': failures})
        authorize()
