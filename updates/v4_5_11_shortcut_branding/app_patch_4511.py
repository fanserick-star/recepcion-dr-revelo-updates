from __future__ import annotations

# v4.5.11 — acceso directo e identidad visual autorreparables.
# Conserva íntegro el runtime 4.5.10 y únicamente eleva la versión estable.

import app_patch_4510 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.11"

_mod = previous
_seen = set()
for _ in range(240):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)

core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = True
