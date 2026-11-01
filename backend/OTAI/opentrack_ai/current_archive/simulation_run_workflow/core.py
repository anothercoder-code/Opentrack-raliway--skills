"""Pure-data readiness and observation triage; never an execution/success oracle."""
import hashlib,json,re
HEX=re.compile(r'^[a-f0-9]{64}$')

def _hash(v):
    if type(v)is not str or not HEX.fullmatch(v):raise ValueError('Expected lowercase SHA256')
    return v

def profile_report(profile):
    if type(profile)is not dict or set(profile)-{'OT_SimNumberOfRuns','useThreads','logTable'}:raise ValueError('Only recovered profile observations allowed')
    if 'OT_SimNumberOfRuns' in profile:
        n=profile['OT_SimNumberOfRuns']
        if type(n)is not int or not 1<=n<=1000:raise ValueError('Explicit batch count must be integer 1..1000 in this preview domain')
    for name in ('useThreads','logTable'):
        if name in profile and type(profile[name])is not bool:raise ValueError('Boolean profile observation required')
    conflicts=[]
    if profile.get('useThreads',True)is False:conflicts.append('useThreads getter always returns true in inspected build; setter is a no-op')
    if profile.get('logTable',False)is True:conflicts.append('logTable getter always returns false in inspected build; setter is a no-op')
    return {'reported_observations':profile,'observations_verified':False,'settings_changed':False,'conflicts':conflicts,
            'batch_count_source':'NSUserDefaults OT_SimNumberOfRuns (non-OTT); OTT reads RailML count separately',
            'batch_count_bound':False,'run_file_batch_count_override_supported':False}

def evidence_report(observation,manifest_digest,run_hash):
    out={'native_success':False,'execution_verified':False,'status':'not_observed','claim_provenance':'untrusted caller observations only',
         'native_result_parser_validated':False,'reasons':[]}
    if observation is None:return out
    if type(observation)is not dict:raise ValueError('Observation must be an object')
    allowed={'input_manifest_sha256','run_sha256','exit_code','error_messages','artifacts'}
    if set(observation)-allowed:raise ValueError('Unknown evidence observation key; success claims are not accepted')
    if set(observation)!=allowed:raise ValueError('Observation requires explicit hashes, exit_code, error_messages and artifacts')
    _hash(observation['input_manifest_sha256']);_hash(observation['run_sha256'])
    code=observation['exit_code']
    if code is not None and (type(code)is not int or not -(2**31)<=code<2**31):raise ValueError('exit_code must be null or int32')
    errors=observation['error_messages']
    if type(errors)is not list or len(errors)>100 or any(type(e)is not str or not e or len(e)>2000 for e in errors):raise ValueError('Bounded explicit error strings required')
    arts=observation['artifacts']
    if type(arts)is not list or len(arts)>1000:raise ValueError('At most 1000 artifact observations')
    names=set();changed=unchanged=0
    for a in arts:
        if type(a)is not dict or set(a)!={'member','before_sha256','after_sha256'}:raise ValueError('Exact artifact observation fields required')
        name=a['member']
        if type(name)is not str or not name or len(name)>500 or '\\' in name or ':' in name or any(p in ('','.','..')for p in name.split('/')) or any(ord(c)<32 for c in name):raise ValueError('Canonical relative artifact member required')
        if name.casefold() in names:raise ValueError('Duplicate artifact observation')
        names.add(name.casefold());_hash(a['after_sha256'])
        if a['before_sha256']is not None:_hash(a['before_sha256'])
        if a['before_sha256']==a['after_sha256']:unchanged+=1
        else:changed+=1
    mismatched=observation['input_manifest_sha256']!=manifest_digest or observation['run_sha256']!=run_hash
    if mismatched:out['status']='rejected_input_binding';out['reasons'].append('Observation is not bound to current exact manifest and run')
    elif (code is not None and code!=0)or errors:out['status']='reported_failure';out['reasons'].append('Caller reports nonzero exit or error; not independently authenticated')
    else:out['status']='inconclusive';out['reasons'].append('Exit zero, files or claimed clean output cannot prove native completion')
    if unchanged:out['reasons'].append('Unchanged artifacts may be stale and cannot be completion evidence')
    if changed:out['reasons'].append('Changed/new artifacts may contain only headers/planned data written before Go')
    if code is None:out['reasons'].append('No process exit observation')
    out.update(artifact_count=len(arts),changed_or_new_count=changed,unchanged_count=unchanged)
    out['required_remaining_evidence']=['Authenticated isolated run provenance and exact input bindings','Validated native result schemas and completeness per expected Course','Observed stop time and finished/uncompleted/failed Course accounting','Output freshness and parsing beyond headers/planned data','Independent runtime validation, unavailable in this preview']
    return out

def summarize(run_blob,source_files,preflight,profile,observation=None):
    if type(source_files)is not dict or not source_files:raise ValueError('Exact source manifest required')
    for name,h in source_files.items():
        if type(name)is not str:raise ValueError('Manifest names must be strings')
        _hash(h)
    manifest_digest=hashlib.sha256(json.dumps(source_files,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    run_hash=hashlib.sha256(run_blob).hexdigest()
    pr=profile_report(profile)
    if preflight.get('passed_static_subset')is not True:
        normalized=None
    else:
        normalized={}
        for line in run_blob.decode('ascii').splitlines():
            if not line or line.startswith('//'):continue
            key,value,_=line.split('#');normalized.setdefault(key,[]).append(value)
    reasons=['This saved-data tool has no process-launch capability; native compatibility validation is separate','Native path/framework/license/profile/physics equivalence unverified','Final publication review remains pending']
    if normalized is None:reasons.insert(0,'Static project preflight failed')
    if pr['conflicts']:reasons.append('Reported profile observations conflict with recovered behavior')
    return {'native_execution':False,'native_success':False,'native_runtime_ready':False,'blocked':True,'requires_native_validation':True,
        'saved':False,'preview_only':True,'static_subset_passed':preflight.get('passed_static_subset')is True,
        'run_sha256':run_hash,'input_manifest_sha256':manifest_digest,'manifest_hash_encoding':'SHA256 of JSON source_files sorted keys, ensure_ascii=True, separators comma/colon',
        'normalized_run_records':normalized,'normalization_policy':'Structured ordered values only; source bytes and preferences unchanged; no defaults filled',
        'profile':pr,'blocking_reasons':reasons,'preflight':preflight,
        'review_plan':[{'step':1,'action':'Verify exact selected run and complete source hashes; refuse fallback','status':'static checks only'},
          {'step':2,'action':'Confirm native namespace mapping and isolated work copies/profile/output destination','status':'not performed'},
          {'step':3,'action':'Perform any separately authorized native compatibility check in a suitable environment; script and scriptinit both auto-Go','status':'blocked'},
          {'step':4,'action':'Observe startup/load/Go/end without treating headers or process exit as success','status':'not performed'},
          {'step':5,'action':'Bind and parse fresh native per-Course results before deciding completion','status':'not performed'}],
        'native_hazards':['Invalid script run can fall back to recent documents and still Go','firstStart writes headers/planned data before Go checks','Valid run may override or bypass CLI outputpath expectation','Application exit may write DestInfo/controller data and preferences','No recovered dependable exit-code success contract','No proven load-only CLI; scriptinit and script both auto-Go'],
        'result_evidence':evidence_report(observation,manifest_digest,run_hash)}
