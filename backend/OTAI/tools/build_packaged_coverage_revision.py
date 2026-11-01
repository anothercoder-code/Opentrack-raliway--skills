"""Explicit build-time metadata refresh, never invoked by a read tool."""
from pathlib import Path
import hashlib,json,datetime,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from opentrack_ai import __version__
paths=list((ROOT/'opentrack_ai').rglob('*.py'))+[ROOT/'server.py',ROOT/'skills/opentrack-rail/scripts/ot.py']
paths += [ROOT/'replica'/name for name in ('requirements.json','current-function-coverage.json','rebuild-interface-matrix.json')]
report={'schema_version':1,'interface_version':__version__,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'Package code/report freshness only; metadata does not re-certify native behavior',
        'input_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(paths)}}
(ROOT/'replica/packaged-coverage-revision.json').write_text(json.dumps(report,indent=2)+'\n')
print('Refreshed explicit package coverage revision:',len(report['input_hashes']),'inputs')
