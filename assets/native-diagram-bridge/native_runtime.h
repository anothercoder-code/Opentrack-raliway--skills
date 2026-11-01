#ifndef NATIVE_EXPORT_RUNTIME_H
#define NATIVE_EXPORT_RUNTIME_H
#include <windows.h>
typedef void *Id;
typedef void *Class;
typedef void *Sel;
typedef struct { Sel name; const char *types; void *imp; } Method;
extern void *nr_msg;
int nr_bind(void);
int nr_ready(Class cls);
Class nr_class(const char *name);
Sel nr_sel(const char *name);
int nr_has(Id obj, const char *name);
int nr_has_class(const char *name, const char *selector);
int nr_check(const char *className, const char *selector, const char *types, unsigned originalVA);
Id nr_app(void);
const char *nr_class_name(Id obj);
#define SEND0(o,s) ((Id (__cdecl *)(Id,Sel))nr_msg)((o),nr_sel(s))
#define SEND1(o,s,a) ((Id (__cdecl *)(Id,Sel,Id))nr_msg)((o),nr_sel(s),(Id)(a))
#define UINT0(o,s) ((unsigned (__cdecl *)(Id,Sel))nr_msg)((o),nr_sel(s))
#define INT0(o,s) ((int (__cdecl *)(Id,Sel))nr_msg)((o),nr_sel(s))
#define AT(o,i) ((Id (__cdecl *)(Id,Sel,unsigned))nr_msg)((o),nr_sel("objectAtIndex:"),(i))
#define BOOL0(o,s) ((signed char (__cdecl *)(Id,Sel))nr_msg)((o),nr_sel(s))
#define BOOL1(o,s,a) ((signed char (__cdecl *)(Id,Sel,Id))nr_msg)((o),nr_sel(s),(Id)(a))
#define FLOAT0(o,s) ((float (__cdecl *)(Id,Sel))nr_msg)((o),nr_sel(s))
#define SAVE(o,p,s) ((signed char (__cdecl *)(Id,Sel,Id,Sel))nr_msg)((o),nr_sel("saveTo:using:"),(p),nr_sel(s))
#endif
