#include "guard_policy.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { int refs,dead; } Object;
typedef struct {
    IgWorld world;
    Object inspector,doc,dv,view,model;
    IgObject selected;
    int clear_count,release_count,retain_count;
    int reenter,clear_reuse;
} Test;
static void retain(void *c,IgObject p)
{
    Test *t=(Test *)c; Object *o=(Object *)p;
    assert(!o->dead); ++o->refs; ++t->retain_count;
}
static void release(void *c,IgObject p)
{
    Test *t=(Test *)c; Object *o=(Object *)p;
    assert(!o->dead); assert(t->selected==NULL || !t->reenter); --o->refs; ++t->release_count;
    if(t->reenter==1) { t->reenter=0; ig_invalidate(&t->world,&t->model); t->model.dead=1; }
}
static void clear(void *c,IgObject owner)
{
    Test *t=(Test *)c;
    (void)owner; t->selected=NULL; ++t->clear_count;
    if(t->clear_reuse) {
        t->clear_reuse=0;
        ig_forget(&t->world,&t->inspector);
        (void)ig_state(&t->world,&t->doc);
    }
}
static void init(Test *t)
{
    IgOps ops;
    memset(t,0,sizeof(*t)); ops.context=t; ops.retain=retain; ops.release=release; ops.clear=clear;
    ig_init(&t->world,ops);
}
static IgLease *pair(Test *t)
{
    IgLease *l=ig_lease_new(&t->world);
    IgPair p; p.doc=&t->doc; p.docview=&t->dv; p.view=&t->view; p.model=&t->model;
    assert(l && ig_add_pair(&t->world,l,p));
    return l;
}
static void ordinary_lifetime(void)
{
    Test t; IgState *s; IgTicket ticket; IgLease *l;
    init(&t); s=ig_state(&t.world,&t.inspector); t.selected=(void *)0xdeadbeef;
    ticket=ig_begin(&t.world,s); assert(t.selected==NULL && s->depth==1);
    l=pair(&t); assert(ig_find_model(l,&t.model)); assert(!ig_find_model(l,(void *)0xdeadbeef));
    t.selected=&t.model; assert(ig_finish(&t.world,s,ticket,l));
    assert(s->selection && !s->depth && t.model.refs==1 && t.view.refs==1 && t.dv.refs==1 && t.doc.refs==1);
    ig_invalidate(&t.world,NULL); assert(!t.selected && !s->selection);
    assert(!t.model.refs && !t.view.refs && !t.dv.refs && !t.doc.refs);
}
static void epoch_prevents_restoration(void)
{
    Test t; IgState *s; IgTicket ticket; IgLease *l;
    init(&t); s=ig_state(&t.world,&t.inspector); ticket=ig_begin(&t.world,s); l=pair(&t);
    ig_invalidate(&t.world,NULL); t.selected=&t.model;
    assert(!ig_finish(&t.world,s,ticket,l)); assert(!t.selected && !s->selection && !t.model.refs);
}
static void pending_explicit_dealloc(void)
{
    Test t; IgState *s; IgTicket ticket; IgLease *l;
    init(&t); s=ig_state(&t.world,&t.inspector); ticket=ig_begin(&t.world,s); l=pair(&t);
    ig_invalidate(&t.world,&t.model); t.model.dead=1; t.selected=&t.model;
    assert(l->poisoned); assert(!ig_finish(&t.world,s,ticket,l)); assert(!t.selected);
    assert(t.release_count==0);  
}
static void nested_dealloc_during_release(void)
{
    Test t; IgState *s; IgTicket ticket; IgLease *pending,*old;
    init(&t); s=ig_state(&t.world,&t.inspector); ticket=ig_begin(&t.world,s);
    old=ig_lease_new(&t.world); assert(ig_pin(&t.world,old,&t.doc)); s->selection=old;
    pending=pair(&t); t.reenter=1;
    ig_invalidate(&t.world,NULL); assert(pending->poisoned && t.model.dead);
    assert(!ig_finish(&t.world,s,ticket,pending));
}
static void forgotten_slot_is_not_reused_by_old_ticket(void)
{
    Test t; IgState *s,*new_state; IgTicket ticket; IgLease *l;
    init(&t); s=ig_state(&t.world,&t.inspector); t.clear_reuse=1;
    ticket=ig_begin(&t.world,s); new_state=ig_state(&t.world,&t.doc); assert(new_state==s);
    l=pair(&t); assert(!ig_finish(&t.world,s,ticket,l));
    assert(s->owner==&t.doc && !s->selection && !s->depth);
}
static void poison_does_not_exhaust_lease_registry(void)
{
    Test t; unsigned i; IgState *s; IgTicket ticket;
    init(&t); s=ig_state(&t.world,&t.inspector);
    for(i=0;i<128;++i) {
        IgLease *l;
        ticket=ig_begin(&t.world,s); l=pair(&t); t.selected=&t.model;
        assert(ig_finish(&t.world,s,ticket,l)); ig_invalidate(&t.world,&t.model);
        assert(!s->selection && !t.selected);
    }
    for(i=0;i<64;++i) assert(!t.world.leases[i]);
}
int main(void)
{
    ordinary_lifetime(); epoch_prevents_restoration(); pending_explicit_dealloc();
    nested_dealloc_during_release(); forgotten_slot_is_not_reused_by_old_ticket();
    poison_does_not_exhaust_lease_registry();
    puts("{\"policy_tests\":6,\"passed\":6,\"original_pe_execution\":false,\"gui_acceptance\":false}");
    return 0;
}
