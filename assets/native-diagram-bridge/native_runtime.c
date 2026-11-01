 

#include "native_runtime.h"
#include <string.h>
void *nr_msg;
static Class (__cdecl *lookup)(const char *);
static Sel (__cdecl *register_sel)(const char *);
static Method *(__cdecl *instance_method)(Class,Sel);
static Method *(__cdecl *class_method)(Class,Sel);
static const char *(__cdecl *object_name)(Id);

int nr_bind(void)
{
    HMODULE runtime = GetModuleHandleW(L"nextpdo.dll");
    if (!runtime) return 0;
    nr_msg = (void *)GetProcAddress(runtime,"objc_msgSend");
    lookup = (Class (__cdecl *)(const char *))GetProcAddress(runtime,"objc_lookUpClass");
    register_sel = (Sel (__cdecl *)(const char *))GetProcAddress(runtime,"sel_registerName");
    instance_method = (Method *(__cdecl *)(Class,Sel))GetProcAddress(runtime,"class_getInstanceMethod");
    class_method = (Method *(__cdecl *)(Class,Sel))GetProcAddress(runtime,"class_getClassMethod");
    object_name = (const char *(__cdecl *)(Id))GetProcAddress(runtime,"object_getClassName");
    return nr_msg && lookup && register_sel && instance_method && class_method && object_name;
}
Class nr_class(const char *name) { return lookup ? lookup(name) : NULL; }
Sel nr_sel(const char *name) { return register_sel ? register_sel(name) : NULL; }
int nr_ready(Class cls)
{
    int depth = 0, ready = 0;
    if (!cls || !lookup) return 0;
    __try {
        while (cls && depth++ < 128) {
            const char *name = *(const char **)((char *)cls + 8);
            unsigned info = *(unsigned *)((char *)cls + 16);
            Class registered;
            if (!(info & 0x100) || !(info & 3) || !name || !*(void **)((char *)cls + 28)) __leave;
            registered = lookup(name);
            if (!registered) __leave;
            if (info & 2) registered = *(Class *)registered;
            if (registered != cls) __leave;
            cls = *(Class *)((char *)cls + 4);
        }
        ready = cls == NULL;
    } __except (EXCEPTION_EXECUTE_HANDLER) { ready = 0; }
    return ready;
}
int nr_has(Id obj, const char *name)
{
    return obj && nr_ready(*(Class *)obj) && instance_method(*(Class *)obj,nr_sel(name)) != NULL;
}
int nr_has_class(const char *name, const char *selector)
{
    Class cls = nr_class(name);
    return cls && nr_ready(*(Class *)cls) && class_method(cls,nr_sel(selector)) != NULL;
}
int nr_check(const char *name, const char *selector, const char *types, unsigned originalVA)
{
    Class cls = nr_class(name); Method *method;
    if (!nr_ready(cls)) return 0;
    method = instance_method(cls,nr_sel(selector));
    return method && method->types && !strcmp(method->types,types) &&
        method->imp == (BYTE *)GetModuleHandleW(NULL) + originalVA - 0x400000;
}
Id nr_app(void)
{
    HMODULE module = GetModuleHandleW(L"AppKit.dll");
    Id *slot = module ? (Id *)GetProcAddress(module,"NSApp") : NULL;
    return slot ? *slot : NULL;
}
const char *nr_class_name(Id obj) { return obj && object_name ? object_name(obj) : "nil"; }
