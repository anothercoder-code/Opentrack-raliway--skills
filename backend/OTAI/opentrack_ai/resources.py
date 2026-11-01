"""Verified native serialization blueprints; no executable/process dependency."""
import json
from pathlib import Path

from .archive import APIError,digest,w


EXPECTED_SHAPES_SHA256='8ee95dbc78c84211cfbea472bcd2c6bae55c68abf8a6f7ce721d541aeed53e07'


def templates(root):
    folder=Path(root)/'OTAI/resources';path=folder/'native-shapes.archive'
    if not path.is_file():
        folder=Path(__file__).resolve().parents[1]/'resources';path=folder/'native-shapes.archive'
    if not path.is_file():raise APIError('NATIVE_SHAPES_MISSING','Install the bundled sanitized archive blueprints.',str(path))
    raw=path.read_bytes()
    if digest(raw)!=EXPECTED_SHAPES_SHA256:raise APIError('NATIVE_SHAPES_CHANGED','Bundled serialization blueprints changed; verify and rebuild their contract before editing.')
    obj,version=w.load_next_compatible(raw);result={w.kind(o):o for o in w.elements(obj)}
    metadata=json.loads((folder/'native-shapes.json').read_text(encoding='utf8'))
    if metadata['sha256']!=digest(raw) or version!=metadata['stream_version']:raise APIError('NATIVE_SHAPES_CHANGED','Blueprint metadata and archive fingerprint disagree.')
    return result,version
