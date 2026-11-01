"""Package assistant-owned code/contracts only; exclude original data and binaries."""
from pathlib import Path
import hashlib,json,zipfile,sys
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'backups'
EXCLUDE={'__pycache__','.git'}
def selected():
 out=[]
 for folder in ('opentrack_ai','skills','contracts','docs'):
  for p in (ROOT/folder).rglob('*'):
   if p.is_file() and p.suffix in ('.py','.json','.md','.yaml') and not any(x in EXCLUDE for x in p.parts):out.append(p)
 for name in ('server.py','pyproject.toml','.python-version','README.md','REBUILD_STATUS.md','INSTALL-REBUILD.md','requirements.txt','requirements-server-tested.txt','requirements-archive-tests.txt',
              'replica/operation-coverage.md','tools/render_operation_coverage.py','replica/dev2-operation-coverage.md','replica/requirements.json','replica/current-function-coverage.json','replica/rebuild-interface-matrix.json','replica/packaged-coverage-revision.json','replica/本轮接口实现表.md','tools/package_rebuild.py','tools/build_packaged_coverage_revision.py'):
  out.append(ROOT/name)
 for p in (ROOT/'tests').glob('test_rebuild_*.py'):
  out.append(p)
 out.append(ROOT/'tests/rebuild_spatial_fixture.py')
 out.extend((ROOT/'tests').glob('test_dev1_*.py'))
 out.extend((ROOT/'tests').glob('test_dev2_*.py'))
 out.extend((ROOT/'tests').glob('test_dev3_*.py'))
 out.extend((ROOT/'tests').glob('test_dev4_*.py'))
 out.extend((ROOT/'tests').glob('test_dev5_*.py'))
 out.extend((ROOT/'tests').glob('test_dev6_*.py'))
 out.extend((ROOT/'tests').glob('test_dev8_*.py'))
 out.extend((ROOT/'tests').glob('test_static_*.py'))
 out.extend((ROOT/'tests').glob('test_bridge_*.py'))
 out.extend((ROOT/'tests').glob('test_compat_*.py'))
 out.extend((ROOT/'tests').glob('test_static4_*.py'))
 out.extend((ROOT/'tests').glob('test_static5_*.py'))
 out.append(ROOT/'tests/test_platform_support.py')
 for p in list((ROOT/'artifacts/rebuild').iterdir()) + list((ROOT/'artifacts/rebuild-dev1').iterdir()) + list((ROOT/'artifacts-dev1').iterdir()) + list((ROOT/'artifacts/rebuild-dev2').iterdir()) + list((ROOT/'artifacts/rebuild-dev3').iterdir()) + list((ROOT/'artifacts/rebuild-dev4').iterdir()) + list((ROOT/'artifacts/rebuild-dev5').iterdir()) + list((ROOT/'artifacts/rebuild-dev6').iterdir()) + list((ROOT/'artifacts/rebuild-dev8').iterdir()) + list((ROOT/'artifacts/static-delivery').iterdir()) + list((ROOT/'artifacts/bridge-fix').iterdir()) + list((ROOT/'artifacts/compatibility').iterdir()) + list((ROOT/'artifacts/static4').iterdir()) + list((ROOT/'artifacts/static5').iterdir()):
  if p.is_file() and p.suffix in ('.json','.md','.txt','.patch') and not p.name.startswith(('initial-','recovered-overlay')):out.append(p)
 return sorted(set(out))
def main():
 DEST.mkdir(exist_ok=True);name=sys.argv[1] if len(sys.argv)>1 else 'opentrack-rebuild-source-checkpoint2-20261029.zip'
 paths=selected();manifest={str(p.relative_to(ROOT)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}for p in paths}
 meta={'version':'0.31.0-static5','kind':'development_source_and_skill_not_stable_release','original_binaries_projects_function_bank_included':False,
       'new_interfaces_persistence':'preview_only','native_execution':False,'files':manifest}
 target=DEST/name
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED)as z:
  for p in paths:z.write(p,'OTAI/'+str(p.relative_to(ROOT)))
  z.writestr('SOURCE_MANIFEST.json',json.dumps(meta,ensure_ascii=False,indent=2))
 print(json.dumps({'path':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'files':len(paths)},indent=2))
if __name__=='__main__':main()
