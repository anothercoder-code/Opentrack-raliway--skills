"""Public read-only audit of operational effects in original interlocking output."""

from typing import Annotated, Literal

from pydantic import Field

from ..errors import APIError
from .native_result_tools import CourseOutcome, EvaluateNativeRunTools, Name
from .tools import Input, PathText


Gap = Annotated[float, Field(ge=0, le=604800, allow_inf_nan=False)]


class Resource(Input):
    document: Name
    group: Name


class Traversal(Input):
    course_id: Name
    resource: Resource


class OrderedRelease(Input):
    course_id: Name
    resources: Annotated[list[Resource], Field(min_length=2, max_length=64)]
    minimum_release_gap_s: Gap = 0


class ConcurrentTraversal(Input):
    first: Traversal
    second: Traversal
    scope: Literal['monitored_spans', 'disjoint_itineraries']
    minimum_overlap_s: Annotated[float, Field(gt=0, le=604800, allow_inf_nan=False)]


class AuthorityHandover(Input):
    resource: Resource
    leading_course: Name
    following_course: Name
    minimum_gap_s: Gap = 0


class InterlockingCourse(CourseOutcome):
    terminal_station: Name


class VerifyNativeInterlocking(Input):
    output_directory: PathText
    evidence_directory: PathText
    course_outcomes: Annotated[list[InterlockingCourse], Field(min_length=1, max_length=64)]
    ordered_releases: list[OrderedRelease] = Field(default_factory=list, max_length=64)
    concurrent_traversals: list[ConcurrentTraversal] = Field(default_factory=list, max_length=64)
    consecutive_authorities: list[AuthorityHandover] = Field(default_factory=list, max_length=64)
    movement_boundary_tolerance_m: Annotated[float, Field(ge=0.2, le=25, allow_inf_nan=False)] = 5.0


class NativeInterlockingTools(EvaluateNativeRunTools):
    def verify(self, args):
        from .native_interlocking import audit
        from .native_run_evaluation import read_receipts

        try:
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            expectations = args.model_dump(exclude={'output_directory', 'evidence_directory'}, exclude_none=True)
            return audit(output, evidence, expectations, secure_bytes=self.secure_bytes)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_INTERLOCKING_INVALID', 'Could not verify bound original interlocking effects',
                           str(exc)[:500]) from exc


def tool_definitions(root):
    from .native_edge_exclusion_effects import CompareNativeEdgeExclusion, NativeEdgeExclusionTools
    from .native_occupied_entry_effects import CompareNativeOccupiedEntry, OccupiedEntryTools
    from .native_platform_join import PlatformJoinTools, VerifyNativePlatformJoin
    from .native_route_protection import TOOL as PROTECTION_TOOL, NativeRouteProtectionTools, VerifyNativeRouteProtection
    from .native_throat_passage import TOOL, NativeThroatPassageTools, VerifyNativeThroatPassage

    service = NativeInterlockingTools(root)
    comparison = NativeEdgeExclusionTools(root)
    return [('opentrack_verify_native_interlocking',
             'Verify monitored section release order, physical overlap and consecutive exclusive authorities from '
             'one original execution. Bind occupation, distance and reservation/release traces to frozen Courses, '
             'Itineraries and Safety Elements. Read only. Never launches OpenTrack.',
             VerifyNativeInterlocking, service.verify),
            ('opentrack_compare_native_edge_exclusion',
             'Compare original control and direct Edge exclusion runs. Verify an isolated native link write, '
             'reservation-only protection, physical occupation and target release handover. Read only.',
             CompareNativeEdgeExclusion, comparison.compare),
            ('opentrack_compare_native_occupied_entry',
             'Verify speed-limited occupied-platform entry and a physical join against an original denial case. '
             'Requires the sole frozen signal permission change and hashed original route, motion and message outputs.',
             CompareNativeOccupiedEntry, OccupiedEntryTools(root).compare),
            ('opentrack_verify_native_platform_join',
             'Verify a physical join on one directed platform from sealed original signal positions, '
             'both Course motion traces and paired messages. Supports distinct saved platform alternatives. Read only.',
             VerifyNativePlatformJoin, PlatformJoinTools(root).verify_join),
            (TOOL,
             'Verify ordered movement through native worksheet connectors and exact monitored Edge membership '
             'against sealed original distance, occupation, reservation and release traces. Read only.',
             VerifyNativeThroatPassage, NativeThroatPassageTools(root).verify_passage),
            (PROTECTION_TOOL,
             'Verify frozen cross-worksheet Route slow-zone endpoints and ordered release group anchors against '
             'original movement, metric signal indication legend and release frontiers. Read only.',
             VerifyNativeRouteProtection, NativeRouteProtectionTools(root).verify_protection)]
