"""Explicit old namespace constructor adapter, not a permissive writer fallback.
The three batch slices never construct systems/diagrams; future static extraction
of their constructors must call this at the original TypedValue(b'*', raw) site.
"""
from opentrack_ai.current_archive import writer as w

def cstring_value(raw):
    if type(raw)is not bytes or b'\0' in raw:raise ValueError('CString requires exact NUL-free bytes')
    return w.TypedValue(b'*',w.CString(w.SharedString(raw)))
