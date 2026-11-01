#ifndef OT_UI_DISPATCH_H
#define OT_UI_DISPATCH_H
#include <windows.h>
 




int ot_ui_dispatch_attach(HMODULE module, DWORD thread,
                          int (*observe)(MSG *), void (*failed)(const char *));
void ot_ui_dispatch_detach(void);
#endif
