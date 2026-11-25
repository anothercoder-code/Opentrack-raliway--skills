"""Single-file, SHA-bound read-only native-result parsing preview."""
from typing import Annotated, Literal
from pydantic import StrictBool, StrictInt, StrictStr, Field
from .tools import Input, ArchiveTools, PathText, sha
from .bundle_tools import Source
from ..errors import APIError

class PreviewNativeResults(Input):
    source: Source
    format: Annotated[StrictStr, Field(min_length=1,max_length=80)]
    encoding: Annotated[StrictStr, Field(min_length=1,max_length=30)] = 'utf-8'
    course_whitelist: list[Annotated[StrictStr,Field(min_length=1,max_length=200)]] | None = None
    preview_only: Literal[True] = True


Name = Annotated[StrictStr, Field(min_length=1, max_length=180)]


class RequiredStop(Input):
    station: Name
    min_dwell_s: Annotated[float, Field(gt=0, le=604800, allow_inf_nan=False)]
    position_min_m: Annotated[float, Field(allow_inf_nan=False)] | None = None
    position_max_m: Annotated[float, Field(allow_inf_nan=False)] | None = None


class CourseOutcome(Input):
    course_id: Name
    origin_station: Name | None = None
    terminal_station: Name | None = None
    terminal_event: Literal['Arr.', 'Pass'] = 'Arr.'
    terminal_stop: StrictBool | None = None
    event_tolerance_s: Annotated[float, Field(ge=0.01, le=5, allow_inf_nan=False)] = 1.05
    distance_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    distance_tolerance_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    required_stops: list[RequiredStop] = Field(default_factory=list, max_length=1000)


class IncidentOutcome(Input):
    name: Name
    target: Name | None = None
    course_id: Name | None = None
    started_clock: Annotated[StrictStr, Field(pattern=r'^[0-9]{2}:[0-9]{2}:[0-9]{2}$')] | None = None
    stopped_clock: Annotated[StrictStr, Field(pattern=r'^[0-9]{2}:[0-9]{2}:[0-9]{2}$')] | None = None


class ExclusiveOccupationGroup(Input):
    document: Name
    group: Name
    courses: Annotated[list[Name], Field(min_length=2, max_length=10000)]


class PhysicalPeak(Input):
    course_id: Name
    quantity: Literal['tractive_effort_kn', 'mechanical_power_kw', 'power_input_kw']
    begin_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    end_s: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    peak_min: Annotated[float, Field(allow_inf_nan=False)] | None = None
    peak_max: Annotated[float, Field(allow_inf_nan=False)] | None = None
    minimum_moving_samples: Annotated[StrictInt, Field(ge=1, le=1000000)] = 1


class SignalReservationHeadway(Input):
    signal_label: Name
    leading_course: Name
    following_course: Name
    minimum_s: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class FollowingSeparation(Input):
    leading_course: Name
    following_course: Name
    begin_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    end_s: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    minimum_reference_gap_m: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class EvaluateNativeRun(Input):
    output_directory: PathText
    evidence_directory: PathText | None = None
    courses: Annotated[list[Name | CourseOutcome], Field(min_length=1, max_length=10000)]
    window_end_s: Annotated[StrictInt, Field(gt=0)] | None = None
    require_end_message: StrictBool = False
    expected_incidents: list[Name | IncidentOutcome] = Field(default_factory=list, max_length=1000)
    expected_physical_peaks: list[PhysicalPeak] = Field(default_factory=list, max_length=128)
    expected_signal_reservation_headways: list[SignalReservationHeadway] = Field(default_factory=list, max_length=128)
    expected_following_separations: list[FollowingSeparation] = Field(default_factory=list, max_length=64)
    exclusive_occupation_groups: list[ExclusiveOccupationGroup] = Field(default_factory=list, max_length=64)
    include_supplementary: StrictBool = False


class ReadEvaluationFile(Input):
    source: Source
    offset: Annotated[StrictInt, Field(ge=0)] = 0
    limit: Annotated[StrictInt, Field(ge=1, le=1000)] = 200


class EvaluateNativeRunTools(ArchiveTools):
    def evaluate(self, args):
        from .native_run_evaluation import evaluate_run, read_receipts

        try:
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes) \
                if args.evidence_directory is not None else None
            expectations = args.model_dump(exclude={'output_directory', 'evidence_directory'}, exclude_none=True)
            return evaluate_run(output, expectations, evidence, secure_bytes=self.secure_bytes)
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise APIError('NATIVE_EVALUATION_INVALID', 'Could not evaluate bound original results',
                           str(exc)[:500]) from exc

    def directory(self, relative):
        path = self.path(relative)
        if path.resolve(strict=True) != path or not path.is_dir():
            raise APIError('ARCHIVE_PATH', 'Use an ordinary non-redirected run directory')
        return path

    def read_evaluation_file(self, args):
        from . import native_evaluation_formats as fmt
        from . import native_monitoring_formats as monitors
        from .native_run_evaluation import decode

        path = self.path(args.source.path)
        blob = self.secure_bytes(path)
        if sha(blob) != args.source.sha256:
            raise APIError('SOURCE_CHANGED', 'Result file SHA-256 differs')
        text = decode(blob)
        units = None
        summary = None
        try:
            if path.name == 'OT_Physic.tsvP':
                records = fmt.physical_series(text)
            elif path.name == 'OT_StationStatistics.txt':
                station = fmt.station_statistics(text)
                records = [dict(type=kind, **row) for kind, rows in station.items() for row in rows]
            elif path.name == 'OT_OccStatistics.txt':
                occupation = monitors.occupation_statistics(text)
                records = occupation['records']
                units = occupation['units']
                summary = {'time_slot': occupation['time_slot']}
            elif path.name.startswith('OT_Occ_') and path.suffix == '.occ':
                records = fmt.occupations(text)
            elif path.name.startswith('OT_') and path.suffix == '.Pt':
                district = monitors.power_supply(text)
                records = district['points']
                units = district['units']
                summary = {'name': district['name'], **district['summary']}
            elif path.name.startswith('OT_') and path.suffix == '.ins':
                parsed = monitors.instruments(text)
                records = parsed['records']
                summary = {key: value for key, value in parsed.items() if key != 'records'}
            elif path.name.startswith('OT_') and path.suffix == '.sig':
                data = monitors.instrument_signals(text)
                records = data['records']
                summary = data['signal']
            else:
                file_type = path.suffix[1:]
                if not path.name.startswith('OT_') or len(path.stem) <= 3:
                    raise ValueError('Use the original output filename')
                course = path.stem[3:]
                if file_type == 'tsvP':
                    records = fmt.physical_series(text, course)
                elif file_type == 'tt':
                    records = fmt.timetable(text, course)
                else:
                    series = fmt.series(text, file_type, course)
                    records = series['points']
                    units = series['units']
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise APIError('NATIVE_EVALUATION_FORMAT', 'Unsupported original evaluation record',
                           str(exc)[:500]) from exc
        return {'source': args.source.model_dump(), 'units': units, 'summary': summary, 'record_count': len(records),
                'offset': args.offset, 'limit': args.limit, 'records': records[args.offset:args.offset + args.limit],
                'read_only': True, 'runtime_verified': False}

class NativeResultTools(ArchiveTools):
    def preview(self,args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','No save, publication, launch or native success certification')
        from .native_results_workflow.core import parse_result
        path=self.path(args.source.path); blob=self.secure_bytes(path)
        if sha(blob)!=args.source.sha256:raise APIError('SOURCE_CHANGED','Result-file SHA mismatch')
        try:
            parsed=parse_result(blob,args.format,args.encoding,args.course_whitelist)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError,UnicodeError) as exc:
            raise APIError('RESULT_FORMAT_INVALID','Outside supported result-reader contract',str(exc)[:500]) from exc
        if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Result file changed during preview')
        return dict(tool='opentrack_preview_native_results',preview_only=True,saved=False,native_execution=False,
                    native_success=False,native_runtime_ready=False,blocked=True,goal_complete=False,requires_native_validation=True,
                    publication_review_pending=True,source={'path':args.source.path,'sha256':sha(blob),'bytes':len(blob)},
                    result=parsed,limitations=['Parsing supplied bytes does not prove native execution or completion.',
                    'No output creation, process launch, directory scan, publication or changes to runtime preferences.'])

def tool_definitions(root):
    service=NativeResultTools(root)
    evaluator = EvaluateNativeRunTools(root)
    return [
        ('opentrack_preview_native_results','Read one explicitly selected SHA-bound native-result text file using a bounded evidenced schema. Return normalized records and descriptive statistics only; never save, launch, or certify simulation success.',PreviewNativeResults,service.preview),
        ('opentrack_evaluate_native_run', 'Evaluate expected course outcomes using original timetable, speed, distance, statistics and protocol. Optionally verify a frozen launcher receipt and inspect station, occupation and physical outputs. Read only; never launches OpenTrack.', EvaluateNativeRun, evaluator.evaluate),
        ('opentrack_read_native_evaluation_file', 'Read a page of SHA-bound original timetable, position, speed, reservation/release, occupation events and statistics, station/switch, power district or measuring-instrument output. Preserve recorded units and unavailable event times.', ReadEvaluationFile, evaluator.read_evaluation_file),
    ]
