"""Registry adapter: no shared registry edits and no archive import at module load."""
from copy import deepcopy
try:
    from .connection_records import ConnectionRecordTools, APPLY_SCHEMA, UNDO_SCHEMA, INSPECT_SCHEMA, RecordError, validate
except ImportError:
    from connection_records import ConnectionRecordTools, APPLY_SCHEMA, UNDO_SCHEMA, INSPECT_SCHEMA, RecordError, validate


def tool_definitions(api_error):
    """Return (name, description, model-like, handler) tuples for one service lifetime.

    Pass the host APIError class. Keep these definitions alive for the transport
    session: the closure owns opaque, single-use undo snapshots.
    """
    service = ConnectionRecordTools()

    def model_for(schema):
        class Arguments:
            def __init__(self, values): self.values = deepcopy(values)

            @classmethod
            def model_json_schema(cls, *args, **kwargs): return deepcopy(schema)

            @classmethod
            def model_validate(cls, values, *args, **kwargs):
                try: validate(values, schema)
                except RecordError as exc: raise api_error('INVALID_ARGUMENTS', str(exc)) from exc
                return cls(values)

            def model_dump(self, *args, **kwargs): return deepcopy(self.values)
        return Arguments

    def handler_for(fn):
        def handler(params):
            try: return fn(**params.model_dump())
            except RecordError as exc: raise api_error(exc.code, str(exc)) from exc
        return handler

    return [
        ('opentrack_inspect_connection_records',
         'Validate JSON record structure and obtain the exact state version required for apply; not operational validation.',
         model_for(INSPECT_SCHEMA), handler_for(service.inspect)),
        ('opentrack_apply_connection_records',
         'Apply an atomic batch of audited connection data commands to JSON records; no native archive or runtime validation.',
         model_for(APPLY_SCHEMA), handler_for(service.apply), False, False),
        ('opentrack_undo_connection_records',
         'Restore a server-held connection snapshot only against its exact result state version; token is single-use.',
         model_for(UNDO_SCHEMA), handler_for(service.undo), False, False),
    ]
