"""Publish scoped outputs from the operating-data candidate generators."""
from ..errors import APIError


def save_candidate(tools, args, source, original, output, result, *, extension, dependencies=None):
    """Retain preview behavior or save a freshly validated archive copy."""
    if args.preview_only:
        return result
    if tools.path(args.target_path).suffix.casefold() != extension:
        raise APIError('ARCHIVE_TARGET_EXTENSION', f'Use an explicit new {extension} target')
    return tools.save_copy(
        source, original, output, result, args.target_path, additional_inputs=dependencies,
    )
