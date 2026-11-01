"""Render current four-axis requirement evidence without inventing completeness."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 data=json.loads((ROOT/'replica/requirements.json').read_text())
 lines=['# Current saved-data operation coverage','','176 original definitions retained. PE = partial source/bounded evidence; NR = not reassessed, not unsupported; NA = native replacement not required. A suffix `(n)` counts explicit bounded evidence cases, not completed original features. Export is assessed separately. See requirements.json for exact scopes/tests.','','| ID | Requirement | Read | Generate | Modify | Export | Unavailable legacy entrypoints |','|---|---|---|---|---|---|---|']
 for r in data['requirements']:
  vals=[]
  for axis in ('read','generate','modify','export'):
   c=r['operation_coverage'][axis];label={'partial_evidence':'PE','not_reassessed':'NR','notapplicable_native_execution':'NA','verifiedbounded':'VB'}.get(c['status'],c['status']);count=len(c.get('verified_bounded_cases',[]));vals.append(label+(f' ({count})'if count else''))
  blocked=sorted({name for c in r['operation_coverage'].values()for name,v in c.get('entrypoint_availability',{}).items()if v['status']in ('unavailable','disabled')})
  lines.append('| '+r['id']+' | '+r['title'].replace('|','/')+' | '+' | '.join(vals)+' | '+', '.join(blocked)+' |')
 (ROOT/'replica/operation-coverage.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
