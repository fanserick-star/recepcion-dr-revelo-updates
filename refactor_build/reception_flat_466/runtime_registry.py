import sys
import core_runtime

layers = {'app_base_4428': core_runtime}

def module_lookup(name, default=None):
    return layers.get(name, sys.modules.get(name, default))
