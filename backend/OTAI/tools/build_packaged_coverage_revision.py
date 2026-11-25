"""Explicit build-time metadata refresh, never invoked by a read tool."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
from opentrack_ai import __version__


paths = list((ROOT / "opentrack_ai").rglob("*.py"))
paths += [
    ROOT / "server.py",
    SKILL_ROOT / "scripts" / "ot.py",
]
paths += [
    ROOT / "replica" / name
    for name in (
        "requirements.json",
        "current-function-coverage.json",
        "rebuild-interface-matrix.json",
    )
]

missing = [str(path) for path in paths if not path.is_file()]
if missing:
    raise FileNotFoundError("Coverage inputs are missing: " + ", ".join(missing))

input_hashes = {
    path.relative_to(SKILL_ROOT).as_posix():
    hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(paths)
}
content_sha256 = hashlib.sha256(
    json.dumps(
        {"interface_version": __version__, "input_hashes": input_hashes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
report = {
    "schema_version": 1,
    "interface_version": __version__,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "content_sha256": content_sha256,
    "path_root": "skill",
    "scope": (
        "Package code/report freshness only; metadata does not re-certify "
        "native behavior"
    ),
    "input_hashes": input_hashes,
}
target = ROOT / "replica" / "packaged-coverage-revision.json"
target.write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)
print(
    "Refreshed explicit package coverage revision:",
    len(report["input_hashes"]),
    "inputs",
    report["content_sha256"],
)
