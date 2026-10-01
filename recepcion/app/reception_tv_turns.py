from __future__ import annotations

import core_runtime
from reception_tv_service import APP_VERSION, TVTurnService

SERVICE = TVTurnService()

# Acceso integrado dentro de Recepción. No cambia atención, caja, facturación ni agenda.
TV_OVERLAY_CSS = r"""
#tvOfficialShortcut{position:fixed;right:18px;bottom:18px;z-index:2147482000;border:1px solid rgba(255,255,255,.22);background:#173a52;color:#fff;border-radius:12px;padding:10px 13px;font:800 12px/1.1 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.2);cursor:pointer}#tvOfficialShortcut:hover{background:#245877}
#tvOfficialModal{position:fixed;inset:0;z-index:2147483000;display:none;align-items:stretch;justify-content:center;background:rgba(4,13,20,.76);backdrop-filter:blur(3px);padding:18px}#tvOfficialModal.tv-open{display:flex}#tvOfficialShell{width:min(1220px,98vw);height:calc(100vh - 36px);background:#0b1821;border:1px solid rgba(255,255,255,.22);border-radius:18px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.42);display:flex;flex-direction:column}#tvOfficialBar{height:48px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 16px;background:#112a36;border-bottom:1px solid rgba(255,255,255,.12);color:#fff;font:800 13px/1 system-ui,-apple-system,Segoe UI,sans-serif}#tvOfficialClose{border:0;background:#294a58;color:#fff;border-radius:9px;padding:8px 12px;font-weight:900;cursor:pointer}#tvOfficialFrame{width:100%;flex:1;border:0;background:#0b1821}
"""
TV_OVERLAY_JS = r"""
;(()=>{if(window.__tvOfficialInstalled)return;window.__tvOfficialInstalled=true;function closeTV(){const m=document.getElementById('tvOfficialModal');if(m)m.classList.remove('tv-open')}async function openTV(){try{const r=await fetch('/api/tv-turnos/health?t='+Date.now(),{cache:'no-store'});const d=await r.json();if(!d.ok){alert('Pantalla TV no inició. '+(d.error||'Revise el puerto 8899.'));return}}catch(_e){}const m=document.getElementById('tvOfficialModal'),f=document.getElementById('tvOfficialFrame');if(!m||!f)return;if(!f.src||f.src==='about:blank')f.src='http://127.0.0.1:8899/control?embedded=1';m.classList.add('tv-open')}function boot(){if(document.getElementById('tvOfficialShortcut'))return;const b=document.createElement('button');b.id='tvOfficialShortcut';b.type='button';b.textContent='📺 Pantalla TV';b.title='Abrir En vivo / Pruebas dentro de Recepción';b.addEventListener('click',openTV);document.body.appendChild(b);const m=document.createElement('div');m.id='tvOfficialModal';m.innerHTML='<div id="tvOfficialShell"><div id="tvOfficialBar"><span>📺 Pantalla TV · Recepción</span><button id="tvOfficialClose" type="button">Cerrar</button></div><iframe id="tvOfficialFrame" src="about:blank" title="Pantalla TV"></iframe></div>';m.addEventListener('click',e=>{if(e.target===m)closeTV()});document.body.appendChild(m);document.getElementById('tvOfficialClose').addEventListener('click',closeTV);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeTV()})}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot()})();
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
