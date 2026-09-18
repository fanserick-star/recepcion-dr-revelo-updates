from __future__ import annotations

# v4.5.0 — runtime consolidado.
# Conserva exactamente la base funcional aprobada hasta v4.4.91, pero los
# parches históricos pasan a dos paquetes de fuente en vez de 31 archivos
# ejecutables encadenados. app_base_4428.py se mantiene separado por seguridad
# y compatibilidad de rollback.

import gc
import os
import sys
import types

import app_base_4428  # base estable y pesada, mantenida como archivo independiente
from runtime_pack_a_4500 import SOURCES as _SOURCES_A, ORDER as _ORDER_A
from runtime_pack_b_4500 import SOURCES as _SOURCES_B, ORDER as _ORDER_B

APP_VERSION = "4.5.0"
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_legacy_module(name: str, source: str):
    module = types.ModuleType(name)
    module.__file__ = os.path.join(_BASE_DIR, name + ".py")
    module.__package__ = ""
    sys.modules[name] = module
    code = compile(source, module.__file__, "exec")
    exec(code, module.__dict__)
    return module


# app_base_4428 ya está en sys.modules; el resto se reconstruye en memoria en
# el mismo orden probado por la cadena v4.4.91.
for _name in list(_ORDER_A):
    _load_legacy_module(_name, _SOURCES_A[_name])
for _name in list(_ORDER_B):
    _load_legacy_module(_name, _SOURCES_B[_name])

legacy = sys.modules["app_patch_4491"]
core = legacy.core
app = legacy.app

# Una sola versión canónica para todos los módulos que aún exponen APP_VERSION.
for _name in ["app_base_4428", *_ORDER_A, *_ORDER_B]:
    _module = sys.modules.get(_name)
    if _module is not None:
        try:
            _module.APP_VERSION = APP_VERSION
        except Exception:
            pass
try:
    core.APP_VERSION = APP_VERSION
except Exception:
    pass

CONSOLIDATED_RUNTIME = True
CONSOLIDATED_LEGACY_MODULES = len(_ORDER_A) + len(_ORDER_B)
DISTRIBUTED_RUNTIME_FILES = 4  # base + 2 packs + este loader

# Las cadenas de fuente ya no hacen falta después del arranque. Liberarlas evita
# retener cerca de medio MB extra en la PC antigua.
try:
    _SOURCES_A.clear()
    _SOURCES_B.clear()
except Exception:
    pass
try:
    sys.modules.pop("runtime_pack_a_4500", None)
    sys.modules.pop("runtime_pack_b_4500", None)
except Exception:
    pass
gc.collect()

del _name, _module
