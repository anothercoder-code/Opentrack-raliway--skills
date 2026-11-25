"""Replay the frozen successful and failed Reading P9 original runs."""

import importlib.util
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[3]
VERIFIER = SKILL_ROOT / "scripts" / "verify_reference_platform_run.py"
PROJECT = Path(r"D:\opentrack\OTAI\workspaces\ReadingP9_20261123")
EVIDENCE = Path(r"D:\opentrack\OTAI\workspaces\ReadingP9Verification_20261123")


def verifier_module():
    if not VERIFIER.is_file():
        pytest.skip("The frozen Reading P9 verifier is unavailable")
    spec = importlib.util.spec_from_file_location("reading_p9_verifier", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence_files():
    request = EVIDENCE / "request.json"
    receipt = EVIDENCE / "build.json"
    successful = EVIDENCE / "NativeRun2"
    failed = EVIDENCE / "NativeRun"
    if not (
        PROJECT.is_dir()
        and request.is_file()
        and receipt.is_file()
        and successful.is_dir()
        and failed.is_dir()
    ):
        pytest.skip("The frozen Reading P9 run evidence is unavailable")
    return request, receipt, successful, failed


def test_frozen_original_run_proves_platform_stop_and_onward_movement():
    request, receipt, successful, _ = evidence_files()
    module = verifier_module()
    import json

    result = module.verify(
        PROJECT,
        json.loads(request.read_bytes()),
        json.loads(receipt.read_bytes()),
        successful,
    )

    assert result["native_run_verified"] is True
    assert result["message_levels"] == {"NORMAL": 6, "WARNING": 2}
    assert len(result["warning_rows"]) == 2
    assert all("Late Arrival" in row or "Late Departure" in row for row in result["warning_rows"])
    assert result["user_preferences_changed"] is False
    course = result["courses"][0]
    assert course == {
        "course_id": "RDG09",
        "actual_arrival": "10:23:05",
        "actual_departure": "10:25:05",
        "dwell_s": 120,
        "zero_speed_samples": 2,
        "zero_speed_interval_s": [37385.91, 37505.91],
        "standing_distance_m": 2025.0,
        "platform_edge_span_m": [1700.0, 2025.0],
        "planned_train_length_m": 209.0,
        "downstream_arrival": "10:27:19",
        "course_distance_m": 4225.0,
        "onward_positive_speed_verified": True,
    }
    assert result["output_sha256"] == {
        "OT_Messages.txt": "49d29ca89d43d8860403870a74cddff100a8facc32eb0c2a4aea4002c912b4c6",
        "OT_CourseStatistics.txt": "f1b876e3e617f5487747c3b25bbd5afc47e10c243822ee51e675bf6d676a69e6",
        "OT_RDG09.tt": "df2cc17cfedf0d71b77716c25dae22e8a2df425655c6f8e4a174f8a22f156c31",
        "OT_RDG09.vt": "afe52b251fa7991225d478dba2256a7a3dc7fddd7f8a5ecec7ec0bee6fcb81f8",
        "OT_RDG09.st1": "b1a15583c24259a3c464aedc63f5938e07f1716a5f59e3412d964304616d72db",
    }


def test_failed_original_attempt_is_not_accepted_as_platform_evidence():
    request, receipt, _, failed = evidence_files()
    module = verifier_module()
    import json

    with pytest.raises(ValueError, match="Original process did not return normally"):
        module.verify(
            PROJECT,
            json.loads(request.read_bytes()),
            json.loads(receipt.read_bytes()),
            failed,
        )
