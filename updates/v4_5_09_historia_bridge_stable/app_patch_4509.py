from __future__ import annotations

# v4.5.9 — release estable e inmutable del puente Recepción -> Historia Clínica.
# No vuelve a envolver la ruta de atención: reutiliza el puente validado de v4.5.8
# y únicamente eleva la versión visible/ejecutable a 4.5.9.

import app_patch_4508 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.9"

_mod = previous
_seen = set()
for _ in range(200):
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
