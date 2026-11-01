"""Fail-closed incoming-object edges through supported typed value containers.

Object cycles are legal and visited once. Inline container cycles are not wire
representable and rejected. Each occurrence of a container contributes its
edges (not deduplicated), so aliases cannot hide a second incoming reference.
"""
from collections import Counter
from . import writer as w

class ReferenceGraphError(ValueError): pass

def reference_inventory(root):
    counts=Counter();seen=set();active=set();objects=[]
    def walk(value,edge=True):
        if isinstance(value,w.GenericArchivedObject):
            if edge:counts[id(value)]+=1
            if id(value) in seen:return
            seen.add(id(value));objects.append(value)
            for group in value.contents:
                if not isinstance(group,w.TypedGroup):raise ReferenceGraphError('Unknown object contents container')
                walk(group)
            return
        if isinstance(value,(w.TypedGroup,w.Array,w.GenericStruct,list,tuple)):
            identity=id(value)
            if identity in active:raise ReferenceGraphError('Cyclic inline typed container')
            active.add(identity)
            try:
                if isinstance(value,w.TypedGroup):
                    if len(value.encodings)!=len(value.values):raise ReferenceGraphError('Malformed typed group')
                    children=value.values
                elif isinstance(value,w.Array):
                    if type(value.elements) is bytes:return
                    if type(value.elements) not in (list,tuple):raise ReferenceGraphError('Unknown typed Array backing container')
                    children=value.elements
                elif isinstance(value,w.GenericStruct):
                    if type(value.fields) not in (list,tuple):raise ReferenceGraphError('Unknown typed Struct backing container')
                    children=value.fields
                else:children=value
                for child in children:walk(child)
            finally:active.remove(identity)
            return
        if value is None or type(value) in (bytes,str,int,float,bool) or isinstance(value,w.WireFloat):return
        
        if isinstance(value,(w.Class,w.SharedString,w.CString)):return
        raise ReferenceGraphError('Unknown graph value/container: '+type(value).__name__)
    walk(root,False)
    return objects,counts

def incoming_counts(root):return reference_inventory(root)[1]

def incoming(root,target):return incoming_counts(root)[id(target)]
