"""Run only our console binaries and offline --check; never use --launch."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = Path(r"D:\opentrack\OpenTrack.app\OpenTrack.exe")
EVIDENCE = ROOT.parent / "evidence"

def run(args, expected=0):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)
    return dict(args=[str(x) for x in args], exit_code=result.returncode,
                stdout=result.stdout.strip(), stderr=result.stderr.strip())

def main():
    launcher=ROOT/"out/ot-inspector-guard.exe"
    results=[run([ROOT/"out/guard-policy-tests.exe"]), run([ROOT/"out/guard-adapter-tests.exe"]),
             run([ROOT/"out/guard-adapter-tests.exe","--unexpected-thread"],92),
             run([launcher]), run([launcher,"--check",APP]), run([launcher,"--attach","1"],2)]
    contract=json.loads((ROOT/"contract.json").read_text())
    fake=bytearray(512); fake[:2]=b"MZ"; struct.pack_into("<I",fake,0x3c,64)
    fake[64:68]=b"PE\0\0"; struct.pack_into("<H",fake,68,0x14c)
    struct.pack_into("<I",fake,72,contract["timestamp"])
    struct.pack_into("<H",fake,88,0x10b)
    struct.pack_into("<I",fake,116,contract["image_base"])
    struct.pack_into("<I",fake,144,contract["image_size"])
    truncated=bytearray(64); truncated[:2]=b"MZ"; struct.pack_into("<I",truncated,0x3c,0x100000)
    negative=bytearray(truncated); struct.pack_into("<I",negative,0x3c,0xffffffff)
    fixtures={"empty":b"", "random":b"not a PE", "truncated-mz":truncated,
              "negative-lfanew":negative, "valid-header-wrong-hash":fake}
    with tempfile.TemporaryDirectory(prefix="otig-offline-check-") as temp:
        for name,data in fixtures.items():
            path=Path(temp)/(name+".bin"); path.write_bytes(data)
            check=run([launcher,"--check",path],3); check["fixture"]=name; results.append(check)
        results.append(run([launcher,"--check",Path(temp)/"missing.bin"],3))
    binaries=[]
    for name in ("ot-inspector-guard.dll","ot-inspector-guard.exe","guard-policy-tests.exe","guard-adapter-tests.exe"):
        path=ROOT/"out"/name; data=path.read_bytes()
        pe=struct.unpack_from("<I",data,0x3c)[0]
        machine=struct.unpack_from("<H",data,pe+4)[0]
        assert machine==0x14c
        binaries.append(dict(name=name,sha256=hashlib.sha256(data).hexdigest(),machine="x86",bytes=len(data)))
    summary=dict(schema=1,status="static_and_headless_passed_gui_pending",version="0.33.0-staticfix1",
                 policy_tests=6,adapter_tests=11,non_ui_fail_stop_mock_tests=1,offline_launcher_cases=len(results)-3,all_passed=True,
                 original_pe_loaded=False,original_pe_executed=False,opentrack_launched=False,
                 existing_process_attached=False,gui_acceptance=False,native_startup_handshake_verified=False,
                 lifecycle_guard_gui_verified=False,commercial_exe_included=False,
                 method_contracts=len(contract["methods"]),class_contracts=len(contract["classes"]),
                 ivar_contracts=len(contract["ivars"]),binaries=binaries,results=results,
                 limitations=["No stock process, OpenStep GUI, message hook injection, or native simulation was run.",
                              "Fresh-process launch and Ready/Failed handshake remain unverified in the real application.",
                              "Explicit dealloc that violates retain ownership abandons dependent references until process exit.",
                              "Unexpected non-UI lifecycle stops only the current guarded process with exit code 92; native workload thread behavior remains unverified.",
                              "Guard intentionally limits capture to 64 documents, 4096 model/view pairs and 16 Inspectors; an exceeded limit clears/denies the Inspector operation."])
    EVIDENCE.mkdir(exist_ok=True)
    summary["source_hashes"]={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                              for folder in ("src","tests") for path in sorted((ROOT/folder).glob("*")) if path.is_file()}
    summary["build"]=dict(compiler="MSVC x86",flags="/O2 /MT /W4 /WX /utf-8",windows_sdk="10.0.26100.0",
                           command="cmd /c build.cmd",original_pe_execution=False)
    target=EVIDENCE/"native-guard-summary.json"
    target.write_text(json.dumps(summary,indent=2)+"\n",encoding="ascii")
    print(json.dumps({k:summary[k] for k in ("status","policy_tests","adapter_tests","offline_launcher_cases","all_passed","gui_acceptance")}))
if __name__=="__main__": main()
