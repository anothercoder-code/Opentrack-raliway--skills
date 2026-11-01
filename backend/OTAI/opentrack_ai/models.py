import copy
from typing import Annotated, Literal
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, create_model, model_validator


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,validate_default=True)


class Empty(Input):pass


class ProjectInput(Input):
    project: str=Field(default='OTProjects/BJTU',description='Project folder under OTProjects, or an OTAI draft project.')
    run_file: str|None=Field(default=None,description='Optional .run file; otherwise prefer BJTU-demo.run, then canonical empty.* catalogs.')


class Page(Input):
    limit: int=Field(default=50,ge=1,le=200)
    offset: int=Field(default=0,ge=0)


class Objects(ProjectInput,Page):
    document: str|None=None
    class_name: str|None=None
    object_id: int|None=Field(default=None,ge=0)
    query: str=Field(default='',max_length=160)


class NativeClass(Page):
    class_name: str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,119}$')
    binary: Literal['opentrack','foundation','appkit']='opentrack'
    method_filter: str=Field(default='',max_length=160)
    category: str|None=Field(default=None,pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,119}$',description='Optional classic Objective-C category, e.g. NSWindowsExtensions on NSWindow in appkit.')


class NativeMethod(Input):
    class_name: str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,119}$')
    binary: Literal['opentrack','foundation','appkit']='opentrack'
    category: str|None=Field(default=None,pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,119}$')
    selector: str=Field(pattern=r'^[A-Za-z_][A-Za-z0-9_:]{0,239}$')
    method_kind: Literal['instance','class']='instance'
    max_bytes: int=Field(default=512,ge=16,le=4096)
    offset: int=Field(default=0,ge=0,le=4096)
    limit: int=Field(default=50,ge=1,le=120)


class FunctionCoverage(Input):
    operation: Literal['read','generate','modify','export']|None=None
    scope: Literal['auto','packaged','legacy']='auto'
    section: Literal['summary','native','python','enhancement','saved_data','interfaces','requirements']='summary'
    query: str=Field(default='',max_length=160)
    binary: Literal['opentrack','foundation','appkit']|None=None
    class_name: str|None=Field(default=None,max_length=120)
    selector: str|None=Field(default=None,max_length=240)
    status: str|None=Field(default=None,max_length=80)
    require_fresh: bool=True
    limit: int=Field(default=25,ge=1,le=200)
    offset: int=Field(default=0,ge=0)


class Schema(Input):
    name: str|None=Field(default=None,max_length=120)


class DecompiledFunction(Input):
    query: str=Field(default='',max_length=160)
    class_name: str|None=Field(default=None,pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,119}$')
    category: str|None=Field(default=None,pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,119}$|^$')
    selector: str|None=Field(default=None,pattern=r'^[A-Za-z_][A-Za-z0-9_:]{0,239}$')
    method_kind: Literal['instance','class']|None=None
    address: str|None=Field(default=None,pattern=r'^0x[0-9a-fA-F]{1,8}$')
    offset: int=Field(default=0,strict=True,ge=0)
    limit: int=Field(default=100,strict=True,ge=1,le=300)

    @model_validator(mode='after')
    def choose_selection(self):
        if self.address and (self.class_name or self.category is not None or self.selector or self.method_kind or self.query):
            raise ValueError('Choose a native entry address or metadata/query filters.')
        return self


class Catalog(ProjectInput,Page):
    kind: Literal['services','trains','engines','categories','stations','timetable','itineraries','shuntings']='services'
    query: str=Field(default='',max_length=160)
    include_curves: bool=False
    itinerary_usage: Literal['all','used','unused']='all'
    itinerary_query_field: Literal['all','name','description']='all'
    include_itinerary_details: bool=False

    @model_validator(mode='after')
    def itinerary_options(self):
        if self.kind!='itineraries' and (self.itinerary_usage!='all' or self.itinerary_query_field!='all' or self.include_itinerary_details):
            raise ValueError('Itinerary options require kind=itineraries.')
        return self


class Service(ProjectInput):
    course_id: str=Field(min_length=1,max_length=120)
    include_curves: bool=False


class Paths(ProjectInput,Page):pass


class Trace(ProjectInput):
    path_name: str=Field(min_length=1,max_length=160)


class Logs(ProjectInput):
    message_lines: int=Field(default=50,ge=0,le=200)


class EndRef(Input):
    document: str=Field(min_length=1,max_length=100)
    end_id: int=Field(ge=0)


class EdgeRef(Input):
    document: str=Field(min_length=1,max_length=100)
    edge_id: int=Field(ge=0)


class TopologyQuery(ProjectInput,Page):
    document: str|None=None
    end_id: int|None=Field(default=None,ge=0)


class NetworkSearch(ProjectInput):
    kind: Literal['topology','routes','paths']='topology'
    start: EndRef
    end: EndRef|None=None
    via: list[EndRef]=Field(default_factory=list,max_length=100)
    avoid_nodes: list[EndRef]=Field(default_factory=list,max_length=1000)
    avoid_edges: list[EdgeRef]=Field(default_factory=list,max_length=1000)
    limit: int=Field(default=10,ge=1,le=50)
    max_expansions: int=Field(default=50000,ge=1,le=500000)
    max_hops: int=Field(default=1000,ge=1,le=4096)


class Routes(ProjectInput,Page):
    document: str|None=None
    start_id: int|None=Field(default=None,ge=0)


class RouteSelector(Input):
    document: str=Field(min_length=1,max_length=100)
    start_id: int=Field(ge=0)
    route_id: int|None=Field(default=None,ge=0)
    name: str|None=Field(default=None,min_length=1,max_length=160)

    @model_validator(mode='after')
    def one_identifier(self):
        if (self.route_id is None)==(self.name is None):raise ValueError('Supply exactly one of route_id or name.')
        return self


class EvidenceSearch(Page):
    query: str=Field(default='',max_length=160)


class EvidenceRead(Input):
    evidence_id: str=Field(pattern=r'^[a-z0-9-]{1,80}$')
    start_line: int=Field(default=1,ge=1)
    max_lines: int=Field(default=60,ge=1,le=120)


CourseId=Annotated[str,Field(pattern=r'^[!-~](?:[ -~]{0,78}[!-~])?$',description='Exact printable ASCII Course ID; no leading/trailing whitespace or control characters.')]
def new_course_id(value):
    if value in ['0','-1']:raise ValueError('Original OpenTrack reserves Course IDs 0 and -1.')
    return value

NewCourseId=Annotated[CourseId,AfterValidator(new_course_id),Field(description='New exact Course ID; original reserved identifiers 0 and -1 are forbidden.',json_schema_extra={'not':{'enum':['0','-1']}})]
MAX_BATCH_OPERATIONS=1000


class EdgeLength(Input):
    kind: Literal['edge_length']
    document: str=Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    edge_id: int=Field(ge=0)
    length_m: int=Field(strict=True,gt=0,le=10000000,description='Whole metres; audited OTEdgeModel stores this field as a signed integer.')


class Shift(Input):
    kind: Literal['shift_timetable']
    course_id: CourseId
    seconds: int=Field(ge=-31622400,le=31622400)


class Bind(Input):
    kind: Literal['bind_course']
    course_id: CourseId
    train: str|None=Field(default=None,min_length=1,max_length=160)
    itinerary: str|None=Field(default=None,min_length=1,max_length=160)


class Clone(Input):
    kind: Literal['clone_course']
    template_id: CourseId
    new_id: NewCourseId
    seconds: int=Field(default=0,ge=-31622400,le=31622400)
    train: str|None=Field(default=None,min_length=1,max_length=160)
    itinerary: str|None=Field(default=None,min_length=1,max_length=160)


class Enabled(Input):
    kind: Literal['course_enabled']
    course_id: CourseId
    enabled: bool


class Normalize(Input):kind: Literal['normalize_labels']
class RepairLayout(Input):kind: Literal['repair_catalog_layout']
class Reencode(Input):kind: Literal['reencode_native']


ArchiveName=Annotated[str,Field(pattern=r'^[!-~](?:[ -~]{0,158}[!-~])?$',description='Exact printable ASCII native name, including stock brackets/parentheses; no leading/trailing whitespace or control characters.')]
ArchiveText=Annotated[str,Field(pattern=r'^[\x20-\x7e]{0,240}$')]


class ShuntingSelector(Input):
    document: str=Field(min_length=1,max_length=100)
    start_id: int=Field(ge=0)
    name: ArchiveName


class SlowSpeedZone(Input):
    start: EndRef
    end: EndRef


class RouteProtection(Input):
    release_group_boundaries: list[EndRef]|None=Field(default=None,min_length=2,max_length=4096)
    slow_speed_zone: SlowSpeedZone|None=None
    overlap: ShuntingSelector|None=None


class DefineShunting(Input):
    kind: Literal['define_shunting']='define_shunting'
    name: ArchiveName
    description: ArchiveText=''
    nodes: list[EndRef]=Field(min_length=2,max_length=4096)
    speed_kmh: float=Field(default=40,gt=0,le=1000)
    release_time_s: int=Field(default=0,ge=0,le=86400)
    reservation_time_s: int=Field(default=0,ge=0,le=86400)


class SetRouteProtection(RouteProtection):
    kind: Literal['set_route_protection']='set_route_protection'
    route: RouteSelector

    @model_validator(mode='after')
    def explicit_change(self):
        if not {'release_group_boundaries','slow_speed_zone','overlap'}.intersection(self.model_fields_set):raise ValueError('Supply at least one protection field; explicit null resets that field.')
        return self


class DefineRoute(RouteProtection):
    kind: Literal['define_route']='define_route'
    name: ArchiveName
    description: ArchiveText=''
    nodes: list[EndRef]=Field(min_length=2,max_length=4096)
    release_point_m: int=Field(default=0,ge=0,le=1000000)
    advance_notice_m: int=Field(default=400,ge=0,le=1000000)
    release_time_s: int=Field(default=5,ge=0,le=86400)
    reservation_time_s: int=Field(default=0,ge=0,le=86400)
    signal_aspects: list[Annotated[int,Field(ge=0,le=10000)]]|None=Field(default=None,min_length=1,max_length=64)
    reserve_with_previous: bool=False
    slow_speed_only_for_head: bool=False
    discrete_for_moving_block: bool=False
    allow_occupied_entry: bool=False
    occupied_entry_use_speed: bool=False
    occupied_entry_use_time: bool=False
    occupied_entry_speed_kmh: float=Field(default=40,ge=0,le=1000)
    occupied_entry_wait_s: float=Field(default=0,ge=0,le=86400)
    approach_zone_length_m: float=Field(default=0,ge=0,le=1000000)
    approach_zone_speed_kmh: float=Field(default=0,ge=0,le=1000)
    reservation_point_m: int=Field(default=5000,ge=0,le=1000000)
    use_reservation_point: bool=False
    use_release_point: bool|None=None


class DefinePath(Input):
    kind: Literal['define_path']='define_path'
    name: ArchiveName
    description: ArchiveText=''
    routes: list[RouteSelector]=Field(min_length=1,max_length=1000)


NativeFloat32=Annotated[float,Field(strict=True,ge=-3.4028234663852886e38,le=3.4028234663852886e38)]
MarginIndex=Annotated[int,Field(strict=True,ge=0,le=9999)]


class SafetyMarginPoint(Input):
    position_m: NativeFloat32
    safety_margin_m: NativeFloat32


class AddItineraryMargin(Input):
    action: Literal['add']='add'
    selected_indices: list[MarginIndex]=Field(default_factory=list,max_length=10000,description='Original Add: no selection appends a copy of the last row or zero defaults; selected rows insert after the last selected row.')


class InsertItineraryMargin(Input):
    action: Literal['insert']='insert'
    index: Annotated[int,Field(strict=True,ge=0,le=10000)]


class UpdateItineraryMargin(Input):
    action: Literal['update']='update'
    index: MarginIndex
    position_m: NativeFloat32|None=None
    safety_margin_m: NativeFloat32|None=None

    @model_validator(mode='after')
    def changed_margin(self):
        if self.position_m is None and self.safety_margin_m is None:raise ValueError('Supply a position or safety margin.')
        return self


class DeleteItineraryMargins(Input):
    action: Literal['delete']='delete'
    indices: list[MarginIndex]=Field(default_factory=list,max_length=10000)


class SortItineraryMargins(Input):action: Literal['sort']='sort'
class ClearItineraryMargins(Input):action: Literal['clear']='clear'


class ImportItineraryMargins(Input):
    action: Literal['import_text']='import_text'
    content: str|None=Field(default=None,max_length=2000000)
    file_path: str|None=Field(default=None,min_length=1,max_length=1000)

    @model_validator(mode='after')
    def input_source(self):
        if (self.content is None)==(self.file_path is None):raise ValueError('Supply exactly one of content or file_path.')
        return self


MarginEdit=Annotated[AddItineraryMargin|InsertItineraryMargin|UpdateItineraryMargin|DeleteItineraryMargins|SortItineraryMargins|ClearItineraryMargins|ImportItineraryMargins,Field(discriminator='action')]


class EditItineraryMargins(Input):
    kind: Literal['edit_itinerary_margins']='edit_itinerary_margins'
    name: ArchiveName
    edits: list[MarginEdit]=Field(min_length=1,max_length=1000)


class ItineraryMargins(ProjectInput,Page):
    name: ArchiveName
    distances_m: list[NativeFloat32]=Field(default_factory=list,max_length=200)


class ExportItineraryMargins(ProjectInput):
    names: list[ArchiveName]=Field(min_length=1,max_length=1000)
    format: Literal['native_text','json']='native_text'

    @model_validator(mode='after')
    def unique_names(self):
        if len(set(self.names))!=len(self.names):raise ValueError('Export names must be unique.')
        return self


class DefineItinerary(Input):
    kind: Literal['define_itinerary']='define_itinerary'
    name: ArchiveName
    description: ArchiveText=''
    paths: list[ArchiveName]=Field(min_length=1,max_length=1000)
    safety_margins: list[SafetyMarginPoint]=Field(default_factory=list,max_length=10000,description='Initial native margin profile, sorted using the original finite-float comparison/order as in text import.')


class EditItinerary(Input):
    kind: Literal['edit_itinerary']='edit_itinerary'
    name: ArchiveName
    description: ArchiveText|None=None
    paths: list[ArchiveName]|None=Field(default=None,min_length=1,max_length=1000)
    catalog_sync: Literal['refresh_selected','preserve']='refresh_selected'

    @model_validator(mode='after')
    def changed_fields(self):
        if self.description is None and self.paths is None:raise ValueError('Supply description or paths.')
        return self


class RenameItinerary(Input):
    kind: Literal['rename_itinerary']='rename_itinerary'
    name: ArchiveName
    new_name: ArchiveName


class DuplicateItinerary(Input):
    kind: Literal['duplicate_itinerary']='duplicate_itinerary'
    name: ArchiveName
    new_name: ArchiveName=Field(description='Explicit fresh name; avoids assuming the localized CopyOf prefix or unverified overwrite behavior.')


class DeleteItineraries(Input):
    kind: Literal['delete_itineraries']='delete_itineraries'
    names: list[ArchiveName]=Field(default_factory=list,max_length=10000)
    selection: Literal['named','unused']='named'

    @model_validator(mode='after')
    def selection_mode(self):
        if self.selection=='named' and not self.names:raise ValueError('Named deletion requires names.')
        if self.selection=='unused' and self.names:raise ValueError('Unused selection cannot include names.')
        if len(set(self.names))!=len(self.names):raise ValueError('Names must be unique.')
        return self


class ResetItineraryCatalog(Input):
    kind: Literal['reset_itinerary_catalog']='reset_itinerary_catalog'


class AppendItinerary(Input):
    kind: Literal['append_itinerary']='append_itinerary'
    name: ArchiveName
    source: ArchiveName


class ReplaceItineraryPaths(Input):
    kind: Literal['replace_itinerary_paths']='replace_itinerary_paths'
    name: ArchiveName
    start_index: int=Field(strict=True,ge=0,le=999)
    count: int=Field(strict=True,ge=1,le=1000)
    paths: list[ArchiveName]=Field(min_length=1,max_length=1000)
    catalog_sync: Literal['refresh_selected','preserve']='refresh_selected'


class RepairItineraryDocuments(Input):kind: Literal['repair_itinerary_documents']


DocumentName=Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,59}$')]


class DeleteAllPaths(Input):
    kind: Literal['delete_all_paths']='delete_all_paths'
    document: DocumentName
    end_ids: list[Annotated[int,Field(strict=True,ge=0,le=2147483647)]]=Field(default_factory=list,max_length=10000,description='Selected directional End IDs in this document. Empty means every route-start End, matching original Delete all Paths. A nonempty selection never falls back to all.')
    dependent_itineraries: Literal['reject','delete']='reject'

    @model_validator(mode='after')
    def unique_ends(self):
        if len(set(self.end_ids))!=len(self.end_ids):raise ValueError('Selected End IDs must be unique.')
        return self
EditorKey=Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,59}$')]


class NewEndRef(Input):
    document: DocumentName
    vertex_key: EditorKey
    side: Literal[0,1]


EditEnd=EndRef|NewEndRef


class CreateDocument(Input):
    kind: Literal['create_document']
    document: DocumentName
    width: float=Field(default=1200,ge=100,le=100000)
    height: float=Field(default=800,ge=100,le=100000)


class Worksheet(ProjectInput):
    document: str|None=None
    max_objects: int=Field(default=10000,ge=1,le=50000)


class WorksheetAttributes(Input):
    kind: Literal['worksheet_attributes']
    document: DocumentName
    width: float|None=Field(default=None,ge=100,le=100000)
    height: float|None=Field(default=None,ge=100,le=100000)
    grid_x: int|None=Field(default=None,ge=1,le=10000)
    grid_y: int|None=Field(default=None,ge=1,le=10000)
    show_grid: bool|None=None
    show_edge_direction: bool|None=None
    big_vertices: bool|None=None


class SignalAttributes(Input):
    kind: Literal['signal_attributes']
    document: DocumentName
    signal_id: int=Field(ge=0)
    name: ArchiveText|None=None
    signal_type: Literal[1,2,24,25,26]|None=None
    main_signal_type: int|None=Field(default=None,ge=0,le=10)
    sight_distance_m: int|None=Field(default=None,ge=0,le=100000)
    release_speed_kmh: int|None=Field(default=None,ge=0,le=1000)
    delay_s: float|None=Field(default=None,ge=0,le=86400)


class CreateVertex(Input):
    kind: Literal['create_vertex']
    document: DocumentName
    vertex_key: EditorKey|None=None
    x: float=Field(ge=-1000000,le=1000000)
    y: float=Field(ge=-1000000,le=1000000)
    angle_degrees: Literal[0,90,180,270]=0
    names: list[ArchiveText]=Field(default_factory=list,max_length=2)


class MoveVertex(Input):
    kind: Literal['move_vertex']
    end: EditEnd
    x: float=Field(ge=-1000000,le=1000000)
    y: float=Field(ge=-1000000,le=1000000)
    angle_degrees: Literal[0,90,180,270]|None=None


class VertexAttributes(Input):
    kind: Literal['vertex_attributes']
    end: EditEnd
    name: ArchiveText|None=None
    kilometre_point: float|None=Field(default=None,ge=-100000,le=100000)
    station_reference_type: int|None=Field(default=None,ge=0,le=10,description='Native stationEndType; archive group 20, not joint/axle-counter group 23.')
    switch_time_s: float|None=Field(default=None,ge=0,le=86400)
    default_second_leg: bool|None=None
    insulated_joint: bool|None=None
    axle_counter: bool|None=None


class TrackSpeed(Input):
    train_type: str=Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    forward_kmh: int=Field(strict=True,ge=0,le=1000)
    reverse_kmh: int=Field(strict=True,ge=0,le=1000)


class CreateEdge(Input):
    kind: Literal['create_edge']
    first: EditEnd
    second: EditEnd
    length_m: int=Field(strict=True,gt=0,le=10000000)
    radius_m: float=Field(default=0,ge=0,le=10000000)
    gradient_per_mille: float=Field(default=0,ge=-1000,le=1000)
    speeds: list[TrackSpeed]=Field(default_factory=lambda:[TrackSpeed(train_type=str(i),forward_kmh=160,reverse_kmh=160) for i in range(4)],min_length=1,max_length=100)
    track_name: ArchiveText|None=None
    line_name: ArchiveText|None=None


class EdgeAttributes(Input):
    kind: Literal['edge_attributes']
    edge: EdgeRef
    length_m: int|None=Field(default=None,strict=True,gt=0,le=10000000)
    radius_m: float|None=Field(default=None,ge=0,le=10000000)
    gradient_per_mille: float|None=Field(default=None,ge=-1000,le=1000)
    speeds: list[TrackSpeed]|None=Field(default=None,min_length=1,max_length=100)
    rack_rail: bool|None=None
    equal_speed: bool|None=None
    contact_wire_mm2: float|None=Field(default=None,ge=0,le=10000)
    tunnel_m2: float|None=Field(default=None,ge=0,le=10000)
    track_name: ArchiveText|None=None
    line_name: ArchiveText|None=None


class ReverseEdge(Input):
    kind: Literal['reverse_edge']
    edge: EdgeRef


class CreateSignal(Input):
    kind: Literal['create_signal']
    end: EditEnd
    name: ArchiveName
    signal_type: Literal[1,2,24,25,26]=1
    main_signal_type: int=Field(default=3,ge=0,le=10)
    sight_distance_m: int=Field(default=400,ge=0,le=100000)
    release_speed_kmh: int=Field(default=0,ge=0,le=1000)
    delay_s: float=Field(default=0,ge=0,le=86400)


class LinkConnectors(Input):
    kind: Literal['link_connectors']
    first: EditEnd
    second: EditEnd


class UnlinkConnector(Input):
    kind: Literal['unlink_connector']
    end: EndRef


class SafetyElements(Input):
    kind: Literal['merge_elements','reset_elements']
    document: DocumentName
    end_ids: list[int]=Field(default_factory=list,max_length=1000)
    edge_ids: list[int]=Field(default_factory=list,max_length=1000)


class ExclusionLink(Input):
    kind: Literal['exclusion_link']
    edge: EdgeRef
    target: EdgeRef|None=None


class DeleteGraphic(Input):
    kind: Literal['delete_graphic']
    document: DocumentName
    object_id: int=Field(ge=0)
    cascade_definitions_and_services: bool=False


class SplitEdge(Input):
    kind: Literal['split_edge']
    edge: EdgeRef
    first_length_m: int=Field(strict=True,gt=0,le=10000000)
    vertex_key: EditorKey|None=None
    x: float|None=Field(default=None,ge=-1000000,le=1000000)
    y: float|None=Field(default=None,ge=-1000000,le=1000000)


class TractionPoint(Input):
    speed_kmh: int=Field(strict=True,ge=0,le=1000)
    force_kn: int=Field(strict=True,ge=0,le=100000)


PowerSystemCode=Annotated[int,Field(strict=True,ge=1,le=2147483647)]


class DiagramForcePoint(Input):
    speed_kmh: int=Field(strict=True,ge=0,le=1000)
    force_kn: int=Field(strict=True,ge=-100000,le=100000)
    interpolation: Literal['linear','hyperbolic']='linear'


class EngineLossBand(Input):
    from_speed_kmh: int=Field(strict=True,ge=0,le=1000)
    loss_factor: float=Field(ge=0,le=1000,description='Fraction of mechanical traction power; 0.16 means 16 percent extra loss.')
    fixed_loss_kw: float=Field(ge=0,le=1000000)


class CalibratedRGB(Input):
    space: Literal['calibrated_rgb']='calibrated_rgb'
    red: float=Field(strict=True,ge=0,le=1)
    green: float=Field(strict=True,ge=0,le=1)
    blue: float=Field(strict=True,ge=0,le=1)
    alpha: float=Field(default=1,strict=True,ge=0,le=1)


class CalibratedWhite(Input):
    space: Literal['calibrated_white']='calibrated_white'
    white: float=Field(strict=True,ge=0,le=1)
    alpha: float=Field(default=1,strict=True,ge=0,le=1)


DiagramColor=Annotated[CalibratedRGB|CalibratedWhite,Field(discriminator='space')]


class TractiveEffortDiagramSpec(Input):
    description: ArchiveText=''
    power_system_codes: list[PowerSystemCode]=Field(max_length=256)
    traction_points: list[DiagramForcePoint]=Field(default_factory=list,max_length=1000)
    braking_points: list[DiagramForcePoint]=Field(default_factory=list,max_length=1000,description='Signed nonpositive force in kN, as in the native Z/V diagram.')
    loss_function: list[EngineLossBand]=Field(default_factory=list,max_length=1000)
    axis_maximum_speed_kmh: int|None=Field(default=None,strict=True,gt=0,le=10000)
    axis_maximum_force_kn: int|None=Field(default=None,strict=True,gt=0,le=100000)
    axis_minimum_force_kn: int|None=Field(default=None,strict=True,ge=-100000,le=0)
    adhesion_good_percent: int=Field(default=150,strict=True,ge=0,le=1000)
    adhesion_normal_percent: int=Field(default=125,strict=True,ge=0,le=1000)
    adhesion_bad_percent: int=Field(default=80,strict=True,ge=0,le=1000)
    adhesion_display_code: int=Field(default=1,strict=True,ge=0,le=1000)
    visible: bool=True
    color: DiagramColor|None=None

    @model_validator(mode='after')
    def diagram_values(self):
        if len(self.power_system_codes)!=len(set(self.power_system_codes)):raise ValueError('Power-system codes must be unique within a diagram.')
        for field in ['traction_points','braking_points']:
            points=getattr(self,field)
            if any(b.speed_kmh<=a.speed_kmh for a,b in zip(points,points[1:])):raise ValueError('Curve speeds must increase strictly.')
            if any(p.force_kn<0 if field=='traction_points' else p.force_kn>0 for p in points):raise ValueError('Traction force must be nonnegative; electrical braking force must be nonpositive.')
        if any(b.from_speed_kmh<=a.from_speed_kmh for a,b in zip(self.loss_function,self.loss_function[1:])):raise ValueError('Loss-function speed thresholds must increase strictly.')
        return self


class EngineSpec(Input):
    name: ArchiveName
    template_name: str|None=None
    mass_t: int=Field(strict=True,gt=0,le=100000)
    length_m: int=Field(strict=True,gt=0,le=10000)
    maximum_speed_kmh: int=Field(strict=True,gt=0,le=1000)
    maximum_force_kn: int=Field(strict=True,gt=0,le=100000)
    rotating_mass_factor: float=Field(default=1.06,ge=1,le=3)
    adhesion_mass_t: int|None=Field(default=None,strict=True,gt=0,le=100000)
    number_of_axles: int=Field(default=8,ge=1,le=1000)
    driven_axles: int=Field(default=4,ge=1,le=1000)
    traction_motors: int=Field(default=4,ge=1,le=1000)
    cw_value: float|None=Field(default=None,ge=0,le=100)
    strahl_resistance_factor: float|None=Field(default=None,ge=0,le=1000)
    adhesion_code: int|None=Field(default=None,ge=0,le=1000)
    minimum_force_kn: int|None=Field(default=None,strict=True,ge=-100000,le=100000)
    drive_type_code: int|None=Field(default=None,ge=0,le=1000)
    voltage_type_code: int|None=Field(default=None,ge=0,le=1000)
    cross_section_girth_m: float|None=Field(default=None,ge=0,le=10000)
    cross_section_area_m2: float|None=Field(default=None,ge=0,le=10000)
    understands_balise: bool|None=None
    understands_loop: bool|None=None
    understands_radio: bool|None=None
    rack_and_pinion: bool|None=None
    nominal_power_kw: int|None=Field(default=None,strict=True,gt=0,le=1000000)
    maximum_power_kw: int|None=Field(default=None,strict=True,ge=0,le=1000000,description='Explicit stored power metadata; does not replace the chosen traction curve source.')
    traction_points: list[TractionPoint]|None=Field(default=None,min_length=2,max_length=1000)
    tractive_effort_diagrams: list[TractiveEffortDiagramSpec]|None=Field(default=None,min_length=1,max_length=64)
    replace_existing: bool=False

    @model_validator(mode='after')
    def curve_source(self):
        if sum(value is not None for value in [self.nominal_power_kw,self.traction_points,self.tractive_effort_diagrams])!=1:raise ValueError('Provide exactly one of nominal_power_kw, traction_points or tractive_effort_diagrams.')
        if self.tractive_effort_diagrams is not None:
            codes=[code for diagram in self.tractive_effort_diagrams for code in diagram.power_system_codes]
            if len(codes)!=len(set(codes)):raise ValueError('Each power system can belong to at most one diagram.')
        if self.adhesion_mass_t is not None and self.adhesion_mass_t>self.mass_t:raise ValueError('Adhesion mass cannot exceed total engine mass.')
        if self.driven_axles>self.number_of_axles:raise ValueError('Driven axles cannot exceed total axles.')
        if self.minimum_force_kn is not None and self.minimum_force_kn>self.maximum_force_kn:raise ValueError('minimum_force_kn cannot exceed maximum_force_kn.')
        return self


class ProbabilityInterval(Input):
    minimum: float=Field(ge=0,le=1000000)
    maximum: float=Field(ge=0,le=1000000)
    probability_percent: float=Field(ge=0,le=100)

    @model_validator(mode='after')
    def order(self):
        if self.maximum<self.minimum:raise ValueError('maximum must be at least minimum.')
        return self


class DelayPriority(Input):
    delay_s: float=Field(ge=0,le=1000000)
    priority: int=Field(ge=1,le=10000)


class CategorySpec(Input):
    name: ArchiveName
    template_name: str|None=None
    dispatching_priority: int=Field(default=1,ge=1,le=10000)
    look_ahead_distance_m: int=Field(default=6000,strict=True,ge=0,le=10000000)
    look_ahead_time_s: float=Field(default=120,ge=0,le=1000000)
    dispatching_type_code: int=Field(default=0,ge=0,le=1000,description='Native selection-menu tag; preserved as a code, not a guessed strategy name.')
    enabled: bool=True
    use_initial_delay: bool=False
    initial_delay_mean_s: float=Field(default=0,ge=0,le=1000000)
    initial_delay_maximum_s: float=Field(default=0,ge=0,le=1000000)
    initial_delay_probability_percent: float=Field(default=0,ge=0,le=100)
    initial_delay_distribution_code: int=Field(default=0,ge=0,le=1000)
    initial_delay_intervals: list[ProbabilityInterval]|None=Field(default=None,max_length=1000)
    use_station_delay: bool=False
    maximum_station_delay_s: float=Field(default=0,ge=0,le=1000000)
    station_delay_probability_percent: float=Field(default=0,ge=0,le=100)
    delay_limit_small_s: float=Field(default=1,ge=0,le=1000000)
    delay_limit_medium_s: float=Field(default=60,ge=0,le=1000000)
    delay_limit_large_s: float=Field(default=300,ge=0,le=1000000)
    delay_priorities: list[DelayPriority]|None=Field(default=None,max_length=1000)
    use_on_time_performance: bool=False
    use_delayed_performance: bool=False
    on_time_performance: list[ProbabilityInterval]|None=Field(default=None,max_length=1000)
    delayed_performance: list[ProbabilityInterval]|None=Field(default=None,max_length=1000)
    stop_at_every_station: bool=False
    stop_at_every_station_time_s: float|None=Field(default=None,ge=0,le=1000000)
    timing_stations_type_code: int|None=Field(default=None,strict=True,ge=-2147483648,le=2147483647)
    foreground_color: DiagramColor|None=None
    background_color: DiagramColor|None=None
    dwell_variation_early: float|None=Field(default=None,ge=-1000000,le=1000000)
    dwell_variation_delayed: float|None=Field(default=None,ge=-1000000,le=1000000)
    dwell_variation_early_unit_code: int|None=Field(default=None,strict=True,ge=-2147483648,le=2147483647,description='Native 0=seconds, 1=percent of planned dwell; other saved codes are not relabelled.')
    dwell_variation_delayed_unit_code: int|None=Field(default=None,strict=True,ge=-2147483648,le=2147483647)
    delay_add_type_code: int|None=Field(default=None,strict=True,ge=-2147483648,le=2147483647)
    default_connection_time_s: float|None=Field(default=None,ge=0,le=1000000)
    departure_process_time_s: float|None=Field(default=None,ge=0,le=1000000)
    departure_process_starts_at_departure_time: bool|None=None
    track_name_creation_type_code: int|None=Field(default=None,strict=True,ge=-2147483648,le=2147483647)
    dwell_variation_early_delay_offset_s: float|None=Field(default=None,ge=-1000000,le=-1)
    dwell_variation_delayed_delay_offset_s: float|None=Field(default=None,ge=1,le=1000000)
    replace_existing: bool=False

    @model_validator(mode='after')
    def ranges(self):
        if self.initial_delay_maximum_s<self.initial_delay_mean_s:raise ValueError('Initial maximum delay must be at least the mean delay.')
        if not self.delay_limit_small_s<=self.delay_limit_medium_s<=self.delay_limit_large_s:raise ValueError('Delay thresholds must be ordered small <= medium <= large.')
        for intervals in [self.initial_delay_intervals,self.on_time_performance,self.delayed_performance]:
            if intervals:
                if abs(sum(p.probability_percent for p in intervals)-100)>.001:raise ValueError('Interval probabilities must sum to 100 percent.')
                if any(b.minimum<a.maximum for a,b in zip(intervals,intervals[1:])):raise ValueError('Probability intervals must be ordered and non-overlapping.')
        if self.delay_priorities and any(b.delay_s<=a.delay_s for a,b in zip(self.delay_priorities,self.delay_priorities[1:])):raise ValueError('Delay-priority thresholds must increase strictly.')
        return self


class EngineReference(Input):
    engine_name: ArchiveName
    count: int=Field(default=1,ge=1,le=32)
    positions: list[Annotated[int,Field(strict=True,ge=1,le=1024)]]|None=None

    @model_validator(mode='after')
    def placement(self):
        if self.positions is not None and (len(self.positions)!=self.count or len(set(self.positions))!=len(self.positions)):
            raise ValueError('positions must contain exactly count distinct positions.')
        return self


class TrailerSpec(Input):
    name: ArchiveName
    mass_t: int=Field(strict=True,gt=0,le=100000)
    length_m: int=Field(strict=True,gt=0,le=10000)
    maximum_speed_kmh: int=Field(strict=True,gt=0,le=1000)
    count: int=Field(default=1,ge=1,le=1000)
    positions: list[Annotated[int,Field(strict=True,ge=1,le=1024)]]|None=None
    rotating_mass_factor: float=Field(default=1.06,ge=1,le=3)
    number_of_axles: int=Field(default=4,ge=1,le=1000)
    number_of_items: int=Field(default=1,ge=0,le=10000,description='Native resistance parameter; does not multiply this record mass/length. Use count for repeated physical records.')
    cw_value: float|None=Field(default=None,ge=0,le=100)
    power_loss_kw: float=Field(default=0,ge=0,le=1000000)
    power_loss_delta_load_factor_kw_per_t: float=Field(default=0,ge=0,le=1000000)

    @model_validator(mode='after')
    def placement(self):
        if self.positions is not None and (len(self.positions)!=self.count or len(set(self.positions))!=len(self.positions)):
            raise ValueError('positions must contain exactly count distinct positions.')
        return self


class BrakingPoint(Input):
    speed_kmh: int=Field(strict=True,ge=0,le=1000)
    deceleration_mps2: float=Field(gt=0,le=5)
    secondary_deceleration_mps2: float|None=Field(default=None,gt=0,le=5)


class FormationSpec(Input):
    name: ArchiveName
    template_name: str|None=None
    engines: list[EngineReference]=Field(min_length=1,max_length=32)
    trailers: list[TrailerSpec]=Field(default_factory=list,max_length=100)
    category: ArchiveName|None=None
    braking_deceleration_mps2: float=Field(default=.8,gt=0,le=5)
    maximum_acceleration_mps2: float=Field(default=1,gt=0,le=10)
    braking_points: list[BrakingPoint]|None=Field(default=None,min_length=2,max_length=1000)
    train_type_code: Literal[0,1,2]|None=None
    acceleration_delay_s: float|None=Field(default=None,ge=0,le=1000000)
    maximum_drawbar_force_kn: float|None=Field(default=None,ge=0,le=1000000)
    use_maximum_drawbar_force: bool|None=None
    use_minimum_time_to_hold_speed: bool|None=None
    braking_delay_s: float|None=Field(default=None,ge=0,le=1000000)
    braking_release_speed_kmh: float|None=Field(default=None,ge=0,le=1000)
    braking_delay_type_code: int|None=Field(default=None,ge=0,le=1000)
    resistance_formula_code: int|None=Field(default=None,ge=0,le=1000)
    resistance_coefficients_excl: tuple[float,float,float]|None=None
    resistance_coefficients_incl: tuple[float,float,float]|None=None
    curve_resistance_formula_code: int|None=Field(default=None,ge=0,le=1000)
    curve_resistance_percent: float|None=Field(default=None,ge=0,le=10000)
    acceleration_delay_at_stop_s: float|None=Field(default=None,ge=0,le=1000000)
    minimum_time_to_hold_speed_s: float|None=Field(default=None,ge=0,le=1000000)
    replace_existing: bool=False


class StockSelection(Input):
    names: list[ArchiveName]=Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def selection_and_fields(self):
        if len(self.names)!=len(set(self.names)):raise ValueError('Selected names must be unique.')
        fields=self.model_fields_set-{'names','kind'}
        if not fields:raise ValueError('Supply at least one field to update.')
        if any(getattr(self,key) is None for key in fields):raise ValueError('Omit unchanged fields; explicit null is not a stock field value.')
        if len({'traction_points','nominal_power_kw','tractive_effort_diagrams'}&fields)>1:raise ValueError('Supply one traction curve source.')
        if 'braking_points' in fields and 'braking_deceleration_mps2' in fields:raise ValueError('Supply one braking curve source.')
        return self


def stock_field_schema(schema):
    schema.pop('default',None)
    if 'anyOf' in schema:
        branches=[branch for branch in schema['anyOf'] if branch.get('type')!='null']
        if len(branches)==1:schema.pop('anyOf');schema.update(branches[0])
        else:schema['anyOf']=branches


def stock_update_model(name,kind,spec):
    """Reuse field bounds without applying creation defaults to partial edits."""
    fields={'kind':(Literal[kind],kind)}
    for key,original in spec.model_fields.items():
        if key in {'name','template_name','replace_existing'}:continue
        field=copy.deepcopy(original);field.default=None;field.default_factory=None
        
        field.json_schema_extra=stock_field_schema
        fields[key]=(original.annotation|None,field)
    return create_model(name,__base__=StockSelection,**fields)


UpdateEngines=stock_update_model('UpdateEngines','update_engines',EngineSpec)
UpdateFormations=stock_update_model('UpdateFormations','update_formations',FormationSpec)
UpdateCategories=stock_update_model('UpdateCategories','update_categories',CategorySpec)


class StockRename(Input):
    name: ArchiveName
    new_name: ArchiveName


class RenameStock(Input):
    kind: Literal['rename_engines','rename_formations','rename_categories']
    renames: list[StockRename]=Field(min_length=1,max_length=1000)


class DeleteStock(Input):
    kind: Literal['delete_engines','delete_formations','delete_categories']
    names: list[ArchiveName]=Field(min_length=1,max_length=1000)
    replacement: ArchiveName|None=None
    reference_policy: Literal['reject','cascade']='reject'

    @model_validator(mode='after')
    def deletion_policy(self):
        if len(self.names)!=len(set(self.names)):raise ValueError('Selected names must be unique.')
        if self.replacement in self.names:raise ValueError('Replacement must survive deletion.')
        if self.replacement is not None and self.reference_policy=='cascade':raise ValueError('Choose a replacement or cascade, not both.')
        return self


class DiagramUpdateBase(Input):
    action: Literal['update']='update'
    index: int=Field(strict=True,ge=0,le=63)

    @model_validator(mode='after')
    def changed_fields(self):
        fields=self.model_fields_set-{'index','action'}
        if not fields:raise ValueError('Supply a diagram field to update.')
        if any(getattr(self,key) is None for key in fields):raise ValueError('Omit unchanged fields; explicit null is not a diagram field value.')
        return self


def diagram_update_model():
    fields={}
    for key,original in TractiveEffortDiagramSpec.model_fields.items():
        field=copy.deepcopy(original);field.default=None;field.default_factory=None;field.json_schema_extra=stock_field_schema
        fields[key]=(original.annotation|None,field)
    return create_model('UpdateEngineDiagram',__base__=DiagramUpdateBase,**fields)


UpdateEngineDiagram=diagram_update_model()


class AddEngineDiagram(Input):
    action: Literal['add']='add'
    diagram: TractiveEffortDiagramSpec
    before_index: int|None=Field(default=None,strict=True,ge=0,le=64)


class DuplicateEngineDiagram(Input):
    action: Literal['duplicate']='duplicate'
    index: int=Field(strict=True,ge=0,le=63)
    description: ArchiveText|None=None
    power_system_codes: list[PowerSystemCode]|None=Field(default=None,max_length=256)
    before_index: int|None=Field(default=None,strict=True,ge=0,le=64)


class DeleteEngineDiagram(Input):
    action: Literal['delete']='delete'
    index: int=Field(strict=True,ge=0,le=63)


class ImportEngineCurve(Input):
    action: Literal['import_text']='import_text'
    index: int|None=Field(default=None,strict=True,ge=0,le=63)
    content: str|None=Field(default=None,max_length=2000000)
    file_path: str|None=Field(default=None,max_length=1000)
    existing: Literal['replace','insert','new']='replace'
    power_system_codes: list[PowerSystemCode]|None=Field(default=None,max_length=256,description='New diagrams only; omit for the original next-free supply order.')
    description: ArchiveText|None=None

    @model_validator(mode='after')
    def inputs(self):
        if (self.content is None)==(self.file_path is None):raise ValueError('Supply exactly one of content or file_path.')
        if self.existing!='new' and self.index is None:raise ValueError('An existing diagram needs its index.')
        if self.existing=='new' and self.index is not None:raise ValueError('New diagrams append; do not supply an existing index.')
        if self.existing!='new' and (self.power_system_codes is not None or self.description is not None):raise ValueError('Existing imports preserve diagram names and systems; use an explicit update command to change them.')
        if self.power_system_codes is not None and len(set(self.power_system_codes))!=len(self.power_system_codes):raise ValueError('Power-system codes must be unique.')
        return self


class ExportEngineCurves(ProjectInput):
    engine_names: list[ArchiveName]=Field(default_factory=list,max_length=1000,description='Empty selects all saved Engines.')
    diagram_indices: list[Annotated[int,Field(strict=True,ge=0,le=63)]]|None=Field(default=None,min_length=1,max_length=64)
    format: Literal['opentrack_text','json']='opentrack_text'

    @model_validator(mode='after')
    def selection(self):
        if len(self.engine_names)!=len(set(self.engine_names)):raise ValueError('Engine selections must be unique.')
        if self.diagram_indices is not None and len(self.diagram_indices)!=len(set(self.diagram_indices)):raise ValueError('Diagram indices must be unique.')
        return self


class ExportRollingStock(ProjectInput):
    format: Literal['railml_2_2','railml_1_00','railml_1_03']='railml_2_2'
    engine_names: list[ArchiveName]|None=Field(default=None,max_length=1000,description='Null exports all Engines, or the dependency closure when formations are selected. Empty explicitly selects none.')
    formation_names: list[ArchiveName]|None=Field(default=None,max_length=1000,description='Null selects all formations; empty selects none.')
    dataset_name: ArchiveText|None=None

    @model_validator(mode='after')
    def unique_selections(self):
        for values in [self.engine_names,self.formation_names]:
            if values is not None and len(values)!=len(set(values)):raise ValueError('Stock selections must be unique.')
        return self


class ImportRollingStockXML(Input):
    kind: Literal['import_rolling_stock_xml']='import_rolling_stock_xml'
    content: str|None=Field(default=None,max_length=20*1024*1024)
    file_path: str|None=Field(default=None,max_length=2000)
    on_conflict: Literal['error','keep','replace']='error'
    clear_catalogs: list[Literal['engines','formations']]=Field(default_factory=list,max_length=2)
    category: ArchiveName|None=Field(default=None,description='Explicit saved Category override. Null preserves the native English Untitled default; define/bind that Category separately if missing.')
    recompute_limits: bool=Field(default=False,description='Explicit post-import Engine diagram-limit command; native XML import alone leaves stored force/power maxima at reset defaults.')

    @model_validator(mode='after')
    def source_and_policy(self):
        if (self.content is None)==(self.file_path is None):raise ValueError('Supply exactly one of content or file_path.')
        if len(self.clear_catalogs)!=len(set(self.clear_catalogs)):raise ValueError('Catalog clearing selections must be unique.')
        return self


NativePointInt=Annotated[int,Field(strict=True,ge=-2147483648,le=2147483647)]


class EnginePointRef(Input):
    curve: Literal['traction','braking']
    point_index: int=Field(strict=True,ge=0,le=99999)


class AddEnginePoint(Input):
    action: Literal['add_point']='add_point'
    index: int=Field(strict=True,ge=0,le=63)
    speed_kmh: NativePointInt
    force_kn: NativePointInt
    interpolation: Literal['linear','hyperbolic']='linear'
    if_speed_exists: Literal['keep_existing','error']='keep_existing'


class UpdateEnginePoint(EnginePointRef):
    action: Literal['update_point']='update_point'
    index: int=Field(strict=True,ge=0,le=63)
    speed_kmh: NativePointInt|None=Field(default=None,json_schema_extra=stock_field_schema)
    force_kn: NativePointInt|None=Field(default=None,json_schema_extra=stock_field_schema)
    interpolation: Literal['linear','hyperbolic']|None=Field(default=None,json_schema_extra=stock_field_schema)

    @model_validator(mode='after')
    def values(self):
        fields=self.model_fields_set-{'action','index','curve','point_index'}
        if not fields or any(getattr(self,key) is None for key in fields):raise ValueError('Supply point fields to change; omit unchanged fields instead of null.')
        return self


class MoveEnginePoint(EnginePointRef):
    action: Literal['move_point']='move_point'
    index: int=Field(strict=True,ge=0,le=63)
    speed_kmh: NativePointInt
    force_kn: NativePointInt


class DeleteEnginePoints(Input):
    action: Literal['delete_points']='delete_points'
    index: int=Field(strict=True,ge=0,le=63)
    points: list[EnginePointRef]=Field(default_factory=list,max_length=100000)
    all_points: bool=False

    @model_validator(mode='after')
    def selection(self):
        if self.all_points==bool(self.points):raise ValueError('Choose explicit point references or all_points=true.')
        keys=[(p.curve,p.point_index) for p in self.points]
        if len(keys)!=len(set(keys)):raise ValueError('Point references must be unique.')
        return self


class SetEngineDiagramScale(Input):
    action: Literal['set_scale']='set_scale'
    index: int=Field(strict=True,ge=0,le=63)
    axis_maximum_speed_kmh: NativePointInt|None=Field(default=None,json_schema_extra=stock_field_schema)
    axis_maximum_force_kn: NativePointInt|None=Field(default=None,json_schema_extra=stock_field_schema)
    axis_minimum_force_kn: NativePointInt|None=Field(default=None,json_schema_extra=stock_field_schema)

    @model_validator(mode='after')
    def values(self):
        fields=self.model_fields_set-{'action','index'}
        if not fields or any(getattr(self,key) is None for key in fields):raise ValueError('Supply scale fields to change; omit unchanged fields instead of null.')
        return self


class AutoScaleEngineDiagram(Input):
    action: Literal['auto_scale']='auto_scale'
    index: int=Field(strict=True,ge=0,le=63)
    limits_source: Literal['saved_engine','curves']='saved_engine'


class EngineDiagramQuery(ProjectInput):
    engine_name: ArchiveName
    index: int=Field(default=0,strict=True,ge=0,le=63)
    curve: Literal['traction','braking','both']='both'
    offset: int=Field(default=0,strict=True,ge=0)
    limit: int=Field(default=50,strict=True,ge=1,le=200)


EngineDiagramCommand=Annotated[UpdateEngineDiagram|AddEngineDiagram|DuplicateEngineDiagram|DeleteEngineDiagram|ImportEngineCurve|AddEnginePoint|UpdateEnginePoint|MoveEnginePoint|DeleteEnginePoints|SetEngineDiagramScale|AutoScaleEngineDiagram,Field(discriminator='action')]


class EditEngineDiagrams(Input):
    kind: Literal['edit_engine_diagrams']='edit_engine_diagrams'
    names: list[ArchiveName]=Field(min_length=1,max_length=1000)
    edits: list[EngineDiagramCommand]=Field(min_length=1,max_length=1000)
    recompute_engine_limits: bool=True

    @model_validator(mode='after')
    def unique_names(self):
        if len(self.names)!=len(set(self.names)):raise ValueError('Selected Engine names must be unique.')
        return self


class MigrateRollingStock(Input):
    kind: Literal['migrate_rolling_stock']='migrate_rolling_stock'
    entities: list[Literal['engines','formations']]=Field(default_factory=lambda:['engines','formations'],min_length=1,max_length=2)

    @model_validator(mode='after')
    def unique_entities(self):
        if len(self.entities)!=len(set(self.entities)):raise ValueError('Migration entity groups must be unique.')
        return self


RollingStockOperation=Annotated[UpdateEngines|UpdateFormations|UpdateCategories|RenameStock|DeleteStock|EditEngineDiagrams|MigrateRollingStock,Field(discriminator='kind')]


class StationSpec(Input):
    sign: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_.-]{0,31}$')
    name: ArchiveName
    document: str|None=None
    end_ids: list[int]=Field(default_factory=list,max_length=1000)
    timing_station: bool|None=None
    replace_existing: bool=False


TimeText=Annotated[str,Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')]


class ConnectionSpec(Input):
    target_course_id: CourseId
    target_station_sign: str|None=Field(default=None,min_length=1,max_length=32)
    minimum_wait_s: int=Field(default=0,ge=0,le=86399)
    maximum_wait_s: int|None=Field(default=None,ge=0,le=86399)
    entry_connection: bool=False
    join: bool=False
    split: bool=False
    dispo_connection: bool=False
    time_reference_type: int=Field(default=0,strict=True,ge=0,le=2147483647,description='Original saved connection-time type; raw native code, not the location flag.')
    dispatching_distance_km: float=Field(default=0,ge=0,le=1000000)

    @model_validator(mode='after')
    def waits(self):
        if self.maximum_wait_s is not None and self.maximum_wait_s<self.minimum_wait_s:raise ValueError('maximum_wait_s must be at least minimum_wait_s.')
        if self.entry_connection and self.dispo_connection:raise ValueError('Entry and dispo connection locations are mutually exclusive.')
        return self


class StopAttributes(Input):
    station_sign: str=Field(min_length=1,max_length=32)
    dwell_s: int=Field(default=0,ge=0,le=86400)
    track_id: ArchiveText=''
    stop_at_station: bool=True
    timing_station: bool=True
    connections: list[ConnectionSpec]=Field(default_factory=list,max_length=100)
    mean_delay_s: float=Field(default=0,ge=0,le=1000000)
    distribution_name: ArchiveText=''
    delta_mass_t: float=Field(default=0,ge=-100000,le=100000)
    interval_reference_course_id: CourseId|None=None
    interval_offset_s: float=Field(default=0,ge=-31622400,le=31622400)


class TimetableStop(StopAttributes):
    arrival: TimeText|None=None
    departure: TimeText|None=None
    arrival_day_offset: int=Field(default=0,strict=True,ge=-366,le=366)
    departure_day_offset: int=Field(default=0,strict=True,ge=-366,le=366)

    @model_validator(mode='after')
    def offsets(self):
        if self.arrival is None and self.arrival_day_offset:raise ValueError('arrival_day_offset requires arrival.')
        if self.departure is None and self.departure_day_offset:raise ValueError('departure_day_offset requires departure.')
        return self


class CourseSpec(Input):
    course_id: NewCourseId
    train: ArchiveName
    itineraries: list[ArchiveName]=Field(min_length=1,max_length=100)
    speed_type: ArchiveName
    template_id: CourseId|None=None
    enabled: bool=True
    acceleration_percent: int=Field(default=100,ge=0,le=1000)
    delayed_acceleration_percent: int=Field(default=100,ge=0,le=1000)
    spacing_mode: Literal['discrete','moving','moving_cbtc']='discrete'
    additional_reservation_time_s: float=Field(default=0,ge=0,le=31622400)
    additional_release_time_s: float=Field(default=0,ge=0,le=31622400)
    entering_speed_kmh: float=Field(default=0,ge=0,le=1000)
    output_offset_m: float=Field(default=0,ge=-10000000,le=10000000)
    description: ArchiveText=''
    comment: ArchiveText=''
    train_number: ArchiveText=''
    course_type: ArchiveText=''
    stops: list[TimetableStop]=Field(min_length=2,max_length=1000)
    replace_existing: bool=False

    @model_validator(mode='before')
    @classmethod
    def reject_priority(cls,values):
        if isinstance(values,dict) and 'priority' in values:raise ValueError('priority was incorrectly named in v0.6: native Course group 6 is acceleration_percent, not dispatch priority. Specify acceleration_percent explicitly; dispatch priority belongs to a Train Category.')
        return values


class PatternStop(StopAttributes):
    arrival_offset_s: int|None=Field(default=None,ge=0,le=31622400)
    departure_offset_s: int|None=Field(default=None,ge=0,le=31622400)


class ServicePattern(Input):
    id_prefix: str=Field(default='G',pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,19}$')
    first_number: int=Field(ge=0,le=99999999)
    count: int=Field(ge=1,le=1000)
    number_step: int=Field(default=2,ge=1,le=1000)
    first_departure: TimeText
    first_departure_day_offset: int=Field(default=0,strict=True,ge=-366,le=366)
    interval_s: int=Field(ge=1,le=31622400)
    train: ArchiveName
    itineraries: list[ArchiveName]=Field(min_length=1,max_length=100)
    speed_type: ArchiveName
    template_id: CourseId|None=None
    description: ArchiveText=''
    stops: list[PatternStop]=Field(min_length=2,max_length=1000)
    enabled: bool=True
    acceleration_percent: int=Field(default=100,ge=0,le=1000)
    delayed_acceleration_percent: int=Field(default=100,ge=0,le=1000)
    spacing_mode: Literal['discrete','moving','moving_cbtc']='discrete'
    additional_reservation_time_s: float=Field(default=0,ge=0,le=31622400)
    additional_release_time_s: float=Field(default=0,ge=0,le=31622400)
    entering_speed_kmh: float=Field(default=0,ge=0,le=1000)
    output_offset_m: float=Field(default=0,ge=-10000000,le=10000000)
    comment: ArchiveText=''
    train_number: ArchiveText=''
    course_type: ArchiveText=''
    keep_interval_reference: bool=False
    replace_existing: bool=False

    @model_validator(mode='before')
    @classmethod
    def reject_priority(cls,values):
        return CourseSpec.reject_priority(values)


class ItineraryMove(Input):
    name: ArchiveName
    priority: int=Field(ge=1,le=1000,description='1 is first; the original method clamps a position past the list to its last position.')


class UpdateCourses(Input):
    kind: Literal['update_courses']='update_courses'
    course_ids: list[CourseId]=Field(min_length=1,max_length=1000)
    train: ArchiveName|None=None
    itineraries: list[ArchiveName]|None=Field(default=None,min_length=1,max_length=100)
    itinerary_move: ItineraryMove|None=None
    speed_type: ArchiveName|None=None
    enabled: bool|None=None
    invert_enabled: bool=False
    acceleration_percent: int|None=Field(default=None,ge=0,le=1000)
    delayed_acceleration_percent: int|None=Field(default=None,ge=0,le=1000)
    spacing_mode: Literal['discrete','moving','moving_cbtc']|None=None
    additional_reservation_time_s: float|None=Field(default=None,ge=0,le=31622400)
    additional_release_time_s: float|None=Field(default=None,ge=0,le=31622400)
    entering_speed_kmh: float|None=Field(default=None,ge=0,le=1000)
    output_offset_m: float|None=Field(default=None,ge=-10000000,le=10000000)
    description: ArchiveText|None=None
    comment: ArchiveText|None=None
    train_number: ArchiveText|None=None
    course_type: ArchiveText|None=None

    @model_validator(mode='before')
    @classmethod
    def reject_priority(cls,values):return CourseSpec.reject_priority(values)

    @model_validator(mode='after')
    def update_fields(self):
        fields=self.model_fields_set-{'kind','course_ids','invert_enabled'}
        if not fields and not self.invert_enabled:raise ValueError('Supply at least one Course attribute or invert_enabled=true.')
        if any(getattr(self,name) is None for name in fields):raise ValueError('Omit unchanged Course fields; use an empty string to clear optional text, not null.')
        if len(set(self.course_ids))!=len(self.course_ids):raise ValueError('course_ids must be unique within an update.')
        if self.itineraries is not None and self.itinerary_move is not None:raise ValueError('Supply either itineraries or itinerary_move.')
        if self.enabled is not None and self.invert_enabled:raise ValueError('Supply either enabled or invert_enabled=true.')
        return self


class DefineEngine(EngineSpec):kind: Literal['define_engine']='define_engine'
class DefineCategory(CategorySpec):kind: Literal['define_category']='define_category'
class DefineFormation(FormationSpec):kind: Literal['define_formation']='define_formation'
class DefineStation(StationSpec):kind: Literal['define_station']='define_station'
class DefineCourse(CourseSpec):kind: Literal['define_course']='define_course'
class DefinePattern(ServicePattern):kind: Literal['service_pattern']='service_pattern'


class TimetableSpec(Input):
    course_id: CourseId
    stops: list[TimetableStop]=Field(min_length=2,max_length=1000)


class DefineTimetable(TimetableSpec):kind: Literal['set_timetable']='set_timetable'


class CreateTimetableSkeletons(Input):
    kind: Literal['create_timetable_skeletons']='create_timetable_skeletons'
    course_ids: list[CourseId]=Field(min_length=1,max_length=1000)
    replace_existing: bool=False

    @model_validator(mode='after')
    def unique_courses(self):
        if len(self.course_ids)!=len(set(self.course_ids)):raise ValueError('Selected Course IDs must be unique.')
        return self


class CourseRename(Input):
    course_id: CourseId
    new_id: NewCourseId


class RenameCourses(Input):
    kind: Literal['rename_courses']='rename_courses'
    renames: list[CourseRename]=Field(min_length=1,max_length=1000,description='Simultaneous exact renames, including swaps; updates audited references in all selected archives.')


class DeleteCourses(Input):
    kind: Literal['delete_courses']='delete_courses'
    course_ids: list[CourseId]=Field(min_length=1,max_length=1000)
    reference_policy: Literal['reject','detach']='reject'


class ResetCourseItineraries(Input):
    kind: Literal['reset_course_itineraries']='reset_course_itineraries'
    course_ids: list[CourseId]=Field(min_length=1,max_length=1000)


class TimetableRowRef(Input):
    course_id: CourseId
    index: int=Field(strict=True,ge=0,le=1000000)


class TimetableSelection(Input):
    course_ids: list[CourseId]=Field(default_factory=list,max_length=1000)
    rows: list[TimetableRowRef]=Field(default_factory=list,max_length=10000)

    @model_validator(mode='after')
    def selection(self):
        if bool(self.course_ids)==bool(self.rows):raise ValueError('Select exactly one of nonempty course_ids or rows.')
        if len(set(self.course_ids))!=len(self.course_ids) or len({(r.course_id,r.index) for r in self.rows})!=len(self.rows):raise ValueError('Timetable selections must not repeat Courses or rows.')
        return self


class UpdateTimetableRows(TimetableSelection):
    kind: Literal['update_timetable_rows']='update_timetable_rows'
    station_sign: str|None=Field(default=None,min_length=1,max_length=32)
    track_id: ArchiveText|None=None
    arrival: TimeText|None=None
    departure: TimeText|None=None
    arrival_day_offset: int|None=Field(default=None,strict=True,ge=-366,le=366)
    departure_day_offset: int|None=Field(default=None,strict=True,ge=-366,le=366)
    dwell_s: int|None=Field(default=None,ge=0,le=86400)
    stop_at_station: bool|None=None
    timing_station: bool|None=None
    mean_delay_s: float|None=Field(default=None,ge=0,le=1000000)
    distribution_name: ArchiveText|None=None
    delta_mass_t: float|None=Field(default=None,ge=-100000,le=100000)
    connections: list[ConnectionSpec]|None=Field(default=None,max_length=100)
    propagate_interval: bool=False
    propagate_delays: bool=False
    rebind_station_connections: bool=False

    @model_validator(mode='after')
    def partial(self):
        fields=self.model_fields_set-{'kind','course_ids','rows','propagate_interval','propagate_delays','rebind_station_connections'}
        if not fields:raise ValueError('Supply at least one timetable attribute to update.')
        if any(getattr(self,name) is None for name in fields-{'arrival','departure'}):raise ValueError('Only arrival/departure accept null to clear a saved time; omit other fields to preserve them.')
        for field in ['arrival','departure']:
            if field in fields and getattr(self,field) is None and getattr(self,field+'_day_offset'):raise ValueError('A cleared time must use day offset zero.')
        return self


class InsertTimetableRows(Input):
    kind: Literal['insert_timetable_rows']='insert_timetable_rows'
    course_id: CourseId
    before_index: int|None=Field(default=None,strict=True,ge=0,le=1000000,description='Null appends; indices refer to the state at this operation.')
    stops: list[TimetableStop]=Field(min_length=1,max_length=1000)


class DeleteTimetableRows(TimetableSelection):
    kind: Literal['delete_timetable_rows']='delete_timetable_rows'
    reference_policy: Literal['reject','detach']='reject'


class ShiftTimetableRows(TimetableSelection):
    kind: Literal['shift_timetable_rows']='shift_timetable_rows'
    seconds: int=Field(strict=True,ge=-31622400,le=31622400)
    propagate_interval: bool=False


class SetTimetableInterval(Input):
    kind: Literal['set_timetable_interval']='set_timetable_interval'
    course_ids: list[CourseId]=Field(min_length=1,max_length=1000)
    reference_course_id: NewCourseId|None=None
    offset_s: float|None=Field(default=None,ge=-31622400,le=31622400)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.course_ids))!=len(self.course_ids):raise ValueError('Interval selections must not repeat Courses.')
        if 'offset_s' in self.model_fields_set and self.offset_s is None:raise ValueError('Omit offset_s to preserve it; null is not a stored offset.')
        return self


class ResetTimetableActual(TimetableSelection):kind: Literal['reset_timetable_actual']='reset_timetable_actual'
class CopyTimetableActual(TimetableSelection):kind: Literal['copy_actual_to_planned']='copy_actual_to_planned'
class SyncTimetable(Input):
    kind: Literal['sync_timetable']='sync_timetable'
    reference_policy: Literal['reject','detach']='reject'


class CreateIntervalCourses(Input):
    kind: Literal['create_interval_courses']='create_interval_courses'
    source_course_id: NewCourseId
    count: int=Field(strict=True,ge=1,le=1000,description='Additional sequential copies, excluding the source.')
    number_step: int=Field(default=1,strict=True,ge=-2147483648,le=2147483647)
    number_position: int=Field(default=0,strict=True,ge=0,le=31,description='Zero-based numeric block; absent block appends .<number_step> as in the original helper.')
    interval_s: int=Field(strict=True,ge=-31622400,le=31622400,description='Signed time step between successive copies; native float32 time semantics apply.')
    update_courses: bool=True
    replace_existing: bool=False

    @model_validator(mode='after')
    def nonzero_number(self):
        if not self.number_step:raise ValueError('number_step must change the Course ID; self-replacement cannot create an interval Course.')
        return self


class ConnectionPatch(Input):
    index: int=Field(strict=True,ge=0,le=1000000)
    target_course_id: CourseId|None=None
    target_station_sign: str|None=Field(default=None,min_length=1,max_length=32)
    minimum_wait_s: int|None=Field(default=None,ge=0,le=86399)
    maximum_wait_s: int|None=Field(default=None,ge=0,le=86399)
    join: bool|None=None
    split: bool|None=None
    location: Literal['exit','entry','dispo']|None=None
    time_reference_type: int|None=Field(default=None,strict=True,ge=0,le=2147483647)
    dispatching_distance_km: float|None=Field(default=None,ge=0,le=1000000)

    @model_validator(mode='after')
    def attributes(self):
        fields=self.model_fields_set-{'index'}
        if not fields or any(getattr(self,key) is None for key in fields-{'maximum_wait_s'}):raise ValueError('Supply connection attributes; only maximum_wait_s accepts null to clear the limit.')
        return self


class EditTimetableConnections(Input):
    kind: Literal['edit_timetable_connections']='edit_timetable_connections'
    row: TimetableRowRef
    updates: list[ConnectionPatch]=Field(default_factory=list,max_length=1000)
    delete_indices: list[Annotated[int,Field(strict=True,ge=0,le=1000000)]]=Field(default_factory=list,max_length=1000)
    append: list[ConnectionSpec]=Field(default_factory=list,max_length=1000)
    clear: bool=False
    propagate_interval: bool=False

    @model_validator(mode='after')
    def changes(self):
        indices=[item.index for item in self.updates]
        if len(indices)!=len(set(indices)) or len(self.delete_indices)!=len(set(self.delete_indices)) or set(indices)&set(self.delete_indices):raise ValueError('Connection indices must be unique and cannot be both updated and deleted.')
        if any(index<0 for index in self.delete_indices):raise ValueError('Connection indices are zero-based nonnegative integers.')
        if self.clear and (self.updates or self.delete_indices):raise ValueError('clear cannot be combined with old-index updates/deletions.')
        if not (self.updates or self.delete_indices or self.append or self.clear):raise ValueError('Supply a connection change.')
        if self.propagate_interval and (not self.updates or self.delete_indices or self.append or self.clear):raise ValueError('Interval connection-property propagation requires indexed updates only; insertion/deletion are separate commands.')
        return self


class TimetableConnectionCommand(Input):
    action: Literal['insert','turnround_to','turnround_from','add_start','add_end','join_at_station','split_at_station','split_at_end','delete']='insert'
    row: TimetableRowRef
    target_course_id: NewCourseId|None=None
    connection_index: int|None=Field(default=None,strict=True,ge=0,le=1000000)

    @model_validator(mode='after')
    def arguments(self):
        if self.action=='delete':
            if self.connection_index is None or self.target_course_id is not None:raise ValueError('delete requires connection_index and no target_course_id.')
        elif self.connection_index is not None:raise ValueError('connection_index applies only to delete.')
        elif self.action!='insert' and self.target_course_id is None:raise ValueError('This command requires target_course_id; only insert supports an unbound placeholder.')
        return self


class PlanTimetableConnections(Input):
    kind: Literal['plan_timetable_connections']='plan_timetable_connections'
    commands: list[TimetableConnectionCommand]=Field(min_length=1,max_length=1000)


class TimetableCourseTemplate(Input):
    course_id: NewCourseId
    template_id: CourseId


class ImportTimetableText(Input):
    kind: Literal['import_timetable_text']='import_timetable_text'
    content: str|None=Field(default=None,max_length=2000000)
    file_path: str|None=Field(default=None,max_length=1000)
    existing: Literal['reject','replace','merge']='reject'
    default_template_id: CourseId|None=None
    templates: list[TimetableCourseTemplate]=Field(default_factory=list,max_length=1000)
    create_unbound_courses: bool=False

    @model_validator(mode='after')
    def input_source(self):
        if (self.content is None)==(self.file_path is None):raise ValueError('Supply exactly one of content or file_path.')
        if len({item.course_id for item in self.templates})!=len(self.templates):raise ValueError('Each imported Course can have only one template mapping.')
        return self


class ImportTimetableXML(ImportTimetableText):
    kind: Literal['import_timetable_xml']='import_timetable_xml'
    format: Literal['opentrack_xml']='opentrack_xml'
    existing: Literal['reject','replace']='reject'
    clear_existing_timetables: bool=Field(default=False,description='Explicit original Remove All choice: clear all saved timetable rows before import, preserving Course definitions.')
    connection_attribute_order: Literal['require_unambiguous','place_then_time_type','time_type_then_place']=Field(default='require_unambiguous',description='Original OTXmlParser enumerates dictionary keys rather than XML attribute order. Conflicting home/station place and time-type callbacks require an explicit order until native dictionary enumeration is verified.')


class RailMLStationFilter(Input):
    uppercase: bool=False
    replace_first: int=Field(default=0,strict=True,ge=0,le=240)
    first_string: ArchiveText=''
    replace_last: int=Field(default=0,strict=True,ge=0,le=240)
    last_string: ArchiveText=''


class RailMLTimetableOptions(Input):
    dataset_name: ArchiveText|None=None
    metadata_date: ArchiveText|None=Field(default=None,description='Explicit metadata date text for reproducible exports; null uses the current original-style local date.')
    planned: bool=True
    published: bool=False
    calculated: bool=False
    only_active: bool=False
    existing_stations_only: bool=False
    station_filter: RailMLStationFilter|None=None


class ExportTimetable(ProjectInput):
    course_ids: list[CourseId]=Field(default_factory=list,max_length=1000,description='Empty exports all saved timetable Courses, including orphan rows for diagnosis.')
    format: Literal['opentrack_17','opentrack_16','opentrack_xml','railml_2_2','json']='opentrack_17'
    saved_actual: Literal['omit','as_valid']=Field(default='omit',description='XML formats only: native actual validity is unpersisted. Explicit as_valid emits saved actual strings; it does not certify runtime validity. RailML also requires calculated=true.')
    railml: RailMLTimetableOptions|None=None

    @model_validator(mode='after')
    def actual_policy(self):
        if self.railml is not None and self.format!='railml_2_2':raise ValueError('railml options apply only to railml_2_2.')
        if self.saved_actual!='omit' and self.format not in ['opentrack_xml','railml_2_2']:raise ValueError('saved_actual applies only to XML formats.')
        if self.saved_actual=='as_valid' and self.format=='railml_2_2' and not (self.railml and self.railml.calculated):raise ValueError('RailML saved_actual=as_valid requires railml.calculated=true.')
        return self


class InspectRailMLTimetable(ProjectInput,Page):
    content: str|None=Field(default=None,max_length=2000000)
    file_path: str|None=Field(default=None,max_length=1000)
    section: Literal['summary','stations','formations','train_parts','trains','train_groups','rows','times','references','diagnostics']='summary'
    train_type: str|None=Field(default=None,max_length=80,description='Diagnostic filter for trains; null selects every observed type. Empty selects missing/empty type.')
    scope: str|None=Field(default=None,max_length=80,description='Diagnostic filter for time blocks; null selects every observed scope. Empty selects missing/empty scope. Does not choose a native import mode.')

    @model_validator(mode='after')
    def input_source(self):
        if (self.content is None)==(self.file_path is None):raise ValueError('Supply exactly one of content or file_path.')
        return self


class Simulation(Input):
    kind: Literal['simulation']
    start: str=Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')
    stop: str=Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')
    start_day_offset: int=Field(default=0,strict=True,ge=-366,le=366)
    stop_day_offset: int=Field(default=0,strict=True,ge=-366,le=366)
    step_s: float=Field(default=.2,ge=.1,le=10)
    time_ratio: Literal['Best','1:1','2:1','5:1','10:1','20:1','30:1','60:1','120:1','300:1','600:1']='30:1'


CourseLifecycle=Annotated[RenameCourses|DeleteCourses|ResetCourseItineraries,Field(discriminator='kind')]
NetworkOperation=Annotated[DeleteAllPaths|EditItineraryMargins|EditItinerary|RenameItinerary|DuplicateItinerary|DeleteItineraries|ResetItineraryCatalog|AppendItinerary|ReplaceItineraryPaths,Field(discriminator='kind')]
TimetableOperation=Annotated[CreateTimetableSkeletons|CreateIntervalCourses|PlanTimetableConnections|UpdateTimetableRows|InsertTimetableRows|DeleteTimetableRows|ShiftTimetableRows|SetTimetableInterval|ResetTimetableActual|CopyTimetableActual|SyncTimetable|EditTimetableConnections|ImportTimetableText|ImportTimetableXML,Field(discriminator='kind')]
Change=Annotated[EdgeLength|Shift|Bind|Clone|Enabled|Normalize|RepairLayout|Reencode|Simulation|DefineRoute|DefineShunting|SetRouteProtection|DefinePath|DefineItinerary|DeleteAllPaths|EditItineraryMargins|EditItinerary|RenameItinerary|DuplicateItinerary|DeleteItineraries|ResetItineraryCatalog|AppendItinerary|ReplaceItineraryPaths|RepairItineraryDocuments|CreateDocument|WorksheetAttributes|SignalAttributes|CreateVertex|MoveVertex|VertexAttributes|CreateEdge|EdgeAttributes|ReverseEdge|CreateSignal|LinkConnectors|UnlinkConnector|SafetyElements|ExclusionLink|DeleteGraphic|SplitEdge|DefineEngine|DefineCategory|DefineFormation|DefineStation|DefineCourse|DefinePattern|DefineTimetable|CreateTimetableSkeletons|CreateIntervalCourses|PlanTimetableConnections|UpdateCourses|RenameCourses|DeleteCourses|ResetCourseItineraries|UpdateTimetableRows|InsertTimetableRows|DeleteTimetableRows|ShiftTimetableRows|SetTimetableInterval|ResetTimetableActual|CopyTimetableActual|SyncTimetable|EditTimetableConnections|ImportTimetableText|ImportTimetableXML|ImportRollingStockXML|UpdateEngines|UpdateFormations|UpdateCategories|RenameStock|DeleteStock|EditEngineDiagrams|MigrateRollingStock,Field(discriminator='kind')]


class Stage(ProjectInput):
    changes: list[Change]=Field(min_length=1,max_length=MAX_BATCH_OPERATIONS)
    label: str=Field(default='',max_length=160)
    validation_scope: Literal['preparation','generation']='preparation'


class Validate(ProjectInput):
    validation_scope: Literal['preparation','generation']='preparation'


class GenerateOperations(ProjectInput):
    label: str=Field(default='Generated operations',max_length=160)
    rolling_stock_imports: list[ImportRollingStockXML]=Field(default_factory=list,max_length=100)
    engines: list[EngineSpec]=Field(default_factory=list,max_length=100)
    categories: list[CategorySpec]=Field(default_factory=list,max_length=100)
    formations: list[FormationSpec]=Field(default_factory=list,max_length=100)
    stations: list[StationSpec]=Field(default_factory=list,max_length=100)
    shuntings: list[DefineShunting]=Field(default_factory=list,max_length=100)
    routes: list[DefineRoute]=Field(default_factory=list,max_length=100)
    route_protection_updates: list[SetRouteProtection]=Field(default_factory=list,max_length=100)
    paths: list[DefinePath]=Field(default_factory=list,max_length=100)
    itineraries: list[DefineItinerary]=Field(default_factory=list,max_length=100)
    courses: list[CourseSpec]=Field(default_factory=list,max_length=100)
    patterns: list[ServicePattern]=Field(default_factory=list,max_length=100)
    course_updates: list[UpdateCourses]=Field(default_factory=list,max_length=1000)
    network_operations: list[NetworkOperation]=Field(default_factory=list,max_length=1000,description='Ordered native network/Itinerary data commands after definitions, before Course lifecycle. Deletion preserves Course itinerary strings; explicit reset_course_itineraries is separate.')
    course_lifecycle: list[CourseLifecycle]=Field(default_factory=list,max_length=1000)
    timetable_operations: list[TimetableOperation]=Field(default_factory=list,max_length=1000)
    rolling_stock_operations: list[RollingStockOperation]=Field(default_factory=list,max_length=1000)
    timetables: list[TimetableSpec]=Field(default_factory=list,max_length=100)


class Draft(Input):
    draft_id: str=Field(pattern=r'^draft-[a-f0-9]{16}$')


class Apply(Draft):
    expected_source_digest: str=Field(pattern=r'^[a-f0-9]{64}$',description='Digest returned by the draft; applying also checks current source bytes.')


class PublishDraft(Draft):
    project_name: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{1,63}$',description='Fresh isolated project under OTProjects; existing project directories are never overwritten.')


class StartEditor(ProjectInput):
    label: str=Field(default='',max_length=160)


class CreateProject(Input):
    project_name: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{1,63}$')
    documents: list[DocumentName]=Field(default_factory=lambda:['Main'],min_length=1,max_length=100)
    width: float=Field(default=1200,ge=100,le=100000)
    height: float=Field(default=800,ge=100,le=100000)


class EditorSession(Input):
    session_id: str=Field(pattern=r'^editor-[a-f0-9]{16}$')


class EditSession(EditorSession):
    expected_revision: int=Field(ge=0)
    action: Literal['edit','undo','redo']='edit'
    changes: list[Change]=Field(default_factory=list,max_length=200)
    label: str=Field(default='',max_length=160)

    @model_validator(mode='after')
    def valid_action(self):
        if self.action=='edit' and not self.changes:raise ValueError('An edit requires at least one change.')
        if self.action!='edit' and self.changes:raise ValueError('Undo/redo does not accept changes.')
        return self


class Runtime(Input):
    pid: int=Field(gt=0)
    courses: list[CourseId]=Field(default=['G1046','G1862'],min_length=1,max_length=2)


class DemoStation(Input):
    sign: str=Field(pattern=r'^[A-Z][A-Z0-9]{1,7}$')
    native_name: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9 -]{1,59}$')
    display_name: str=Field(min_length=1,max_length=60)
    document: str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{1,59}$')


class CreateDemo(ProjectInput):
    project_name: str=Field(default='NJ_SH_400_DEMO',pattern=r'^[A-Za-z][A-Za-z0-9_-]{1,63}$',description='New directory directly under OTProjects; existing directories are never overwritten.')
    stations: list[DemoStation]=Field(default_factory=lambda:[
        DemoStation(sign='NJN',native_name='Nanjing South',display_name='南京南',document='NanjingSouth'),
        DemoStation(sign='SZB',native_name='Suzhou North',display_name='苏州北',document='SuzhouNorth'),
        DemoStation(sign='SHH',native_name='Shanghai Hongqiao',display_name='上海虹桥',document='ShanghaiHongqiao')],min_length=3,max_length=3)
    section_distances_m: list[Annotated[int,Field(strict=True,ge=30000,le=500000)]]=Field(default_factory=lambda:[200000,100000],min_length=2,max_length=2,description='Synthetic distances, not surveyed railway mileage.')
    maximum_speed_kmh: int=Field(default=400,strict=True,ge=200,le=500)
    station_speed_kmh: int=Field(default=160,strict=True,ge=80,le=200)
    nominal_power_kw: int=Field(default=16000,strict=True,ge=8000,le=30000)
    maximum_force_kn: int=Field(default=320,strict=True,ge=200,le=500)
    departures_each_direction: int=Field(default=8,ge=1,le=24)
    first_departure: str=Field(default='06:00:00',pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')
    departure_interval_s: int=Field(default=2400,ge=600,le=7200)
    reverse_offset_s: int=Field(default=300,ge=0,le=3600)
    dwell_s: int=Field(default=180,ge=60,le=600)
    source_train: str=Field(default='CR400AF_8_PROXY_350',min_length=1,max_length=160)
