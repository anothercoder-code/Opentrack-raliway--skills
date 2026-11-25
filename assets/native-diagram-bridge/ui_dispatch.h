#ifndef OT_UI_DISPATCH_H
#define OT_UI_DISPATCH_H
#include <windows.h>
/* Patch a loaded host module's PeekMessageA / DispatchMessageA imports.
 * Observe runs on the caller thread. thread=0 lets the callback select the real
 * UI thread from native message ownership. Nonzero restricts it to that thread.
 * Return 1 from observe to consume a removed message before host processing.
 * observe(NULL) means an empty PM_REMOVE poll. Does not create a window. */
int ot_ui_dispatch_attach(HMODULE module, DWORD thread,
                          int (*observe)(MSG *), void (*failed)(const char *));
void ot_ui_dispatch_detach(void);
#endif
