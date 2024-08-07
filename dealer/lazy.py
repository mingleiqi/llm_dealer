import sys
import importlib.util

def lazy(fullname):
    if fullname in sys.modules:
        return sys.modules[fullname]  # 如果模块已加载，直接返回
    
    spec = importlib.util.find_spec(fullname)
    if spec is None:
        return None  # 模块未安装，返回 None
    
    module = importlib.util.module_from_spec(spec)
    loader = importlib.util.LazyLoader(spec.loader)
    sys.modules[fullname] = module  # 预先插入模块对象到 sys.modules
    loader.exec_module(module)
    return module
