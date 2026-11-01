#ifndef IG_POLICY_H
#define IG_POLICY_H
#include <stddef.h>
#define IG_MAX_PAIRS 4096
#define IG_MAX_PINS (IG_MAX_PAIRS * 4 + 256)
#define IG_MAX_INSPECTORS 16
typedef void *IgObject;
typedef struct { IgObject doc, docview, view, model; } IgPair;
typedef struct {
    IgObject pins[IG_MAX_PINS];
    unsigned pin_count;
    IgPair pairs[IG_MAX_PAIRS];
    unsigned pair_count;
    int poisoned;
} IgLease;
typedef struct {
    void *context;
    void (*retain)(void *, IgObject);
    void (*release)(void *, IgObject);
    void (*clear)(void *, IgObject);
} IgOps;
typedef struct {
    IgObject owner;
    IgLease *selection;
    unsigned depth;
    unsigned generation;
    int refreshing;
    int clearing;
} IgState;
typedef struct { unsigned epoch,generation; IgObject owner; } IgTicket;
typedef struct {
    IgOps ops;
    IgState states[IG_MAX_INSPECTORS];
    unsigned epoch;
    int invalidating;
    unsigned serial;
    IgLease *leases[64];
} IgWorld;
void ig_init(IgWorld *, IgOps);
IgLease *ig_lease_new(IgWorld *);
IgState *ig_state(IgWorld *, IgObject);
int ig_pin(IgWorld *, IgLease *, IgObject);
int ig_add_pair(IgWorld *, IgLease *, IgPair);
const IgPair *ig_find_view(const IgLease *, IgObject);
const IgPair *ig_find_model(const IgLease *, IgObject);
int ig_contains(const IgLease *, IgObject);
void ig_drop(IgWorld *, IgLease *);
void ig_clear(IgWorld *, IgState *);
IgTicket ig_begin(IgWorld *, IgState *);
int ig_finish(IgWorld *, IgState *, IgTicket, IgLease *);
void ig_invalidate(IgWorld *, IgObject dying);
void ig_forget(IgWorld *, IgObject);
#endif
