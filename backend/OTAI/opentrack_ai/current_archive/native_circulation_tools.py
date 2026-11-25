"""Public audit for a chain of native Through or Turning Courses."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool

from ..errors import APIError
from .native_interlocking_tools import InterlockingCourse, Resource
from .native_result_tools import EvaluateNativeRunTools
from .tools import Input, PathText


class Movement(Input):
    movement: Literal['reverse', 'continue']
    resource: Resource
    crosses_midnight: StrictBool | None = Field(
        default=None, description='Require that the original predecessor arrival and successor departure are on different days.',
    )


class VerifyCirculation(Input):
    output_directory: PathText
    evidence_directory: PathText
    mode: Literal['linked', 'unlinked']
    courses: Annotated[list[InterlockingCourse], Field(min_length=2, max_length=64)]
    connections: Annotated[list[Movement], Field(min_length=1, max_length=63)]


class CirculationTools(EvaluateNativeRunTools):
    def verify(self, args):
        from .native_circulation import audit
        from .native_run_evaluation import read_receipts

        try:
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            request = args.model_dump(exclude={'output_directory', 'evidence_directory'}, exclude_none=True)
            return audit(output, evidence, request, secure_bytes=self.secure_bytes)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_CIRCULATION_INVALID', 'Could not verify the bound original stock circulation',
                           str(exc)[:500]) from exc


def tool_definitions(root):
    service = CirculationTools(root)
    return [('opentrack_verify_native_turnround_chain',
             'Verify an ordered native formation circulation or unlinked control using frozen reciprocal '
             'timetable connections, directed termini, original activation, idle-to-motion and occupancy. Read only.',
             VerifyCirculation, service.verify)]
