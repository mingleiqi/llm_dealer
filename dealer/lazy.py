import sys
import importlib.util
from threading import Lock

_module_cache = {}
_module_cache_lock = Lock()

def lazy(fullname):
    with _module_cache_lock:
        if fullname in _module_cache:
            return _module_cache[fullname]

    try:
        spec = importlib.util.find_spec(fullname)
        if spec is None:
            raise ModuleNotFoundError(f"No module named '{fullname}'")

        module = importlib.util.module_from_spec(spec)
        loader = importlib.util.LazyLoader(spec.loader)
        loader.exec_module(module)

        with _module_cache_lock:
            _module_cache[fullname] = module

        return module
    except (ModuleNotFoundError, ImportError) as e:
        raise ImportError(f"Could not import module '{fullname}': {e}")
