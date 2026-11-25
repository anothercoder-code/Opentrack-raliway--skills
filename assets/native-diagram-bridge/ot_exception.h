/* Classic OpenStep exceptions use MSVCRT longjmp, not Windows SEH. */
#ifndef OT_EXCEPTION_H
#define OT_EXCEPTION_H

typedef void (*OtExceptionAction)(void *context);
typedef struct {
    unsigned code;
    void *exception; /* Borrowed NSException, only for code 100000. */
    void *data1;
    void *data2;
} OtException;

/* Requires the host's nextpdo.dll and MSVCRT.dll to be loaded. No UI calls. */
int ot_exception_init(void);
/* 1: callback returned; 0: caught an OpenStep exception; -1: unavailable/invalid.
 * The callback runs inside the actual legacy _setjmp frame. Windows SEH is
 * propagated after removing our OpenStep handler. Nested calls are supported.
 * C resources owned by the callback still need explicit cleanup by its caller;
 * a legacy longjmp does not execute callback __finally blocks reliably. */
int ot_exception_invoke(OtExceptionAction action, void *context, OtException *error);

/* Scope cleanup without catching or redirecting the host's OpenStep exception.
 * Uses the runtime's native alternative-handler callbacks, not setjmp.
 * cleanup(context) runs exactly once on normal return, OpenStep unwinding or
 * Windows SEH. It MUST only restore C state and MUST NOT throw or message ObjC.
 * Returns 1 normally; -1 means unavailable/invalid and neither callback ran.
 * An exception continues to the host's existing handler after cleanup. */
int ot_exception_cleanup(OtExceptionAction action, void *context, OtExceptionAction cleanup);

#endif
