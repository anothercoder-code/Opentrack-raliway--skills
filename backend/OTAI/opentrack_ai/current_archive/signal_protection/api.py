"""Pure bytes API; caller supplies archive plus explicit SHA-256/spec."""
import hashlib
from .core import configure_route,inspect_protection,require

def generate_from_spec(data,spec):
    require(type(spec)==dict and set(spec)=={'input_sha256','configuration'},'Exact request keys required')
    require(type(data)==bytes and hashlib.sha256(data).hexdigest()==spec['input_sha256'],'Input SHA mismatch')
    return configure_route(data,spec['configuration'])
