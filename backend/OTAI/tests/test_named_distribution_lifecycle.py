"""Current Distribution lifecycle and run-bound consumer regression."""

from pathlib import Path
import hashlib

import pytest

from opentrack_ai import license_authorization
from opentrack_ai.current_archive import (
    catalogs as c,
    course_factories as cf,
    distribution_references as refs,
    named_distributions as nd,
    writer,
)
from opentrack_ai.current_archive.incident_operations import SCHEMA
from opentrack_ai.current_archive.zero_generation import (
    native_signal_routes as native,
)
from opentrack_ai.registry import Registry
from opentrack_ai.service import Service


SOURCE = Path(
    r"D:\opentrack\OTProjects\EmptyProject\OTData\empty.courses"
)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def record(kind, version, layout, values=None):
    default = {"@": None, "f": 0.0, "i": 0}
    values = values or {}
    return native.obj(
        [(kind, version), ("NSObject", 0)],
        [
            (encoding, values.get(index, [default[x] for x in encoding]))
            for index, encoding in enumerate(layout)
        ],
    )


def dictionary(rows):
    return native.obj(
        [
            ("NSMutableDictionary", 0),
            ("NSDictionary", 0),
            ("NSObject", 0),
        ],
        [("i", [len(rows)])]
        + [
            group
            for key, row in rows.items()
            for group in (("@", [native.string(key)]), ("@", [row]))
        ],
    )


def timetable(distribution_name):
    row = record(
        "OTTimetable",
        9,
        cf.TT,
        {
            0: [17],
            1: [native.string("C01")],
            2: [native.string("0")],
            3: [0],
            4: [0],
            5: [native.string("RDG")],
            6: [native.string("10:00:00")],
            7: [native.string("10:02:00")],
            8: [native.string("120")],
            9: [native.arr()],
            10: [1],
            12: [native.string("0")],
            13: [native.string("HH:MM:SS")],
            14: [native.string("HH:MM:SS")],
            16: [native.string(distribution_name)],
            18: [native.string("P9")],
        },
    )
    return writer.dump_verified(dictionary({"C01#0": row}))


def course_catalog():
    root, _ = writer.load_next_compatible(SOURCE.read_bytes())
    course = record(
        "OTCourse",
        11,
        c.LAYOUTS["OTCourse"][1],
        {0: [native.string("C01")], 5: [1]},
    )
    incident = record(
        "OTIncident",
        12,
        SCHEMA,
        {
            0: [native.string("Delay event")],
            1: [native.string("C01")],
            2: [native.string("0")],
            3: [native.string("10:00:00")],
            4: [native.string("10:05:00")],
            5: [-1, -1, 1],
            6: [0.0, 1.0, 0.0, 0.0],
            7: [1],
            8: [native.string("")],
            9: [native.string("")],
            10: [native.string("")],
            11: [native.string("")],
            12: [native.string("")],
            13: [native.string("")],
            15: [0, 0],
            16: [native.string("")],
            18: [native.string("Experiment 1")],
            19: [100.0],
            20: [native.arr()],
            21: [native.string("")],
            22: [100.0],
            23: [native.string("")],
            24: [-1.0],
        },
    )
    writer.set_elements(root.contents[1].value, [incident])
    writer.set_elements(root.contents[4].value, [course])
    return writer.dump_verified(root, 1000)


def source(tmp_path, relative, blob):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return {"path": relative, "sha256": sha(blob)}


def project(tmp_path, *, with_timetable_reference=True):
    courses = course_catalog()
    table = timetable("Uniform 30-50" if with_timetable_reference else "")
    run = (
        b"CourseFile#OTData/empty.courses#\n"
        b"TimetableFile#OTData/empty.timetable#\n"
    )
    return {
        "courses": source(
            tmp_path,
            "OTAI/workspaces/distribution-lifecycle/OTData/empty.courses",
            courses,
        ),
        "timetable": source(
            tmp_path,
            "OTAI/workspaces/distribution-lifecycle/OTData/empty.timetable",
            table,
        ),
        "run": source(tmp_path, "OTAI/workspaces/distribution-lifecycle/a.run", run),
    }


def update_project_hashes(files, tmp_path):
    for role in ("courses", "timetable", "run"):
        blob = (tmp_path / files[role]["path"]).read_bytes()
        files[role]["sha256"] = sha(blob)
    return files


def corrupt_timetable_root(tmp_path, files):
    table = tmp_path / files["timetable"]["path"]
    table.write_bytes(b"not a typedstream")
    return update_project_hashes(files, tmp_path)


def replace_problematic_table(tmp_path, files):
    table = tmp_path / files["timetable"]["path"]
    table.write_bytes(timetable(""))
    return update_project_hashes(files, tmp_path)


def request(files, operation, *, preview_only=True):
    return {
        "source": files["courses"],
        "policy": "piecewise_linear_guard",
        "audit": {
            "project_run": files["run"],
            "catalogs": {
                "courses": files["courses"],
                "timetable": files["timetable"],
            },
        },
        "operation": operation,
        "preview_only": preview_only,
    }


def test_native_default_create_rename_and_delete_preserve_unrelated_graph():
    original = SOURCE.read_bytes()
    created, create_report = nd.transform(
        original,
        "create",
        template_name=None,
        new_name="Native Default",
        current_class="OTDistribution:1",
        mode="new",
        intervals=None,
        policy="piecewise_linear_guard",
    )
    fresh, _ = writer.load_next_compatible(created)
    created_record = nd.catalog(fresh)["Native Default"]
    assert created_record.contents[1].value == 1
    rows = nd.interval_array(created_record.contents[2].value)[1]
    assert [list(row.contents[0].values) for row in rows] == [[0.0, 0.0, 100.0]]

    renamed, rename_report = nd.transform(
        created,
        "rename",
        name="Native Default",
        new_name="Renamed Default",
        policy="piecewise_linear_guard",
        external_consumer_policy="require_unreferenced",
        audit_run_blob=b"CourseFile#empty.courses#\n",
    )
    fresh, _ = writer.load_next_compatible(renamed)
    assert "Renamed Default" in nd.catalog(fresh)
    assert "Native Default" not in nd.catalog(fresh)
    assert rename_report["existing_timetable_or_incident_references_retargeted"] is False

    deleted, delete_report = nd.transform(
        renamed,
        "delete",
        name="Renamed Default",
        policy="piecewise_linear_guard",
        external_consumer_policy="require_unreferenced",
        audit_run_blob=b"CourseFile#empty.courses#\n",
    )
    fresh, _ = writer.load_next_compatible(deleted)
    assert "Renamed Default" not in nd.catalog(fresh)
    assert delete_report["audited_run_sha256"] == sha(
        b"CourseFile#empty.courses#\n"
    )


def test_bound_audit_rejects_delete_and_registered_rename_is_atomic(tmp_path):
    files = update_project_hashes(project(tmp_path), tmp_path)
    license_authorization.record_authorization(
        tmp_path,
        user_statement="I confirm a valid full OpenTrack licence for this local test.",
        user_scope="Automated local regression",
        purpose="Verify Distribution reference-gated lifecycle writes.",
    )
    registry = Registry(Service(tmp_path, False, False), profile="all")
    tool = registry.tools["opentrack_edit_named_distribution_lifecycle"]

    with pytest.raises(Exception, match="known Timetable/Incident consumer"):
        tool.handler(
            tool.model.model_validate(
                request(files, {"action": "delete", "name": "Uniform 30-50"})
            )
        )
    with pytest.raises(Exception, match="known Timetable/Incident consumer"):
        tool.handler(
            tool.model.model_validate(
                request(
                    files,
                    {
                        "action": "rename",
                        "name": "Experiment 1",
                        "new_name": "Incident renamed",
                    },
                )
            )
        )

    preview = tool.handler(
        tool.model.model_validate(
            request(
                files,
                {
                    "action": "rename",
                    "name": "Duration Distribution 1",
                    "new_name": "Duration renamed",
                },
            )
        )
    )
    assert preview["saved"] is False
    assert preview["change_report"]["existing_timetable_or_incident_references_retargeted"] is False

    saved = tool.handler(
        tool.model.model_validate(
            {
                **request(
                    files,
                    {
                        "action": "rename",
                        "name": "Duration Distribution 1",
                        "new_name": "Duration renamed",
                    },
                    preview_only=False,
                ),
                "target_path": (
                    "OTAI/workspaces/distribution-lifecycle/OTData/renamed.courses"
                ),
            }
        )
    )
    assert saved["saved"] is True
    source_path = tmp_path / files["courses"]["path"]
    assert sha(source_path.read_bytes()) == files["courses"]["sha256"]
    target = tmp_path / saved["target_path"]
    assert sha(target.read_bytes()) == saved["output_sha256"]
    cold, _ = writer.load_next_compatible(target.read_bytes())
    assert "Duration renamed" in nd.catalog(cold)


def test_unreferenced_rename_lifecycle_and_second_save_target_exists(
    tmp_path,
):
    files = update_project_hashes(project(tmp_path), tmp_path)
    license_authorization.record_authorization(
        tmp_path,
        user_statement="I confirm a valid full OpenTrack licence for this local test.",
        user_scope="Automated local regression",
        purpose="Verify Distribution reference-gated lifecycle writes.",
    )
    registry = Registry(Service(tmp_path, False, False), profile="all")
    tool = registry.tools["opentrack_edit_named_distribution_lifecycle"]
    operation = {"action": "rename", "name": "Uniform 30-50", "new_name": "Used renamed"}
    with pytest.raises(Exception, match="known Timetable/Incident consumer"):
        tool.handler(tool.model.model_validate(request(files, operation)))

    files = replace_problematic_table(tmp_path, files)
    preview = tool.handler(
        tool.model.model_validate(
            request(
                files,
                {
                    "action": "rename",
                    "name": "Duration Distribution 1",
                    "new_name": "Unused renamed",
                },
            )
        )
    )
    assert preview["saved"] is False
    # The project still contains a reference to another Distribution. The
    # lifecycle audit reports that consumer, while allowing this rename because
    # the selected target has no known reference.
    assert preview["change_report"]["lifecycle_audit"]["known_reference_count"] == 1
    assert preview["change_report"]["lifecycle_audit"]["known_references"] == [
        {
            "catalog": "courses",
            "object_key": "0",
            "identity": "Delay event",
            "class": "OTIncident",
            "group": 18,
            "field": "durationDistributionName",
            "name": "Experiment 1",
        }
    ]
    target = "OTAI/workspaces/distribution-lifecycle/OTData/renamed-unused.courses"
    saved = tool.handler(
        tool.model.model_validate(
            {
                **request(
                    files,
                    {
                        "action": "rename",
                        "name": "Duration Distribution 1",
                        "new_name": "Unused renamed",
                    },
                    preview_only=False,
                ),
                "target_path": target,
            }
        )
    )
    assert saved["saved"] is True
    assert sha((tmp_path / files["courses"]["path"]).read_bytes()) == files["courses"]["sha256"]
    cold, _ = writer.load_next_compatible((tmp_path / target).read_bytes())
    assert "Unused renamed" in nd.catalog(cold)
    with pytest.raises(Exception, match="Target exists"):
        tool.handler(
            tool.model.model_validate(
                {
                    **request(
                        files,
                        {
                            "action": "rename",
                            "name": "Duration Distribution 1",
                            "new_name": "Unused renamed again",
                        },
                        preview_only=False,
                    ),
                    "target_path": target,
                }
            )
        )
    with pytest.raises(Exception, match="known Timetable/Incident consumer"):
        tool.handler(
            tool.model.model_validate(
                request(
                    files,
                    {"action": "delete", "name": "Experiment 1"},
                )
            )
        )


def test_unreferenced_delete_registered_save_and_independent_reload(tmp_path):
    files = update_project_hashes(project(tmp_path), tmp_path)
    courses_path = tmp_path / files["courses"]["path"]
    courses, version = writer.load_next_compatible(courses_path.read_bytes())
    writer.set_elements(
        courses.contents[3].value,
        [
            row
            for row in c.array(courses.contents[3].value)
            if c.text(row.contents[0].value) != "Uniform 30-50"
        ],
    )
    courses_path.write_bytes(writer.dump_verified(courses, version))
    files = replace_problematic_table(tmp_path, files)
    license_authorization.record_authorization(
        tmp_path,
        user_statement="I confirm a valid full OpenTrack licence for this local test.",
        user_scope="Automated local regression",
        purpose="Verify Distribution reference-gated lifecycle writes.",
    )
    registry = Registry(Service(tmp_path, False, False), profile="all")
    tool = registry.tools["opentrack_edit_named_distribution_lifecycle"]
    target = "OTAI/workspaces/distribution-lifecycle/OTData/deleted-unused.courses"
    result = tool.handler(
        tool.model.model_validate(
            {
                **request(
                    files,
                    {"action": "delete", "name": "Duration Distribution 1"},
                    preview_only=False,
                ),
                "target_path": target,
            }
        )
    )
    assert result["saved"] is True
    assert sha(courses_path.read_bytes()) == files["courses"]["sha256"]
    cold, _ = writer.load_next_compatible((tmp_path / target).read_bytes())
    assert "Duration Distribution 1" not in nd.catalog(cold)


def test_catalog_parse_boundary_blocks_lifecycle_authorization(tmp_path):
    files = corrupt_timetable_root(
        tmp_path, update_project_hashes(project(tmp_path), tmp_path)
    )
    license_authorization.record_authorization(
        tmp_path,
        user_statement="I confirm a valid full OpenTrack licence for this local test.",
        user_scope="Automated local regression",
        purpose="Verify Distribution parser boundaries block lifecycle writes.",
    )
    registry = Registry(Service(tmp_path, False, False), profile="all")
    tool = registry.tools["opentrack_edit_named_distribution_lifecycle"]
    with pytest.raises(Exception, match="malformed typedstream"):
        tool.handler(
            tool.model.model_validate(
                request(
                    files,
                    {
                        "action": "rename",
                        "name": "Duration Distribution 1",
                        "new_name": "Must not rename",
                    },
                )
            )
        )
