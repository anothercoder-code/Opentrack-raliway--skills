"""Independent generic typedstream-v4 graph codec; no OpenTrack field layouts guessed.

Implemented from the public wire format documented by dgelessus/python-typedstream
0.1.0 (LGPL-3.0-or-later). That upstream package is NOT copied or bundled here.
This implementation is independent source, copyright 2026, MIT license.
Native application acceptance is NOT implied by structural round-trip validation.
"""
from dataclasses import dataclass, field
import struct
import hashlib
import types

class InvalidTypedStreamError(ValueError): pass
stream = types.SimpleNamespace(InvalidTypedStreamError=InvalidTypedStreamError)

class WireFloat(float):
    """Float value retaining IEEE bits (including signaling-NaN payloads)."""
    def __new__(cls, bits, encoding, byte_order):
        value=struct.unpack(('<' if byte_order=='little' else '>')+encoding.decode(),bits)[0]
        obj=super().__new__(cls,value)
        obj.bits, obj.encoding, obj.byte_order=bits,encoding,byte_order
        return obj
    def __reduce__(self): return (type(self),(self.bits,self.encoding,self.byte_order))

@dataclass(eq=False)
class SharedString:
    data: bytes

@dataclass(eq=False)
class Class:
    name: bytes
    version: int
    superclass: object = None
    _name_token: object = field(default=None, repr=False)

@dataclass(eq=False, init=False)
class GenericArchivedObject:
    clazz: object = None
    contents: list = field(default_factory=list)
    def __init__(self, clazz=None, super_object=None, contents=None):
        
        
        if contents is None and isinstance(super_object,list):
            contents,super_object=super_object,None
        if super_object is not None: raise ValueError('known superclass objects are unsupported')
        self.clazz,self.contents=clazz,[] if contents is None else list(contents)
        self.super_object=None

@dataclass(eq=False)
class CString:
    token: SharedString

@dataclass(eq=False)
class Array:
    elements: object

@dataclass(eq=False)
class GenericStruct:
    name: object
    fields: list

class TypedGroup:
    def __init__(self, encodings, values, token=None):
        self.encodings, self.values, self._token = list(encodings), list(values), token
    @property
    def value(self):
        if len(self.values) != 1: raise ValueError('not a single value')
        return self.values[0]
    @value.setter
    def value(self, value):
        if len(self.values) != 1: raise ValueError('not a single value')
        self.values[0] = value
    @property
    def encoding(self):
        if len(self.encodings) != 1: raise ValueError('not a single type')
        return self.encodings[0]

class TypedValue(TypedGroup):
    def __init__(self, encoding, value): super().__init__([encoding], [value])
ar = types.SimpleNamespace(TypedValue=TypedValue, TypedGroup=TypedGroup,
    Class=Class, GenericArchivedObject=GenericArchivedObject, Array=Array, GenericStruct=GenericStruct)

@dataclass
class Archive:
    groups: list
    system_version: int = 1000
    byte_order: str = 'little'
    streamer_version: int = 4


def split_types(data):
    if not isinstance(data, bytes) or not data: raise InvalidTypedStreamError('empty type encoding')
    result=[]; start=0; stack=[]
    for i,b in enumerate(data):
        if b in b'[{': stack.append(b)
        elif b in b']}':
            if not stack or stack.pop() != {93:91,125:123}[b]: raise InvalidTypedStreamError('unbalanced type')
        if not stack:
            result.append(data[start:i+1]); start=i+1
    if stack: raise InvalidTypedStreamError('unterminated type')
    return result


def array_type(enc):
    i=1
    while i<len(enc)-1 and 48<=enc[i]<=57: i+=1
    if i==1 or len(split_types(enc[i:-1]))!=1: raise InvalidTypedStreamError('invalid array type')
    return int(enc[1:i]), enc[i:-1]


def struct_type(enc):
    body=enc[1:-1]
    if b'=' in body: name, fields=body.split(b'=',1)
    else: name, fields=None,body
    return name, split_types(fields) if fields else []


class Reader:
    def __init__(self, data, strict_lengths=True):
        if len(data)>20*1024*1024: raise InvalidTypedStreamError('archive exceeds 20 MiB')
        self.data=memoryview(data); self.pos=0; self.shared=[]; self.refs=[]; self.order='little'; self.strict_lengths=strict_lengths
    def take(self,n):
        if n<0 or self.pos+n>len(self.data): raise InvalidTypedStreamError('truncated data')
        value=bytes(self.data[self.pos:self.pos+n]); self.pos+=n; return value
    def head(self): return int.from_bytes(self.take(1),'little',signed=True)
    def integer(self,signed=True,head=None):
        h=self.head() if head is None else head
        if not -128<=h<=-111: return h if signed else h&255
        if h not in (-127,-126): raise InvalidTypedStreamError('invalid integer tag')
        return int.from_bytes(self.take(2 if h==-127 else 4),self.order,signed=signed)
    def raw_string(self,head=None):
        h=self.head() if head is None else head
        if h==-123: return None
        n=self.integer(False,h)
        
        if self.strict_lengths and ((h==-127 and n>32767) or (h==-126 and n>2147483647) or (h not in (-127,-126) and n>127)):
            raise InvalidTypedStreamError('non-native signed length representation')
        return self.take(n)
    def shared_string(self,head=None):
        h=self.head() if head is None else head
        if h==-123: return None
        if h==-124:
            data=self.raw_string()
            if data is None: raise InvalidTypedStreamError('nil literal shared string')
            value=SharedString(data); self.shared.append(value); return value
        i=self.integer(True,h)+110
        if not 0<=i<len(self.shared): raise InvalidTypedStreamError('invalid shared-string reference')
        return self.shared[i]
    def ref(self,h,kind):
        i=self.integer(True,h)+110
        if not 0<=i<len(self.refs) or self.refs[i][0]!=kind: raise InvalidTypedStreamError('invalid reference index/type')
        return self.refs[i][1]
    def clazz(self):
        h=self.head()
        if h==-123: return None
        if h!=-124: return self.ref(h,'class')
        token=self.shared_string()
        if token is None: raise InvalidTypedStreamError('nil class name')
        c=Class(token.data,self.integer(),_name_token=token)
        self.refs.append(('class',c)); c.superclass=self.clazz(); return c
    def group(self):
        token=self.shared_string()
        if token is None: raise InvalidTypedStreamError('nil type')
        encs=split_types(token.data)
        return TypedGroup(encs,[self.value(enc) for enc in encs],token)
    def value(self,enc):
        if enc in (b'c',b'C',b'B'):
            v=int.from_bytes(self.take(1),self.order,signed=enc==b'c')
            if enc==b'B' and v not in (0,1): raise InvalidTypedStreamError('invalid boolean')
            return bool(v) if enc==b'B' else v
        if enc in (b's',b'i',b'l',b'q',b'S',b'I',b'L',b'Q'):
            value=self.integer(enc.islower())
            if (enc==b's' and not -32768<=value<=32767) or (enc==b'S' and not 0<=value<=65535):
                raise InvalidTypedStreamError('short value outside declared type range')
            return value
        if enc in (b'f',b'd'):
            h=self.head()
            return WireFloat(self.take(4 if enc==b'f' else 8),enc,self.order) if h==-125 else float(self.integer(True,h))
        if enc==b'+': return self.raw_string()
        if enc in (b'%',b':'): return self.shared_string()
        if enc==b'#': return self.clazz()
        if enc in (b'@',b'*'):
            h=self.head()
            if h==-123: return None
            kind='object' if enc==b'@' else 'cstring'
            if h!=-124: return self.ref(h,kind)
            if enc==b'*':
                token=self.shared_string()
                if token is None or b'\0' in token.data: raise InvalidTypedStreamError('invalid C string')
                v=CString(token); self.refs.append((kind,v)); return v
            v=GenericArchivedObject(); self.refs.append((kind,v)); v.clazz=self.clazz()
            if v.clazz is None: raise InvalidTypedStreamError('nil object class')
            while self.pos<len(self.data) and self.data[self.pos]!=134: v.contents.append(self.group())
            if self.take(1)!=b'\x86': raise InvalidTypedStreamError('missing object end')
            return v
        if enc==b'!': return None
        if enc.startswith(b'['):
            n,t=array_type(enc)
            if n>20*1024*1024: raise InvalidTypedStreamError('array too large')
            return Array(self.take(n) if t in (b'c',b'C') else [self.value(t) for _ in range(n)])
        if enc.startswith(b'{'):
            name,ts=struct_type(enc); return GenericStruct(name,[self.value(t) for t in ts])
        raise InvalidTypedStreamError(f'unsupported encoding {enc!r}')
    def read(self):
        if self.take(2)!=b'\x04\x0b': raise InvalidTypedStreamError('only v4 supported')
        sig=self.take(11)
        if sig not in (b'streamtyped',b'typedstream'): raise InvalidTypedStreamError('invalid signature')
        self.order='little' if sig==b'streamtyped' else 'big'
        version=self.integer(False); groups=[]
        while self.pos<len(self.data): groups.append(self.group())
        return Archive(groups,version,self.order)


class Writer:
    def __init__(self,order):
        if order not in ('little','big'): raise ValueError('invalid byte order')
        self.order=order; self.out=bytearray(); self.shared={}; self.refs={}; self.keep=[]; self.class_stack=set()
    def tag(self,n): self.out.append(n&255)
    def integer(self,n,signed=True,length=False):
        if not isinstance(n,int): raise ValueError('integer required')
        if length and n<0: raise ValueError('negative length')
        low,high=(-128,127) if signed else (0,255)
        h=n if n<128 else n-256
        if low<=n<=high and not -128<=h<=-111 and (not length or n<=127): self.tag(n); return
        for width,tag in ((2,-127),(4,-126)):
            lo=-(1<<(width*8-1)) if signed else 0
            hi=(1<<(width*8-(1 if signed or length else 0)))-1
            if lo<=n<=hi:
                self.tag(tag); self.out.extend(n.to_bytes(width,self.order,signed=signed)); return
        raise ValueError('integer outside supported 32-bit wire range')
    def raw_string(self,data):
        if data is None: self.tag(-123); return
        if not isinstance(data,bytes): raise ValueError('bytes required')
        self.integer(len(data),False,True); self.out.extend(data)
    def shared_string(self,token):
        if token is None: self.tag(-123); return
        if not isinstance(token,SharedString): raise ValueError('SharedString required')
        ident=id(token)
        if ident in self.shared: self.integer(self.shared[ident]-110); return
        self.shared[ident]=len(self.shared); self.keep.append(token)
        self.tag(-124); self.raw_string(token.data)
    def reference(self,value,kind):
        if value is None: self.tag(-123); return True
        ident=id(value)
        if ident in self.refs:
            k,n=self.refs[ident]
            if kind!=k: raise ValueError('reference type mismatch')
            self.integer(n-110); return True
        self.refs[ident]=(kind,len(self.refs)); self.keep.append(value); self.tag(-124); return False
    def clazz(self,c):
        if c is not None and id(c) in self.class_stack: raise ValueError('cyclic superclass chain unsupported')
        if self.reference(c,'class'): return
        if not isinstance(c,Class): raise ValueError('Class required')
        token=c._name_token if c._name_token is not None and c._name_token.data==c.name else SharedString(c.name)
        self.shared_string(token); self.integer(c.version)
        self.class_stack.add(id(c)); self.clazz(c.superclass); self.class_stack.remove(id(c))
    def group(self,g):
        if len(g.encodings)!=len(g.values) or not g.encodings: raise ValueError('typed group arity mismatch')
        encoding=b''.join(g.encodings)
        if split_types(encoding)!=g.encodings: raise ValueError('invalid group encodings')
        token=g._token if g._token is not None and g._token.data==encoding else SharedString(encoding)
        self.shared_string(token)
        for e,v in zip(g.encodings,g.values): self.value(e,v)
    def value(self,e,v):
        if e in (b'c',b'C',b'B'):
            if not isinstance(v,int) or (e==b'B' and v not in (0,1)): raise ValueError('invalid byte/bool')
            self.out.extend(v.to_bytes(1,self.order,signed=e==b'c')); return
        if e in (b's',b'i',b'l',b'q',b'S',b'I',b'L',b'Q'):
            if not isinstance(v,int): raise ValueError('integer required')
            if (e==b's' and not -32768<=v<=32767) or (e==b'S' and not 0<=v<=65535):
                raise ValueError('short value outside declared type range')
            self.integer(v,e.islower()); return
        if e in (b'f',b'd'):
            if not isinstance(v,(int,float)): raise ValueError('float required')
            self.tag(-125)
            if isinstance(v,WireFloat) and v.encoding==e:
                self.out.extend(v.bits if v.byte_order==self.order else v.bits[::-1])
            else: self.out.extend(struct.pack(('<' if self.order=='little' else '>')+e.decode(),v))
            return
        if e==b'+': self.raw_string(v); return
        if e in (b'%',b':'): self.shared_string(v); return
        if e==b'#': self.clazz(v); return
        if e in (b'@',b'*'):
            if self.reference(v,'object' if e==b'@' else 'cstring'): return
            if e==b'*':
                if not isinstance(v,CString) or b'\0' in v.token.data: raise ValueError('invalid C string')
                self.shared_string(v.token); return
            if not isinstance(v,GenericArchivedObject) or v.clazz is None: raise ValueError('generic object required')
            self.clazz(v.clazz)
            for g in v.contents: self.group(g)
            self.tag(-122); return
        if e==b'!':
            if v is not None: raise ValueError('ignored field must be None')
            return
        if e.startswith(b'['):
            n,t=array_type(e)
            if not isinstance(v,Array) or len(v.elements)!=n: raise ValueError('array length mismatch')
            if t in (b'c',b'C'):
                if not isinstance(v.elements,bytes): raise ValueError('byte array requires bytes')
                self.out.extend(v.elements)
            else:
                for a in v.elements: self.value(t,a)
            return
        if e.startswith(b'{'):
            name,ts=struct_type(e)
            if not isinstance(v,GenericStruct) or v.name!=name or len(v.fields)!=len(ts): raise ValueError('struct mismatch')
            for t,a in zip(ts,v.fields): self.value(t,a)
            return
        raise ValueError(f'unsupported encoding {e!r}')
    def write(self,archive):
        if archive.streamer_version!=4: raise ValueError('only v4 supported')
        self.out.extend(b'\x04\x0b'+(b'streamtyped' if self.order=='little' else b'typedstream'))
        self.integer(archive.system_version,False)
        for g in archive.groups: self.group(g)
        return bytes(self.out)


def decode(data, *, strict_lengths=True): return Reader(data,strict_lengths).read()
def encode(archive): return Writer(archive.byte_order).write(archive)
def load(data):
    archive=decode(data,strict_lengths=False)
    if len(archive.groups)!=1 or archive.groups[0].encodings!=[b'@']: raise ValueError('expected single root object')
    root=archive.groups[0].value
    if root is None: raise ValueError('nil root')
    root._archive_header=(archive.system_version,archive.byte_order)
    root._root_token=archive.groups[0]._token
    return root,archive.system_version

def load_next_compatible(data):
    decode(data,strict_lengths=True)
    return load(data)

def root_archive(root,version=1000):
    header=getattr(root,'_archive_header',(version,'little'))
    return Archive([TypedGroup([b'@'],[root],getattr(root,'_root_token',None))],version,header[1])

def fingerprint(root): return hashlib.sha256(encode(root_archive(root,getattr(root,'_archive_header',(1000,))[0]))).hexdigest()
def dump(root,version=1000): return encode(root_archive(root,version))

def dump_verified(root,version=1000):
    result=encode(root_archive(root,version))
    reparsed,v=load_next_compatible(result)
    if fingerprint(reparsed)!=fingerprint(root): raise ValueError('graph verification mismatch')
    return result

def kind(obj): return obj.clazz.name.decode('ascii') if isinstance(obj,GenericArchivedObject) else None

def objects(root):
    seen=set(); result=[]
    def visit(v):
        if isinstance(v,GenericArchivedObject):
            if id(v) in seen: return
            seen.add(id(v)); result.append(v)
            for g in v.contents:
                for a in g.values: visit(a)
        elif isinstance(v,Array) and not isinstance(v.elements,bytes):
            for a in v.elements: visit(a)
        elif isinstance(v,GenericStruct):
            for a in v.fields: visit(a)
    visit(root); return result

def string(obj):
    if obj is None: return None
    if kind(obj) not in ('NSString','NSMutableString'): raise ValueError('not NSString')
    if len(obj.contents)!=1 or obj.contents[0].encodings!=[b'+']: raise ValueError('unsupported NSString layout')
    return obj.contents[0].value.decode('utf-8')

def elements(obj):
    if kind(obj) not in ('NSArray','NSMutableArray','OTMutableArray'): raise ValueError('not supported array class')
    if not obj.contents or obj.contents[0].encodings!=[b'i']: raise ValueError('unsupported array count')
    values=[]
    for g in obj.contents[1:]:
        if g.encodings!=[b'@']: raise ValueError('unsupported array layout')
        values.append(g.value)
    if obj.contents[0].value!=len(values): raise ValueError('array count mismatch')
    return values

def set_elements(obj,values):
    if obj.contents: elements(obj)
    elif kind(obj) not in ('NSArray','NSMutableArray','OTMutableArray'): raise ValueError('not supported array class')
    obj.contents=[TypedValue(b'i',len(values))]+[TypedValue(b'@',v) for v in values]
