"""Packaged coverage metadata must resolve every input from its declared root."""

import types

from opentrack_ai.coverage import read_packaged_coverage


def _args():
    return types.SimpleNamespace(
        section="summary",
        scope="packaged",
        require_fresh=True,
        query=None,
        binary=None,
        class_name=None,
        selector=None,
        status=None,
        operation=None,
        limit=20,
        offset=0,
    )


def test_packaged_coverage_is_fresh_at_the_skill_root():
    result = read_packaged_coverage(_args())

    assert result["freshness"]["fresh"] is True
    assert result["freshness"]["changed_input_count"] == 0
    assert result["freshness"]["content_sha256"] is not None
    assert result["summary"]["saved_function_records"] == 89
