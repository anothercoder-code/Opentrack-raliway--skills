"""Read-only independent worksheet views over original-format archives."""
import json
from pathlib import Path

from .archive import APIError,inside,page,w,END_KINDS
from .editor import Editor


def ident(obj):return obj.contents[0].value if obj is not None else None
def string(obj):return w.string(obj) if obj is not None else ''


class Worksheets:
    def __init__(self,service):self.service=service

    def projects(self,args):
        base=self.service.root/'OTProjects';rows=[];errors=[]
        if not base.is_dir():return {**page([],args.limit,args.offset),'errors':[]}
        for folder in sorted(base.iterdir(),key=lambda p:p.name.casefold()):
            if not folder.is_dir() or args.query.casefold() not in folder.name.casefold():continue
            try:
                folder=inside(folder,[base]);metadata=folder/'opentrack-project.json'
                settings=json.loads(metadata.read_text(encoding='utf8')) if metadata.is_file() and metadata.stat().st_size<=65536 else {}
                rows.append({'name':folder.name,'project':str(folder),'default_run':settings.get('default_run'),
                    'documents':sorted(p.stem for p in (folder/'OTDocuments').glob('*.opentrack'))})
            except (APIError,OSError,ValueError,AttributeError) as error:errors.append({'name':folder.name,'error':str(error)[:200]})
            if len(rows)>=5000:raise APIError('PROJECT_SIZE','Project inventory exceeds 5000 folders; narrow query.')
        return {**page(rows,args.limit,args.offset),'errors':errors[:100]}

    def editors(self,args):
        rows=[];errors=[];editor=Editor(self.service)
        for path in sorted(self.service.work.glob('editor-*/session.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            try:
                if path.stat().st_size>1024*1024:raise ValueError('Session metadata exceeds limit')
                state=json.loads(path.read_text(encoding='utf8'))
                if args.query.casefold() not in (state['label']+' '+state['source_project']).casefold():continue
                state=editor.load(state['session_id'])
                rows.append({key:state[key] for key in ['session_id','label','source_project','revision','cursor']})
            except (APIError,OSError,ValueError,KeyError) as error:errors.append({'session_id':path.parent.name,'error':str(error)[:200]})
            if len(rows)>=5000:raise APIError('PROJECT_SIZE','Editor inventory exceeds 5000 sessions; narrow query.')
        return {**page(rows,args.limit,args.offset),'errors':errors[:100]}

    def snapshot(self,args):
        p=self.service.project(args);names=[args.document] if args.document else list(p.docs)
        if any(name not in p.docs for name in names):raise APIError('DOCUMENT_NOT_FOUND','Select a document returned by project inspection.',args.document)
        count=sum(len(p.models[name]) for name in names)
        if count>args.max_objects:raise APIError('WORKSHEET_SIZE','Select one document or explicitly raise max_objects; no graphics were silently omitted.',{'objects':count,'maximum':args.max_objects})
        docs=[]
        for name in names:
            doc=p.docs[name];vertices=[];edges=[];signals=[];other=[]
            for obj in p.models[name]:
                kind=w.kind(obj);row={'id':ident(obj),'class':kind,'angle_degrees':obj.contents[1].value,'x':obj.contents[2].value,'y':obj.contents[3].value}
                if kind in END_KINDS:
                    row.update(related_id=obj.contents[8].value,name=string(obj.contents[18].value),
                        edge_ids=[ident(obj.contents[i].value) for i in [9,10] if obj.contents[i].value is not None],
                        signal_id=ident(obj.contents[11].value),element_id=ident(obj.contents[7].value),
                        station_sign=string(obj.contents[12].value.contents[7].value) if obj.contents[12].value else None,
                        kilometre_point=None if obj.contents[14].value==-99999 else obj.contents[14].value,
                        station_reference_type=obj.contents[20].value,switch_time_s=obj.contents[21].value,
                        default_second_leg=bool(obj.contents[22].value),insulated_joint=bool(obj.contents[23].values[0]),axle_counter=bool(obj.contents[23].values[1]),
                        alignment_x=obj.contents[4].value,alignment_y=obj.contents[5].value)
                    if kind=='OTConnModel':row['connector']={'document':string(obj.contents[25].value),'end_id':obj.contents[26].value}
                    vertices.append(row)
                elif kind=='OTEdgeModel':
                    speeds=[{'train_type':string(o.contents[0].value),'forward_kmh':o.contents[1].value,'reverse_kmh':o.contents[2].value}
                        for o in w.objects(obj.contents[16].value) if w.kind(o)=='OTSpeed']
                    row.update(first_end_id=ident(obj.contents[7].value),second_end_id=ident(obj.contents[8].value),
                        length_m=obj.contents[9].values[1],radius_m=obj.contents[9].values[2],gradient_per_mille=obj.contents[9].values[3],
                        speeds=speeds,equal_speed=bool(obj.contents[11].value&1),rack_rail=bool(obj.contents[11].value&2),
                        contact_wire_mm2=obj.contents[10].values[0],tunnel_m2=obj.contents[10].values[1],
                        track_name=string(obj.contents[19].value),line_name=string(obj.contents[20].value),exclusion_target_id=ident(obj.contents[13].value))
                    edges.append(row)
                elif kind=='OTSignalModel':
                    row.update(end_id=ident(obj.contents[7].value),name=string(obj.contents[13].value),signal_type=obj.contents[8].values[0],
                        main_signal_type=obj.contents[8].values[1],display_system=obj.contents[9].values[0],
                        sight_distance_m=obj.contents[9].values[1],release_speed_kmh=obj.contents[9].values[3],delay_s=obj.contents[16].value)
                    signals.append(row)
                elif kind!='OTElement':
                    row['text']=[string(v)[:1024] for g in obj.contents for v in g.values if isinstance(v,w.ar.GenericArchivedObject) and w.kind(v)=='NSString']
                    other.append(row)
            flags=doc.contents[1].value
            docs.append({'name':name,'bounds':dict(zip(['x','y','width','height'],doc.contents[9].values)),
                'grid_x':doc.contents[3].value,'grid_y':doc.contents[4].value,'show_grid':None,'unsupported_fields':['show_grid: saved mapping not established; protected flags not exposed'],
                'show_edge_direction':bool(flags&1),'big_vertices':bool(flags&2),
                'vertices':vertices,'edges':edges,'signals':signals,'other_graphics':other,
                'native_graphic_count':len(p.models[name])})
        return {'project':str(p.project),'source_digest':p.source_digest,'documents':docs,'all_document_names':list(p.docs),
            'object_count':count,'coordinates_are_metres':False,'native_editor_parity_verified':False,
            'scope':'Original-format worksheet geometry/attributes; unknown worksheet classes remain explicitly represented, not converted.'}
