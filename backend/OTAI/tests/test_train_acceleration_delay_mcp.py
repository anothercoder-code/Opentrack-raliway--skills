"""Registered MCP save and independent reload for accelerationDelay_s."""

import hashlib
import shutil
from pathlib import Path

import pytest

from opentrack_ai import license_authorization
from opentrack_ai.current_archive import train_fields
from opentrack_ai.current_archive import writer
from opentrack_ai.registry import Registry
from opentrack_ai.service import Service


SOURCE_ROOT = Path(
    r"D:\opentrack\deliverables\opentrack-cross-document-edit-20261114"
    r"\native-baseline-stock\inputs"
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def copied_project(tmp_path):
    if not (SOURCE_ROOT / "OTData" / "chain.trains").is_file():
        pytest.skip("The reviewed populated BJTU Train16 fixture is unavailable")
    target = tmp_path / "OTAI" / "workspaces" / "train-acceleration-delay"
    shutil.copytree(SOURCE_ROOT, target)
    license_authorization.record_authorization(
        tmp_path,
        user_statement="I confirm a valid full OpenTrack licence for this local test.",
        user_scope="Automated local regression",
        purpose="Verify an audited saved-field write through the registered tool.",
    )
    return target


def test_registered_save_and_fresh_independent_reload(tmp_path, monkeypatch):
    project = copied_project(tmp_path)
    source = project / "OTData" / "chain.trains"
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    name = next(iter(train_fields.c.train_items(root)))
    name = train_fields.c.text(name.contents[0].value)
    target = project / "OTData" / "acceleration-delay.trains"
    registry = Registry(Service(tmp_path, False, False), profile="all")

    inspect = registry.envelope(
        "opentrack_inspect_current_stock_fields",
        {
            "source_path": "OTAI/workspaces/train-acceleration-delay/OTData/chain.trains",
            "kind": "OTTrain",
            "name": name,
            "fields": ["accelerationDelay_s"],
        },
    )
    assert inspect["ok"] is True
    assert inspect["result"]["fields"]["accelerationDelay_s"] is not None

    preview = registry.envelope(
        "opentrack_edit_current_stock_fields",
        {
            "source": {
                "path": "OTAI/workspaces/train-acceleration-delay/OTData/chain.trains",
                "sha256": sha256(original),
            },
            "kind": "OTTrain",
            "name": name,
            "changes": {"accelerationDelay_s": -4.5},
            "preview_only": True,
        },
    )
    assert preview["ok"] is True
    assert preview["result"]["saved"] is False
    assert not target.exists()

    saved = registry.envelope(
        "opentrack_edit_current_stock_fields",
        {
            "source": {
                "path": "OTAI/workspaces/train-acceleration-delay/OTData/chain.trains",
                "sha256": sha256(original),
            },
            "kind": "OTTrain",
            "name": name,
            "changes": {"accelerationDelay_s": -4.5},
            "preview_only": False,
            "target_path": "OTAI/workspaces/train-acceleration-delay/OTData/acceleration-delay.trains",
        },
    )
    assert saved["ok"] is True
    assert saved["result"]["saved"] is True
    assert source.read_bytes() == original
    assert sha256(target.read_bytes()) == saved["result"]["output_sha256"]

    # This deliberately bypasses the Registry/Service cache and opens the
    # published bytes through the standalone archive reader.
    reloaded = train_fields.read_fields(
        target.read_bytes(), name, ["accelerationDelay_s"]
    )
    assert reloaded["accelerationDelay_s"] == 0.0


def test_registered_schema_exposes_new_field_and_save_boundary():
    registry = Registry(Service(Path.cwd(), False, False), profile="all")
    edit = registry.tools["opentrack_edit_current_stock_fields"]
    schema = edit.model.model_json_schema()
    encoded = str(schema)
    assert "accelerationDelay_s" in encoded
    assert edit.read_only is False
    assert edit.destructive is False
