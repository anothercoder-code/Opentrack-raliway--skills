 

#include <windows.h>
#include <tlhelp32.h>
#include <wincrypt.h>
#include <stdio.h>
#include <wchar.h>
#include "fingerprint.h"
static int existing_stock_process(void)
{
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    PROCESSENTRY32W process;
    int found=0;
    if(snapshot==INVALID_HANDLE_VALUE) return 1;
    process.dwSize=sizeof(process);
    if(!Process32FirstW(snapshot,&process)) { CloseHandle(snapshot); return 1; }
    do {
        if(!_wcsicmp(process.szExeFile,L"OpenTrack.exe")) { found=1; break; }
    } while(Process32NextW(snapshot,&process));
    CloseHandle(snapshot);
    return found;
}
static int make_token(WCHAR token[33])
{
    HCRYPTPROV provider=0;
    BYTE bytes[16]; unsigned i;
    if(!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)) return 0;
    if(!CryptGenRandom(provider,16,bytes)) { CryptReleaseContext(provider,0); return 0; }
    CryptReleaseContext(provider,0);
    for(i=0;i<16;++i) swprintf_s(token+i*2,33-i*2,L"%02x",bytes[i]);
    return 1;
}
static int launch_fresh(const WCHAR *path)
{
    STARTUPINFOW startup;
    PROCESS_INFORMATION child;
    WCHAR dll[32768],directory[32768],command[32768],token[33],event_name[180];
    WCHAR old_session[128],old_path[32768],new_path[32768];
    WCHAR *slash;
    HMODULE module=NULL;
    HHOOK hook=NULL;
    HOOKPROC entry;
    HANDLE ready=NULL,failed=NULL,waits[3];
    DWORD result,old_session_length,old_path_length,dll_length;
    int owned=0,success=0;
    memset(&startup,0,sizeof(startup)); memset(&child,0,sizeof(child));
    startup.cb=sizeof(startup); startup.dwFlags=STARTF_USESHOWWINDOW; startup.wShowWindow=SW_SHOWNORMAL;
    if(existing_stock_process()) { fputs("Launch refused: close existing OpenTrack processes first.\n",stderr); return 4; }
    dll_length=GetModuleFileNameW(NULL,dll,32768);
    if(!make_token(token) || !dll_length || dll_length>=32768) goto done;
    slash=wcsrchr(dll,L'\\'); if(!slash) goto done;
    wcscpy_s(slash+1,32768-(size_t)(slash+1-dll),L"ot-inspector-guard.dll");
    module=LoadLibraryExW(dll,NULL,LOAD_WITH_ALTERED_SEARCH_PATH);
    if(!module) goto done;
    entry=(HOOKPROC)GetProcAddress(module,"GuardMessageHook");
    if(!entry) goto done;
    wcscpy_s(directory,32768,path);
    slash=wcsrchr(directory,L'\\'); if(!slash) goto done; *slash=0;
    if(wcschr(path,L'"') || _snwprintf_s(command,32768,_TRUNCATE,L"\"%s\"",path)<0) goto done;
    old_session_length=GetEnvironmentVariableW(L"OTIG_SESSION",old_session,128);
    if(old_session_length>=128) goto done;
    old_path_length=GetEnvironmentVariableW(L"PATH",old_path,32768);
    if(old_path_length>=32768 || _snwprintf_s(new_path,32768,_TRUNCATE,L"C:\\NEXT\\NEXTLIBRARY\\EXECUTABLES;%s",old_path)<0) goto done;
    if(!SetEnvironmentVariableW(L"OTIG_SESSION",token) || !SetEnvironmentVariableW(L"PATH",new_path)) goto done;
    owned=CreateProcessW(path,command,NULL,NULL,FALSE,CREATE_SUSPENDED,NULL,directory,&startup,&child)!=0;
    SetEnvironmentVariableW(L"OTIG_SESSION",old_session_length?old_session:NULL);
    SetEnvironmentVariableW(L"PATH",old_path_length?old_path:NULL);
    if(!owned) goto done;
    _snwprintf_s(event_name,180,_TRUNCATE,L"Local\\OpenTrack.InspectorGuard.Ready.%lu.%s",child.dwProcessId,token);
    ready=CreateEventW(NULL,TRUE,FALSE,event_name);
    if(!ready || GetLastError()==ERROR_ALREADY_EXISTS) goto done;
    _snwprintf_s(event_name,180,_TRUNCATE,L"Local\\OpenTrack.InspectorGuard.Failed.%lu.%s",child.dwProcessId,token);
    failed=CreateEventW(NULL,TRUE,FALSE,event_name);
    if(!failed || GetLastError()==ERROR_ALREADY_EXISTS) goto done;
     

    hook=SetWindowsHookExW(WH_GETMESSAGE,entry,module,child.dwThreadId);
    if(!hook || ResumeThread(child.hThread)==(DWORD)-1) goto done;
    waits[0]=ready; waits[1]=failed; waits[2]=child.hProcess;
    result=WaitForMultipleObjects(3,waits,FALSE,30000);
    if(result!=WAIT_OBJECT_0) goto done;
    success=1;
    puts("Inspector guard Ready. Native GUI acceptance is still required.");
done:
    if(!success && owned) {
         

        TerminateProcess(child.hProcess,91);
        WaitForSingleObject(child.hProcess,5000);
    }
    if(hook) UnhookWindowsHookEx(hook);
    if(module) FreeLibrary(module);
    if(ready) CloseHandle(ready);
    if(failed) CloseHandle(failed);
    if(owned) { CloseHandle(child.hThread); CloseHandle(child.hProcess); }
    if(!success) fputs("Fresh launch failed or guard did not become Ready; the owned child was stopped.\n",stderr);
    return success?0:5;
}
int wmain(int argc,WCHAR **argv)
{
    WCHAR path[32768]; char hash[65],error[192]={0};
    DWORD path_length;
    int launch;
    if(argc==1) {
        puts("OpenTrack Inspector Guard (English, x86)\nUsage: ot-inspector-guard.exe --check <OpenTrack.exe>\n       ot-inspector-guard.exe --launch <OpenTrack.exe>\nDefault and --check never launch, attach to, or execute OpenTrack.");
        return 0;
    }
    if(argc!=3 || (wcscmp(argv[1],L"--check") && wcscmp(argv[1],L"--launch"))) {
        fputs("Invalid arguments. Use --check or the explicit future --launch entry.\n",stderr); return 2;
    }
    launch=!wcscmp(argv[1],L"--launch");
    path_length=GetFullPathNameW(argv[2],32768,path,NULL);
    if(!path_length || path_length>=32768) {
        fputs("REJECT: executable path could not be resolved within the path limit.\n",stderr); return 3;
    }
    if(!ig_check_file(path,hash,error,sizeof(error))) {
        fprintf(stderr,"REJECT: %s\n",error); return 3;
    }
    if(!launch) { printf("CHECK OK: stock PE32 x86 SHA256=%s; original_pe_execution=false; launched=false; attached=false\n",hash); return 0; }
    return launch_fresh(path);
}
