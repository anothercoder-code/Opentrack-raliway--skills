 
#ifndef OT_EXCEPTION_H
#define OT_EXCEPTION_H

typedef void (*OtExceptionAction)(void *context);
typedef struct {
    unsigned code;
    void *exception;  
    void *data1;
    void *data2;
} OtException;

 
int ot_exception_init(void);
 




int ot_exception_invoke(OtExceptionAction action, void *context, OtException *error);

 





int ot_exception_cleanup(OtExceptionAction action, void *context, OtExceptionAction cleanup);

#endif
