"""Build, verify, extract, and smoke-test the complete distributable Skill."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
from tempfile import TemporaryDirectory
import zipfile


SKILL_NAME = "opentrack-network-rail"
MANIFEST_NAME = "RELEASE-MANIFEST.json"
SCHEMA = "opentrack-skill-payload-manifest/1"
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
EXCLUDED_NAMES = {
    "software-authorization.json",
}
PROHIBITED_SUFFIXES = {".dll", ".dylib", ".exe", ".pyd", ".pyc", ".so"}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def edition_metadata(source: Path) -> dict[str, object]:
    metadata = json.loads((source / "EDITION.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("EDITION.json must contain an object")
    return metadata


def package_version(source: Path) -> str:
    version = edition_metadata(source).get("paired_backend_protocol")
    if not isinstance(version, str) or not version:
        raise ValueError("EDITION.json has no paired_backend_protocol")
    return version


def payload_paths(source: Path) -> list[Path]:
    selected: list[Path] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or relative.name in EXCLUDED_NAMES:
            continue
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in PROHIBITED_SUFFIXES:
            raise ValueError(f"Native or generated binary is not distributable: {relative}")
        selected.append(path)
    return selected


def assert_frozen(
    source: Path,
    manifest: dict[str, object] | None = None,
) -> None:
    """Detect files changed or appeared after the manifest was written."""
    first = {
        path.relative_to(source).as_posix(): sha256(path.read_bytes())
        for path in payload_paths(source)
        if path.relative_to(source).as_posix() != MANIFEST_NAME
    }
    if manifest is not None:
        recorded = {name: entry["sha256"] for name, entry in manifest["files"].items()}
        if first != recorded:
            raise ValueError("Payload changed after the release manifest was written")
    time.sleep(0.05)
    second = {
        path.relative_to(source).as_posix(): sha256(path.read_bytes())
        for path in payload_paths(source)
        if path.relative_to(source).as_posix() != MANIFEST_NAME
    }
    if first != second:
        raise ValueError("Payload changed during release packaging")


def assert_safe_member(name: str) -> None:
    member = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or member.is_absolute()
        or ".." in member.parts
        or member.parts[0] != SKILL_NAME
    ):
        raise ValueError(f"Unsafe ZIP member: {name!r}")


def build_manifest(
    source: Path,
    paths: list[Path],
    distribution_version: str,
) -> Path:
    manifest_path = source / MANIFEST_NAME
    if manifest_path.exists():
        raise FileExistsError(
            "Manifest already exists in the manifest build root; refusing to overwrite it"
        )

    files = {
        path.relative_to(source).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()),
        }
        for path in paths
        if path != manifest_path
    }
    metadata = edition_metadata(source)
    manifest = {
        "schema": SCHEMA,
        "edition": metadata.get("edition", "maintained"),
        "name": SKILL_NAME,
        "version": package_version(source),
        "distribution_version": distribution_version,
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


def verify_manifest(
    source: Path,
    paths: list[Path],
    manifest_path: Path,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        path.relative_to(source).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()),
        }
        for path in paths
        if path != manifest_path
    }
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Release manifest schema mismatch")
    if manifest.get("name") != SKILL_NAME:
        raise ValueError("Release manifest Skill identity mismatch")
    if manifest.get("version") != package_version(source):
        raise ValueError("Release manifest version mismatch")
    if manifest.get("files") != expected:
        raise ValueError("Release manifest file collection or hashes mismatch")
    assert_frozen(source, manifest)
    return manifest


def assert_replaceable_manifest(path: Path) -> None:
    """Accept an existing manifest only when it is this Skill's prior release."""
    if not path.exists():
        return
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "Existing release manifest is not valid UTF-8 JSON"
        ) from error
    if (
        not isinstance(previous, dict)
        or previous.get("schema") != SCHEMA
        or previous.get("name") != SKILL_NAME
    ):
        raise ValueError(
            "Existing release manifest is not a recognized previous release"
        )


def verify_archive(
    archive_path: Path,
    source: Path,
    paths: list[Path],
    manifest_path: Path,
) -> dict[str, object]:
    expected = {
        f"{SKILL_NAME}/{path.relative_to(source).as_posix()}": path.read_bytes()
        for path in paths
    }
    expected[f"{SKILL_NAME}/{MANIFEST_NAME}"] = manifest_path.read_bytes()
    with zipfile.ZipFile(archive_path, "r") as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC verification failed")
        members = archive.namelist()
        if len(members) != len(set(members)):
            raise ValueError("ZIP contains duplicate member names")
        for member in members:
            assert_safe_member(member)
        if set(members) != set(expected):
            raise ValueError("ZIP member set differs from frozen payload set")
        for member, raw in expected.items():
            if archive.read(member) != raw:
                raise ValueError(f"ZIP member bytes mismatch: {member}")
    computed_digest = sha256(archive_path.read_bytes())
    return {
        "entries": len(expected),
        "payload_files": len(expected) - 1,
        "sha256": computed_digest,
    }


def run_smoke(
    runtime: Path,
    skill: Path,
    *,
    profile: str,
) -> dict[str, object]:
    backend = skill / "backend" / "OTAI"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(backend),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    command = [
        str(runtime),
        "-u",
        "-X",
        "utf8",
        "-B",
        str(backend / "server.py"),
        "--root",
        str(skill),
        "--profile",
        profile,
        "tools",
    ]
    completed = subprocess.run(
        command,
        cwd=skill,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Packaged {profile} tool listing failed: {completed.stderr.strip()}"
        )
    result = json.loads(completed.stdout)
    tools = result.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"Packaged {profile} profile exposes no tools")
    names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    required_by_profile = {
        "ai": {
            "opentrack_get_railway_capabilities",
            "opentrack_compile_railway_plan",
            "opentrack_inspect_railway",
            "opentrack_apply_railway_plan",
            "opentrack_verify_railway_outcomes",
            "opentrack_validate_reality_station_plan",
        },
        "generation": {
            "opentrack_edit_named_distribution_lifecycle",
            "opentrack_build_reference_platform_corridor",
            "opentrack_edit_current_stock_fields",
        },
        "all": {
            "opentrack_edit_named_distribution_lifecycle",
            "opentrack_build_reference_platform_corridor",
            "opentrack_edit_current_stock_fields",
        },
    }
    required = required_by_profile[profile]
    missing = required - names
    if missing:
        raise ValueError(
            f"Packaged {profile} profile lacks required tools: {sorted(missing)}"
        )
    return {"profile": profile, "tool_count": len(tools), "required_present": True}


def stage_source(
    source: Path,
    target: Path,
) -> tuple[Path, dict[str, str]]:
    snapshot: dict[str, str] = {}
    for path in payload_paths(source):
        relative = path.relative_to(source)
        if relative.as_posix() == MANIFEST_NAME:
            continue
        before = sha256(path.read_bytes())
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        after = sha256(path.read_bytes())
        if before != after:
            raise ValueError(f"Source changed while staging: {relative.as_posix()}")
        if sha256(destination.read_bytes()) != before:
            raise ValueError(f"Staged copy hash mismatch: {relative.as_posix()}")
        snapshot[relative.as_posix()] = before
    return target, snapshot


def assert_source_unchanged(
    source: Path,
    snapshot: dict[str, str],
) -> None:
    current = {
        path.relative_to(source).as_posix(): sha256(path.read_bytes())
        for path in payload_paths(source)
        if path.relative_to(source).as_posix() != MANIFEST_NAME
    }
    if current != snapshot:
        raise ValueError("Source payload changed during release construction")


def tree_sha256(hashes: dict[str, str]) -> str:
    payload = b"".join(
        name.encode("utf-8") + b"\0" + digest.encode("ascii") + b"\n"
        for name, digest in sorted(hashes.items())
    )
    return sha256(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--distribution-version")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output_directory.resolve()
    runtime = args.runtime.resolve()
    if output.is_relative_to(source):
        raise ValueError("Release output directory must be outside the source Skill")
    if not source.is_dir():
        raise FileNotFoundError(source)
    if not runtime.is_file():
        raise FileNotFoundError(runtime)
    output.mkdir(parents=True, exist_ok=True)

    metadata = edition_metadata(source)
    version = package_version(source)
    distribution_version = (
        args.distribution_version
        or f"{date.today().isoformat()}-{metadata.get('edition', 'maintained')}-{version}"
    )
    paths = [
        path for path in payload_paths(source)
        if path.relative_to(source).as_posix() != MANIFEST_NAME
    ]
    if not any(path.relative_to(source).as_posix().startswith("backend/OTAI/") for path in paths):
        raise ValueError("Packaged payload has no backend/OTAI content")

    archive_name = f"{SKILL_NAME}-{distribution_version}.zip"
    bundle_name = f"{SKILL_NAME}-{distribution_version}"
    staged_bundle = output / f".{bundle_name}.staging"
    final_bundle = output / bundle_name
    if staged_bundle.exists() or final_bundle.exists():
        raise FileExistsError(
            f"Refusing to replace existing release bundle: {staged_bundle}, {final_bundle}"
        )
    staged_bundle.mkdir()
    target = staged_bundle / archive_name
    checksum = staged_bundle / f"{archive_name}.sha256"
    report_path = staged_bundle / f"{archive_name}.verification.json"
    manifest_install = source / MANIFEST_NAME
    assert_replaceable_manifest(manifest_install)

    try:
        with TemporaryDirectory(prefix="skill-package-", dir=staged_bundle) as temporary:
            staged_root = Path(temporary)
            snapshot_root, snapshot = stage_source(source, staged_root / "source")
            source_tree_sha256 = tree_sha256(snapshot)
            manifest_path = build_manifest(snapshot_root, payload_paths(snapshot_root), distribution_version)
            snapshot_paths = payload_paths(snapshot_root)
            manifest = verify_manifest(snapshot_root, snapshot_paths, manifest_path)
            manifest_sha256 = sha256(manifest_path.read_bytes())
            assert_source_unchanged(source, snapshot)
            installed_manifest = manifest_path.read_bytes()
            staged = staged_root / archive_name
            with zipfile.ZipFile(
                staged,
                "x",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for path in snapshot_paths:
                    if path.name == MANIFEST_NAME:
                        continue
                    archive.write(
                        path,
                        f"{SKILL_NAME}/{path.relative_to(snapshot_root).as_posix()}",
                    )
                archive.write(
                    manifest_path,
                    f"{SKILL_NAME}/{MANIFEST_NAME}",
                )
            archive_paths = payload_paths(snapshot_root)
            receipt = verify_archive(staged, snapshot_root, archive_paths, manifest_path)

            extracted_root = staged_root / "extract"
            extracted_root.mkdir()
            with zipfile.ZipFile(staged, "r") as archive:
                archive.extractall(extracted_root)
            extracted = extracted_root / SKILL_NAME
            extracted_manifest = extracted / MANIFEST_NAME
            extracted_paths = payload_paths(extracted)
            verify_manifest(extracted, extracted_paths, extracted_manifest)
            smoke = {
                profile: run_smoke(runtime, extracted, profile=profile)
                for profile in ("ai", "generation", "all")
            }
            assert_source_unchanged(source, snapshot)
            checked_snapshot = {
                path.relative_to(snapshot_root).as_posix(): sha256(path.read_bytes())
                for path in payload_paths(snapshot_root)
                if path.relative_to(snapshot_root).as_posix() != MANIFEST_NAME
            }
            if checked_snapshot != snapshot:
                raise ValueError("Frozen staging snapshot changed during release construction")
            shutil.copyfile(staged, target)
    except BaseException:
        shutil.rmtree(staged_bundle, ignore_errors=True)
        raise

    digest = sha256(target.read_bytes())
    if digest != receipt["sha256"]:
        shutil.rmtree(staged_bundle, ignore_errors=True)
        raise ValueError("Committed ZIP digest differs from verified staged ZIP")
    checksum.write_text(
        f"{digest}  {archive_name}\n",
        encoding="ascii",
    )
    checksum_digest = checksum.read_text(encoding="ascii").split()[0]
    if checksum_digest != digest:
        shutil.rmtree(staged_bundle, ignore_errors=True)
        raise ValueError("Checksum sidecar does not bind committed ZIP")
    report = {
        "archive": str(final_bundle / archive_name),
        "checksum_file": str(final_bundle / checksum.name),
        "distribution_version": distribution_version,
        "source_tree_sha256": source_tree_sha256,
        "manifest_sha256": manifest_sha256,
        "manifest_files": len(manifest["files"]),
        "zip": receipt,
        "checksum_verified": True,
        "extracted_manifest_verified": True,
        "smoke": smoke,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "native_gui_verified": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    assert_source_unchanged(source, snapshot)

    installed_manifest = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    try:
        if final_bundle.exists():
            raise FileExistsError(f"Release bundle appeared during construction: {final_bundle}")
        staged_bundle.rename(final_bundle)
    except BaseException:
        shutil.rmtree(staged_bundle, ignore_errors=True)
        raise

    manifest_install.write_bytes(installed_manifest)
    if sha256(manifest_install.read_bytes()) != manifest_sha256:
        manifest_install.unlink(missing_ok=True)
        raise ValueError("Installed root manifest hash does not match frozen manifest")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
