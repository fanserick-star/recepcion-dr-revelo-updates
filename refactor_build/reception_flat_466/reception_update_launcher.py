from __future__ import annotations
import reception_update_restart as _dep_update_restart
import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path
core = _dep_update_restart.core
app = _dep_update_restart.app
APP_VERSION = '4.4.83'
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''

def _launch_official_launcher():
    launcher = _Path(core.BASE_DIR) / 'ABRIR_RECEPCION.py'
    if not launcher.is_file():
        raise core.HTTPException(500, 'No se encontró ABRIR_RECEPCION.py')
    candidates = [_Path(core.BASE_DIR) / '.venv' / 'Scripts' / 'pythonw.exe', _Path(core.BASE_DIR) / '.venv' / 'Scripts' / 'python.exe', _Path(_sys.executable)]
    py = next((p for p in candidates if p.is_file()), None)
    if py is None:
        raise core.HTTPException(500, 'No se encontró el Python de Recepción')
    flags = 0
    if _os.name == 'nt':
        flags = getattr(_subprocess, 'CREATE_NO_WINDOW', 0) | getattr(_subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    try:
        _subprocess.Popen([str(py), str(launcher)], cwd=str(core.BASE_DIR), env=_os.environ.copy(), stdin=_subprocess.DEVNULL, stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL, creationflags=flags, close_fds=True)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo abrir el actualizador: {type(exc).__name__}')
    return {'ok': True, 'launcher_started': True, 'version': APP_VERSION}
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.83';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.83';", _js)
    V4483_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.83"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4483_JS = '\n;(()=>{\n  if(window.__v4483MandatoryUpdater)return;\n  window.__v4483MandatoryUpdater=true;\n  const VERSION=\'4.4.83\';\n\n  async function installUpdate(){\n    const status=document.querySelector(\'#updateStatus\');\n    try{\n      if(status)status.textContent=\'Abriendo actualizador seguro…\';\n      const r=await fetch(\'/api/v4483/launch-updater\',{\n        method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:\'{}\',cache:\'no-store\'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||\'No se pudo abrir el actualizador.\');\n      if(status)status.textContent=\'Actualizador abierto. Las versiones obligatorias se instalan antes de continuar.\';\n      return d;\n    }catch(e){\n      if(status)status.textContent=e?.message||String(e);\n      throw e;\n    }\n  }\n\n  function wire(){\n    window.restartReception=installUpdate;\n    document.querySelectorAll(\'button[onclick*="restartReception"]\').forEach(btn=>{\n      btn.textContent=\'⬆ Instalar actualización\';\n      btn.title=\'Comprueba e instala mediante el launcher oficial\';\n    });\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION; el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n\n  wire();\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',wire,{once:true});\n  setTimeout(wire,250);setTimeout(wire,900);\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4483_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4483_JS
    app.router.routes[:] = [route for route in app.router.routes if not (getattr(route, 'path', None) == '/api/app/restart' and 'POST' in (getattr(route, 'methods', set()) or set()))]
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.post('/api/app/restart')
def restart_v4483(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta acción solo se ejecuta desde la PC de Recepción')
    return _launch_official_launcher()

@app.post('/api/v4483/launch-updater')
def launch_updater_v4483(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta acción solo se ejecuta desde la PC de Recepción')
    return _launch_official_launcher()

@app.get('/api/v4483/health')
def v4483_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'mandatory_update_gate': True, 'legacy_restart_redirected_to_launcher': True, 'automatic_backup_retention': 1, 'database_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
