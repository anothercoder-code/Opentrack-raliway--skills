"""The route compiler must not advertise a quarantined archive writer."""

from opentrack_ai.route_bundle import compile_route_bundle


def test_compiler_returns_definitions_without_a_legacy_apply_batch():
    result = compile_route_bundle(
        {
            "project": "OTProjects/RouteBundleTest",
            "route_name_prefix": "RB",
            "nodes": [
                {
                    "document": "Line",
                    "end_id": 1,
                    "main_signal": True,
                    "signal_aspects": [1],
                },
                {"document": "Line", "end_id": 2, "main_signal": False},
                {
                    "document": "Line",
                    "end_id": 3,
                    "main_signal": True,
                    "signal_aspects": [1],
                },
            ],
            "links": [
                {
                    "source": {"document": "Line", "end_id": 1},
                    "target": {"document": "Line", "end_id": 2},
                    "length_m": 100,
                },
                {
                    "source": {"document": "Line", "end_id": 2},
                    "target": {"document": "Line", "end_id": 3},
                    "length_m": 100,
                },
            ],
            "paths": [
                {
                    "name": "Through",
                    "start": {"document": "Line", "end_id": 1},
                    "end": {"document": "Line", "end_id": 3},
                }
            ],
            "itineraries": [{"name": "Line", "paths": ["Through"]}],
        }
    )

    assert result["counts"]["routes"] == 1
    assert result["counts"]["paths"] == 1
    assert result["native_archive_written"] is False
    assert result["application"]["status"] == "not_applicable"
    assert "quarantined" in result["application"]["reason"]
    assert "native_apply_spec" not in result
    assert "opentrack_generate_operations" not in str(result)
