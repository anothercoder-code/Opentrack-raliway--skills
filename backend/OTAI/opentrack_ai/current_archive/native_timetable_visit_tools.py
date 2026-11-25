"""Public original-output audit for individual native timetable visits."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from ..errors import APIError
from .native_interlocking_tools import InterlockingCourse
from .native_result_tools import EvaluateNativeRunTools, Name
from .network_operating_plan import DirectedStationEnd
from .tools import Input, PathText


class ExpectedVisit(Input):
    visit_index: Annotated[StrictInt, Field(ge=1, le=998)]
    station_sign: Name
    reference_end: DirectedStationEnd
    expected: Literal['stop', 'pass']
    minimum_observed_dwell_s: Annotated[float, Field(gt=0, le=604800, allow_inf_nan=False)] | None = None

    @model_validator(mode='after')
    def check_dwell(self):
        if (self.expected == 'stop') != (self.minimum_observed_dwell_s is not None):
            raise ValueError('Set a minimum observed dwell exactly for expected stops')
        return self


class VerifyTimetableVisits(Input):
    output_directory: PathText
    evidence_directory: PathText
    course: InterlockingCourse
    visits: Annotated[list[ExpectedVisit], Field(min_length=1, max_length=998)]
    position_tolerance_m: Annotated[float, Field(ge=0.2, le=50, allow_inf_nan=False)] = 5.0


class TimetableVisitTools(EvaluateNativeRunTools):
    def verify(self, args):
        from .native_run_evaluation import read_receipts
        from .native_timetable_visits import audit

        try:
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            request = args.model_dump(exclude={'output_directory', 'evidence_directory'}, exclude_none=True)
            return audit(output, evidence, request, secure_bytes=self.secure_bytes)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_TIMETABLE_VISITS_INVALID', 'Could not verify bound original timetable visits',
                           str(exc)[:500]) from exc


def tool_definitions(root):
    service = TimetableVisitTools(root)
    return [('opentrack_verify_native_timetable_visits',
             'Verify stop or passage at exact intermediate rows of an original unlinked single-Itinerary Course. '
             'Bind frozen timetable, directed station Ends and original actual clocks, speed and location. Read only.',
             VerifyTimetableVisits, service.verify)]
