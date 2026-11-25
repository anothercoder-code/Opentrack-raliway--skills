"""Contract and offline end-to-end checks for the real-platform request profile."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multistation_timetable.api import generate_from_spec
from opentrack_ai.current_archive.multistation_timetable_tools import (
    BuildReferencePlatform,
    MultistationTimetableTools,
)
from opentrack_ai.current_archive.zero_operations import run_bundle
from opentrack_ai.errors import APIError


SKILL_ROOT = Path(__file__).resolve().parents[3]
DONORS = Path(r"D:\opentrack\OTAI\workspaces\winrelease1-acceptance-20261029\donors")
SOURCE_ROLES = (
    "header_document",
    "shapes",
    "depot_template",
    "trains_template",
    "courses_template",
    "timetable_template",
)
SOURCE_FILES = {
    "header_document": "header",
    "shapes": "shapes",
    "depot_template": "depot_template",
    "trains_template": "trains_template",
    "courses_template": "courses_template",
    "timetable_template": "timetable_template",
}
EXPECTED_DONOR_SHA256 = {
    "header": "8323d7f1486c1754c5a1d320ba10e27fe2bfa57cf394cb3753f30742a67d4de6",
    "shapes": "8ee95dbc78c84211cfbea472bcd2c6bae55c68abf8a6f7ce721d541aeed53e07",
    "depot_template": "74620eb27e9a8138fdeca89659d746773a476c43c4b7e5ae868693dfb2536f0c",
    "trains_template": "3258d5020c1755fa0242b0fce2c147b44f8b9a1fc22a628f78f19ee623d01f07",
    "courses_template": "54671d7b3979e1f6a5ecfca8bffd15e936243fa9e6e0cea7afa96edb9ab45a4c",
    "timetable_template": "ee57fdbba1509f93638b25e1e7245a5252bed24099a0f869fa3f752fbcb12523",
}


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _example_request():
    return json.loads(
        (
            SKILL_ROOT
            / "assets/reference-platform/reading-p9.request.example.json"
        ).read_text(encoding="utf-8")
    )


def _template_request():
    return json.loads(
        (
            SKILL_ROOT
            / "assets/reference-platform/reality-station.request.template.json"
        ).read_text(encoding="utf-8")
    )


def _require_donors():
    missing = [str(DONORS / name) for name in EXPECTED_DONOR_SHA256 if not (DONORS / name).is_file()]
    if missing:
        pytest.skip("Reviewed six-source donor fixture is unavailable: " + ", ".join(missing))
    for name, expected in EXPECTED_DONOR_SHA256.items():
        if _sha((DONORS / name).read_bytes()) != expected:
            pytest.skip(f"Reviewed donor {name} no longer matches its frozen SHA-256")


def _fixture_request(root):
    _require_donors()
    request = _example_request()
    workspace = root / "OTAI/workspaces/reality-fixture"
    donor_root = workspace / "donors"
    donor_root.mkdir(parents=True)

    expected_sources = {}
    for role, donor_name in SOURCE_FILES.items():
        blob = (DONORS / donor_name).read_bytes()
        assert _sha(blob) == EXPECTED_DONOR_SHA256[donor_name]
        destination = donor_root / donor_name
        destination.write_bytes(blob)
        expected_sources[role] = {
            "path": destination.relative_to(root).as_posix(),
            "sha256": _sha(blob),
        }

    target = workspace / "published"
    request["sources"] = expected_sources
    request["target_directory"] = target.relative_to(root).as_posix()
    request["spec"]["network"]["execution_root"] = target.as_posix()
    request["preview_only"] = True
    return request, donor_root, target, expected_sources


def _assert_request_contract(request, station_sign):
    model = BuildReferencePlatform.model_validate(request)
    assert set(model.sources.model_fields_set) == set(SOURCE_ROLES)
    platform = request["spec"]["network"]["platform"]
    assert type(platform["length_m"]) is int and platform["length_m"] > 0
    if "width_m" in platform:
        assert type(platform["width_m"]) in (int, float)
        assert platform["width_m"] > 0
        assert "drawing_side" in platform
    visits = request["spec"]["plan"][0]["visits"]
    real_visit = next(row for row in visits if row["station_sign"] == station_sign)
    assert real_visit["stop"] is True
    assert real_visit["arrival_s"] < real_visit["departure_s"]


def _assert_new_directory_only(target):
    assert target.is_dir()
    siblings = list(target.parent.glob(".opentrack-project-*"))
    assert siblings == []


def test_reality_template_is_a_valid_fresh_preview_request():
    request = _template_request()
    assert request["preview_only"] is True
    assert "width_m" not in request["spec"]["network"]["platform"]
    assert request["spec"]["network"]["platform"]["length_m"] > 0
    visits = request["spec"]["plan"][0]["visits"]
    station = next(row for row in visits if row["station_sign"] == "STA")
    assert station["arrival_s"] == 300
    assert station["departure_s"] == 420
    assert station["stop"] is True
    assert request["spec"]["simulation"]["stop_s"] >= visits[-1]["arrival_s"]
    assert all(
        binding["sha256"] == "REPLACE_WITH_64_LOWERCASE_HEX"
        for binding in request["sources"].values()
        if binding is not None
    )
    with pytest.raises(ValueError):
        BuildReferencePlatform.model_validate(request)


def test_multi_track_contract_is_not_an_executable_single_corridor_request():
    contract = json.loads(
        (
            SKILL_ROOT
            / "assets/reference-platform/reality-station.multi-track.request.template.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["template_status"] == "documentation_and_contract_only"
    assert contract["satisfies_single_corridor_builder"] is False
    assert "spec" not in contract
    with pytest.raises(ValueError):
        BuildReferencePlatform.model_validate(contract)


def test_reading_platform_request_binds_one_positive_through_stop():
    request = _example_request()
    _assert_request_contract(request, "RDG")
    platform = request["spec"]["network"]["platform"]
    assert platform["length_m"] == 325
    assert platform["direction"] == "forward"
    assert request["spec"]["simulation"]["start_s"] < request["spec"]["simulation"]["stop_s"]


def test_offline_generation_from_real_donors_reloads_every_member_and_run_binding():
    _require_donors()
    request = _example_request()
    sources = {
        role: (DONORS / SOURCE_FILES[role]).read_bytes()
        for role in SOURCE_ROLES
    }
    files, receipt = generate_from_spec(sources, request["spec"])
    assert receipt["saved"] is False
    assert receipt["native_execution"] is False
    assert receipt["reference_platform_visits"] == [
        {
            "course_id": "RDG09",
            "station_sign": "RDG",
            "planned_arrival_s": 37380,
            "planned_departure_s": 37500,
            "stop_edge_id": 21,
            "distance_m": 2025.0,
            "area_length_m": 325,
            "train_length_m": 209.0,
        }
    ]
    run_name = "chain.run"
    assert run_name in files
    for name, blob in files.items():
        if name != run_name:
            root, version = writer.load_next_compatible(blob)
            assert root is not None and isinstance(version, int)
    catalogs = {
        "dest": "OTData/chain.dest",
        "depot": "OTData/chain.depot",
        "trains": "OTData/chain.trains",
        "courses": "OTData/chain.courses",
        "stations": "OTData/chain.stations",
        "timetable": "OTData/chain.timetable",
    }
    documents = [
        f"OTDocuments/{name}.opentrack"
        for name in ("EA", "RDG", "WB")
    ]
    bindings = run_bundle.verify_archive_bindings(
        files[run_name],
        {name: blob for name, blob in files.items() if name != run_name},
        catalog_paths=catalogs,
        document_paths=documents,
    )
    assert bindings["archive_bindings_checked"] is True
    assert bindings["courses"] == 1
    assert bindings["timetable_rows"] == 3


def test_reference_platform_service_publishes_once_and_rejects_an_existing_target(tmp_path):
    if os.name != "nt":
        pytest.skip("The normal publication entry requires local Windows NTFS")
    if not tmp_path.as_posix().isascii():
        pytest.skip("Windows native archive checks require an ASCII --basetemp")
    request, donor_root, target, source_binding = _fixture_request(tmp_path)
    before = {name: _sha((tmp_path / binding["path"]).read_bytes()) for name, binding in source_binding.items()}

    preview = BuildReferencePlatform.model_validate(request)
    tool = MultistationTimetableTools(tmp_path)
    preview_result = tool.reference_platform(preview)
    assert preview_result["saved"] is False
    assert not target.exists()
    assert preview_result["reference_platform_visits"][0]["station_sign"] == "RDG"

    saved_request = deepcopy(request)
    saved_request["preview_only"] = False
    saved = tool.reference_platform(BuildReferencePlatform.model_validate(saved_request))
    assert saved["saved"] is True
    assert saved["publication"]["atomic_no_replace"] is True
    assert saved["publication"]["all_input_hashes_rechecked"] is True
    assert saved["publication"]["post_commit_verified"] is True
    assert saved["saved"] is True
    actual = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    }
    assert set(actual) == set(saved["files"])
    assert {
        name: _sha(blob) for name, blob in actual.items()
    } == {
        name: row["sha256"] for name, row in saved["files"].items()
    }
    after = {name: _sha((tmp_path / binding["path"]).read_bytes()) for name, binding in source_binding.items()}
    assert after == before
    for name, blob in actual.items():
        if name == "chain.run":
            continue
        root, version = writer.load_next_compatible(blob)
        assert root is not None and isinstance(version, int)
    catalogs = {
        "dest": "OTData/chain.dest",
        "depot": "OTData/chain.depot",
        "trains": "OTData/chain.trains",
        "courses": "OTData/chain.courses",
        "stations": "OTData/chain.stations",
        "timetable": "OTData/chain.timetable",
    }
    documents = [
        f"OTDocuments/{name}.opentrack"
        for name in ("EA", "RDG", "WB")
    ]
    bindings = run_bundle.verify_archive_bindings(
        actual["chain.run"],
        {name: blob for name, blob in actual.items() if name != "chain.run"},
        catalog_paths=catalogs,
        document_paths=documents,
    )
    assert bindings["timetable_rows"] == 3
    manifest = run_bundle.verify_manifest(
        actual["chain.run"],
        {name: blob for name, blob in actual.items() if name != "chain.run"},
        saved["run"],
    )
    assert manifest["manifest_verified"] is True
    assert (target / "output").is_dir()
    _assert_new_directory_only(target)

    with pytest.raises(APIError) as duplicate:
        tool.reference_platform(BuildReferencePlatform.model_validate(saved_request))
    assert duplicate.value.code == "TARGET_EXISTS"
    assert {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    } == actual
