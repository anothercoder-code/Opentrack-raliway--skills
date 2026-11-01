 

#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "guard_policy.h"
#include "fingerprint.h"
#include "contract_types.h"
#include "contract.inc"
typedef void *Id;
typedef void *Sel;
typedef void *Class;
typedef void (__cdecl *Imp)(void);
typedef struct { Sel name; const char *types; Imp imp; } Method;
typedef struct MethodList { struct MethodList *next; int count; Method list[1]; } MethodList;
typedef struct { const char *name,*types; int offset; } Ivar;
typedef char ig_pointer_width_must_be_32[(sizeof(void *)==4)?1:-1];
typedef char ig_method_size_must_be_12[(sizeof(Method)==12)?1:-1];
static Id (__cdecl *lookup)(const char *);
static Sel (__cdecl *selector)(const char *);
static Method *(__cdecl *get_method)(Class,Sel);
static Method *(__cdecl *get_class_method)(Class,Sel);
static Ivar *(__cdecl *get_ivar)(Class,const char *);
static void (__cdecl *add_methods)(Class,MethodList *);
static void (__cdecl *flush)(Class);
static void (__cdecl *objc_send)(void);
static Imp originals[IG_METHOD_COUNT], inherited_dealloc;
static Method *slots[IG_METHOD_COUNT];
static MethodList local_dealloc;
static IgWorld world;
static DWORD ui_thread;
static HMODULE self_module;
static int status, bound, fingerprinted;
static char last_error[192];
#define S(s) selector(s)
#define M0(o,s) ((Id (__cdecl *)(Id,Sel))objc_send)((o),S(s))
#define M1(o,s,a) ((Id (__cdecl *)(Id,Sel,Id))objc_send)((o),S(s),(a))
#define N(o) ((unsigned (__cdecl *)(Id,Sel))objc_send)((o),S("count"))
#define AT(o,i) ((Id (__cdecl *)(Id,Sel,unsigned))objc_send)((o),S("objectAtIndex:"),(i))
#define V0(o,s) ((void (__cdecl *)(Id,Sel))objc_send)((o),S(s))
#define FIELD(o,n) (*(Id *)((BYTE *)(o)+(n)))
#define ORIG1(i,o,s,a) ((void (__cdecl *)(Id,Sel,Id))originals[i])((o),(s),(a))
#define ORIG0(i,o,s) ((void (__cdecl *)(Id,Sel))originals[i])((o),(s))

static void signal_status(const WCHAR *kind)
{
    WCHAR token[40], name[180];
    HANDLE event;
    unsigned i;
    DWORD n = GetEnvironmentVariableW(L"OTIG_SESSION",token,40);
    if (n != 32) return;
    for (i=0;i<32;++i) if (!((token[i]>=L'0'&&token[i]<=L'9')||(token[i]>=L'a'&&token[i]<=L'f'))) return;
    _snwprintf_s(name,180,_TRUNCATE,L"Local\\OpenTrack.InspectorGuard.%s.%lu.%s",kind,GetCurrentProcessId(),token);
    event = OpenEventW(EVENT_MODIFY_STATE,FALSE,name);
    if (event) { SetEvent(event); CloseHandle(event); }
}
static void fail(const char *why)
{
    status = -1;
    strncpy_s(last_error,sizeof(last_error),why,_TRUNCATE);
    OutputDebugStringA("OpenTrack Inspector Guard refused activation: ");
    OutputDebugStringA(last_error); OutputDebugStringA("\n");
    signal_status(L"Failed");
}
static void retain_object(void *unused, IgObject o) { (void)unused; (void)M0(o,"retain"); }
static void release_object(void *unused, IgObject o) { (void)unused; V0(o,"release"); }
static void clear_native(void *unused, IgObject owner)
{
    Id list;
    (void)unused;
    FIELD(owner,996) = NULL;
    list = FIELD(owner,1000);
    if (list) V0(list,"removeAllObjects");
}
static int array_has(Id array, Id candidate)
{
    unsigned n=N(array), i;
    if (n>IG_MAX_PAIRS) return 0;
    for(i=0;i<n;++i) if(AT(array,i)==candidate) return 1;
    return 0;
}
static int tree_contains(IgLease *lease,Id current,Id candidate,unsigned depth,unsigned *visited)
{
    Id children; unsigned i,n;
    if(!current || depth>128 || ++*visited>8192 || !ig_pin(&world,lease,current)) return 0;
    if(current==candidate) return 1;
    children=M0(current,"subviews");
    if(!ig_pin(&world,lease,children)) return 0;
    n=N(children); if(n>IG_MAX_PAIRS) return 0;
    for(i=0;i<n;++i) if(tree_contains(lease,AT(children,i),candidate,depth+1,visited)) return 1;
    return 0;
}
 

static IgLease *capture_graph(void)
{
    IgLease *lease = ig_lease_new(&world);
    Id documents,windows,application;
    unsigned d,n;
    if (!lease) return NULL;
    application=M0(lookup("NSApplication"),"sharedApplication");
    windows=M0(application,"windows");
    if(!windows || N(windows)>256 || !ig_pin(&world,lease,windows)) goto bad;
    documents = M0(lookup("OTDocument"),"documentList");
    if(!documents) return lease;
    if(!ig_pin(&world,lease,documents)) goto bad;
    n=N(documents);
    if(n>64) goto bad;
    for(d=0;d<n;++d) {
        Id doc=AT(documents,d), dv, views, models,window;
        unsigned i,count,visited=0;
        if(!doc || !ig_pin(&world,lease,doc)) goto bad;
        window=FIELD(doc,24);
         

        if(!window || !array_has(windows,window)) continue;
        if(!ig_pin(&world,lease,window)) goto bad;
        dv=M0(doc,"documentView");
        if(!dv) continue;
        if(!tree_contains(lease,M0(window,"contentView"),dv,0,&visited)) goto bad;
        if(*(Class *)dv!=lookup("OTDocView") || !ig_pin(&world,lease,dv) || FIELD(dv,80)!=doc) goto bad;
        models=FIELD(doc,4); views=FIELD(dv,84);
        if(!ig_pin(&world,lease,models)||!ig_pin(&world,lease,views)) goto bad;
        count=N(views);
        if(count>IG_MAX_PAIRS || N(models)>IG_MAX_PAIRS) goto bad;
        for(i=0;i<count;++i) {
            IgPair pair;
            Id view=AT(views,i), model;
            if(!view || !ig_pin(&world,lease,view)) goto bad;
            model=FIELD(view,80);
            if(!model) continue;
            if(!array_has(models,model)) goto bad;
            if(!ig_pin(&world,lease,model) || FIELD(model,8)!=view) goto bad;
            pair.doc=doc; pair.docview=dv; pair.view=view; pair.model=model;
            if(!ig_add_pair(&world,lease,pair)) goto bad;
        }
    }
    return lease;
bad:
    ig_drop(&world,lease);
    return NULL;
}
static IgLease *capture_selection(Id owner, const IgLease *graph)
{
    Id model=FIELD(owner,996), list=FIELD(owner,1000);
    IgLease *chosen=ig_lease_new(&world);
    const IgPair *pair;
    unsigned i,n=N(list);
    if(!chosen || !graph || graph->poisoned || n>IG_MAX_PAIRS) goto bad;
    if(model) {
        pair=ig_find_model(graph,model);
        if(!pair || !ig_add_pair(&world,chosen,*pair)) goto bad;
    }
    for(i=0;i<n;++i) {
        pair=ig_find_view(graph,AT(list,i));
        if(!pair || !ig_add_pair(&world,chosen,*pair)) goto bad;
    }
    return chosen;
bad:
    ig_drop(&world,chosen);
    return NULL;
}
static int on_ui(void) { return status==1 && ui_thread==GetCurrentThreadId() && !world.invalidating; }
static int same_owner(const IgState *state,IgTicket ticket)
{
    return state && state->owner==ticket.owner && state->generation==ticket.generation;
}
static void refresh_tables(Id owner,IgState *state,IgTicket ticket)
{
    static const int offsets[]=IG_TABLE_OFFSETS;
    IgLease *lease;
    Id windows,panel;
    unsigned i;
    if(!same_owner(state,ticket) || state->depth || state->refreshing || ticket.epoch!=world.epoch) return;
    state->refreshing=1;
    lease=ig_lease_new(&world);
    if(!lease) { state->refreshing=0; return; }
    windows=M0(M0(lookup("NSApplication"),"sharedApplication"),"windows");
    panel=FIELD(owner,984);
    if(!ig_pin(&world,lease,windows) || !panel || !array_has(windows,panel) || !ig_pin(&world,lease,panel)) goto done;
    for(i=0;i<sizeof(offsets)/sizeof(offsets[0]);++i) {
        Id table;
        unsigned visited=0;
        if(!same_owner(state,ticket) || world.epoch!=ticket.epoch) break;
        if(FIELD(owner,984)!=panel) break;
        table=FIELD(owner,offsets[i]);
        if(!panel) break;
        if(table && tree_contains(lease,M0(panel,"contentView"),table,0,&visited)) V0(table,"reloadData");
    }
done:
    ig_drop(&world,lease);
    if(same_owner(state,ticket)) state->refreshing=0;
}
static void operation(unsigned index, Id owner, Sel cmd, Id argument)
{
    IgState *state;
    IgTicket ticket;
    IgLease *graph,*chosen=NULL;
    if(!on_ui()) return;
    state=ig_state(&world,owner);
    if(!state) { clear_native(NULL,owner); return; }
    (void)M0(owner,"retain");
    ticket=ig_begin(&world,state);
    if(!same_owner(state,ticket) || ticket.epoch!=world.epoch) goto done;
     
    if(index==1 && !FIELD(owner,984)) goto done;
    graph=capture_graph();
    if(!graph) goto done;
    if(!same_owner(state,ticket) || ticket.epoch!=world.epoch || graph->poisoned) { ig_drop(&world,graph); goto done; }
    if(index!=0 && argument && !ig_find_view(graph,argument)) { ig_drop(&world,graph); goto done; }
    ORIG1(index,owner,cmd,argument);
    if(same_owner(state,ticket) && ticket.epoch==world.epoch && !graph->poisoned) chosen=capture_selection(owner,graph);
    if(!chosen && same_owner(state,ticket)) clear_native(NULL,owner);
    ig_drop(&world,graph);
done:
    if(ig_finish(&world,state,ticket,chosen) && chosen) refresh_tables(owner,state,ticket);
    if(same_owner(state,ticket)) V0(owner,"release");
}
static void __cdecl inspect(Id o,Sel s,Id a) { operation(0,o,s,a); }
static void __cdecl update(Id o,Sel s,Id a) { operation(1,o,s,a); }
static void __cdecl update_signal(Id o,Sel s,Id a) { operation(2,o,s,a); }
static char __cdecl inspector_close(Id o,Sel s,Id a)
{
    char result;
    IgState *state;
    IgTicket ticket;
    if(!on_ui()) return 1;
    state=ig_state(&world,o);
    if(!state) { clear_native(NULL,o); return 1; }
    ticket.owner=o; ticket.generation=state->generation; ticket.epoch=world.epoch;
    (void)M0(o,"retain");
    ++world.epoch;
    if(state) { ++state->depth; ig_clear(&world,state); }
    if(!same_owner(state,ticket)) return 1;
    result=((char (__cdecl *)(Id,Sel,Id))originals[3])(o,s,a);
    if(same_owner(state,ticket)) ig_clear(&world,state);
    if(same_owner(state,ticket)) { if(state->depth) --state->depth; V0(o,"release"); }
    return result;
}
static IgLease *table_begin(Id owner, IgState **state_out, IgTicket *ticket)
{
    IgLease *graph,*chosen;
    IgState *state;
    if(!on_ui()) return NULL;
    state=ig_state(&world,owner);
    if(!state || state->depth) return NULL;
    ticket->epoch=world.epoch; ticket->owner=owner; ticket->generation=state->generation;
    (void)M0(owner,"retain");
    graph=capture_graph();
    if(!graph || !same_owner(state,*ticket) || ticket->epoch!=world.epoch) {
        ig_drop(&world,graph);
        if(same_owner(state,*ticket)) ig_clear(&world,state);
        if(same_owner(state,*ticket)) V0(owner,"release");
        return NULL;
    }
    chosen=capture_selection(owner,graph);
    if(!chosen) {
        ig_drop(&world,graph);
        if(same_owner(state,*ticket)) ig_clear(&world,state);
        if(same_owner(state,*ticket)) V0(owner,"release");
        return NULL;
    }
    ++state->depth;
    {
        IgLease *old=state->selection;
        state->selection=chosen;
        ig_drop(&world,old);
    }
    if(!same_owner(state,*ticket) || ticket->epoch!=world.epoch || graph->poisoned ||
       !state->selection || state->selection->poisoned) {
        ig_drop(&world,graph);
        if(same_owner(state,*ticket)) ig_clear(&world,state);
        if(same_owner(state,*ticket)) { if(state->depth) --state->depth; V0(owner,"release"); }
        return NULL;
    }
    *state_out=state;
    return graph;
}
static void table_end(Id owner, IgState *state, IgTicket ticket, IgLease *graph)
{
    IgLease *chosen=NULL;
    if(same_owner(state,ticket) && ticket.epoch==world.epoch && !graph->poisoned) chosen=capture_selection(owner,graph);
    if(!chosen && same_owner(state,ticket)) clear_native(NULL,owner);
    ig_drop(&world,graph);
    (void)ig_finish(&world,state,ticket,chosen);
    if(same_owner(state,ticket)) V0(owner,"release");
}
static Id __cdecl table_value(Id o,Sel s,Id table,Id column,int row)
{
    IgState *state=NULL;
    IgTicket ticket;
    IgLease *graph=table_begin(o,&state,&ticket);
    Id result;
    int rows;
    if(!graph || row<0) { if(graph) table_end(o,state,ticket,graph); return NULL; }
    rows=((int (__cdecl *)(Id,Sel,Id))originals[5])(o,S("numberOfRowsInTableView:"),table);
    if(row>=rows || !same_owner(state,ticket) || ticket.epoch!=world.epoch || graph->poisoned) {
        table_end(o,state,ticket,graph); return NULL;
    }
    result=((Id (__cdecl *)(Id,Sel,Id,Id,int))originals[4])(o,s,table,column,row);
    if(!same_owner(state,ticket) || ticket.epoch!=world.epoch || graph->poisoned) result=NULL;
    if(result) (void)M0(result,"retain");
    table_end(o,state,ticket,graph);
    if(result) (void)M0(result,"autorelease");
    return result;
}
static int __cdecl table_rows(Id o,Sel s,Id table)
{
    IgState *state=NULL;
    IgTicket ticket;
    IgLease *graph=table_begin(o,&state,&ticket);
    int result;
    if(!graph) return 0;
    result=((int (__cdecl *)(Id,Sel,Id))originals[5])(o,s,table);
    if(!same_owner(state,ticket) || ticket.epoch!=world.epoch || graph->poisoned) result=0;
    table_end(o,state,ticket,graph);
    return result;
}
static char __cdecl doc_close(Id o,Sel s,Id doc,char ask)
{
    char result;
    if(!on_ui()) return 0;
    ig_invalidate(&world,NULL);
    result=((char (__cdecl *)(Id,Sel,Id,char))originals[6])(o,s,doc,ask);
    ig_invalidate(&world,NULL);
    return result;
}
static void __cdecl delete_view(Id o,Sel s,Id view)
{
    if(!on_ui()) return;
    ig_invalidate(&world,NULL);
    ORIG1(7,o,s,view);
    ig_invalidate(&world,NULL);
}
static void __cdecl docview_close(Id o,Sel s,Id notification)
{
    if(GetCurrentThreadId()!=ui_thread) { fail("Unsupported non-UI document lifecycle"); TerminateProcess(GetCurrentProcess(),92); return; }
    ig_invalidate(&world,NULL); ORIG1(8,o,s,notification); ig_invalidate(&world,NULL);
}
static void destroy(unsigned index,Id o,Sel s)
{
    if(GetCurrentThreadId()!=ui_thread) { fail("Unsupported non-UI object lifecycle"); TerminateProcess(GetCurrentProcess(),92); return; }
    ig_invalidate(&world,o);
    ORIG0(index,o,s);
}
#define DECL_DESTROY(i) static void __cdecl destroy_##i(Id o,Sel s) { destroy(i,o,s); }
DECL_DESTROY(9) DECL_DESTROY(10) DECL_DESTROY(11) DECL_DESTROY(12)
IG_EXTRA_DEALLOC_LIST(DECL_DESTROY)
static void __cdecl inspector_destroy(Id o,Sel s)
{
    if(GetCurrentThreadId()!=ui_thread) { fail("Unsupported non-UI Inspector lifecycle"); TerminateProcess(GetCurrentProcess(),92); return; }
    ig_forget(&world,o);
    ((void (__cdecl *)(Id,Sel))inherited_dealloc)(o,s);
}
static Imp replacements[IG_METHOD_COUNT] = {
    (Imp)inspect,(Imp)update,(Imp)update_signal,(Imp)inspector_close,(Imp)table_value,(Imp)table_rows,
    (Imp)doc_close,(Imp)delete_view,(Imp)docview_close,(Imp)destroy_9,(Imp)destroy_10,(Imp)destroy_11,(Imp)destroy_12,
#define DESTROY_ENTRY(i) (Imp)destroy_##i,
    IG_EXTRA_DEALLOC_LIST(DESTROY_ENTRY)
};
static int class_ready(Class cls)
{
    unsigned depth=0;
    __try {
        while(cls && depth++<128) {
            const char *name=*(const char **)((BYTE *)cls+8);
            unsigned info=*(unsigned *)((BYTE *)cls+16);
            Class registered;
            if(!(info&0x100) || !(info&3) || !name || !*(void **)((BYTE *)cls+28)) return 0;
            registered=lookup(name);
            if(info&2) registered=registered?*(Class *)registered:NULL;
            if(registered!=cls) return 0;
            cls=*(Class *)((BYTE *)cls+4);
        }
        return !cls;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return 0; }
}
static int module_hash(HMODULE module,const char *expected)
{
    WCHAR path[32768]; char hash[65];
    DWORD n=module?GetModuleFileNameW(module,path,32768):0;
    return n && n<32768 && ig_hash_file(path,hash) && !strcmp(hash,expected);
}
static int prepare(void)
{
    HMODULE runtime=GetModuleHandleW(L"nextpdo.dll"), foundation=GetModuleHandleW(L"Foundation.dll"), appkit=GetModuleHandleW(L"AppKit.dll");
    BYTE *base=(BYTE *)GetModuleHandleW(NULL);
    unsigned i;
    Method *parent;
    IgOps ops;
    if(!runtime || !foundation || !appkit) return 0;
    if(!fingerprinted) {
        WCHAR path[32768]; char hash[65],error[192];
        DWORD length=GetModuleFileNameW(NULL,path,32768);
        if(!length || length>=32768 || !ig_check_file(path,hash,error,sizeof(error)) ||
           !module_hash(runtime,"85afaa0c35ee8eab59bf68f9ea9cef0ab8324619245bc87507e382cce233e1e7") ||
           !module_hash(foundation,"3f33e3e33d144ef265a0e0d7b87b54ec147cdd6aae2838d3977a5763541b1b89") ||
           !module_hash(appkit,"ccf61f59340d7f4b31664d1f26ef9ee6aa4930439b46c38c26771c5c2af53323")) {
            fail("Stock executable or OpenStep runtime SHA-256 mismatch"); return -1;
        }
        fingerprinted=1;
    }
    if(!bound) {
#define BIND(v,n,t) v=(t)GetProcAddress(runtime,n); if(!v) { fail("Required classic Objective-C runtime export is missing"); return -1; }
        BIND(lookup,"objc_lookUpClass",Id (__cdecl *)(const char *))
        BIND(selector,"sel_registerName",Sel (__cdecl *)(const char *))
        BIND(get_method,"class_getInstanceMethod",Method *(__cdecl *)(Class,Sel))
        BIND(get_class_method,"class_getClassMethod",Method *(__cdecl *)(Class,Sel))
        BIND(get_ivar,"class_getInstanceVariable",Ivar *(__cdecl *)(Class,const char *))
        BIND(add_methods,"class_addMethods",void (__cdecl *)(Class,MethodList *))
        BIND(flush,"_objc_flush_caches",void (__cdecl *)(Class))
        BIND(objc_send,"objc_msgSend",void (__cdecl *)(void))
        bound=1;
    }
    for(i=0;i<IG_CLASS_COUNT;++i) if(!class_ready(lookup(ig_classes[i].name))) return 0;
    if(!class_ready(lookup("NSObject")) || !class_ready(lookup("NSMutableArray")) || !class_ready(lookup("NSApplication"))) return 0;
    __try {
        IMAGE_NT_HEADERS32 *nt=(IMAGE_NT_HEADERS32 *)(base+((IMAGE_DOS_HEADER *)base)->e_lfanew);
        if(nt->OptionalHeader.ImageBase!=IG_IMAGE_BASE || nt->OptionalHeader.SizeOfImage!=IG_IMAGE_SIZE) goto mismatch;
        for(i=0;i<IG_CLASS_COUNT;++i) {
            Class cls=lookup(ig_classes[i].name);
            if(cls!=base+ig_classes[i].rva || *(unsigned *)((BYTE *)cls+20)!=ig_classes[i].size) goto mismatch;
        }
        for(i=0;i<IG_IVAR_COUNT;++i) {
            const IgIvarContract *c=&ig_ivars[i];
            Ivar *iv=get_ivar(lookup(c->cls),c->name);
            if(!iv || !iv->types || strcmp(iv->types,c->types) || iv->offset!=c->offset) goto mismatch;
        }
        for(i=0;i<IG_METHOD_COUNT;++i) {
            const IgMethodContract *c=&ig_methods[i];
            Method *method=get_method(lookup(c->cls),S(c->selector));
            if(!method || !method->types || strcmp(method->types,c->types) ||
               (BYTE *)method->imp!=base+c->rva || memcmp((BYTE *)method->imp,c->prefix,16)) goto mismatch;
            slots[i]=method; originals[i]=method->imp;
        }
        parent=get_method(lookup("NSObject"),S("dealloc"));
        if(!parent || strcmp(parent->types,"v8@0:4") ||
           get_method(lookup("OTInspector"),S("dealloc"))!=parent) goto mismatch;
        inherited_dealloc=parent->imp;
        parent=get_class_method(lookup("OTDocument"),S("documentList"));
        if(!parent || strcmp(parent->types,"@8@0:4") || (BYTE *)parent->imp!=base+0x996cc) goto mismatch;
        parent=get_method(lookup("OTDocument"),S("documentView"));
        if(!parent || strcmp(parent->types,"@8@0:4") || (BYTE *)parent->imp!=base+0x9c970) goto mismatch;
    } __except(EXCEPTION_EXECUTE_HANDLER) { goto mismatch; }
    ops.context=NULL; ops.retain=retain_object; ops.release=release_object; ops.clear=clear_native;
    ig_init(&world,ops);
    ui_thread=GetCurrentThreadId();
     

    local_dealloc.next=NULL; local_dealloc.count=1;
    local_dealloc.list[0].name=S("dealloc"); local_dealloc.list[0].types="v8@0:4"; local_dealloc.list[0].imp=(Imp)inspector_destroy;
    add_methods(lookup("OTInspector"),&local_dealloc);
    for(i=0;i<IG_METHOD_COUNT;++i) slots[i]->imp=replacements[i];
    for(i=0;i<IG_CLASS_COUNT;++i) flush(lookup(ig_classes[i].name));
    if(get_method(lookup("OTInspector"),S("dealloc"))!=&local_dealloc.list[0]) {
        fail("Class-local Inspector dealloc installation failed"); return -1;
    }
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCWSTR)(const void *)&prepare,&self_module)) {
        fail("Guard module could not be pinned"); return -1;
    }
    status=1; signal_status(L"Ready");
    return 1;
mismatch:
    fail("Objective-C class, ivar, method address, or ABI contract mismatch"); return -1;
}
__declspec(dllexport) LRESULT CALLBACK GuardMessageHook(int code,WPARAM wp,LPARAM lp)
{
    if(code>=0 && wp==PM_REMOVE) {
        MSG *message=(MSG *)lp;
        if(!status) (void)prepare();
        if(status!=1 && message && ((message->message>=WM_KEYFIRST && message->message<=WM_KEYLAST)||
           (message->message>=WM_MOUSEFIRST && message->message<=WM_MOUSELAST)||message->message==WM_CLOSE)) message->message=WM_NULL;
    }
    return CallNextHookEx(NULL,code,wp,lp);
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved)
{
    (void)reserved;
    if(reason==DLL_PROCESS_ATTACH) { self_module=instance; DisableThreadLibraryCalls(instance); }
    return TRUE;
}
