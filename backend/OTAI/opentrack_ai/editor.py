"""Persistent undo/redo over immutable native archive drafts."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import uuid

from .archive import APIError,digest,inside
from .drafts import DraftManager,atomic_write
from .models import Draft,Stage


class Editor:
    def __init__(self,service):self.service=service;self.drafts=DraftManager(service)

    def path(self,identifier):return inside(self.service.work/identifier/'session.json',[self.service.work])

    def load(self,identifier):
        path=self.path(identifier)
        if not path.is_file():raise APIError('EDITOR_NOT_FOUND','Editor session does not exist.',identifier)
        state=json.loads(path.read_text(encoding='utf8'));self.current(state)
        return state

    def current(self,state):return self.drafts.describe(Draft(draft_id=state['history'][state['cursor']]['draft_id']))

    def view(self,state):
        draft=self.current(state);folder=self.drafts.folder(draft['draft_id'])/'project'
        return {**state,'draft_id':draft['draft_id'],'draft_project':str(folder),'run_file':str(folder/'BJTU-demo.run'),
            'validation':draft['validation'],'undo_available':state['cursor']>0,'redo_available':state['cursor']+1<len(state['history']),
            'source_files_unchanged':all(Path(path).is_file() and digest(Path(path).read_bytes())==sha for path,sha in state['source_files'].items()),
            'native_editor_parity_verified':False}

    def start(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        initial=self.drafts.stage(Stage(project=args.project,run_file=args.run_file,label='Editor initial snapshot',changes=[{'kind':'reencode_native'}]))
        draft=self.drafts.describe(Draft(draft_id=initial['draft_id']));identifier='editor-'+uuid.uuid4().hex[:16]
        state={'session_id':identifier,'label':args.label,'revision':0,'cursor':0,'history':[{'draft_id':initial['draft_id'],'label':'Initial snapshot'}],
            'source_project':draft['source_project'],'source_digest':draft['source_digest'],'source_files':draft['source_files']}
        path=self.path(identifier);path.parent.mkdir(parents=True,exist_ok=False)
        atomic_write(path,json.dumps(state,ensure_ascii=False,indent=2).encode('utf8'));return self.view(state)

    def read(self,args):return self.view(self.load(args.session_id))

    def change(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        path=self.path(args.session_id)
        if not path.is_file():raise APIError('EDITOR_NOT_FOUND','Editor session does not exist.',args.session_id)
        with self.lock(path.with_suffix('.lock')):return self.change_locked(args)

    @contextmanager
    def lock(self,path):
        handle=path.open('a+b');acquired=False
        try:
            if path.stat().st_size==0:handle.write(b'0');handle.flush()
            handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired=True
            except OSError as error:raise APIError('EDITOR_BUSY','Another process is committing an editor action. Read state and retry.') from error
            yield
        finally:
            if acquired:
                handle.seek(0)
                if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
            handle.close()

    def change_locked(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        state=self.load(args.session_id)
        if args.expected_revision!=state['revision']:raise APIError('EDITOR_REVISION_CONFLICT','Read the current editor state before retrying; no edit was performed.',{'expected':args.expected_revision,'actual':state['revision']})
        if args.action in ['undo','redo']:
            cursor=state['cursor']+(-1 if args.action=='undo' else 1)
            if not 0<=cursor<len(state['history']):raise APIError('EDITOR_HISTORY_BOUNDARY','No '+args.action+' is available.')
            state['cursor']=cursor;self.current(state)
        else:
            base=self.view(state)
            result=self.drafts.stage(Stage(project=base['draft_project'],run_file=base['run_file'],label=args.label,changes=args.changes))
            state['history']=state['history'][:state['cursor']+1]+[{'draft_id':result['draft_id'],'label':args.label}]
            state['cursor']+=1
        state['revision']+=1
        atomic_write(self.path(args.session_id),json.dumps(state,ensure_ascii=False,indent=2).encode('utf8'))
        return self.view(state)
