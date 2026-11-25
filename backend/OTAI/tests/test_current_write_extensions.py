"""Archive-level regression for the remaining current scalar write families."""

from pathlib import Path
import struct

import pytest

from opentrack_ai.current_archive import catalogs
from opentrack_ai.current_archive import category_dwell
from opentrack_ai.current_archive import edge_operations
from opentrack_ai.current_archive import engine_physics
from opentrack_ai.current_archive import route_factory
from opentrack_ai.current_archive import writer


BJTU_DATA = Path(r"D:\opentrack\OTProjects\BJTU\OTData")
READING_DOCUMENTS = Path(r"D:\opentrack\OTAI\workspaces\ReadingP9_20261123\OTDocuments")


def require_fixtures(*paths):
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        pytest.skip("Reviewed native fixtures are unavailable: " + ", ".join(missing))


def pack_float(value):
    return struct.pack("<f", value)


def test_engine_physics_setters_reload_and_preserve_other_engines():
    source = BJTU_DATA / "empty.depot"
    require_fixtures(source)
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    name = catalogs.text(catalogs.engine_items(root)[0].contents[1].value)
    before = {
        catalogs.text(item.contents[1].value): writer.fingerprint(item)
        for item in catalogs.engine_items(root)
    }

    output, receipt = engine_physics.patch_archive(
        original,
        name,
        {"adhesion_load": 123, "force_max_kn": 456, "force_min_kn": 78},
    )

    assert original != output
    reloaded_root, _ = writer.load_next_compatible(output)
    reloaded = next(
        item for item in catalogs.engine_items(reloaded_root)
        if catalogs.text(item.contents[1].value) == name
    )
    assert (
        reloaded.contents[3].value,
        reloaded.contents[6].value,
        reloaded.contents[17].value,
    ) == (123, 456, 78)
    assert receipt["fresh_reload_verified"] is True
    assert receipt["native_application_tested"] is False
    assert {row["setter"] for row in receipt["changes"]} == {
        "0x004cbd60",
        "0x004cbde0",
        "0x004cbdf0",
    }
    retained = {
        catalogs.text(item.contents[1].value): writer.fingerprint(item)
        for item in catalogs.engine_items(reloaded_root)
        if catalogs.text(item.contents[1].value) != name
    }
    assert retained == {
        other_name: digest
        for other_name, digest in before.items()
        if other_name != name
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"adhesion_load": True},
        {"adhesion_load": 1.0},
        {"force_max_kn": 2**31},
        {"force_min_kn": None},
        {"not_a_field": 1},
    ],
)
def test_engine_physics_rejects_values_outside_exact_int32_contract(changes):
    source = BJTU_DATA / "empty.depot"
    require_fixtures(source)
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    name = catalogs.text(catalogs.engine_items(root)[0].contents[1].value)
    with pytest.raises((ValueError, TypeError)):
        engine_physics.patch_archive(original, name, changes)


def test_category_dwell_setters_reload_rows_and_preserve_unselected_categories():
    source = BJTU_DATA / "empty.trains"
    require_fixtures(source)
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    name = catalogs.text(
        catalogs.array(root.contents[1].value)[0].contents[1].value
    )
    values = {
        "stop_at_every_station_time_s": -30.0,
        "dwell_variation_early": 2.5,
        "dwell_variation_delayed": -0.0,
        "dwell_variation_early_unit_code": 0,
        "dwell_variation_delayed_unit_code": 1,
        "dwell_variation_early_delay_offset_s": 4.0,
        "dwell_variation_delayed_delay_offset_s": -3.0,
    }

    output, receipt = category_dwell.patch_archive(original, name, values)

    reloaded = category_dwell.read_archive(output, name)
    assert reloaded["stop_at_every_station_time_s"] == pytest.approx(0.0)
    assert reloaded["dwell_variation_early_delay_offset_s"] == pytest.approx(-1.0)
    assert reloaded["dwell_variation_delayed_delay_offset_s"] == pytest.approx(1.0)
    assert pack_float(reloaded["dwell_variation_delayed"]) == pack_float(-0.0)
    assert reloaded["dwell_variation_delayed_unit"] == "percent_of_planned_dwell"
    assert receipt["fresh_reload_verified"] is True
    assert receipt["native_application_tested"] is False
    assert len(receipt["changes"]) == len(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"stop_at_every_station_time_s": True},
        {"dwell_variation_early": float("nan")},
        {"dwell_variation_delayed": float("inf")},
        {"dwell_variation_early_unit_code": 1.0},
        {"dwell_variation_delayed_unit_code": 2**31},
        {"unknown": 1.0},
    ],
)
def test_category_dwell_rejects_outside_contract(changes):
    source = BJTU_DATA / "empty.trains"
    require_fixtures(source)
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    name = catalogs.text(
        catalogs.array(root.contents[1].value)[0].contents[1].value
    )
    with pytest.raises((ValueError, TypeError)):
        category_dwell.patch_archive(original, name, changes)


def test_edge_scalar_setters_reload_and_retain_graph_topology():
    source = READING_DOCUMENTS / "RDG.opentrack"
    require_fixtures(source)
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    models, by_id = route_factory.document(root)
    edge = next(item for item in models if writer.kind(item) == "OTEdgeModel")
    model_id = edge.contents[0].value
    before_fingerprint = writer.fingerprint(root)

    output, receipt = edge_operations.patch_edge_archive(
        original,
        model_id,
        {"length_m": 325, "radius_raw": 2500.25, "gradient_raw": -4.5},
    )

    assert original != output
    reloaded_root, _ = writer.load_next_compatible(output)
    reloaded_models, reloaded_by_id = route_factory.document(reloaded_root)
    reloaded = reloaded_by_id[model_id]
    assert reloaded.contents[9].values[1] == 325
    assert pack_float(float(reloaded.contents[9].values[2])) == pack_float(2500.25)
    assert pack_float(float(reloaded.contents[9].values[3])) == pack_float(-4.5)
    assert [item.contents[0].value for item in reloaded_models] == [
        item.contents[0].value for item in models
    ]
    assert receipt["whole_graph_expected_fields_only"] is True
    assert receipt["native_application_tested"] is False
    assert receipt["simulation_tested"] is False
    assert writer.fingerprint(root) == before_fingerprint


@pytest.mark.parametrize(
    "changes",
    [
        {"length_m": 1.0},
        {"length_m": 2**31},
        {"radius_raw": True},
        {"gradient_raw": float("nan")},
        {"gradient_raw": float("inf")},
        {"not_a_field": 1},
    ],
)
def test_edge_scalar_setters_reject_outside_contract(changes):
    source = READING_DOCUMENTS / "RDG.opentrack"
    require_fixtures(source)
    original = source.read_bytes()
    root, _ = writer.load_next_compatible(original)
    models, _ = route_factory.document(root)
    edge = next(item for item in models if writer.kind(item) == "OTEdgeModel")
    with pytest.raises((ValueError, TypeError)):
        edge_operations.patch_edge_archive(
            original,
            edge.contents[0].value,
            changes,
        )
