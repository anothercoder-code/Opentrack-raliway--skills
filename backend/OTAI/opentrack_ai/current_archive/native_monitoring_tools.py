"""User-callable saved power supplies and measuring instruments."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr

from .bundle_tools import Source
from .native_monitoring import DEMO_DONOR_SHA256, records, transform
from .next_tools import NextFunctions, Ordinal, Save
from .tools import Input
from ..errors import APIError


Name = Annotated[StrictStr, Field(min_length=1, max_length=60)]
Number = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
Position = Annotated[list[Number], Field(min_length=2, max_length=2)]
Frame = Annotated[list[Number], Field(min_length=4, max_length=4)]
Edges = Annotated[list[Ordinal], Field(max_length=10000)]
PowerCode = Annotated[StrictInt, Field(ge=0, le=14)] | Annotated[StrictInt, Field(ge=101, le=200)]
SegmentCode = Annotated[StrictInt, Field(ge=1000, le=1002)]
SegmentIds = Annotated[list[Ordinal], Field(max_length=10000)]
DisplayMode = Annotated[StrictInt, Field(ge=0, le=2)]
Flag = Literal['name', 'course', 'speed', 'clock', 'headway', 'marked',
               'train_count', 'switch_operations', 'signal_stops']


class Inspection(Input):
    source: Source


class CreateSupply(Input):
    action: Literal['create_supply']
    name: Name
    power_system_code: PowerCode
    position: Position
    edge_ids: Edges
    icon_mode: DisplayMode = 0
    edge_mode: DisplayMode = 0
    replace: StrictBool = False


class UpdateSupply(Input):
    action: Literal['update_supply']
    id: Ordinal
    name: Name | None = None
    power_system_code: PowerCode | None = None
    position: Position | None = None
    icon_mode: DisplayMode | None = None
    edge_mode: DisplayMode | None = None


class BindSupply(Input):
    action: Literal['set_edge_supply']
    supply_id: Ordinal | None
    edge_ids: Edges
    replace: StrictBool = False


class CreatePropulsionSegment(Input):
    action: Literal['create_propulsion_segment']
    name: Name
    power_system_code: SegmentCode
    position: Position
    edge_ids: Edges
    allow_multiple_trains: StrictBool = False
    icon_mode: DisplayMode = 0
    edge_mode: DisplayMode = 0
    replace: StrictBool = False


class UpdatePropulsionSegment(Input):
    action: Literal['update_propulsion_segment']
    id: Ordinal
    name: Name | None = None
    power_system_code: SegmentCode | None = None
    position: Position | None = None
    allow_multiple_trains: StrictBool | None = None
    icon_mode: DisplayMode | None = None
    edge_mode: DisplayMode | None = None


class BindPropulsionSegment(Input):
    action: Literal['set_edge_propulsion_segment']
    segment_id: Ordinal | None
    edge_ids: Edges
    replace: StrictBool = False


class CreatePropulsionGroup(Input):
    action: Literal['create_propulsion_group']
    name: Name
    position: Position
    segment_ids: SegmentIds
    max_active_segments: Ordinal
    icon_mode: DisplayMode = 0
    edge_mode: DisplayMode = 0


class UpdatePropulsionGroup(Input):
    action: Literal['update_propulsion_group']
    id: Ordinal
    name: Name | None = None
    position: Position | None = None
    segment_ids: SegmentIds | None = None
    max_active_segments: Ordinal | None = None
    icon_mode: DisplayMode | None = None
    edge_mode: DisplayMode | None = None


class DeletePowerModel(Input):
    action: Literal['delete_power_model']
    id: Ordinal


class InstrumentOptions(Input):
    name: Name | None = None
    frame: Frame | None = None
    display: Annotated[list[Flag], Field(max_length=9)] | None = None
    edge_ids: Edges | None = None
    visible: StrictBool | None = None
    direction_code: Literal[1, 2, 3] | None = None
    size_code: Annotated[StrictInt, Field(ge=1, le=7)] | None = None


class CreateInstrument(InstrumentOptions):
    action: Literal['create_instrument']
    end_id: Ordinal
    name: Name
    frame: Frame


class UpdateInstrument(InstrumentOptions):
    action: Literal['update_instrument']
    id: Ordinal


class RelocateInstrument(Input):
    action: Literal['relocate_instrument']
    id: Ordinal
    from_end_id: Ordinal
    to_end_id: Ordinal
    expected_edge_ids: Edges | None = None
    edge_ids: Edges | None = None


class CreateInstrumentsAtLocations(Input):
    action: Literal['create_instruments_at_locations']
    location: Literal['main_signal', 'switch']
    selected_end_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=4096)] | None = None


Operation = Annotated[CreateSupply | UpdateSupply | BindSupply | CreatePropulsionSegment | UpdatePropulsionSegment
                      | BindPropulsionSegment | CreatePropulsionGroup | UpdatePropulsionGroup | DeletePowerModel
                      | CreateInstrument | UpdateInstrument
                      | RelocateInstrument | CreateInstrumentsAtLocations,
                      Field(discriminator='action')]


class EditMonitoring(Save):
    source: Source
    stock_donor: Source | None = None
    operations: Annotated[list[Operation], Field(min_length=1, max_length=96)]


class MonitoringTools(NextFunctions):
    def inspect_models(self, args):
        _, _, root, _ = self.checked(args.source)
        try:
            return {'source': args.source.model_dump(), **records(root), 'read_only': True}
        except (ValueError, KeyError, IndexError) as exc:
            raise APIError('MONITOR_MODEL_INVALID', str(exc)[:500]) from exc

    def edit_models(self, args):
        path, original, _, _ = self.checked(args.source)
        if path.suffix != '.opentrack' or (args.target_path and self.path(args.target_path).suffix != '.opentrack'):
            raise APIError('MONITOR_PROJECT_PATH', 'Use native .opentrack worksheets')
        additional = {}
        donor = None
        operations = []
        for command in args.operations:
            operation = command.model_dump(exclude_none=True)
            if isinstance(command, BindSupply):
                operation['supply_id'] = command.supply_id
            elif isinstance(command, BindPropulsionSegment):
                operation['segment_id'] = command.segment_id
            operations.append(operation)
        creation_types = (CreateSupply, CreatePropulsionSegment, CreatePropulsionGroup, CreateInstrument,
                          CreateInstrumentsAtLocations)
        needs_donor = any(isinstance(command, creation_types) for command in args.operations)
        if needs_donor and args.stock_donor is None:
            raise APIError('MONITOR_TEMPLATE_REQUIRED', 'Creation requires the SHA-bound local stock Demo topology donor')
        if args.stock_donor is not None:
            donor_path, donor, _, _ = self.checked(args.stock_donor)
            if args.stock_donor.sha256 != DEMO_DONOR_SHA256:
                raise APIError('MONITOR_TEMPLATE_INVALID', 'Use the reviewed stock Demo topoOst worksheet')
            additional[donor_path] = donor
        try:
            output, report = transform(original, donor, operations)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError('MONITOR_EDIT_INVALID', str(exc)[:600]) from exc
        return self.finish(args, path, original, output, report, additional_inputs=additional)


def tool_definitions(root):
    service = MonitoringTools(root)
    return [
        ('opentrack_inspect_power_and_measurement',
         'Inspect saved power areas, propulsion segments and groups, bound Edges, and measuring instruments in a hashed native worksheet.',
         Inspection, service.inspect_models),
        ('opentrack_edit_power_and_measurement',
         'Create or edit power areas, propulsion segments and groups, and measuring instruments. '
         'Batch-instrument eligible main signals or turnouts, '
         'relocate an existing instrument between directional Ends, bind local supply Edges, and save a fresh '
         'native worksheet. Creation uses a verified local stock donor.',
         EditMonitoring, service.edit_models, False, False),
    ]
