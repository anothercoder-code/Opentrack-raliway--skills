"""Bounded Train rename with atomic publication of the changed native catalogs."""
from pathlib import PurePosixPath
from .multi_document_tools import MultiDocumentTools,ProjectInput,Name
from .tools import sha
from .project_candidate_publication import ProjectSave
from ..errors import APIError
class RenameTrain(ProjectInput, ProjectSave):
    old_name:Name
    new_name:Name
class SavedReferenceTools(MultiDocumentTools):
    def rename(self,args):
        state=self.load_project(args.source_project)
        if not args.preview_only:
            target=self.path(args.target_directory)
            if target.is_relative_to(state['base']) or state['base'].is_relative_to(target):
                raise APIError('REFERENCE_SCOPE','Fresh catalog bundle must be outside the source project')
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
        output_files={n:{'sha256':sha(b),'bytes':len(b),'changed':b!=state['files'][n]} for n,b in out.items()}
        result={'saved':False,'preview_only':args.preview_only,'source':self.source_receipt(args,state),
                'receipt':receipt,'output_files':output_files,'native_execution':False,
                'scope':'Current Train16 identity and Course11 exact references in the complete selected single-run inventory'}
        if args.preview_only:
            return result
        changed=[name for name,data in output_files.items() if data['changed']]
        if not changed or set(changed)-{state['roles']['trains'],state['roles']['courses']}:
            raise APIError('REFERENCE_UPDATE_INVALID','Rename must modify only the selected Train/Course catalogs')
        aliases={PurePosixPath(name).name:name for name in changed}
        if len(aliases)!=len(changed):
            raise APIError('REFERENCE_SCOPE','Changed catalogs must have distinct output names')
        manifest={'format':'opentrack-train-rename-catalogs-v1',
                  'replacement_for':{name:(state['base']/path).relative_to(self.root).as_posix()
                                     for name,path in aliases.items()},
                  'files':{name:output_files[path] for name,path in aliases.items()},
                  'complete_relocated_project':False}
        result.update(manifest=manifest,bundle_type='Train and Course catalog increment')
        return self.publish_bundle(inputs=state['inputs'],members={name:out[path] for name,path in aliases.items()},
                                   manifest=manifest,result=result,target_directory=args.target_directory,
                                   scope_check=state['scope_check'],windows_publication=True)
def tool_definitions(root):
    s=SavedReferenceTools(root)
    return [('opentrack_preview_rename_train_references','Preview or publish changed Train/Course archives with an exact Train16 rename and all Course11 reverse references. Requires a complete selected project inventory and fresh target. No native execution.',RenameTrain,s.rename,False,False)]
