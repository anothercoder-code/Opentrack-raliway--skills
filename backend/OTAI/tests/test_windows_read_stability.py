"""Repeat native Windows read verification without weakening source binding."""

from pathlib import Path

import pytest

from opentrack_ai.current_archive import windows_io


@pytest.mark.skipif(not windows_io.availability()[0], reason="Needs the native Windows x64 NTFS reader")
def test_repeated_secure_read_is_stable_for_one_file(tmp_path):
    if not tmp_path.as_posix().isascii():
        pytest.skip("Windows native reads require an ASCII --basetemp")
    root = Path(tmp_path)
    folder = root / "OTProjects" / "Stability"
    folder.mkdir(parents=True)
    expected = bytes(range(256)) * 17
    source = folder / "Line.opentrack"
    source.write_bytes(expected)

    for _ in range(20):
        assert windows_io.secure_bytes(str(root), source) == expected
