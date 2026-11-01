#include "guard_policy.h"
#include <stdlib.h>
#include <string.h>

void ig_init(IgWorld *w, IgOps ops) { memset(w, 0, sizeof(*w)); w->ops = ops; }
IgLease *ig_lease_new(IgWorld *w)
{
    unsigned i;
    for (i=0;i<64;++i) if (!w->leases[i]) {
        IgLease *l = (IgLease *)calloc(1,sizeof(IgLease));
        w->leases[i] = l;
        return l;
    }
    return NULL;
}
IgState *ig_state(IgWorld *w, IgObject owner)
{
    unsigned i;
    if (!owner) return NULL;
    for (i = 0; i < IG_MAX_INSPECTORS; ++i)
        if (w->states[i].owner == owner) return &w->states[i];
    for (i = 0; i < IG_MAX_INSPECTORS; ++i)
        if (!w->states[i].owner) {
            w->states[i].owner = owner;
            w->states[i].generation = ++w->serial;
            return &w->states[i];
        }
    return NULL;
}
int ig_contains(const IgLease *l, IgObject o)
{
    unsigned i;
    if (!l || !o) return 0;
    for (i = 0; i < l->pin_count; ++i) if (l->pins[i] == o) return 1;
    return 0;
}
int ig_pin(IgWorld *w, IgLease *l, IgObject o)
{
    if (!l || l->poisoned) return 0;
    if (!o || ig_contains(l, o)) return 1;
    if (l->pin_count == IG_MAX_PINS) return 0;
     
    w->ops.retain(w->ops.context, o);
    l->pins[l->pin_count++] = o;
    return 1;
}
int ig_add_pair(IgWorld *w, IgLease *l, IgPair p)
{
    if (!p.doc || !p.docview || !p.view || !p.model || l->pair_count == IG_MAX_PAIRS) return 0;
    if (!ig_pin(w,l,p.doc) || !ig_pin(w,l,p.docview) || !ig_pin(w,l,p.view) || !ig_pin(w,l,p.model)) return 0;
    l->pairs[l->pair_count++] = p;
    return 1;
}
const IgPair *ig_find_view(const IgLease *l, IgObject o)
{
    unsigned i;
    if (l && o) for (i = 0; i < l->pair_count; ++i) if (l->pairs[i].view == o) return &l->pairs[i];
    return NULL;
}
const IgPair *ig_find_model(const IgLease *l, IgObject o)
{
    unsigned i;
    if (l && o) for (i = 0; i < l->pair_count; ++i) if (l->pairs[i].model == o) return &l->pairs[i];
    return NULL;
}
void ig_drop(IgWorld *w, IgLease *l)
{
    unsigned i;
    if (!l) return;
     
    while (!l->poisoned && l->pin_count) {
        IgObject o = l->pins[--l->pin_count];
        w->ops.release(w->ops.context, o);
    }
    for (i=0;i<64;++i) if (w->leases[i] == l) { w->leases[i] = NULL; break; }
    free(l);
}
void ig_clear(IgWorld *w, IgState *s)
{
    IgLease *old;
    IgObject owner;
    unsigned generation;
    if (!s) return;
    old = s->selection;
    s->selection = NULL;
    owner=s->owner; generation=s->generation;
     
    if(!s->clearing) {
        s->clearing=1;
        w->ops.clear(w->ops.context,owner);
        if(s->owner==owner && s->generation==generation) s->clearing=0;
    }
    ig_drop(w, old);
}
IgTicket ig_begin(IgWorld *w, IgState *s)
{
    IgTicket ticket;
    ticket.epoch = w->epoch; ticket.generation = s->generation; ticket.owner = s->owner;
    ++s->depth;
    ig_clear(w, s);
    return ticket;
}
int ig_finish(IgWorld *w, IgState *s, IgTicket ticket, IgLease *verified)
{
    int same = s->owner == ticket.owner && s->generation == ticket.generation;
    int accept = same && !w->invalidating && w->epoch == ticket.epoch && (!verified || !verified->poisoned);
    if (accept) {
        IgLease *old = s->selection;
        s->selection = verified;
        ig_drop(w, old);
    } else {
        if (same) ig_clear(w, s);
        ig_drop(w, verified);
    }
    if (same && s->depth) --s->depth;
    return accept;
}
void ig_invalidate(IgWorld *w, IgObject dying)
{
    unsigned i;
    if (dying) for (i=0;i<64;++i)
        if (ig_contains(w->leases[i],dying)) w->leases[i]->poisoned = 1;
    if (w->invalidating) return;
    w->invalidating = 1;
    ++w->epoch;
    for (i = 0; i < IG_MAX_INSPECTORS; ++i) {
        IgState *s = &w->states[i];
        if (!s->owner) continue;
         


        ig_clear(w,s);
    }
    w->invalidating = 0;
}
void ig_forget(IgWorld *w, IgObject owner)
{
    unsigned i;
    ++w->epoch;
    for (i = 0; i < IG_MAX_INSPECTORS; ++i) if (w->states[i].owner == owner) {
        ig_clear(w, &w->states[i]);
        memset(&w->states[i], 0, sizeof(w->states[i]));
        return;
    }
}
