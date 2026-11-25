"""Exercise the narrowly bounded retry around a transient NTFS rename denial."""

import os

import pytest

from opentrack_ai.current_archive import windows_publish
from opentrack_ai.current_archive.windows_publish import (
    _Writer, availability, publish_project,
)
from opentrack_ai.errors import APIError


STATUS_ACCESS_DENIED = 0xc0000022


@pytest.fixture
def publication(tmp_path):
    if os.name != "nt" or not availability()[0]:
        pytest.skip("Windows native fixed-volume NTFS publisher required")
    if not tmp_path.as_posix().isascii():
        pytest.skip("Windows native publication requires an ASCII --basetemp")
    target = tmp_path / "OTAI/workspaces/published"
    target.parent.mkdir(parents=True)
    return tmp_path, target


def retry_after_denial(publication, monkeypatch, statuses):
    root, target = publication
    native_attempt = _Writer._rename_attempt
    sleeps = []

    def attempt(writer, handle, buffer):
        if statuses:
            return statuses.pop(0), 0
        return native_attempt(writer, handle, buffer)

    monkeypatch.setattr(_Writer, "_rename_attempt", attempt)
    monkeypatch.setattr(windows_publish.time, "sleep", sleeps.append)
    result = publish_project(
        root,
        target,
        {"payload.bin": b"reviewed payload"},
        recheck=lambda: None,
        validate_bundle=lambda actual: actual == {"payload.bin": b"reviewed payload"},
    )
    return result, sleeps


def test_transient_access_denied_retries_once_and_commits(publication, monkeypatch):
    result, sleeps = retry_after_denial(publication, monkeypatch, [STATUS_ACCESS_DENIED])
    root, target = publication

    assert result["commit_completed"] is True
    assert sleeps == [0.010]
    assert (target / "payload.bin").read_bytes() == b"reviewed payload"
    assert list(target.parent.glob(".opentrack-project-*")) == []


def test_requested_retry_denial_preserves_error_and_cleans_staging(publication, monkeypatch):
    root, target = publication
    calls = []

    def denied(writer, handle, buffer):
        calls.append(STATUS_ACCESS_DENIED)
        return STATUS_ACCESS_DENIED, 0

    sleeps = []
    monkeypatch.setattr(_Writer, "_rename_attempt", denied)
    monkeypatch.setattr(windows_publish.time, "sleep", sleeps.append)

    with pytest.raises(APIError) as raised:
        publish_project(
            root,
            target,
            {"payload.bin": b"reviewed payload"},
            recheck=lambda: None,
            validate_bundle=lambda actual: None,
        )

    assert raised.value.code == "ARCHIVE_IO_ERROR"
    assert raised.value.details["ntstatus"] == "0xc0000022"
    assert raised.value.details["attempt_count"] == 3
    assert len(calls) == 3
    assert sleeps == [0.010, 0.025]
    assert not target.exists()
    assert list(target.parent.glob(".opentrack-project-*")) == []
