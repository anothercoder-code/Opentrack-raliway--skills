"""Fail-closed checks for the AI reality-station semantic planning contract."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from opentrack_ai.current_archive.reality_station_semantics import (
    ValidateRealityStationPlan,
    RealityStationPlan,
    validate_reality_station_plan,
)


ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "assets/reference-platform"


def example():
    return json.loads(
        (ASSETS / "reality-station.semantic.example.json").read_text(encoding="utf-8")
    )


def codes(report):
    return {
        row["code"] for row in report["issues"]
    }


def test_example_is_valid_but_not_a_native_write_or_execution_claim():
    report = validate_reality_station_plan(example())

    assert report["status"] == "valid_for_offline_planning"
    assert report["ready_for_offline_composition"] is True
    assert report["ready_for_native_write"] is False
    assert report["native_write_performed"] is False
    assert report["native_application_started"] is False
    assert report["native_simulation_verified"] is False
    assertions = {row["assertion_id"]: row for row in report["assertions"]}
    assert assertions["platforms.island_faces"]["status"] == "verified"
    assert assertions["platforms.contiguous_unbranched_span"]["status"] == "verified"
    assert assertions["movements.train_fits_usable_platform"]["status"] == "verified"
    assert (
        assertions["movements.stop_chronology_and_day_crossing"]["status"]
        == "verified"
    )
    assert assertions["native.arrival_at_platform"]["status"] == "not_run"
    assert assertions["native.zero_speed_dwell"]["status"] == "not_run"


def test_template_is_schema_shaped_but_not_a_final_plan():
    template = json.loads(
        (ASSETS / "reality-station.multi-track.request.template.json").read_text(
            encoding="utf-8"
        )
    )
    model = RealityStationPlan.model_validate(template)
    assert model.template_status == "documentation_and_contract_only"
    assert model.satisfies_single_corridor_builder is False
    report = validate_reality_station_plan(model)
    assert report["status"] == "invalid"
    assert "TEMPLATE_NOT_FINAL_PLAN" in codes(report)
    assert "TEMPLATE_PLACEHOLDER" in codes(report)
    assert report["ready_for_offline_composition"] is False


def test_unsupported_example_preserves_the_missing_native_capability():
    plan = json.loads(
        (ASSETS / "reality-station.unsupported.example.json").read_text(
            encoding="utf-8"
        )
    )
    report = validate_reality_station_plan(plan)

    assert report["status"] == "unsupported"
    assert "UNSUPPORTED_COMPOUND_TURNOUT" in codes(report)
    assert report["ready_for_offline_composition"] is False
    assert report["ready_for_native_write"] is False
    assert report["native_write_performed"] is False
    assert report["native_application_started"] is False
    assert report["native_simulation_verified"] is False


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("compound_turnout", "UNSUPPORTED_COMPOUND_TURNOUT"),
        ("crossover", "UNSUPPORTED_COMPOUND_TURNOUT"),
        ("diamond_crossing", "UNSUPPORTED_COMPOUND_TURNOUT"),
        ("ladder_track", "UNSUPPORTED_COMPOUND_TURNOUT"),
    ],
)
def test_compound_throat_kinds_are_fail_closed(kind, expected):
    plan = example()
    plan["directed_links"][1]["kind"] = kind
    report = validate_reality_station_plan(plan)

    assert report["status"] == "unsupported"
    assert expected in codes(report)
    assert report["ready_for_offline_composition"] is False
    assertion = next(
        row
        for row in report["assertions"]
        if row["assertion_id"] == "throats.explicit_directed_connectivity"
    )
    assert assertion["status"] == "unsupported"


def test_noncontiguous_platform_span_is_not_inferred_from_nearby_edges():
    plan = example()
    edges = plan["platform_spans"][0]["ordered_native_edges"]
    edges.append(
        {
            **edges[0],
            "edge_id": 103,
            "start_end_id": 999,
            "end_end_id": 1000,
            "length_m": 50,
        }
    )
    plan["platform_spans"][0]["ordered_native_edges"] = edges
    face = plan["platform_faces"][0]
    face["end_position_m"] += 50

    report = validate_reality_station_plan(plan)
    assert report["status"] == "unsupported"
    assert "UNSUPPORTED_NONCONTIGUOUS_PLATFORM" in codes(report)
    assertion = next(
        row
        for row in report["assertions"]
        if row["assertion_id"] == "platforms.contiguous_unbranched_span"
    )
    assert assertion["status"] == "unsupported"


def test_platform_crossing_a_turnout_is_rejected_as_an_internal_boundary():
    plan = example()
    plan["platform_spans"][0]["ordered_native_edges"][0]["transition_after"] = (
        "compound_turnout"
    )
    report = validate_reality_station_plan(plan)
    assert report["status"] == "unsupported"
    assert "UNSUPPORTED_COMPOUND_TURNOUT" in codes(report)


def test_route_cannot_use_drawing_proximity_or_an_undeclared_transition():
    plan = example()
    plan["directed_links"] = [
        row
        for row in plan["directed_links"]
        if not (row["source"]["end_id"] == 11 and row["target"]["end_id"] == 20)
    ]
    report = validate_reality_station_plan(plan)
    assert report["status"] == "invalid"
    assert "UNDECLARED_DIRECTED_TRANSITION" in codes(report)


def test_train_must_fit_and_stopping_departure_must_follow_arrival():
    plan = example()
    plan["movements"][0]["train_length_m"] = 301
    plan["movements"][0]["departure_s"] = 50
    report = validate_reality_station_plan(plan)
    assert report["status"] == "invalid"
    assert "TRAIN_EXCEEDS_USABLE_PLATFORM" in codes(report)
    assert "MOVEMENT_STOP_CHRONOLOGY" not in codes(report)

    plan = example()
    plan["movements"][0]["arrival_day_offset"] = 1
    plan["movements"][0]["arrival_s"] = 120
    plan["movements"][0]["departure_day_offset"] = 1
    plan["movements"][0]["departure_s"] = 120
    report = validate_reality_station_plan(plan)
    assert "MOVEMENT_STOP_CHRONOLOGY" in codes(report)


def test_unknown_source_missing_signal_and_route_chain_break_are_explicit():
    plan = example()
    plan["site_identity"]["source_ids"].append("missing_evidence")
    plan["stop_posts"][0]["signal_id"] = "MissingExit"
    plan["movements"][0]["route_ids"].append("MissingRoute")
    report = validate_reality_station_plan(plan)
    actual = codes(report)

    assert report["status"] == "invalid"
    assert "UNRESOLVED_SOURCE" in actual
    assert "STOP_POST_SIGNAL_UNKNOWN" in actual
    assert "MOVEMENT_ROUTE_UNKNOWN" in actual


def test_assumptions_require_explicit_supporting_provenance():
    plan = example()
    plan["assumptions"] = [
        {
            "field": "proxy vehicle physics",
            "value": "accepted template train model",
            "reason": "No measured formation was supplied",
            "affects_acceptance": True,
            "source_id": None,
        }
    ]
    report = validate_reality_station_plan(plan)
    assert report["status"] == "invalid"
    assert "ASSUMPTION_SOURCE_UNRESOLVED" in codes(report)


def test_registry_contract_is_strict_and_contains_no_hidden_write_flag():
    args = ValidateRealityStationPlan(plan=example())
    assert args.plan.contract_kind == "reality_station_semantic_plan"
    schema = ValidateRealityStationPlan.model_json_schema()
    assert "preview_only" not in json.dumps(schema)
    assert "target_directory" not in json.dumps(schema)


def test_multi_edge_face_can_validate_when_exact_end_continuity_and_lengths_match():
    plan = example()
    first = plan["platform_spans"][0]["ordered_native_edges"][0]
    first["length_m"] = 150
    second = {
        **deepcopy(first),
        "edge_id": 104,
        "start_end_id": first["end_end_id"],
        "end_end_id": 12,
        "length_m": 150,
    }
    plan["platform_spans"][0]["ordered_native_edges"] = [first, second]
    plan["signals"][0]["end_id"] = 12
    plan["stop_posts"][0]["end_id"] = 12

    report = validate_reality_station_plan(plan)
    assert report["status"] == "valid_for_offline_planning"
    assertion = next(
        row
        for row in report["assertions"]
        if row["assertion_id"] == "platforms.contiguous_unbranched_span"
    )
    assert assertion["status"] == "verified"
