"""Release packaging must identify prior manifests without trusting their payload."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "package_release.py"
SPEC = importlib.util.spec_from_file_location("package_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
package_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_release)


def test_prior_release_manifest_is_replaceable(tmp_path):
    manifest = tmp_path / "RELEASE-MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": package_release.SCHEMA,
                "name": package_release.SKILL_NAME,
                "edition": "full1",
            }
        ),
        encoding="utf-8",
    )

    package_release.assert_replaceable_manifest(manifest)


@pytest.mark.parametrize(
    "body",
    [
        "{",
        "[]",
        json.dumps({"schema": package_release.SCHEMA, "name": "other"}),
        json.dumps({"schema": "other", "name": package_release.SKILL_NAME}),
    ],
)
def test_unexpected_manifest_is_never_replaced(tmp_path, body):
    manifest = tmp_path / "RELEASE-MANIFEST.json"
    manifest.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError):
        package_release.assert_replaceable_manifest(manifest)
