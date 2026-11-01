"""SHA-bound current Connection archive operations; no runtime/circulation solver."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .tools import Input
from .operation_tools import Name
from .bundle_tools import Source
from .next_tools import Save, Ordinal, NextFunctions
from . import native_connections as core, catalogs as c, writer as w
from .course_factories import timetable
from ..errors import APIError

class Sources(Input):
    timetable: Source
    courses: Source
    trains: Source
    stations: Source
    connection_template: Source
class Delete(Input):
    action: Literal['delete']
    course_id: Name
    index: Ordinal
    connection_index: Ordinal
class Bound(Input):
    action: Literal['insert','turnround_to','turnround_from']
    course_id: Name
    index: Ordinal
    target_course_id: Name
Operation=Annotated[Delete|Bound,Field(discriminator='action')]
class ApplyConnections(Save):
    sources: Sources
    commands: Annotated[list[Operation],Field(min_length=1,max_length=1000)]

def validate_references(blobs):
    """Validate the actual supplied catalogs, not caller assertions or name lists.
    Missing Train/Category retains the separately documented native 420s fallback;
    Engine/Itinerary/geometry are deliberately outside this dependency contract.
    """
    roots={k:w.load_next_compatible(v)[0] for k,v in blobs.items()}
    courses={core.text(o,0):o for o in c.course_items(roots['courses'])}
    c.train_items(roots['trains'])
    stations=c.station_items(roots['stations'])
    rows=timetable(roots['timetable']); visits={}
    for row in rows.values():
        owner=core.text(row,1);sign=core.text(row,5)
        core.need(owner in courses and owner not in ('0','-1'),'Timetable owner missing/reserved')
        core.need(sign in stations,'Timetable station missing')
        visits.setdefault(owner,set()).add(sign)
    for row in rows.values():
        owner=core.text(row,1);sign=core.text(row,5)
        for conn in c.array(row.contents[9].value):
            core.connection(conn)
            core.need(core.text(conn,0)==owner and core.text(conn,2)==sign,'Connection owner/station mismatch')
            target=core.text(conn,1);target_sign=core.text(conn,6)
            core.need(target in courses and target not in ('0','-1'),'Connection target missing/reserved')
            core.need(target_sign in stations and target_sign in visits.get(target,set()),'Connection target station visit missing')
    return {'timetable_rows':len(rows),'course_count':len(courses),'all_connection_owner_target_station_references_resolved':True,
            'engine_itinerary_geometry_checked':False}

class ConnectionFunctions(NextFunctions):
    def apply_connections(self,args):
        inputs={}; blobs={}
        for role in type(args.sources).model_fields:
            p,b,_,_=self.checked(getattr(args.sources,role));inputs[role]=p;blobs[role]=b
        self.same_project(list(inputs.values()))
        if len(set(inputs.values()))!=len(inputs) or len({p.parent for p in inputs.values()})!=1:
            raise APIError('DATASET_MISMATCH','Five distinct inputs, including explicit Connection template, must be in one catalog directory')
        try:
            before=validate_references(blobs)
            commands=[core.Command(**op.model_dump()) for op in args.commands]
            output,report=core.apply(blobs,commands)
            after=validate_references({**blobs,'timetable':output})
            report.update(reference_validation_before=before,reference_validation_after=after,
                          native_category_fallback_policy='Retain native 420 seconds when Course Train/Category lookup is absent; evidence appears per new connection',
                          complete_project_validated=False)
        except (ValueError,TypeError,IndexError,KeyError,OverflowError) as exc:
            raise APIError('CURRENT_CONNECTION_OPERATION',str(exc)[:500]) from exc
        return self.finish(args,inputs['timetable'],blobs['timetable'],output,report,
                           {inputs[k]:blobs[k] for k in inputs if k!='timetable'})

def tool_definitions(root):
    service=ConnectionFunctions(root)
    return [('opentrack_apply_current_connections','Apply bound insert/delete/turnround to current Timetable9/Connection6 with five SHA-bound real dependencies and before/after reference checks. Preserve original first-match, own Category defaults and reciprocal rules. Preview/fresh copy only; not runtime coupling or circulation feasibility.',ApplyConnections,service.apply_connections,False,False)]
