#include "ot_exception.h"
#include <windows.h>
#include <stddef.h>
#include <string.h>

 


typedef struct {
    unsigned jump[16];
    void *previous;
    unsigned code;
    void *data1;
    void *data2;
} LegacyHandler;
typedef char HandlerSizeIs80[(sizeof(LegacyHandler) == 80) ? 1 : -1];
typedef char HandlerCodeIs68[(offsetof(LegacyHandler, code) == 68) ? 1 : -1];

typedef void (__cdecl *HandlerFn)(LegacyHandler *);
typedef int (__cdecl *SetjmpFn)(unsigned *);
static HandlerFn g_add, g_remove;
static SetjmpFn g_setjmp;
typedef void (__cdecl *AltCallback)(void *, unsigned, void *, void *);
typedef void *(__cdecl *AltAddFn)(AltCallback, void *);
typedef void (__cdecl *AltRemoveFn)(void *);
static AltAddFn g_addAlt;
static AltRemoveFn g_removeAlt;

int ot_exception_init(void)
{
    HMODULE runtime, crt;
    HandlerFn add, remove;
    SetjmpFn save;
    if (g_add && g_remove && g_setjmp) return 1;
    runtime = GetModuleHandleW(L"nextpdo.dll");
    crt = GetModuleHandleW(L"msvcrt.dll");
    if (!runtime || !crt) return 0;
    add = (HandlerFn)GetProcAddress(runtime, "_NXAddHandler");
    remove = (HandlerFn)GetProcAddress(runtime, "_NXRemoveHandler");
    save = (SetjmpFn)GetProcAddress(crt, "_setjmp");
    if (!add || !remove || !save) return 0;
    g_add = add; g_remove = remove; g_setjmp = save;
    return 1;
}

typedef struct {
    LegacyHandler handler;
    volatile int registered;
    OtExceptionAction action;
    void *context;
    OtException *error;
} Invocation;

 

__declspec(noinline) static int invoke_legacy(Invocation *call)
{
    g_add(&call->handler);
    call->registered = 1;
    if (!g_setjmp(call->handler.jump)) {
        call->action(call->context);
        g_remove(&call->handler);
        call->registered = 0;
        return 1;
    }
     
    call->registered = 0;
    if (call->error) {
        call->error->code = call->handler.code;
        call->error->data1 = call->handler.data1;
        call->error->data2 = call->handler.data2;
        call->error->exception = call->handler.code == 100000 ? call->handler.data1 : NULL;
    }
    return 0;
}

int ot_exception_invoke(OtExceptionAction action, void *context, OtException *error)
{
    Invocation call;
    int result = -1;
    if (error) memset(error, 0, sizeof(*error));
    if (!action || !ot_exception_init()) return -1;
    memset(&call, 0, sizeof(call));
    call.action = action; call.context = context; call.error = error;
    __try { result = invoke_legacy(&call); }
    __finally {
         
        if (call.registered) { g_remove(&call.handler); call.registered = 0; }
    }
    return result;
}

typedef struct {
    void *token;
    volatile int registered, cleaned;
    OtExceptionAction cleanup;
    void *context;
} CleanupInvocation;

static void cleanup_once(CleanupInvocation *call)
{
    if (call->cleaned) return;
    call->cleaned = 1;
    call->cleanup(call->context);
}

static void __cdecl cleanup_alt(void *context, unsigned code, void *data1, void *data2)
{
    CleanupInvocation *call = context;
    (void)code; (void)data1; (void)data2;
     

    call->registered = 0;
    cleanup_once(call);
}

int ot_exception_cleanup(OtExceptionAction action, void *context, OtExceptionAction cleanup)
{
    HMODULE runtime;
    CleanupInvocation call;
    if (!action || !cleanup) return -1;
    if (!g_addAlt || !g_removeAlt) {
        AltAddFn add; AltRemoveFn remove;
        runtime = GetModuleHandleW(L"nextpdo.dll");
        if (!runtime) return -1;
        add = (AltAddFn)GetProcAddress(runtime, "_NXAddAltHandler");
        remove = (AltRemoveFn)GetProcAddress(runtime, "_NXRemoveAltHandler");
        if (!add || !remove) return -1;
        g_addAlt = add; g_removeAlt = remove;
    }
    memset(&call, 0, sizeof(call));
    call.cleanup = cleanup; call.context = context;
    call.token = g_addAlt(cleanup_alt, &call);
    if (!call.token) return -1;
    call.registered = 1;
    __try { action(context); }
    __finally {
        __try {
            if (call.registered) {
                call.registered = 0;
                 

                g_removeAlt(call.token);
            }
        }
        __finally { cleanup_once(&call); }
    }
    return 1;
}
