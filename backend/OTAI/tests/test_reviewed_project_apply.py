"""Native project rotation proof on disposable Windows project members."""

import json

import pytest

from opentrack_ai.current_archive import windows_project_rotation as rotation
from opentrack_ai.current_archive.reviewed_project_apply import ApplyReviewedProjectFiles
from opentrack_ai.current_archive.windows_publish import availability
from opentrack_ai.current_archive.windows_scoped_replace import inspect_current
from opentrack_ai.errors import APIError


@pytest.fixture
def images(tmp_path):
    if not availability()[0]:
        pytest.skip('Windows native NTFS publisher required')
    root = tmp_path
    project = root / 'OTProjects/Example'
    vault = root / 'OTAI/workspaces/Recovery'
    entries = []
    for member in ('OTData/example.courses', 'OTDocuments/Main.opentrack'):
        target = project / member
        target.parent.mkdir(parents=True, exist_ok=True)
        before, after = ('before ' + member).encode(), ('after ' + member).encode()
        target.write_bytes(before)
        entries.append((target, before, after))

    def journal(rows):
        assert all(target in target.parent.iterdir() for target, _, _ in entries)
        (vault / 'before-held').mkdir(parents=True)
        (vault / 'after-held').mkdir()
        (vault / 'transaction.json').write_text(json.dumps(rows), encoding='utf8')
        return 'sealed-test-journal'

    return root, entries, vault, journal


def bindings(vault, entries):
    rows = json.loads((vault / 'transaction.json').read_text(encoding='utf8'))
    return [(*entry, row) for entry, row in zip(entries, rows, strict=True)]


def test_apply_then_restore_complete_project_original_identities(images):
    root, entries, vault, journal = images
    originals = [inspect_current(root, target) for target, _, _ in entries]
    assert rotation.apply_images(root, entries, vault, authorize=lambda: None, journal=journal) == 'sealed-test-journal'
    approved = bindings(vault, entries)
    assert [target.read_bytes() for target, _, _ in entries] == [after for _, _, after in entries]
    for index, (target, *_data, binding) in enumerate(approved):
        assert inspect_current(root, target)[0] == binding['after_identity']
        assert inspect_current(root, vault / 'before-held' / binding['vault_name']) == originals[index]
        assert not target.with_name(binding['stage']).exists()
    rotation.recover_images(root, approved, vault, authorize=lambda: None)
    rotation.recover_images(root, approved, vault, authorize=lambda: None)
    assert [inspect_current(root, target) for target, _, _ in entries] == originals


def test_midway_failure_reverse_compensates_all_installed_members(images, monkeypatch):
    root, entries, vault, journal = images
    move = rotation._move
    originals = [inspect_current(root, target) for target, _, _ in entries]

    def fail_on_second_install(image, source, old, destination, new):
        if old.endswith('-staged') and new == entries[1][0].name:
            raise OSError('simulated midway installation failure')
        return move(image, source, old, destination, new)

    monkeypatch.setattr(rotation, '_move', fail_on_second_install)
    with pytest.raises(APIError) as raised:
        rotation.apply_images(root, entries, vault, authorize=lambda: None, journal=journal)
    assert raised.value.code == 'PROJECT_FILE_APPLY_RESTORED'
    assert [inspect_current(root, target) for target, _, _ in entries] == originals
    rotation.recover_images(root, bindings(vault, entries), vault, authorize=lambda: None)


def test_restart_recovers_a_committed_and_a_vacant_member_together(images, monkeypatch):
    root, entries, vault, journal = images
    move = rotation._move
    originals = [inspect_current(root, target) for target, _, _ in entries]

    def exit_before_second_install(image, source, old, destination, new):
        if old.endswith('-staged') and new == entries[1][0].name:
            raise SystemExit(79)
        return move(image, source, old, destination, new)

    monkeypatch.setattr(rotation, '_move', exit_before_second_install)
    with pytest.raises(SystemExit):
        rotation.apply_images(root, entries, vault, authorize=lambda: None, journal=journal)
    assert entries[0][0].read_bytes() == entries[0][2]
    assert not entries[1][0].exists()
    rotation.recover_images(root, bindings(vault, entries), vault, authorize=lambda: None)
    assert [inspect_current(root, target) for target, _, _ in entries] == originals


def test_competing_occupant_preserved_and_recovery_checks_entire_set(images, monkeypatch):
    root, entries, vault, journal = images
    move = rotation._move
    original = inspect_current(root, entries[0][0])
    conflicting = entries[1][0]

    def add_occupant(image, source, old, destination, new):
        result = move(image, source, old, destination, new)
        if old == conflicting.name and destination.directory.name == 'before-held':
            with conflicting.open('xb') as external:
                external.write(b'foreign')
        return result

    monkeypatch.setattr(rotation, '_move', add_occupant)
    with pytest.raises(APIError) as raised:
        rotation.apply_images(root, entries, vault, authorize=lambda: None, journal=journal)
    assert raised.value.code == 'PROJECT_FILE_RECOVERY_REQUIRED'
    assert inspect_current(root, entries[0][0]) == original
    conflicting_identity = inspect_current(root, conflicting)
    with pytest.raises(APIError, match='prove both owned identities'):
        rotation.recover_images(root, bindings(vault, entries), vault, authorize=lambda: None)
    assert inspect_current(root, conflicting) == conflicting_identity
    assert conflicting.read_bytes() == b'foreign'
    conflicting.rename(conflicting.with_name('held-foreign-copy'))
    rotation.recover_images(root, bindings(vault, entries), vault, authorize=lambda: None)
    assert conflicting.read_bytes() == entries[1][1]


def test_journal_failure_leaves_all_project_preimages_and_removes_staging(images):
    root, entries, vault, _ = images
    originals = [inspect_current(root, target) for target, _, _ in entries]

    def reject(_):
        raise ValueError('publication interrupted before commit')

    with pytest.raises(ValueError, match='before commit'):
        rotation.apply_images(root, entries, vault, authorize=lambda: None, journal=reject)
    assert [inspect_current(root, target) for target, _, _ in entries] == originals
    assert all(list(path.parent.iterdir()) == [path] for path, _, _ in entries)


def test_unchanged_run_bound_dependency_is_write_locked_during_commit(images, monkeypatch):
    root, entries, vault, journal = images
    dependency = entries[0][0].parent / 'peer.timetable'
    dependency.write_bytes(b'unchanged')
    move = rotation._move

    def verify_write_denied(*args):
        with pytest.raises(PermissionError):
            dependency.write_bytes(b'foreign write')
        return move(*args)

    monkeypatch.setattr(rotation, '_move', verify_write_denied)
    rotation.apply_images(root, entries, vault, authorize=lambda: None, journal=journal,
                          dependencies={dependency: b'unchanged'})
    rotation.recover_images(root, bindings(vault, entries), vault, authorize=lambda: None,
                            dependencies={dependency: b'unchanged'})
    assert dependency.read_bytes() == b'unchanged'


def test_explicit_consent_and_two_changed_members_are_required():
    from pydantic import ValidationError

    spec = {'path': 'OTProjects/Test/current.run', 'sha256': 'a' * 64}
    with pytest.raises(ValidationError):
        ApplyReviewedProjectFiles.model_validate({'project_run': spec, 'replacements': [],
                                                  'unchanged_sha256': {spec['path']: spec['sha256']},
                                                  'recovery_directory': 'OTAI/workspaces/Undo'})
