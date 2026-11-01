#ifndef IG_CONTRACT_TYPES_H
#define IG_CONTRACT_TYPES_H
typedef struct { const char *cls,*selector,*types; unsigned rva; unsigned char prefix[16]; } IgMethodContract;
typedef struct { const char *name; unsigned rva,size; } IgClassContract;
typedef struct { const char *cls,*name,*types; int offset; } IgIvarContract;
#endif
