 

#include "ui_dispatch.h"
#include <string.h>
#define MAX_SLOTS 12
typedef struct { ULONG_PTR *slot, previous, replacement; } Slot;
static Slot g_slots[MAX_SLOTS];
static int g_slotN;
static __declspec(thread) int g_notifying;
static DWORD g_thread;
static int (*g_observe)(MSG *);
static void (*g_failed)(const char *);
static BOOL (WINAPI *g_peek)(LPMSG, HWND, UINT, UINT, UINT);
static LRESULT (WINAPI *g_dispatch)(const MSG *);

static int notify(MSG *message)
{
    int consumed = 0;
    if (!g_observe || g_notifying || (g_thread && GetCurrentThreadId() != g_thread)) return 0;
    g_notifying = 1;
    __try { consumed = g_observe(message); }
    __except (EXCEPTION_EXECUTE_HANDLER) { g_failed("native message observer failed"); }
    g_notifying = 0;
    return consumed;
}
static BOOL WINAPI peek_bridge(LPMSG message, HWND window, UINT first, UINT last, UINT flags)
{
    BOOL result = g_peek(message, window, first, last, flags);
    if (flags & PM_REMOVE) {
        if (notify(result ? message : NULL) && result) {
            message->message = WM_NULL; message->wParam = 0; message->lParam = 0;
        }
    }
    return result;
}
static LRESULT WINAPI dispatch_bridge(const MSG *message)
{
    MSG local = *message;
    if (notify(&local)) return 0;
    return g_dispatch(&local);
}
static int patch_slot(ULONG_PTR *slot, FARPROC replacement)
{
    DWORD previousProtection, ignored;
    if (*slot == (ULONG_PTR)replacement) return 1;
    if (g_slotN == MAX_SLOTS || !VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE, &previousProtection)) return 0;
    g_slots[g_slotN].slot = slot;
    g_slots[g_slotN].replacement = (ULONG_PTR)replacement;
    g_slots[g_slotN].previous = (ULONG_PTR)InterlockedExchangePointer((PVOID volatile *)slot, (PVOID)replacement);
    ++g_slotN;
    VirtualProtect(slot, sizeof(*slot), previousProtection, &ignored);
    return 1;
}
int ot_ui_dispatch_attach(HMODULE module, DWORD thread,
                          int (*observe)(MSG *), void (*failed)(const char *))
{
    BYTE *base = (BYTE *)module;
    IMAGE_DOS_HEADER *dos;
    IMAGE_NT_HEADERS *nt;
    IMAGE_IMPORT_DESCRIPTOR *imports;
    HMODULE user32 = GetModuleHandleW(L"user32.dll");
    int hooked = 0;
    if (!module || !observe || !failed || !user32) return 0;
    if (g_slotN && (g_observe != observe || g_failed != failed || g_thread != thread)) return 0;
    g_observe = observe; g_failed = failed; g_thread = thread;
    g_peek = (BOOL (WINAPI *)(LPMSG, HWND, UINT, UINT, UINT))GetProcAddress(user32, "PeekMessageA");
    g_dispatch = (LRESULT (WINAPI *)(const MSG *))GetProcAddress(user32, "DispatchMessageA");
    if (!g_peek || !g_dispatch) return 0;
    dos = (IMAGE_DOS_HEADER *)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return 0;
    nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC ||
        !nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress) return 0;
    imports = (IMAGE_IMPORT_DESCRIPTOR *)(base + nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    for (; imports->Name; ++imports) {
        IMAGE_THUNK_DATA *names, *dest;
        if (_stricmp((const char *)base + imports->Name, "user32.dll") || !imports->OriginalFirstThunk) continue;
        names = (IMAGE_THUNK_DATA *)(base + imports->OriginalFirstThunk);
        dest = (IMAGE_THUNK_DATA *)(base + imports->FirstThunk);
        for (; names->u1.AddressOfData; ++names, ++dest) {
            IMAGE_IMPORT_BY_NAME *entry;
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
            entry = (IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData);
            if (!strcmp((char *)entry->Name, "PeekMessageA"))
                hooked += patch_slot((ULONG_PTR *)&dest->u1.Function, (FARPROC)peek_bridge);
            else if (!strcmp((char *)entry->Name, "DispatchMessageA"))
                hooked += patch_slot((ULONG_PTR *)&dest->u1.Function, (FARPROC)dispatch_bridge);
        }
    }
    return hooked == 2;
}
void ot_ui_dispatch_detach(void)
{
    while (g_slotN) {
        Slot *slot = &g_slots[--g_slotN]; DWORD old, ignored;
        if (*slot->slot != slot->replacement) continue;
        if (VirtualProtect(slot->slot, sizeof(*slot->slot), PAGE_READWRITE, &old)) {
            InterlockedExchangePointer((PVOID volatile *)slot->slot, (PVOID)slot->previous);
            VirtualProtect(slot->slot, sizeof(*slot->slot), old, &ignored);
        }
    }
    g_observe = NULL;
}
