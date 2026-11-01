"""Read the frozen original-build function bank; never execute native code."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import zipfile

from .errors import APIError
from .catalog import EXPECTED_EXE_SHA256


def sha(blob):return hashlib.sha256(blob).hexdigest()

REVIEW_NOTES={
    '005bcbb0':['Native lookup walks saved array order: first exact position match, otherwise the preceding row before the first greater position, else the last row. No implicit sorting. Duplicate positions can select a different row just after the exact boundary. Only finite-float32 semantics are implemented by the Agent data query.'],
    '005bce44':['The original Foundation selector sort uses exported _NSMergeSort, whose equal heads interleave left/right; it is not Python stable sorting. Its count>63 shortcut is selected once at top level. See itinerary-margins function evidence and the separate typed Foundation C.'],
    '00492328':['For the Misc margin table, editing position sorts immediately; editing safetyMargin preserves order. Both public fields compose margin edit then position edit on the same selected row. Other table/UI branches are outside the data implementation.'],
    '0048c51c':['Import clears the profile, accepts a digit after spaces only, replaces commas, splits tabs, reads two NSString float prefixes, ignores extra fields, then sorts. Signed/leading-tab position lines skip. The Agent snapshots and parses before committing, so read/parse failure does not clear source data.'],
    '0048c300':['Recovered float getters, index argument and fprintf doubles are visible in the generated C. Original MSVCRT two-decimal output uses half-away rounding and a 17-significant-digit conversion for wide fields; independent bit-level formatting fixtures anchor the portable writer. Header timestamps and GUI state are not imitated.'],
    '0048c838':['Receiver-specific float levelDiff recovery restores edit argument types. Native existing info Path caches can remain stale; the Agent default composes an explicit selected-info refresh. GUI collision/notification branches remain outside the verified data subset.'],
    '0048a980':['Original Add requires exact document and directional End equality at the join. Shared UI/error exits retain inferred sites; self-Add is unsupported. The reviewed body growth retains old bytes and original metadata identity, with executable-section and adjacent-entry checks.'],
    '0040ff1c':['Receiver repair recovered omitted getBlockEnd blocks. Outside simulation this adjusts the connection and resolves blockTopo/blockEnd, accepting a connector or its graphic target. Body growth was explicitly checked; native runtime branch behavior is unverified.'],
    '0047503c':['Original copy shares Path objects, copies info and safety margins, and does not copy arrayDescription. OTOrgArray initializes description to the verified empty literal.'],
    '0045ee48':['Native rename replaces only the first matching Itinerary string in each Course. Do not silently replace subsequent duplicate occurrences.'],
    '00489b10':['Native continuation excludes the immediately previous Path object. A setting back requires the next firstEnd.actualRelated to occur before the last vertex in the previous lastRoute; paired terminal Ends alone are insufficient.'],
    '0048dd48':['Replacement preserves interior first/last End boundaries; prefix/suffix can change outer endpoints. Native indexOfObject targets the first object occurrence; Agent rejects aliased repeated-Path selections instead of silently moving the interval.'],
    '00478058':['Original encoder removes embedded Paths after index zero with rebuildingPathInfoArray=false before super coding, then saves every Path info and safety margin and calls update. The bounded Agent writer persists the first Path object and every ordered reference; cross-document foreign graphs must not be embedded. Native coder invocation and transient post-save rebuilding are not executed.'],
    '0068fb34':['Metadata-based NSRange argument recovery restores location, length and replacement. Both comma and dot are replaced with the colon literal before splitting. Read the string annotations and callees; the final ROUND and all dynamic semantics are not fully certified.'],
    '006643b4':['Regenerated with explicit doubleValue return metadata. The C now carries a double value instead of an untyped extraout_ST0 temporary. This is function recovery evidence, not native execution.'],
    '0066440c':['Regenerated with explicit doubleValue return metadata. Native floating-point/runtime acceptance remains unverified.'],
    '0067bc5c':['Getter and compare: call arguments are restored in the regenerated C. Read the comparison function before deriving sorting behavior; Foundation collation is not fully replicated.'],
    '006a1e24':['Shared reset dispatch still contains invalid inferred stack temporaries. This branch is not implementation-ready from raw C alone. Repair its function/call types instead of filling the gap with an automatic instruction-level review.'],
    '006a5a44':['String range arguments are recovered from metadata, but shared setter arguments and branch-dependent receivers remain unresolved. Do not infer a complete RailML importer from this C.'],
    '00692794':['The count creates additional sequential copies and updates the selected source after each iteration. Row 0 chooses the saved reference root; each row accumulates its own float32 offset. Connections are copied then renumbered with the same rule. Saved actual fields are copied, while their transient validity is not archived.'],
    '006901ec':['The shared final dispatch merges NSString stringWithFormat: and setCourseNumber:ofString:atPosition:. The missing-block branch uses verified %@.%i with the original name and delta; the other branch rejects negative numeric results. Do not interpret inferred generic pointer casts as source-level types.'],
    '006797ac':['The refined float getter/setter calls restore the day calculation. Nonnegative absolute values recalculate floor(value/86400); negative results clear the day to zero and format as HH:MM:SS. addSecondsToTime: skips already negative or undefined inputs.'],
    '006acab4':['Property linkage uses the same station/row/connection index in a direct interval family. It copies the complete station/wait/join/split/location/time-type property set, excluding target Course ID and dispatching distance. A reference row is a root only if it has no own interval reference; missing connection indices skip.'],
    '00685230':['The removed unreachable blocks are disabled debug-print branches, verified by zero/test/jump windows. local_18 carries float32 dwell bits; the shared setWait:/setWaitTime_s: call mixes object and float argument words, so its generic pointer casts are not source-level types. The implementation follows the reviewed branch and truncating wait setter.'],
    '0068a310':['Reviewed zero/test/jump windows skip diagnostic printing. Selection appends station vertices/halt or exit signals, removes blank signs, and performs reverse identity-based duplicate removal. Usually this retains the first station vertex or last plain candidate in a same-station run; revisiting the same object can remove a farther alias. The following row pass skips adjacent equal signs but preserves the candidate-count maxIndex.'],
    '00679e94':['ROUND is FISTP with RC=truncate after loading the float32 argument. Saved dwell is an integer string, not nearest-integer rounding.'],
    '006c513c':['Category archive group 22 stores the inverse of departureProcessTimeStartsAtDepartureTime; groups 18 and 24 store signed dwell values/units and delay offsets. Read the decoder version branch before assigning indices.'],
    '006c2dbc':['The coder variadic pointer arguments were restored in bank-v019-coders. Archive group 20 is minTimeToHoldSpeed_s and group 22 is accelerationDelayAtStop_s; API versions through 0.18 had these two mappings reversed. Existing saved values are never automatically exchanged.'],
    '0053fde0':['The legacy exporter has a merged printf argument artifact at auxPowerDeltaLoadFactor. The data implementation uses the reviewed Train getter (first Trailer delta-load factor) and does not claim byte-identical native output or verified correctness of all raw C temporaries.'],
    '006d4c4c':['Shared dispatch at 0x6d4f6e mixes object, int and float argument words. The raw C can propagate the wrong selector/value through merged stack branches. Repair function/call types before extending it. The rolling-stock XML contract records historical evidence; it is not an instruction to resume assembly inspection.'],
    '006d52b8':['Shared dispatch merges differently named calls; do not treat inferred temporary receiver names as source-level types. ROUND at the point conversion sites uses an explicitly truncating x87 control word, not nearest rounding.'],
    '0047171c':['ROUND at the final return is FISTP with RC=truncate. Power uses saved endpoints and float32 temporaries, not an interior piecewise-curve maximum.'],
}


def page_literals(blob,expected,binary_sha256,entry,offset,end):
    if sha(blob)!=expected:raise APIError('FUNCTION_BANK_INTEGRITY','Function string annotations differ from verification.')
    data=json.loads(blob)
    if data['schema_version']!=1 or data['binary_sha256']!=binary_sha256:
        raise APIError('FUNCTION_BANK_INTEGRITY','Function string annotations belong to a different build or schema.')
    result=[]
    for ref in data['function_references'].get(entry,[]):
        lines=[number for number in ref['lines'] if offset<number<=end]
        if lines:
            result.append({**data['literals'][ref['literal_address']],'literal_address':ref['literal_address'],'lines':lines})
    if sum(len(row['value']) for row in result)>120000:raise APIError('FUNCTION_PAGE_SIZE','Use a smaller line limit for function string annotations.')
    return result


class FunctionBank:
    def __init__(self,service):
        self.folder=Path(__file__).resolve().parents[1]/'resources'

    def read(self,args):
        try:return self._read(args)
        except (zipfile.BadZipFile,KeyError,TypeError,ValueError,UnicodeError) as error:
            raise APIError('FUNCTION_BANK_INTEGRITY','The function bank is malformed or incomplete.',str(error)[:160]) from error

    def _read(self,args):
        descriptor=self.folder/'function-bank.json'
        if not descriptor.is_file():raise APIError('FUNCTION_BANK_UNAVAILABLE','Build or install the verified function-bank resource first.')
        specification=json.loads(descriptor.read_text(encoding='utf8'))
        if specification['binary_sha256']!=EXPECTED_EXE_SHA256:raise APIError('FUNCTION_BANK_BUILD','The function bank belongs to a different original executable.')
        name=specification['archive']
        if Path(name).name!=name or not name.endswith('.zip'):raise APIError('FUNCTION_BANK_INTEGRITY','Invalid bank resource filename.')
        blob=(self.folder/name).read_bytes()
        if sha(blob)!=specification['archive_sha256']:raise APIError('FUNCTION_BANK_INTEGRITY','The function bank changed after verification.')
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(blob)) as bank:
            quality_blob=bank.read('quality-report.json')
            if sha(quality_blob)!=specification['quality_report_sha256']:raise APIError('FUNCTION_BANK_INTEGRITY','The quality report differs from the bank descriptor.')
            quality=json.loads(quality_blob)
            if quality['binary_sha256']!=EXPECTED_EXE_SHA256 or not quality['critical_function_gate_passed'] or quality['message_send_truncations']:
                raise APIError('FUNCTION_BANK_QUALITY','This bank failed its build or control-flow checks.')
            raw=bank.read('function-index-all.jsonl')
            if sha(raw)!=quality['input_hashes']['function-index-all.jsonl']:raise APIError('FUNCTION_BANK_INTEGRITY','The function index differs from its verified digest.')
            records=[json.loads(line) for line in raw.decode('utf8').splitlines()]
            rows=[]
            for row in records:
                if args.address:
                    if int(row['address'],16)!=int(args.address,0):continue
                else:
                    aliases=[m for m in row['metadata_aliases'] if (not args.class_name or m['class']==args.class_name) and
                        (args.category is None or m.get('category','')==args.category) and (not args.selector or m['selector']==args.selector) and
                        (not args.method_kind or m['method_kind']==args.method_kind)]
                    if (args.class_name or args.category is not None or args.selector or args.method_kind) and not aliases:continue
                    if args.query and args.query.casefold() not in json.dumps([row['name'],row['metadata_aliases']],ensure_ascii=True).casefold():continue
                rows.append(row)
            context={'bank_id':specification['bank_id'],'binary_sha256':EXPECTED_EXE_SHA256,'native_code_executed':False,
                'source_recovery_complete':False,'semantic_correctness_verified':False,
                'bank_functions':len(records),'bank_failed_entries':quality['failed_decompilations'],
                'complex_metadata_signatures':quality['unapplied_complex_signatures']}
            if not (args.address or args.selector):
                return {**context,'total_count':len(rows),'offset':args.offset,'has_more':args.offset+args.limit<len(rows),
                    'items':[{k:r[k] for k in ['address','name','signature','metadata_aliases','decompile_completed','body_bytes']} for r in rows[args.offset:args.offset+args.limit]]}
            if len(rows)!=1:raise APIError('FUNCTION_SELECTION','Exact function selection is missing or ambiguous.',{'matches':len(rows)})
            row=rows[0]
            if not row['decompile_completed'] or not row.get('pseudocode_file'):
                raise APIError('FUNCTION_NOT_DECOMPILED','This function has a recorded decompiler failure.',row)
            manifest=bank.read('function-file-hashes.json')
            if sha(manifest)!=quality['pseudocode_hash_manifest_sha256']:raise APIError('FUNCTION_BANK_INTEGRITY','The code hash manifest differs from verification.')
            hashes=json.loads(manifest);relative=PurePosixPath(row['pseudocode_file'])
            if len(relative.parts)!=2 or relative.parts[0]!='functions' or relative.suffix!='.c' or str(relative)!=row['pseudocode_file']:
                raise APIError('FUNCTION_BANK_INTEGRITY','Invalid pseudocode entry path.')
            code=bank.read(str(relative))
            if sha(code)!=hashes.get(str(relative)):raise APIError('FUNCTION_BANK_INTEGRITY','Pseudocode bytes differ from verification.')
            lines=code.decode('utf8').splitlines();end=min(len(lines),args.offset+args.limit)
            selected=[{'line':i+1,'text':lines[i]} for i in range(args.offset,end)]
            if sum(len(line['text']) for line in selected)>120000:raise APIError('FUNCTION_PAGE_SIZE','Use a smaller line limit for this function.')
            literal_hash=quality['input_hashes'].get('function-string-literals.json')
            literals=page_literals(bank.read('function-string-literals.json'),literal_hash,EXPECTED_EXE_SHA256,row['address'],args.offset,end) if literal_hash else []
            return {**context,**row,'sha256':hashes[str(relative)],'total_lines':len(lines),'offset':args.offset,'has_more':end<len(lines),'lines':selected,
                'referenced_string_literals':literals,'string_annotations_available':bool(literal_hash),
                'review_notes':REVIEW_NOTES.get(row['address'],[]),
                'control_flow_warning_in_report':row['address'] in quality['other_warning_functions'],
                'dynamic_call_abi_verified':False,'scope':'Machine-generated C pseudocode. Check receiver types, variadic calls and aggregate ABI before relying on behavior.'}
