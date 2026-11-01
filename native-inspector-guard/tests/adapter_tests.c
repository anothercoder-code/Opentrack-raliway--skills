 

#include <assert.h>
#include <stdarg.h>
#include "../src/guard.c"
typedef struct { Id value; int dead,refs; unsigned count; Id items[8]; Id docview,content,children; } Mock;
static Mock mocks[24];
static unsigned mock_count;
static Id inspector,doc,docview,view,model,documents,models,views,list,column,cell,application,windows,docwindow,panel;
static int marker,app_marker,dv_marker,mode,original_updates,original_tables,cleared_before_order,reloads;
static Mock *object(Id value)
{
    unsigned i;
    for(i=0;i<mock_count;++i) if(mocks[i].value==value) { assert(!mocks[i].dead); return &mocks[i]; }
    assert(!"Unowned or poison object was messaged"); return NULL;
}
static Id make(unsigned size)
{
    Mock *m=&mocks[mock_count++];
    memset(m,0,sizeof(*m)); m->value=calloc(1,size); assert(m->value); m->refs=1;
    return m->value;
}
static Sel __cdecl mock_selector(const char *name) { return (Sel)name; }
static Id __cdecl mock_lookup(const char *name)
{
    if(!strcmp(name,"OTDocument")) return &marker;
    if(!strcmp(name,"NSApplication")) return &app_marker;
    if(!strcmp(name,"OTDocView")) return &dv_marker;
    assert(0); return NULL;
}
static Id __cdecl mock_send(Id value,Sel command,...)
{
    const char *name=(const char *)command;
    Mock *m;
    va_list args;
    if(!value) return NULL;
    if(value==&marker) { assert(!strcmp(name,"documentList")); return documents; }
    if(value==&app_marker) { assert(!strcmp(name,"sharedApplication")); return application; }
    m=object(value);
    if(!strcmp(name,"retain")) { ++m->refs; return value; }
    if(!strcmp(name,"release")) { assert(m->refs>0); --m->refs; return NULL; }
    if(!strcmp(name,"autorelease")) return value;
    if(!strcmp(name,"count")) return (Id)(UINT_PTR)m->count;
    if(!strcmp(name,"removeAllObjects")) { m->count=0; return NULL; }
    if(!strcmp(name,"documentView")) return m->docview;
    if(!strcmp(name,"windows")) return windows;
    if(!strcmp(name,"contentView")) return m->content;
    if(!strcmp(name,"subviews")) return m->children;
    if(!strcmp(name,"reloadData")) {
        ++reloads;
        assert(value==column);
        assert(table_rows(inspector,S("numberOfRowsInTableView:"),column)==1);
        assert(table_value(inspector,S("tableView:objectValueForTableColumn:row:"),column,column,0)==cell);
        return NULL;
    }
    if(!strcmp(name,"objectAtIndex:")) {
        unsigned index;
        va_start(args,command); index=va_arg(args,unsigned); va_end(args);
        assert(index<m->count); return m->items[index];
    }
    assert(!"Unexpected Objective-C message"); return NULL;
}
static void __cdecl mock_update(Id owner,Sel cmd,Id arg)
{
    (void)cmd;
    ++original_updates;
    assert(!FIELD(owner,996));
    assert(arg==view || !arg);
    FIELD(owner,996)=model;
    assert(table_rows(owner,S("numberOfRowsInTableView:"),column)==0);
    assert(table_value(owner,S("tableView:objectValueForTableColumn:row:"),column,column,0)==NULL);
    if(mode==2) { ig_invalidate(&world,NULL); FIELD(owner,996)=model; }
    if(mode==3) { ig_invalidate(&world,model); object(model)->dead=1; FIELD(owner,996)=model; }
    if(mode==4) { ig_forget(&world,owner); object(owner)->dead=1; }
}
static void __cdecl mock_inspect(Id owner,Sel cmd,Id sender)
{
    (void)cmd; (void)sender;
    assert(!FIELD(owner,996)); cleared_before_order=1;
    assert(table_value(owner,S("tableView:objectValueForTableColumn:row:"),column,column,0)==NULL);
    update(owner,S("update:"),view);
}
static Id __cdecl mock_table(Id owner,Sel cmd,Id table,Id col,int row)
{
    (void)cmd; (void)table; (void)col; (void)row;
    ++original_tables; assert(FIELD(owner,996)==model);
    assert(object(model)->refs>1 && object(view)->refs>1 && object(doc)->refs>1 && object(docview)->refs>1);
    assert(table_value(owner,S("tableView:objectValueForTableColumn:row:"),column,column,0)==NULL);
    return cell;
}
static int __cdecl mock_rows(Id owner,Sel cmd,Id table)
{
    (void)cmd; (void)table; assert(FIELD(owner,996)==model); return 1;
}
static char __cdecl mock_close(Id owner,Sel cmd,Id closing_panel)
{
    (void)cmd; (void)closing_panel;
    assert(!FIELD(owner,996)); FIELD(owner,984)=NULL; return 1;
}
static void reset(void)
{
    unsigned i;
    IgOps ops;
    for(i=0;i<64;++i) if(world.leases[i]) ig_drop(&world,world.leases[i]);
    for(i=0;i<mock_count;++i) free(mocks[i].value);
    mock_count=0; mode=0; original_updates=0; original_tables=0; cleared_before_order=0; reloads=0;
    memset(mocks,0,sizeof(mocks));
    inspector=make(1836); doc=make(228); docview=make(128); view=make(124); model=make(40);
    documents=make(4); models=make(4); views=make(4); list=make(4); column=make(4); cell=make(4);
    application=make(4); windows=make(4); docwindow=make(4); panel=make(4);
    object(documents)->count=1; object(documents)->items[0]=doc;
    object(models)->count=1; object(models)->items[0]=model;
    object(views)->count=1; object(views)->items[0]=view;
    object(doc)->docview=docview;
    object(windows)->count=2; object(windows)->items[0]=docwindow; object(windows)->items[1]=panel;
    object(docwindow)->content=docview; object(panel)->content=column;
    *(Class *)docview=&dv_marker;
    FIELD(doc,4)=models; FIELD(doc,24)=docwindow; FIELD(docview,80)=doc; FIELD(docview,84)=views;
    FIELD(view,80)=model; FIELD(model,8)=view;
    FIELD(inspector,984)=panel; FIELD(inspector,1000)=list; FIELD(inspector,424)=column;
    ops.context=NULL; ops.retain=retain_object; ops.release=release_object; ops.clear=clear_native;
    ig_init(&world,ops);
    lookup=mock_lookup; selector=mock_selector; objc_send=(void (__cdecl *)(void))mock_send;
    originals[0]=(Imp)mock_inspect; originals[1]=(Imp)mock_update; originals[2]=(Imp)mock_update;
    originals[3]=(Imp)mock_close; originals[4]=(Imp)mock_table;
    originals[5]=(Imp)mock_rows;
    status=1; ui_thread=GetCurrentThreadId();
}
static DWORD WINAPI wrong_thread(LPVOID ignored)
{
    (void)ignored; destroy(11,model,S("dealloc")); return 99;
}
int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"--unexpected-thread")) {
        HANDLE thread;
        reset(); thread=CreateThread(NULL,0,wrong_thread,NULL,0,NULL); assert(thread);
        WaitForSingleObject(thread,5000); assert(!"Expected current mock process fail-stop"); return 99;
    }
    reset(); FIELD(inspector,996)=(Id)0xdeadbeef;
    inspect(inspector,S("inspector:"),NULL);
    assert(cleared_before_order && original_updates==1 && FIELD(inspector,996)==model && reloads==1 && original_tables==1);
    assert(table_value(inspector,S("tableView:objectValueForTableColumn:row:"),column,column,0)==cell && original_tables==2);
    assert(!table_value(inspector,S("tableView:objectValueForTableColumn:row:"),column,column,1) && original_tables==2);
    reset(); FIELD(inspector,984)=NULL; FIELD(inspector,996)=(Id)0xdeadbeef;
    update(inspector,S("update:"),NULL); assert(!FIELD(inspector,996) && !original_updates);
    reset(); FIELD(inspector,996)=(Id)0xdeadbeef;
    assert(!table_value(inspector,S("tableView:objectValueForTableColumn:row:"),column,column,0));
    assert(!FIELD(inspector,996) && !original_tables);
    reset(); update(inspector,S("update:"),(Id)0xdeadbeef); assert(!original_updates && !FIELD(inspector,996));
    reset(); mode=2; update(inspector,S("update:"),view); assert(!FIELD(inspector,996));
    reset(); mode=3; update(inspector,S("update:"),view); assert(!FIELD(inspector,996));
    reset(); update(inspector,S("update:"),view); assert(FIELD(inspector,996)==model);
    assert(inspector_close(inspector,S("windowShouldClose:"),column)); assert(!FIELD(inspector,996));
    reset(); FIELD(model,8)=NULL; update(inspector,S("update:"),view); assert(!original_updates);
    reset(); mode=4; update(inspector,S("update:"),view); assert(!ig_state(&world,doc)->selection);
    reset(); object(doc)->docview=(Id)0xdeadbeef; update(inspector,S("update:"),view); assert(!original_updates);
    reset(); FIELD(inspector,424)=(Id)0xdeadbeef; update(inspector,S("update:"),view); assert(!reloads);
    puts("{\"adapter_tests\":11,\"passed\":11,\"mock_only\":true,\"original_pe_execution\":false,\"gui_acceptance\":false}");
    return 0;
}
