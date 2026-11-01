 

#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>
#include "contract.h"

static int no_existing_original(void)
{
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    PROCESSENTRY32W entry; int safe=1;
    if(snapshot==INVALID_HANDLE_VALUE) return 0;
    memset(&entry,0,sizeof(entry)); entry.dwSize=sizeof(entry);
    if(!Process32FirstW(snapshot,&entry)) safe=0;
    else do {
        if(!_wcsicmp(entry.szExeFile,L"OpenTrack.exe")) {
            HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,entry.th32ProcessID);
            wchar_t path[1100]; DWORD length=1100;
            if(!process || !QueryFullProcessImageNameW(process,0,path,&length)) safe=0;
            else if(!_wcsicmp(path,ORIGINAL_EXE_W)) {
                wprintf(L"Refusing existing original OpenTrack PID %lu. No attach will occur.\n",entry.th32ProcessID); safe=0;
            }
            if(process)CloseHandle(process);
        }
    } while(Process32NextW(snapshot,&entry));
    CloseHandle(snapshot); return safe;
}
static ULONG_PTR module_base(DWORD pid,const wchar_t *name)
{
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid);
    MODULEENTRY32W entry; ULONG_PTR result=0;
    if(snapshot==INVALID_HANDLE_VALUE)return 0;
    memset(&entry,0,sizeof(entry));entry.dwSize=sizeof(entry);
    if(Module32FirstW(snapshot,&entry))do {
        if(!_wcsicmp(entry.szModule,name)){result=(ULONG_PTR)entry.modBaseAddr;break;}
    }while(Module32NextW(snapshot,&entry));
    CloseHandle(snapshot);return result;
}
static int load_owned_child(const PROCESS_INFORMATION *child,const wchar_t *dll)
{
    FARPROC load=GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"LoadLibraryW");
    MEMORY_BASIC_INFORMATION mapping; wchar_t path[1100]; const wchar_t *name;
    ULONG_PTR base=0,entry; HANDLE thread; void *remote;
    SIZE_T bytes=(wcslen(dll)+1)*sizeof(wchar_t),written=0; DWORD status,code=0; int i;
    if(!load || !VirtualQuery((const void *)load,&mapping,sizeof(mapping)) ||
        !GetModuleFileNameW((HMODULE)mapping.AllocationBase,path,1100))return 0;
    name=wcsrchr(path,L'\\');name=name?name+1:path;
    for(i=0;i<100 && !base;++i){base=module_base(child->dwProcessId,name);if(!base)Sleep(50);}
    if(!base)return 0;
    entry=base+(ULONG_PTR)load-(ULONG_PTR)mapping.AllocationBase;
    remote=VirtualAllocEx(child->hProcess,NULL,bytes,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!remote)return 0;
    if(!WriteProcessMemory(child->hProcess,remote,dll,bytes,&written)||written!=bytes){VirtualFreeEx(child->hProcess,remote,0,MEM_RELEASE);return 0;}
    thread=CreateRemoteThread(child->hProcess,NULL,0,(LPTHREAD_START_ROUTINE)entry,remote,0,NULL);
    if(!thread){VirtualFreeEx(child->hProcess,remote,0,MEM_RELEASE);return 0;}
    status=WaitForSingleObject(thread,10000);
    if(status==WAIT_OBJECT_0){GetExitCodeThread(thread,&code);VirtualFreeEx(child->hProcess,remote,0,MEM_RELEASE);}
     
    CloseHandle(thread);return status==WAIT_OBJECT_0 && code!=0;
}
static int absent(const wchar_t *path){return GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES;}
int wmain(int argc,wchar_t **argv)
{
    const wchar_t *dll=EXPORT_ROOT_W L"\\native-export.dll";
    wchar_t command[]=ORIGINAL_COMMAND_W;
    wchar_t name[128]; STARTUPINFOW startup; PROCESS_INFORMATION child;
    HANDLE events[3]={0},owned=NULL; DWORD status; int run=argc==2&&!wcscmp(argv[1],L"--run-native-export");
    if(argc>2 || (argc==2&&!run&&wcscmp(argv[1],L"--check"))) {
        wprintf(L"Usage: launch-owned.exe --check | --run-native-export\n");return 2;
    }
    if(!verify_software_authorization()) {
        wprintf(L"Full OpenTrack user authorization record is missing or changed. Nothing launched.\n");return 7;
    }
    if(!verify_sha256(ORIGINAL_EXE_W,ORIGINAL_SHA)||!verify_sha256(CORRIDOR_W,CORRIDOR_SHA)) {
        wprintf(L"Exact original EXE or corridor SHA guard failed.\n");return 3;
    }
    if(GetFileAttributesW(dll)==INVALID_FILE_ATTRIBUTES){wprintf(L"Isolated DLL missing.\n");return 3;}
    if(!no_existing_original()){wprintf(L"Existing-process guard failed. Nothing launched.\n");return 4;}
    if(!absent(EXPORT_ROOT_W L"\\H2_Actual.eps")||!absent(EXPORT_ROOT_W L"\\H2_Actual.tiff")||
        !absent(EXPORT_ROOT_W L"\\native-result.json")||!absent(EXPORT_ROOT_W L"\\native-trace.log")) {
        wprintf(L"An export or runtime receipt already exists. Preserve/review it before any new run.\n");return 4;
    }
    wprintf(L"Preflight passed: exact EXE/corridor SHA; no existing original process; fresh export targets.\n");
    if(!run){wprintf(L"CHECK ONLY. No process created, no DLL loaded, no native API invoked.\n");return 0;}
    memset(&startup,0,sizeof(startup));startup.cb=sizeof(startup);
    startup.dwFlags=STARTF_USESHOWWINDOW;startup.wShowWindow=SW_SHOWNORMAL;
    memset(&child,0,sizeof(child));
    if(!verify_software_authorization()) {
        wprintf(L"Full software authorization changed after preflight. Nothing launched.\n");return 7;
    }
    if(!CreateProcessW(ORIGINAL_EXE_W,command,NULL,NULL,FALSE,0,NULL,
        ORIGINAL_CWD_W,&startup,&child)) {
        wprintf(L"CreateProcess failed: %lu\n",GetLastError());return 5;
    }
    wprintf(L"Created owned original child PID %lu. Only this PID is eligible.\n",child.dwProcessId);fflush(stdout);
    swprintf_s(name,128,OWNED_EVENT,child.dwProcessId);owned=CreateEventW(NULL,TRUE,TRUE,name);
    swprintf_s(name,128,FAILED_EVENT,child.dwProcessId);events[1]=CreateEventW(NULL,TRUE,FALSE,name);
    swprintf_s(name,128,READY_EVENT,child.dwProcessId);events[2]=CreateEventW(NULL,TRUE,FALSE,name);
    events[0]=child.hProcess;
    if(!owned||!events[1]||!events[2]||!load_owned_child(&child,dll)) {
        wprintf(L"Owned child DLL load failed. Child retained for review; no other process touched.\n");status=WAIT_FAILED;
    } else {
        status=WaitForMultipleObjects(3,events,FALSE,60000);
        if(status==WAIT_OBJECT_0+2)wprintf(L"Native export completed. Review native-result.json and both files. Application left open.\n");
        else if(status==WAIT_OBJECT_0+1)wprintf(L"Native export failed. Review native-result.json; application left open.\n");
        else if(status==WAIT_OBJECT_0)wprintf(L"Owned original child exited before export completion.\n");
        else wprintf(L"Native export not confirmed within 60 seconds. Child retained for review.\n");
    }
    if(owned)CloseHandle(owned);if(events[1])CloseHandle(events[1]);if(events[2])CloseHandle(events[2]);
    CloseHandle(child.hThread);CloseHandle(child.hProcess);
    return status==WAIT_OBJECT_0+2?0:6;
}
