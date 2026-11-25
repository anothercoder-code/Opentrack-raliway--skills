"""Public original-output audit for saved platform preferences."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool

from ..errors import APIError
from .native_interlocking_tools import InterlockingCourse, Resource
from .native_result_tools import EvaluateNativeRunTools, Name
from .tools import Input, PathText


class Platform(Input):
    itinerary: Name
    resource: Resource


class Availability(Input):
    course: InterlockingCourse
    mode: Literal[
        'occupied_at_alternative_reservation', 'released_before_primary_reservation',
        'unoccupied_at_primary_reservation',
    ]


class CandidateAvailability(Input):
    itinerary: Name
    course: InterlockingCourse
    mode: Literal['occupied_at_selected_reservation', 'unreserved_at_selected_reservation']


class ThroatAuthority(Input):
    resource: Resource
    preceding_courses: Annotated[list[Name], Field(max_length=32)] = Field(default_factory=list)
    following_courses: Annotated[list[Name], Field(max_length=32)] = Field(default_factory=list)


class VerifyPlatformChoice(Input):
    output_directory: PathText
    evidence_directory: PathText
    course: InterlockingCourse
    platform_station: Name | None = None
    choices: Annotated[list[Platform], Field(min_length=1, max_length=33)]
    expected_selected_itinerary: Name
    primary_availability: Availability | None = None
    availability_checks: Annotated[list[CandidateAvailability], Field(max_length=33)] = Field(default_factory=list)
    require_all_higher_priorities_occupied: StrictBool = False
    throat_authority: Annotated[list[ThroatAuthority], Field(max_length=32)] = Field(default_factory=list)
    movement_boundary_tolerance_m: Annotated[float, Field(ge=0.2, le=25, allow_inf_nan=False)] = 5.0


class PlatformChoiceTools(EvaluateNativeRunTools):
    def verify(self, args):
        from .native_platform_choice import audit
        from .native_run_evaluation import read_receipts

        try:
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            checks = args.model_dump(exclude={'output_directory', 'evidence_directory'}, exclude_none=True)
            return audit(output, evidence, checks, secure_bytes=self.secure_bytes)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_PLATFORM_CHOICE_INVALID', 'Could not audit the original platform choice',
                           str(exc)[:500]) from exc


def tool_definitions(root):
    service = PlatformChoiceTools(root)
    return [('opentrack_verify_native_platform_choice',
             'Verify the occupied platform and native itinerary priority using frozen topology, occupation, '
             'original movement and Course completion. Optionally verify blockers across higher priorities and '
             'the ordered release of common approach authorities. Read only.',
             VerifyPlatformChoice, service.verify)]
