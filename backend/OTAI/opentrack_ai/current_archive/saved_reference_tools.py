"""Complete-project preview adapter for a bounded saved Train identity update."""
from typing import Literal
from .multi_document_tools import MultiDocumentTools,ProjectInput,Name
from .tools import sha
from ..errors import APIError
class RenameTrain(ProjectInput):
    old_name:Name
    new_name:Name
    preview_only:Literal[True]=True
class SavedReferenceTools(MultiDocumentTools):
    def rename(self,args):
        self.readonly(args);state=self.load_project(args.source_project)
        if set(state['files'])!=set(state['selected']):raise APIError('REFERENCE_SCOPE','Only a complete single selected-run inventory is supported; unbound extra files refused')
        from .prepare_contract import preflight
        def validate(files):
            self.project({**state,'files':files})
            def bound(path):
                if not path.startswith(state['root']+'/'):raise ValueError('Dependency outside exact execution mapping')
                return files[self.member(path[len(state['root'])+1:])]
            r=preflight.check(state['run'],bound)
            if not r['passed_static_subset']:raise ValueError('Complete operating preflight must pass before and after rename: '+str(r['errors'])[:700])
        try:
            validate(state['files'])
            from .saved_reference_updates import rename_train
            run_member=args.source_project.run_file
            if args.old_name.encode('ascii')in state['run']:raise ValueError('Name appears in run text; no guessed textual substitution')
            archives={n:b for n,b in state['files'].items()if n!=run_member}
            out,receipt=rename_train(archives,train_member=state['roles']['trains'],course_member=state['roles']['courses'],old_name=args.old_name,new_name=args.new_name)
            validate({**out,run_member:state['run']})
        except (ValueError,TypeError,KeyError,UnicodeError)as e:raise APIError('REFERENCE_UPDATE_INVALID','Unsupported or unclosed Train identity update',str(e))from e
        self.recheck(state)
        return {'saved':False,'preview_only':True,'source':self.source_receipt(args,state),'receipt':receipt,'output_files':{n:{'sha256':sha(b),'bytes':len(b),'changed':b!=state['files'][n]}for n,b in out.items()},'scope':'Current Train16 identity and Course11 exact references in complete single-run selected inventory; other same-name uses rejected','native_execution':False}
def tool_definitions(root):
    s=SavedReferenceTools(root)
    return [('opentrack_preview_rename_train_references','Preview exact Train16 rename and all Course11 reverse references in a complete selected multi-document operating project. Unknown same-name references, extra files and incomplete preflight refused; no save, export or native execution.',RenameTrain,s.rename)]
