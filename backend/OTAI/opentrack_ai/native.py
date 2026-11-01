"""Read-only classic Objective-C metadata and bounded instruction windows."""
from pathlib import Path

from .archive import APIError,digest,page


def binary_path(root,name):
    paths={'opentrack':Path(root)/'OpenTrack.app/OpenTrack.exe',
        'foundation':Path('C:/NEXT/NextLibrary/Executables/Foundation.dll'),
        'appkit':Path('C:/NEXT/NextLibrary/Executables/AppKit.dll')}
    path=paths[name]
    if not path.is_file():raise APIError('BINARY_MISSING','Native binary is unavailable.',str(path))
    return path


def resolve(root,args):
    from audit_binary import Image
    path=binary_path(root,args.binary);image=Image(path)
    try:result=image.find_category(args.class_name,args.category) if args.category else image.find_class(args.class_name)
    except (TypeError,ValueError) as error:
        raise APIError('NATIVE_METADATA_INVALID','A classic Objective-C metadata candidate could not be parsed.',str(error)[:240]) from error
    if 'error' in result:
        raise APIError('CATEGORY_NOT_FOUND' if args.category else 'CLASS_NOT_FOUND',
            'Requested class/category was not found in the selected module.',{'binary':args.binary,'class':args.class_name,'category':args.category})
    return path,image,result


def disassemble(root,args):
    from capstone import Cs,CS_ARCH_X86,CS_MODE_32
    path,image,metadata=resolve(root,args)
    methods=[dict(row,method_kind='instance') for row in metadata.get('methods',[])]+[dict(row,method_kind='class') for row in metadata.get('class_methods',[])]
    matches=[row for row in methods if row['name']==args.selector and row['method_kind']==args.method_kind]
    if not matches:raise APIError('METHOD_NOT_FOUND','Resolve an exact selector and method_kind using opentrack_get_native_class first.')
    if len(matches)!=1:raise APIError('AMBIGUOUS_METHOD','More than one metadata entry matches the selected method.')
    if image.pe.OPTIONAL_HEADER.Magic!=0x10b:raise APIError('UNSUPPORTED_BINARY','Only the audited PE32/x86 instruction format is supported.')
    method=matches[0];address=int(method['imp'],0);rva=address-image.base
    section=image.pe.get_section_by_rva(rva)
    if section is None or not section.Characteristics&0x20000000:
        raise APIError('METHOD_NOT_EXECUTABLE','Method address is outside an executable PE section.')
    raw_end=section.VirtualAddress+section.SizeOfRawData+image.base
    next_methods=[int(row['imp'],0) for row in methods if int(row['imp'],0)>address]
    boundaries=[(address+args.max_bytes,'byte_window'),(raw_end,'section_boundary')]
    if next_methods:boundaries.append((min(next_methods),'next_known_method'))
    end,reason=min(boundaries)
    if end<=address:raise APIError('METHOD_NOT_EXECUTABLE','Method address has no backed executable bytes.')
    code=image.read(address,end-address);instructions=[]
    for instruction in Cs(CS_ARCH_X86,CS_MODE_32).disasm(code,address):
        instructions.append({'address':hex(instruction.address),'bytes':instruction.bytes.hex(),
            'mnemonic':instruction.mnemonic,'operands':instruction.op_str})
        if instruction.mnemonic.startswith(('ret','iret')):
            reason='first_return';break
    return {'binary':str(path),'binary_sha256':digest(path.read_bytes()),'class':args.class_name,'category':args.category,
        'selector':args.selector,'method_kind':args.method_kind,'method_address':hex(address),'types':method['types'],
        'instructions':page(instructions,args.limit,args.offset),'stop_reason':reason,'requested_max_bytes':args.max_bytes,
        'complete_function':False,'native_code_executed':False,
        'evidence_level':'Read-only PE instruction window. Early returns and other branches may lie outside this window; metadata is not a complete decompilation or callable wrapper.'}
