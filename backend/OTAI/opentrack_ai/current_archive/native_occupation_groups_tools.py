"""Read and edit a bounded native occupation group worksheet."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr

from . import native_occupation_groups as groups
from .bundle_tools import Source
from .next_tools import NextFunctions, Ordinal, Save
from .tools import Input
from ..errors import APIError


Name = Annotated[StrictStr, Field(pattern=f'^{groups.SAFE_NAME}$')]
Edges = Annotated[list[Ordinal], Field(min_length=1, max_length=10000)]


class InspectGroups(Input):
    source: Source


class CreateGroup(Input):
    action: Literal['create']
    name: Name
    edge_ids: Edges
    selected: StrictBool = True


class UpdateGroup(Input):
    action: Literal['update']
    name: Name
    edge_ids: Edges | None = None
    selected: StrictBool | None = None


Operation = Annotated[CreateGroup | UpdateGroup, Field(discriminator='action')]


class EditGroups(Save):
    source: Source
    operations: Annotated[list[Operation], Field(min_length=1, max_length=96)]


class OccupationGroupTools(NextFunctions):
    def inspect_groups(self, args):
        path, _, root, _ = self.checked(args.source)
        if path.suffix.lower() != '.opentrack':
            raise APIError('OCCUPATION_PROJECT_PATH', 'Use a native .opentrack worksheet')
        try:
            result = groups.records(root, path.stem)
        except (ValueError, TypeError, IndexError, AttributeError) as exc:
            raise APIError('OCCUPATION_GROUP_INVALID', str(exc)[:500]) from exc
        return {'source': args.source.model_dump(), 'groups': result, 'read_only': True}

    def edit_groups(self, args):
        path, original, _, _ = self.checked(args.source)
        if path.suffix.lower() != '.opentrack' or (args.target_path and self.path(args.target_path).suffix.lower() != '.opentrack'):
            raise APIError('OCCUPATION_PROJECT_PATH', 'Use native .opentrack worksheets')
        try:
            operations = [operation.model_dump(exclude_none=True) for operation in args.operations]
            output, report = groups.transform(original, path.stem, operations)
        except (ValueError, TypeError, IndexError, AttributeError, OverflowError) as exc:
            raise APIError('OCCUPATION_GROUP_INVALID', str(exc)[:500]) from exc
        return self.finish(args, path, original, output, report)


def tool_definitions(root):
    service = OccupationGroupTools(root)
    return [
        ('opentrack_inspect_occupation_groups',
         'Inspect names, local Edge IDs, saved selections and unresolved members of native worksheet occupation groups.',
         InspectGroups, service.inspect_groups),
        ('opentrack_edit_occupation_groups',
         'Create native multi-Edge occupation monitor groups or update their selected state and Edge IDs in a fresh worksheet copy.',
         EditGroups, service.edit_groups, False, False),
    ]
