 


#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <wchar.h>
#include "contract.h"
#include "native_runtime.h"
#include "ui_dispatch.h"
#include "ot_exception.h"

static HANDLE g_ready, g_failed;
static FILE *g_trace;
static volatile LONG g_enabled, g_terminal;
static DWORD g_uiThread, g_readyTick, g_loadedTick;
static int g_bound, g_loaded, g_license = -1, g_eps, g_tiff, g_documentValid, g_viewValid, g_filenameMatch;
static unsigned g_stations, g_courseCount, g_eventCounts[5];
static const char *g_courses[5] = {"H2E1","H2E2","H2W1","H2W2","H2E1_FOLLOW"};
static const unsigned g_expectedCounts[5] = {2881,3118,2881,3081,3094};
static int g_length;
static Id g_document, g_window, g_docView, g_pool;
static const char *g_stage = "bootstrap";

static void trace(const char *format, ...)
{
    va_list args;
    if (!g_trace) return;
    fprintf(g_trace,"[%lu thread=%lu] ",GetTickCount(),GetCurrentThreadId());
    va_start(args,format); vfprintf(g_trace,format,args); va_end(args);
    fputc('\n',g_trace); fflush(g_trace);
}
static unsigned long long file_size(const char *path)
{
    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExA(path,GetFileExInfoStandard,&data)) return 0;
    return ((unsigned long long)data.nFileSizeHigh << 32) | data.nFileSizeLow;
}
static void receipt(int success, const char *reason)
{
    FILE *out = fopen(EXPORT_ROOT_A "/native-result.json","wb");
    if (!out) return;
    fprintf(out,"{\n  \"success\": %s,\n  \"reason\": \"%s\",\n  \"stage\": \"%s\",\n"
        "  \"pid\": %lu,\n  \"ui_thread\": %lu,\n  \"exe_sha256\": \"%s\",\n"
        "  \"input_sha256\": \"%s\",\n  \"license_allowed\": %d,\n"
        "  \"document_class\": \"%s\",\n  \"document_window\": %s,\n"
        "  \"export_view_class\": \"%s\",\n  \"station_count\": %u,\n"
        "  \"document_filename_matched\": %s,\n  \"course_count\": %u,\n"
        "  \"course_event_counts\": {\"H2E1\": %u, \"H2E2\": %u, \"H2W1\": %u, \"H2W2\": %u, \"H2E1_FOLLOW\": %u},\n"
        "  \"corridor_length_m\": %d,\n  \"eps_native_return\": %d,\n"
        "  \"tiff_native_return\": %d,\n  \"eps_bytes\": %llu,\n  \"tiff_bytes\": %llu,\n"
        "  \"original_disk_exe_modified\": false,\n  \"input_synthesis_used\": false\n}\n",
        success ? "true":"false",reason,g_stage,GetCurrentProcessId(),g_uiThread,
        ORIGINAL_SHA,CORRIDOR_SHA,g_license,g_documentValid?"OTCorridorDocument":"unverified",g_window?"true":"false",
        g_viewValid?"OTCorridorDocView":"unverified",g_stations,g_filenameMatch?"true":"false",g_courseCount,
        g_eventCounts[0],g_eventCounts[1],g_eventCounts[2],g_eventCounts[3],g_eventCounts[4],
        g_length,g_eps,g_tiff,file_size(EPS_A),file_size(TIFF_A));
    fclose(out);
}
static void fail(const char *reason)
{
    if (InterlockedCompareExchange(&g_terminal,1,0)) return;
    InterlockedExchange(&g_enabled,0);
    trace("FAILED stage=%s reason=%s",g_stage,reason);
    receipt(0,reason); ot_ui_dispatch_detach();
    if (g_failed) SetEvent(g_failed);
}
static int verify_methods(void)
{
    return nr_check("OTController","versionAllowsSaving","c8@0:4",0x41e69c) &&
        nr_check("OTCorridorDocument","initWithFile:","@12@0:4@8",0x43e878) &&
        nr_check("OTCorridorDocument","open::","@16@0:4@8@12",0x43f3b4) &&
        nr_check("OTCorridorDocument","docWindow","@8@0:4",0x441874) &&
        nr_check("OTCorridorDocument","docFileName","@8@0:4",0x440018) &&
        nr_check("OTCorridorDocument","corridorStationArray","@8@0:4",0x440868) &&
        nr_check("OTCorridorDocument","simulationController","@8@0:4",0x440000) &&
        nr_check("OTCorridorDocument","topoController","@8@0:4",0x44000c) &&
        nr_check("OTTCorridorSimController","eventDict","@8@0:4",0x6719d4) &&
        nr_check("OTCorridorDocument","saveTo:using:","c16@0:4@8:12",0x442370) &&
        nr_check("OTCorridorDocView","dataForEPS","@8@0:4",0x449d10) &&
        nr_check("OTCorridorDocView","dataForTIFF","@8@0:4",0x449db4) &&
        nr_check("OTTCorridorTopoController","corridorLength","i8@0:4",0x674fac);
}
static int license_allows(Id app)
{
    Id delegate = SEND0(app,"delegate");
    if (!delegate || strcmp(nr_class_name(delegate),"OTController") || !nr_has(delegate,"versionAllowsSaving")) return 0;
    g_license = BOOL0(delegate,"versionAllowsSaving") != 0;
    trace("Original versionAllowsSaving=%d",g_license);
    return g_license;
}
static void load_action(void *context)
{
    Id allocated, stations, topo, simulation, events, filename; unsigned i;
    (void)context;
    g_stage = "full-user-software-authorization-before-load";
    if(!verify_software_authorization()) {
        fail("full-software-authorization-record-missing-or-changed"); return;
    }
    g_stage = "native-license-before-load";
    if (!license_allows(nr_app())) { fail("original-version-disallows-saving"); return; }
    g_stage = "native-initWithFile";
    g_pool = SEND0(SEND0(nr_class("NSAutoreleasePool"),"alloc"),"init");
    allocated = SEND0(nr_class("OTCorridorDocument"),"alloc");
    trace("Calling original initWithFile with reviewed H2 archive");
    g_document = SEND1(allocated,"initWithFile:",SEND1(nr_class("NSString"),"stringWithCString:",CORRIDOR_A));
    trace("initWithFile returned %p class=%s",g_document,nr_class_name(g_document));
    if (!g_document || strcmp(nr_class_name(g_document),"OTCorridorDocument")) { fail("native-load-returned-nil-or-wrong-class"); return; }
    g_documentValid=1;
    filename=SEND0(g_document,"docFileName");
    g_filenameMatch=nr_has(filename,"isEqualToString:") &&
        BOOL1(filename,"isEqualToString:",SEND1(nr_class("NSString"),"stringWithCString:",CORRIDOR_A));
    if (!g_filenameMatch) { fail("native-document-source-filename-mismatch"); return; }
    g_window = SEND0(g_document,"docWindow");
    if (!g_window) { fail("native-document-window-is-nil"); return; }
    if (!nr_has(g_document,"corridorStationArray") || !nr_has(g_document,"topoController")) {
        fail("native-document-validation-getter-missing"); return;
    }
    stations = SEND0(g_document,"corridorStationArray");
    topo = SEND0(g_document,"topoController");
    if (!nr_has(stations,"count") || !nr_has(topo,"corridorLength")) { fail("native-corridor-validation-method-missing"); return; }
    g_stations = UINT0(stations,"count");
    g_length = INT0(topo,"corridorLength");
    trace("Loaded station_count=%u corridor_length=%d",g_stations,g_length);
    if (g_stations != 3 || g_length != 12000) { fail("native-corridor-content-mismatch"); return; }
    simulation=SEND0(g_document,"simulationController");
    if (!simulation || strcmp(nr_class_name(simulation),"OTTCorridorSimController")) { fail("native-simulation-controller-class-mismatch"); return; }
    events=SEND0(simulation,"eventDict");
    if (!nr_has(events,"count") || !nr_has(events,"objectForKey:")) { fail("native-event-dictionary-unavailable"); return; }
    g_courseCount=UINT0(events,"count");
    if (g_courseCount!=5) { fail("native-course-count-mismatch"); return; }
    for (i=0;i<5;++i) {
        Id series=SEND1(events,"objectForKey:",SEND1(nr_class("NSString"),"stringWithCString:",g_courses[i]));
        if (!nr_has(series,"count")) { fail("native-course-event-series-missing"); return; }
        g_eventCounts[i]=UINT0(series,"count");
        trace("Native course %s event count=%u",g_courses[i],g_eventCounts[i]);
        if(g_eventCounts[i]!=g_expectedCounts[i]) { fail("native-course-event-count-mismatch"); return; }
    }
    g_loaded = 1; g_loadedTick = GetTickCount(); g_stage = "loaded-awaiting-next-native-poll";
}
static void export_action(void *context)
{
    Id content, subviews, cls; unsigned i,n;
    (void)context;
    g_stage = "full-user-software-authorization-before-export";
    if(!verify_software_authorization()) {
        fail("full-software-authorization-record-missing-or-changed"); return;
    }
    g_stage = "native-license-before-export";
    if (!license_allows(nr_app())) { fail("original-version-disallows-saving"); return; }
    if (GetFileAttributesA(EPS_A) != INVALID_FILE_ATTRIBUTES || GetFileAttributesA(TIFF_A) != INVALID_FILE_ATTRIBUTES) {
        fail("refusing-to-overwrite-existing-export"); return;
    }
    g_stage = "native-export-view-validation";
    content = SEND0(g_window,"contentView"); subviews = SEND0(content,"subviews");
    if (!nr_has(subviews,"count")) { fail("native-content-subviews-unavailable"); return; }
    n = UINT0(subviews,"count"); cls = nr_class("OTCorridorDocView");
    for (i=0; i<n; ++i) {
        Id candidate = AT(subviews,i);
        if (nr_has(candidate,"isKindOfClass:") && BOOL1(candidate,"isKindOfClass:",cls)) { g_docView=candidate; break; }
    }
    if (!g_docView || !nr_has(g_docView,"dataForEPS") || !nr_has(g_docView,"dataForTIFF")) {
        fail("native-complete-corridor-view-missing"); return;
    }
    g_viewValid=1;
    trace("Complete export view=%p class=%s",g_docView,nr_class_name(g_docView));
    g_stage = "native-saveTo-EPS";
    g_eps = SAVE(g_document,SEND1(nr_class("NSString"),"stringWithCString:",EPS_A),"dataForEPS") != 0;
    trace("Original saveTo:using:dataForEPS returned=%d bytes=%llu",g_eps,file_size(EPS_A));
    if (!g_eps || !file_size(EPS_A)) { fail("native-eps-export-failed"); return; }
    g_stage = "native-saveTo-TIFF";
    g_tiff = SAVE(g_document,SEND1(nr_class("NSString"),"stringWithCString:",TIFF_A),"dataForTIFF") != 0;
    trace("Original saveTo:using:dataForTIFF returned=%d bytes=%llu",g_tiff,file_size(TIFF_A));
    if (!g_tiff || !file_size(TIFF_A)) { fail("native-tiff-export-failed"); return; }
    g_stage = "complete";
    receipt(1,"native-eps-and-tiff-written");
    trace("SUCCESS. Native application and document remain open.");
    InterlockedExchange(&g_terminal,1); InterlockedExchange(&g_enabled,0);
    ot_ui_dispatch_detach(); SetEvent(g_ready);
     
}
static void guarded(OtExceptionAction action)
{
    OtException error; int result;
    __try {
        result = ot_exception_invoke(action,NULL,&error);
        if (result == 0) { trace("OpenStep exception code=%u exception=%p",error.code,error.exception); fail("native-openstep-exception"); }
        else if (result < 0) fail("native-exception-handler-unavailable");
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        trace("Windows SEH exception code=0x%08lx",GetExceptionCode()); fail("native-windows-exception");
    }
}
static int native_message(MSG *message)
{
    DWORD current=GetCurrentThreadId(),pid,owner;
    HWND window = message && message->hwnd ? GetAncestor(message->hwnd,GA_ROOT) : GetActiveWindow();
    Id app,delegate,menu;
    if (!g_enabled || g_terminal) return 0;
    if (!g_uiThread) {
        if (!window || !IsWindowVisible(window)) return 0;
        owner=GetWindowThreadProcessId(window,&pid);
        if (pid != GetCurrentProcessId() || owner != current) return 0;
        g_uiThread=current; trace("Confirmed native host message thread=%lu",current);
    }
    if (current != g_uiThread) return 0;
    if (!g_bound) { if (!nr_bind()) return 0; g_bound=1; }
    if (!nr_ready(nr_class("NSApplication")) || !nr_ready(nr_class("NSString")) ||
        !nr_ready(nr_class("OTController")) || !nr_ready(nr_class("OTCorridorDocument")) ||
        !nr_ready(nr_class("OTCorridorDocView"))) return 0;
    app=nr_app(); if (!nr_has(app,"delegate") || !nr_has(app,"mainMenu")) return 0;
    delegate=SEND0(app,"delegate"); menu=SEND0(app,"mainMenu");
    if (!delegate || !menu) return 0;
    if (!g_readyTick) { g_readyTick=GetTickCount(); trace("Native application/delegate/mainMenu ready"); return 0; }
    if (GetTickCount()-g_readyTick < 1500) return 0;
    if (!g_loaded) {
        g_stage="native-method-ABI-validation";
        if (!verify_methods()) { fail("native-method-IMP-or-ABI-mismatch"); return 0; }
        guarded(load_action);
    } else if (GetTickCount()-g_loadedTick >= 200) guarded(export_action);
    return 0;  
}
static DWORD WINAPI bootstrap(void *module)
{
    wchar_t path[1100],name[128]; HANDLE owned; DWORD n; int i;
    (void)module;
    swprintf_s(name,128,READY_EVENT,GetCurrentProcessId()); g_ready=CreateEventW(NULL,TRUE,FALSE,name);
    swprintf_s(name,128,FAILED_EVENT,GetCurrentProcessId()); g_failed=CreateEventW(NULL,TRUE,FALSE,name);
    g_trace=fopen(EXPORT_ROOT_A "/native-trace.log","ab");
    swprintf_s(name,128,OWNED_EVENT,GetCurrentProcessId()); owned=OpenEventW(SYNCHRONIZE,FALSE,name);
    if (!owned || WaitForSingleObject(owned,0) != WAIT_OBJECT_0) { if(owned)CloseHandle(owned); fail("no-owned-child-launch-authorization-event"); return 0; }
    CloseHandle(owned);
    if(!verify_software_authorization()) {
        fail("full-software-authorization-record-missing-or-changed"); return 0;
    }
    n=GetModuleFileNameW(NULL,path,1100);
    if (!n || n>=1100 || _wcsicmp(path,ORIGINAL_EXE_W) || !verify_sha256(path,ORIGINAL_SHA) || !verify_sha256(CORRIDOR_W,CORRIDOR_SHA)) {
        fail("exact-original-or-corridor-SHA-guard-failed"); return 0;
    }
    trace("Exact original EXE and corridor SHA verified; PID=%lu",GetCurrentProcessId());
    for(i=0;i<1200;++i) {
        HMODULE appkit=GetModuleHandleW(L"AppKit.dll"), foundation=GetModuleHandleW(L"Foundation.dll");
        if(appkit && foundation) {
            if(!ot_ui_dispatch_attach(appkit,0,native_message,fail) || !ot_ui_dispatch_attach(foundation,0,native_message,fail)) {
                fail("named-host-message-import-binding-failed"); return 0;
            }
            trace("Bound native pump imports; all Objective-C calls deferred to actual host thread");
            InterlockedExchange(&g_enabled,1); return 0;
        }
        Sleep(50);
    }
    fail("native-message-modules-timeout"); return 0;
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID reserved)
{
    (void)reserved;
    if(reason==DLL_PROCESS_ATTACH) {
        HANDLE thread; DisableThreadLibraryCalls(module);
        thread=CreateThread(NULL,0,bootstrap,module,0,NULL); if(thread)CloseHandle(thread);
    }
    return TRUE;
}
