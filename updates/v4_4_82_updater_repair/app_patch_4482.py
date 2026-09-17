from __future__ import annotations

# v4.4.82 — reparación del flujo de actualización/reinicio.
# - Conserva v4.4.81 y el arreglo de Emitidas.
# - El botón "Reiniciar Recepción" heredado reiniciaba app.py directamente,
#   por lo que nunca pasaba por ABRIR_RECEPCION.py y no instalaba el canal nuevo.
# - Añade una acción local que relanza el launcher oficial.
# - No cambia BD, AZUR, recibos, Agenda ni guardado de atención.

import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path

import app_patch_4481 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.82"

_mod = previous
_seen = set()
for _ in range(56):
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

try:
    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const VERSION='4.4.82';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const V='4.4.82';",
        _js,
    )

    V4482_CSS = r"""
/* v4.4.82 — actualización pasa por el launcher oficial */
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.82"!important;
  font-size:9px!important;line-height:1!important;font-weight:850!important
}
"""

    V4482_JS = r"""
;(()=>{
  if(window.__v4482LauncherUpdateRepair)return;
  window.__v4482LauncherUpdateRepair=true;
  const VERSION='4.4.82';

  async function launchOfficialUpdater(){
    const status=document.querySelector('#updateStatus');
    try{
      if(status)status.textContent='Abriendo el actualizador seguro…';
      const r=await fetch('/api/v4482/launch-updater',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:'{}',
        cache:'no-store'
      });
      const d=await r.json().catch(()=>({}));
      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||'No se pudo abrir el actualizador.');
      if(status)status.textContent='Actualizador abierto. Si hay una versión nueva, se instalará automáticamente.';
      return d;
    }catch(e){
      if(status)status.textContent=e?.message||String(e);
      throw e;
    }
  }

  function installRestartOverride(){
    window.restartReception=launchOfficialUpdater;
    document.querySelectorAll('button[onclick*="restartReception"]').forEach(btn=>{
      btn.textContent='⬆ Instalar actualización';
      btn.title='Abre el launcher oficial para comprobar e instalar la versión nueva';
    });
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
  }

  installRestartOverride();
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',installRestartOverride,{once:true});
  }
  setTimeout(installRestartOverride,250);
  setTimeout(installRestartOverride,900);
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4482_CSS
    )
    core.V460_OVERLAY_JS = _js + "\n" + V4482_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.82 launcher update repair failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.post("/api/v4482/launch-updater")
def v4482_launch_updater(
    request: core.Request,
    user=core.Depends(core.current_user),
):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")

    launcher = _Path(core.BASE_DIR) / "ABRIR_RECEPCION.py"
    if not launcher.is_file():
        raise core.HTTPException(500, "No se encontró ABRIR_RECEPCION.py")

    python_candidates = [
        _Path(core.BASE_DIR) / ".venv" / "Scripts" / "pythonw.exe",
        _Path(core.BASE_DIR) / ".venv" / "Scripts" / "python.exe",
        _Path(_sys.executable),
    ]
    python_exe = next((p for p in python_candidates if p.is_file()), None)
    if python_exe is None:
        raise core.HTTPException(500, "No se encontró el Python de Recepción")

    flags = 0
    if _os.name == "nt":
        flags = getattr(_subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            _subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        _subprocess.Popen(
            [str(python_exe), str(launcher)],
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

    return {
        "ok": True,
        "version": APP_VERSION,
        "launcher_started": True,
        "message": "Se abrió el launcher oficial de Recepción.",
    }


@app.get("/api/v4482/health")
def v4482_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "restart_button_uses_launcher": True,
        "billing_emitidas_fix_preserved": True,
        "facturero_removed_globally": True,
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
