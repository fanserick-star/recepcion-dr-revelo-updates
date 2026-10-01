from __future__ import annotations

import core_runtime
from reception_tv_service import APP_VERSION, TVTurnService

SERVICE = TVTurnService()

# Acceso rápido dentro de Recepción. No cambia atención, caja, facturación ni agenda.
TV_OVERLAY_CSS = r"""
#tvOfficialShortcut{position:fixed;right:18px;bottom:18px;z-index:2147482000;border:1px solid rgba(255,255,255,.22);background:#173a52;color:#fff;border-radius:12px;padding:10px 13px;font:800 12px/1.1 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.2);cursor:pointer}#tvOfficialShortcut:hover{background:#245877}
"""
TV_OVERLAY_JS = r"""
;(()=>{if(window.__tvOfficialInstalled)return;window.__tvOfficialInstalled=true;function boot(){if(document.getElementById('tvOfficialShortcut'))return;const b=document.createElement('button');b.id='tvOfficialShortcut';b.type='button';b.textContent='📺 Pantalla TV';b.title='Abrir En vivo / Pruebas de la pantalla de turnos';b.addEventListener('click',async()=>{try{const r=await fetch('/api/tv-turnos/health?t='+Date.now(),{cache:'no-store'});const d=await r.json();if(!d.ok){alert('Pantalla TV no inició. '+(d.error||'Revise el puerto 8899.'));return}}catch(_e){}window.open('http://127.0.0.1:8899/control','tv_turnos_control')});document.body.appendChild(b)}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot()})();
"""
core_runtime.V460_OVERLAY_CSS = (getattr(core_runtime, "V460_OVERLAY_CSS", "") or "") + "\n" + TV_OVERLAY_CSS
core_runtime.V460_OVERLAY_JS = (getattr(core_runtime, "V460_OVERLAY_JS", "") or "") + "\n" + TV_OVERLAY_JS

app = core_runtime.app


@app.on_event("startup")
def _start_official_tv_turn_service():
    SERVICE.start()


@app.get("/api/tv-turnos/health")
def tv_turnos_health(user=core_runtime.Depends(core_runtime.current_user)):
    return SERVICE.status()


PATCH_BOOT_OK = True
