"""Fresh Windows publication for prevalidated native project candidates."""

import os
from pathlib import PurePosixPath

from pydantic import StrictBool, model_validator

from ..errors import APIError
from ..json_safe import checked_json
from .tools import Input, PathText
from .zero_operations import run_bundle as rb


class ProjectSave(Input):
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode="after")
    def explicit_target(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError("Saving requires an explicit fresh target_directory")
        return self


def project_target(tools, args, execution_root=None):
    if args.target_directory is None:
        return None
    target = tools.path(args.target_directory)
    if not args.preview_only and os.name != "nt":
        raise APIError("UNSUPPORTED_SECURE_FILESYSTEM", "Project publication requires Windows x64 local NTFS")
    try:
        final_root = rb.root_path(target.as_posix(), "windows")
        if execution_root is not None and rb.root_path(execution_root, "windows").casefold() != final_root.casefold():
            raise ValueError("Run execution root differs from the publication target")
    except (TypeError, ValueError) as exc:
        raise APIError("PROJECT_TARGET_BINDING", str(exc)) from exc
    return target


def require_external_target(target, source):
    if target is not None and target.is_relative_to(source):
        raise APIError("PROJECT_TARGET_BINDING", "Publication target must be outside the source project's inventory")


def _run_bindings(files, root, require_run):
    from .prepare_contract.auxiliary import records, set_bindings

    runs = [name for name in files if name.endswith(".run")]
    if not require_run and not runs:
        return ()
    if len(runs) != 1:
        raise ValueError("Exactly one run file is required in a complete project candidate")
    rows = records(files[runs[0]])
    bindings = {key: [] for key in rb.PATH_KEYS}
    for key, value, _ in rows:
        if key not in bindings:
            continue
        value = rb.root_path(value, "windows")
        if not value.casefold().startswith(root.casefold() + "/"):
            raise ValueError(f"{key} is outside the actual publication target")
        relative = rb.relative(value[len(root) + 1:])
        if key != "OutputPath" and relative not in files:
            raise ValueError(f"{key} does not resolve to a published member: {relative}")
        bindings[key].append(relative)
    catalogs = {}
    for role, key in rb.CATALOG_KEYS.items():
        paths = bindings[key]
        if len(paths) != 1:
            raise ValueError(f"{key} requires exactly one bound native catalog")
        catalogs[role] = paths[0]
    set_bindings(rows, {value for key, value, _ in rows if key in ("Infrastructure Document", "Train Diagram Document")})
    output = bindings["OutputPath"]
    if len(output) != 1:
        raise ValueError("Exactly one empty output directory is required")
    rb._layout(
        {name: blob for name, blob in files.items() if name != runs[0]},
        catalogs, bindings["Infrastructure Document"], bindings["Train Diagram Document"], output[0],
    )
    return tuple(output)


def publish_candidate(tools, target, members, result, recheck, *, require_run=True):
    from .windows_publish import publish_project
    from .writer import load_next_compatible

    final_root = rb.root_path(target.as_posix(), "windows")

    def validate(files):
        try:
            if files != members:
                raise ValueError("Readback differs from the reviewed native candidate")
            for name, blob in files.items():
                rb.relative(name)
                if PurePosixPath(name).suffix != ".run":
                    load_next_compatible(blob)
            return _run_bindings(files, final_root, require_run)
        except (IndexError, OverflowError, TypeError, ValueError) as exc:
            raise APIError("PROJECT_PUBLICATION_VERIFY", "Native project candidate or readback failed validation", str(exc)) from exc

    output_directories = validate(members)
    result = checked_json(result)
    receipt = publish_project(
        tools.root, target, members, recheck=recheck, validate_bundle=validate,
        empty_directories=output_directories,
    )
    return {
        **result, "preview_only": False, "saved": True,
        "publication_review_pending": False, "publication": receipt,
        "target_directory": receipt["target_directory"],
    }
