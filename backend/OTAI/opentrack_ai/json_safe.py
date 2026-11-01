"""Strict JSON reports without discarding native nonfinite floating-point bits.

This affects response metadata only, never archive values or setter inputs.
"""
import json,math,struct

def json_safe(value):
    if isinstance(value,float) and not math.isfinite(value):
        from .current_archive.writer import WireFloat
        if isinstance(value,WireFloat):
            bits=value.bits if value.byte_order=='little' else value.bits[::-1]
            metadata={'encoding':value.encoding.decode('ascii'),'width_bits':len(bits)*8,'bits_le':bits.hex(),'bits_source':'native_archive'}
        else:
            metadata={'encoding':'d','width_bits':64,'bits_le':struct.pack('<d',value).hex(),'bits_source':'python_float_not_asserted_native_storage'}
        return {'native_nonfinite':'nan' if math.isnan(value) else ('positive_infinity' if value>0 else 'negative_infinity'),**metadata,'native_setter_semantics_claimed':False}
    if isinstance(value,dict):return {k:json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_safe(v) for v in value]
    return value

def checked_json(value):
    result=json_safe(value)
    json.dumps(result,ensure_ascii=False,allow_nan=False)
    return result
