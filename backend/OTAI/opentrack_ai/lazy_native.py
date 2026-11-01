"""Load optional native components only on invocation; never fake success."""
from importlib import import_module
from .errors import APIError



OPTIONAL_PREFIXES = ('typedstream', 'opentrack_', 'hsr_capacity_graph', 'native_text_schema')

class LazyComponent:
    def __init__(self, module, class_name, *args):
        self.module, self.class_name, self.args = module, class_name, args
        self.instance = None

    def __getattr__(self, name):
        def invoke(*args, **kwargs):
            if self.instance is None:
                try:
                    cls=getattr(import_module(self.module, __package__), self.class_name)
                    self.instance=cls(*self.args)
                except ModuleNotFoundError as exc:
                    if not exc.name or exc.name.startswith('opentrack_ai') or not exc.name.startswith(OPTIONAL_PREFIXES):
                        raise
                    raise APIError('NATIVE_DEPENDENCY_MISSING',
                        'Native archive operation is blocked: an optional legacy dependency is unavailable. Independent information generation remains available.',
                        {'status':'blocked', 'module':exc.name, 'component':self.module,
                         'native_simulation_verified':False}) from exc
            return getattr(self.instance, name)(*args, **kwargs)
        return invoke
