"""Explicit bounded terminal-area input contract; static configuration, not execution."""
from typing import Annotated,Literal
from pydantic import Field,StrictBool,StrictInt,model_validator
from .tools import Input
from .network_generation_tools import Text,EndRef,Number
from .graphic_alignment import GraphicPlacement as Placement
Line=Literal['H1','H2','H3','V1','V2','V3']
class AreaStop(Input):
    entry:EndRef
    exit:EndRef
    area_edge:Text
    length_m:Annotated[StrictInt,Field(ge=1,le=100000)]
    exit_signal_name:Text
    direction:Literal['forward_only']
class AreaStation(Input):
    sign:Text
    name:Text
    reference_end:EndRef
    ordinary_ends:Annotated[list[EndRef],Field(max_length=1)]
    placement:Placement
    station_type_raw:Annotated[StrictInt,Field(ge=2,le=2)]
    interlock_type_raw:Annotated[StrictInt,Field(ge=4,le=4)]
    icon_show_type_raw:Annotated[StrictInt,Field(ge=1,le=1)]
    timing_point:StrictBool
    stop:AreaStop|None
    @model_validator(mode='after')
    def area_contract(self):
        if not self.timing_point:raise ValueError('Explicit timing catalog flag required')
        if bool(self.ordinary_ends)!=(self.stop is not None):raise ValueError('Ordinary station area members require an explicit stop contract; pass references cannot have one')
        if self.stop and (self.stop.entry!=self.ordinary_ends[0] or self.stop.exit!=self.reference_end):raise ValueError('Stop entry/exit must match the exact selected ordinary/reference EndRef')
        return self
class TerminalVisit(Input):
    index:Annotated[StrictInt,Field(ge=0,le=4)]
    max_index:Annotated[StrictInt,Field(ge=4,le=4)]
    station_sign:Text
    absolute_seconds:Annotated[StrictInt,Field(ge=0,lt=86400)]
    stop:StrictBool
    timing:StrictBool
    flags_raw:Annotated[StrictInt,Field(ge=2,le=3)]
    actual_time:None
    @model_validator(mode='after')
    def visit_contract(self):
        if self.stop!=(self.index==4) or not self.timing or self.flags_raw!=(3 if self.stop else 2):raise ValueError('Exactly final occurrence stops; all visits timing; explicit raw flags must agree')
        return self
class TerminalCoursePlan(Input):
    course_id:Text
    train:Text
    itinerary:Text
    corridor:Line
    visits:Annotated[list[TerminalVisit],Field(min_length=5,max_length=5)]
    @model_validator(mode='after')
    def sequence(self):
        if [v.index for v in self.visits]!=list(range(5)):raise ValueError('Exact ordered occurrence indices 0..4 required')
        number=('H1','H2','H3','V1','V2','V3').index(self.corridor)+1
        if self.itinerary!='I:terminal:'+self.corridor or self.train!=f'TRAIN_{number:02}':raise ValueError('Explicit corridor must match reviewed Train/Itinerary identity')
        return self
class TerminalChain(Input):
    line_id:Line
    train:Text
    itinerary:Text
    station_sign:Text
    course_ids:Annotated[list[Text],Field(min_length=2,max_length=24)]
class TerminalCounts(Input):
    courses:Annotated[StrictInt,Field(ge=2,le=144)]
    timetable_rows:Annotated[StrictInt,Field(ge=10,le=720)]
    terminal_stops:Annotated[StrictInt,Field(ge=2,le=144)]
    chains:Annotated[StrictInt,Field(ge=1,le=6)]
    pairs:Annotated[StrictInt,Field(ge=1,le=138)]
    connection_records:Annotated[StrictInt,Field(ge=2,le=276)]
    roots:Annotated[StrictInt,Field(ge=1,le=6)]
    tails:Annotated[StrictInt,Field(ge=1,le=6)]
    internal_courses:Annotated[StrictInt,Field(ge=0,le=132)]
    @model_validator(mode='after')
    def counts(self):
        if not(self.timetable_rows==5*self.courses and self.terminal_stops==self.courses and self.roots==self.tails==self.chains and self.pairs==self.courses-self.chains and self.connection_records==2*self.pairs and self.internal_courses==self.courses-2*self.chains):raise ValueError('Expected counts do not describe finite independent chains')
        return self
class TerminalProfile(Input):
    stations:Annotated[list[AreaStation],Field(min_length=2,max_length=12)]
    plan:Annotated[list[TerminalCoursePlan],Field(min_length=2,max_length=144)]
    chains:Annotated[list[TerminalChain],Field(min_length=1,max_length=6)]
    expected_counts:TerminalCounts
    minimum_turnround_s:Annotated[StrictInt,Field(ge=420,le=420)]
    window_start_s:Annotated[StrictInt,Field(ge=0,le=0)]
    window_end_s:Annotated[StrictInt,Field(ge=86400,le=86400)]
    @model_validator(mode='after')
    def terminal_contract(self):
        if len(self.plan)!=self.expected_counts.courses or len(self.chains)!=self.expected_counts.chains:raise ValueError('Explicit expected counts disagree with plan/chains')
        names=[s.sign for s in self.stations]
        if len(names)!=len(set(names)):raise ValueError('Duplicate Station sign')
        cids=[p.course_id for p in self.plan];claimed=[x for chain in self.chains for x in chain.course_ids]
        if len(set(cids))!=len(cids) or len(set(claimed))!=len(claimed) or set(cids)!=set(claimed):raise ValueError('Chains must partition every generated Course exactly once')
        return self
