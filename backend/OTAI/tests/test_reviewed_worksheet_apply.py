"""Offline rollback of a reviewed worksheet, including interrupted rename states."""

from subprocess import TimeoutExpired

import pytest

from opentrack_ai.current_archive import reviewed_movement_apply as workflow
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.windows_publish import _Writer, availability
from opentrack_ai.current_archive.windows_scoped_replace import (
    inspect_current, recover_vacant_name, replace_verified, retained_siblings,
)
from opentrack_ai.errors import APIError


@pytest.fixture
def worksheet(tmp_path):
    if not availability()[0]:
        pytest.skip('Windows native fixed-volume NTFS publisher required')
    target = tmp_path / 'OTProjects/Fixture/Only.opentrack'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'before')
    return tmp_path, target


def test_same_path_replaces_exact_raw_file_identity(worksheet):
    root, target = worksheet
    original, _ = inspect_current(root, target)
    events = []

    def record(rotation):
        assert rotation['original_identity'] == original
        events.append('journaled')
        return 'sealed'

    result = replace_verified(root, target, b'before', b'after', expected_identity=original,
                              authorize=lambda: events.append('authorized'), journal=record)
    assert result['journal'] == 'sealed'
    assert events == ['journaled', 'authorized', 'authorized']
    assert inspect_current(root, target) == (result['replacement_identity'], sha(b'after'))
    assert result['replacement_identity'] != original
    assert retained_siblings(root, target, result) == []
    assert list(target.parent.iterdir()) == [target]


def test_same_bytes_with_wrong_identity_are_never_replaced(worksheet):
    root, target = worksheet
    original, digest = inspect_current(root, target)
    with pytest.raises(APIError, match='different native file identity'):
        replace_verified(root, target, b'before', b'after', authorize=lambda: None,
                         journal=lambda _: pytest.fail('unexpected journal'),
                         expected_identity={**original, 'file_id': '0' * 32})
    assert inspect_current(root, target) == (original, digest)
    assert list(target.parent.iterdir()) == [target]


def test_failed_second_rename_restores_original(worksheet, monkeypatch):
    root, target = worksheet
    initial = inspect_current(root, target)
    native_rename = _Writer.rename
    journal = []

    def fail_second_move(writer, handle, parent, name):
        if name == target.name and not any(row == 'failed' for row in journal):
            journal.append('failed')
            raise OSError('simulated failure during staged install')
        return native_rename(writer, handle, parent, name)

    monkeypatch.setattr(_Writer, 'rename', fail_second_move)
    with pytest.raises(APIError) as raised:
        replace_verified(root, target, b'before', b'after', authorize=lambda: None,
                         journal=lambda rotation: journal.append(rotation))
    assert raised.value.code == 'SCOPED_REPLACEMENT_RESTORED'
    assert len(journal) == 2 and journal[1] == 'failed'
    assert inspect_current(root, target) == initial
    assert list(target.parent.iterdir()) == [target]


def test_new_foreign_name_survives_failed_install_and_recovery(worksheet, monkeypatch):
    root, target = worksheet
    initial = inspect_current(root, target)
    native_rename = _Writer.rename

    def occupy_vacant_name(writer, handle, parent, name):
        result = native_rename(writer, handle, parent, name)
        if name.endswith('-original'):
            with target.open('xb') as handle:
                handle.write(b'foreign')
        return result

    monkeypatch.setattr(_Writer, 'rename', occupy_vacant_name)
    with pytest.raises(APIError) as raised:
        replace_verified(root, target, b'before', b'after',
                         authorize=lambda: None, journal=lambda _: 'sealed')
    assert raised.value.code == 'SCOPED_REPLACEMENT_RECOVERY_REQUIRED'
    rotation = raised.value.details['rotation']
    assert target.read_bytes() == b'foreign'
    assert inspect_current(root, target.with_name(rotation['original_sibling'])) == initial
    assert set(retained_siblings(root, target, rotation)) == {rotation['original_sibling'], rotation['staged_sibling']}
    with pytest.raises(APIError, match='vacant target name'):
        recover_vacant_name(root, target, b'before', b'after', rotation, authorize=lambda: None)
    assert target.read_bytes() == b'foreign'


def test_vacant_name_recovery_uses_retained_original_and_stage(worksheet):
    root, target = worksheet
    original = target.with_name('.otai-worksheet-' + '1' * 32 + '-original')
    stage = target.with_name('.otai-worksheet-' + '1' * 32 + '-staged')
    initial = inspect_current(root, target)
    target.rename(original)
    stage.write_bytes(b'after')
    replacement, _ = inspect_current(root, stage)
    rotation = {'original_sibling': original.name, 'staged_sibling': stage.name,
                'original_identity': initial[0], 'replacement_identity': replacement}
    assert workflow._rotation_from({'rotation': rotation}) == rotation
    with pytest.raises(APIError, match='staging sibling differs'):
        recover_vacant_name(root, target, b'before', b'wrong', rotation, authorize=lambda: None)
    assert not target.exists() and original.exists() and stage.exists()
    result = recover_vacant_name(root, target, b'before', b'after', rotation, authorize=lambda: None)
    assert result['original_file_identity_preserved']
    assert inspect_current(root, target) == initial
    assert not original.exists() and not stage.exists()


def test_active_or_unverifiable_original_process_fails_closed(monkeypatch):
    monkeypatch.setattr(workflow, 'process_is_open', lambda: True)
    with pytest.raises(APIError) as raised:
        workflow._closed()
    assert raised.value.code == 'APPLICATION_RUNNING'

    def query_timeout():
        raise TimeoutExpired('query', 1)

    monkeypatch.setattr(workflow, 'process_is_open', query_timeout)
    with pytest.raises(APIError) as raised:
        workflow._closed()
    assert raised.value.code == 'APPLICATION_STATE_UNVERIFIED'


def test_immutable_history_project_is_rejected_before_inventory(tmp_path, monkeypatch):
    tools = workflow.ReviewedWorksheetTools(tmp_path, True)
    scope = ('OTAI', 'workspaces', 'edit', 'history', '0001', 'project')
    run = tmp_path.joinpath(*scope, 'test.run')
    monkeypatch.setattr(tools, 'bytes_for', lambda _: (run, b''))
    monkeypatch.setattr(tools, 'project_scope', lambda _: scope)
    with pytest.raises(APIError, match='outside any immutable editor snapshot'):
        tools.project_paths(None)
