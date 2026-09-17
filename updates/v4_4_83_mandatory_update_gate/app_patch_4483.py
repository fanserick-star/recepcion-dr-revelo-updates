from __future__ import annotations

# v4.4.83 — actualización obligatoria reforzada.
# - El launcher 4.4.83 bloquea el arranque de una versión vieja si ya detectó
#   una actualización obligatoria y la descarga/instalación falla.
# - Si Recepción está abierta y se vuelve a ejecutar el launcher, una actualización
#   obligatoria puede cerrar la ventana de forma normal y continuar instalando.
# - El botón interno usa siempre el launcher oficial.
# - Se conserva solo un respaldo automático: la versión inmediatamente anterior.
# - No cambia BD, AZUR, recibos, Agenda ni atenciones.

import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path

import app_patch_4482 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.83"

_mod = previous
_seen = set()
for _ in range(60):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

def _launch_official_launcher():
    launcher = _Path(core.BASE_DIR) / "ABRIR_RECEPCION.py"
    if not launcher.is_file():
        raise core.HTTPException(500, "No se encontró ABRIR_RECEPCION.py")
    candidates = [
        _Path(core.BASE_DIR) / ".venv" / "Scripts" / "pythonw.exe",
        _Path(core.BASE_DIR) / ".venv" / "Scripts" / "python.exe",
        _Path(_sys.executable),
    ]
    py = next((p for p in candidates if p.is_file()), None)
    if py is None:
        raise core.HTTPException(500, "No se encontró el Python de Recepción")
    flags = 0
    if _os.name == "nt":
        flags = getattr(_subprocess, "CREATE_NO_WINDOW", 0) | getattr(_subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        _subprocess.Popen(
            [str(py), str(launcher)],
            cwd=str(core.BASE_DIR),
            env=_os.environ.copy(),
            stdin=_subprocess.DEVNULL,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except Exception as exc:
        raise core.HTTPException(500, f"No se pudo abrir el actualizador: {type(exc).__name__}")
    return {"ok": True, "launcher_started": True, "version": APP_VERSION}

try:
    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _js = _re.sub(r"""const\s+VERSION\s*=\s*['"]4\.4\.\d+['"]\s*;""", "const VERSION='4.4.83';", _js)
    _js = _re.sub(r"""const\s+V\s*=\s*['"]4\.4\.\d+['"]\s*;""", "const V='4.4.83';", _js)

    V4483_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.83"!important;
  font-size:9px!important;line-height:1!important;font-weight:850!important
}
"""

    V4483_JS = r"""
;(()=>{
  if(window.__v4483MandatoryUpdater)return;
  window.__v4483MandatoryUpdater=true;
  const VERSION='4.4.83';

  async function installUpdate(){
    const status=document.querySelector('#updateStatus');
    try{
      if(status)status.textContent='Abriendo actualizador seguro…';
      const r=await fetch('/api/v4483/launch-updater',{
        method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'
      });
      const d=await r.json().catch(()=>({}));
      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||'No se pudo abrir el actualizador.');
      if(status)status.textContent='Actualizador abierto. Las versiones obligatorias se instalan antes de continuar.';
      return d;
    }catch(e){
      if(status)status.textContent=e?.message||String(e);
      throw e;
    }
  }

  function wire(){
    window.restartReception=installUpdate;
    document.querySelectorAll('button[onclick*="restartReception"]').forEach(btn=>{
      btn.textContent='⬆ Instalar actualización';
      btn.title='Comprueba e instala mediante el launcher oficial';
    });
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION; el.setAttribute('data-version','v'+VERSION);
    });
  }

  wire();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire,{once:true});
  setTimeout(wire,250);setTimeout(wire,900);
})();
"""

    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4483_CSS
    core.V460_OVERLAY_JS = _js + "\n" + V4483_JS

    # Reemplaza el reinicio heredado, que arrancaba app.py directamente.
    app.router.routes[:] = [
        route for route in app.router.routes
        if not (getattr(route, "path", None) == "/api/app/restart" and "POST" in (getattr(route, "methods", set()) or set()))
    ]

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.post("/api/app/restart")
def restart_v4483(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    return _launch_official_launcher()


@app.post("/api/v4483/launch-updater")
def launch_updater_v4483(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    return _launch_official_launcher()


@app.get("/api/v4483/health")
def v4483_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "mandatory_update_gate": True,
        "legacy_restart_redirected_to_launcher": True,
        "automatic_backup_retention": 1,
        "database_changes": False,
        "receipt_layout_version": "4.4.69",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )
