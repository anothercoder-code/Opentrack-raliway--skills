"""Bind the semantic publication gateway to the current Registry instance."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from .models import InvokeRailwayWriterRequest
from .publication import publish


_REGISTRY: ContextVar[Any | None] = ContextVar(
    "opentrack_semantic_registry",
    default=None,
)


def bind(registry):
    _REGISTRY.set(registry)


def publish_request(args: InvokeRailwayWriterRequest):
    registry = _REGISTRY.get()
    if registry is None:
        raise RuntimeError("Semantic publication gateway is not bound to a Registry.")
    return publish(
        args,
        registered_tools=registry._writer_tools,
        dispatch=registry.dispatch_writer,
    )


def publish(args: InvokeRailwayWriterRequest):
    return publish_request(args)

