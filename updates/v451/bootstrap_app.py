from __future__ import annotations
APP_VERSION = "4.3.51"
import hashlib, os, re, subprocess, sys, urllib.request, zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / "data" / "update_backups"
V450_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v450/bootstrap_app.py"
V450_GIT_BLOB = "56d510e83a90a3be6d3b808410c40bce092c83a0"

APP_MARKER = "# v4.3.51 — PROGRAM_UPDATE_API"
JS_MARKER = "/* v4.3.51 — professional agenda/settings enhancer */"
CSS_MARKER = "/* v4.3.51 — compact professional UI */"

PROGRAM_API = r'''

# v4.3.51 — PROGRAM_UPDATE_API
@app.post("/api/program/update-now")
def program_update_now():
    """Comprueba el canal oficial y, si hay una versión nueva, la instala y reinicia.

    El flujo reutiliza exactamente el mismo manifiesto de actualización del programa,
    verifica SHA-256, crea respaldo local y deja el arranque del bootstrap para después
    de responder al navegador. No toca bases de datos ni archivos clínicos.
    """
    import hashlib as _hashlib
    import json as _json
    import os as _os
    import subprocess as _subprocess
    import sys as _sys
    import threading as _threading
    import urllib.request as _urlrequest
    import zipfile as _zipfile
    from datetime import datetime as _datetime
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parent
    _url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json"

    def _ver(v):
        out=[]
        for p in str(v or "0").split("."):
            try: out.append(int(p))
            except Exception: out.append(0)
        return tuple((out+[0,0,0,0])[:4])

    def _download(url):
        req=_urlrequest.Request(str(url),headers={"User-Agent":"Recepcion-Dr-Revelo-program-update"})
        with _urlrequest.urlopen(req,timeout=20) as r:
            return r.read(2_000_000)

    try:
        manifest=_json.loads(_download(_url).decode("utf-8-sig"))
        latest=str(manifest.get("version") or "").strip()
        current=str(APP_VERSION)
        if not latest:
            return {"ok":False,"message":"El canal de actualización no informó una versión."}
        if _ver(latest) <= _ver(current):
            return {"ok":True,"update":False,"current":current,"latest":latest,"message":"El programa ya está actualizado."}

        files=list(manifest.get("files") or [])
        if not files:
            return {"ok":False,"message":"La actualización publicada no contiene archivos."}

        prepared=[]
        for item in files:
            rel=str(item.get("path") or "").replace("\\","/").lstrip("/")
            if not rel or ".." in rel.split("/"):
                raise RuntimeError("Ruta no válida en la actualización")
            if item.get("parts"):
                data=b"".join(_download(u) for u in item.get("parts") or [])
            elif item.get("url"):
                data=_download(item["url"])
            else:
                raise RuntimeError("Archivo sin origen: "+rel)
            want=str(item.get("sha256") or "").lower().strip()
            if want and _hashlib.sha256(data).hexdigest()!=want:
                raise RuntimeError("No se pudo verificar "+rel)
            prepared.append((rel,data))

        _backup=_root/"data"/"update_backups"
        _backup.mkdir(parents=True,exist_ok=True)
        z=_backup/("programa_antes_actualizacion_"+_datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
        with _zipfile.ZipFile(z,"w",_zipfile.ZIP_DEFLATED) as q:
            for rel,_data in prepared:
                p=_root/rel
                if p.exists(): q.write(p,rel)
            # app.py es imprescindible para que cualquier puente futuro pueda recuperar la versión anterior.
            ap=_root/"app.py"
            if ap.exists() and not any(rel=="app.py" for rel,_ in prepared): q.write(ap,"app.py")

        for rel,data in prepared:
            p=_root/rel; p.parent.mkdir(parents=True,exist_ok=True)
            t=p.with_name(p.name+".program_update_tmp")
            t.write_bytes(data); _os.replace(t,p)

        # El nuevo app.py es el bootstrap publicado. Espera a que esta respuesta salga,
        # luego cierra el proceso actual y deja que el bootstrap reinicie la aplicación.
        py=str(_sys.executable)
        app=str(_root/"app.py")
        code=("import os,sys,time; time.sleep(1.4); "
              "os.chdir("+repr(str(_root))+"); os.execv("+repr(py)+",["+repr(py)+","+repr(app)+"])")
        flags=getattr(_subprocess,"CREATE_NO_WINDOW",0)
        _subprocess.Popen([py,"-c",code],cwd=str(_root),creationflags=flags)
        _threading.Timer(0.65,lambda:_os._exit(0)).start()
        return {"ok":True,"update":True,"current":current,"latest":latest,"message":"Actualización encontrada. Reiniciando el programa…"}
    except Exception as e:
        return {"ok":False,"update":False,"current":str(APP_VERSION),"message":str(e)}
'''

JS_ADDON = r'''

/* v4.3.51 — professional agenda/settings enhancer */
(()=>{
  'use strict';
  const VERSION='4.3.51';
  const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
  const low=v=>norm(v).toLowerCase();
  let scheduled=0;
  function schedule(){clearTimeout(scheduled);scheduled=setTimeout(enhance,70)}
  function visible(el){if(!el||!el.isConnected)return false;const s=getComputedStyle(el);return s.display!=='none'&&s.visibility!=='hidden'}
  function panelOf(el){
    if(!el)return null;
    return el.closest('.settings-card,.config-card,.setting-card,.panel,.card,section,fieldset') || el.parentElement;
  }
  function textNodes(sel='h1,h2,h3,h4,legend,.section-title,.settings-title,.card-title,label'){
    return [...document.querySelectorAll(sel)].filter(visible);
  }
  function pageLooksLikeAgenda(){
    const body=low(document.body?.innerText||'');
    return body.includes('esta semana') && body.includes('pendiente') && body.includes('confirmada') && (body.includes('reagendada')||body.includes('disponible'));
  }
  function markAgenda(){
    document.body.classList.toggle('v451-agenda-active',pageLooksLikeAgenda());
    if(!document.body.classList.contains('v451-agenda-active'))return;
    const els=[...document.querySelectorAll('div,td,article')];
    for(const el of els){
      if(!visible(el))continue;
      const t=norm(el.textContent);
      if(!t||t.length>180)continue;
      const hit=/\bDisponible\b/i.test(t)||/\b(Pendiente|Confirmada|Reagendada|Cancelada|No asistirá)\b/i.test(t);
      if(!hit)continue;
      const r=el.getBoundingClientRect();
      if(r.width>70&&r.height>=28&&r.height<100)el.classList.add('v451-agenda-cell');
    }
  }
  function markSettings(){
    for(const el of textNodes()){
      const t=low(el.textContent);
      if(t==='whatsapp'||t.includes('whatsapp cloud'))panelOf(el)?.classList.add('v451-whatsapp-panel');
      if(t==='agenda'||t.includes('agenda 24/7')||t.includes('configuración de agenda'))panelOf(el)?.classList.add('v451-agenda-settings');
      if(t==='programa'||t.includes('acerca del programa'))panelOf(el)?.classList.add('v451-program-panel');
    }
    // Si el título está fuera de la tarjeta, marca la zona por contenido.
    for(const el of document.querySelectorAll('section,.settings-card,.config-card,.card,.panel')){
      if(!visible(el))continue;
      const t=low(el.textContent);
      if(t.length>8000)continue;
      if(t.includes('whatsapp')&&(t.includes('mensajes')||t.includes('plantilla')||t.includes('recordatorio')))el.classList.add('v451-whatsapp-panel');
      if(t.includes('agenda')&&(t.includes('24/7')||t.includes('enlace')||t.includes('doctor')))el.classList.add('v451-agenda-settings');
      if(t.includes('versión')&&(t.includes('programa')||t.includes('actualiz')))el.classList.add('v451-program-panel');
    }
  }
  function markWhatsAppMessages(){
    const tokens=['recordatorio_cita','recordatorio_hoy','cita_agendada'];
    for(const el of document.querySelectorAll('article,li,tr,.list-item,.message-row,.card,[class*="message"],[class*="event"],[class*="log-row"]')){
      if(!visible(el))continue;
      const t=low(el.textContent);
      if(tokens.some(x=>t.includes(x)) || (/\b(error|enviado|entregado|leído|pendiente)\b/.test(t)&&t.includes('2026-'))){
        const r=el.getBoundingClientRect();
        if(r.height>38&&r.height<260)el.classList.add('v451-whatsapp-message');
      }
    }
  }
  function hideLegacy(){
    const obsolete=['ENABLE_RECORDATORIO_CITA_LOGO','RECORDATORIO_CITA_HEADER_IMAGE_ID'];
    for(const el of document.querySelectorAll('.v451-whatsapp-panel label,.v451-whatsapp-panel span,.v451-whatsapp-panel code,.v451-whatsapp-panel .field,.v451-whatsapp-panel .form-row,.v451-whatsapp-panel tr,.v451-whatsapp-panel .setting-row')){
      const t=norm(el.textContent);
      if(obsolete.some(x=>t.includes(x))){
        const row=el.closest('.form-row,.field-row,.setting-row,tr,.field')||el;
        row.classList.add('v451-legacy-hidden');
      }
    }
  }
  function notify(msg,type){
    try{if(typeof window.toast==='function'){window.toast(msg,type==='error'?'error':undefined,5000);return}}catch(_e){}
    if(type==='error')alert(msg);
  }
  function addUpdateButton(){
    if(document.getElementById('v451-check-update'))return;
    let panel=document.querySelector('.v451-program-panel');
    if(!panel){
      const heading=textNodes().find(x=>low(x.textContent)==='programa');
      panel=panelOf(heading);
    }
    if(!panel)return;
    const host=panel.querySelector('.actions,.buttons,.settings-actions,.card-actions')||panel;
    const box=document.createElement('div');box.className='v451-update-box';
    box.innerHTML=`<div class="v451-update-copy"><b>Actualizaciones</b><span>Versión instalada ${VERSION}</span></div><button type="button" id="v451-check-update" class="v451-update-btn">Buscar actualizaciones</button>`;
    host.appendChild(box);
    box.querySelector('button').addEventListener('click',async e=>{
      const b=e.currentTarget;if(b.disabled)return;
      const old=b.textContent;b.disabled=true;b.textContent='Comprobando…';
      try{
        const r=await fetch('/api/program/update-now',{method:'POST',headers:{'Content-Type':'application/json'}});
        const d=await r.json();
        if(!r.ok||!d.ok)throw new Error(d.message||'No se pudo comprobar la actualización.');
        if(d.update){b.textContent='Actualizando…';notify('Actualización encontrada. El programa se reiniciará automáticamente.');}
        else{b.textContent='Programa actualizado';notify(d.message||'Ya tienes la versión más reciente.');setTimeout(()=>{b.disabled=false;b.textContent=old},1800)}
      }catch(err){b.disabled=false;b.textContent=old;notify(err.message||'No se pudo comprobar la actualización.','error')}
    });
  }
  function enhance(){
    document.body?.classList.add('v451-professional-ui');
    markAgenda();markSettings();markWhatsAppMessages();hideLegacy();addUpdateButton();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',enhance,{once:true});else enhance();
  new MutationObserver(schedule).observe(document.documentElement,{subtree:true,childList:true});
  window.addEventListener('hashchange',schedule);window.addEventListener('popstate',schedule);
})();
'''

CSS_ADDON = r'''

/* v4.3.51 — compact professional UI */
.v451-professional-ui .v451-whatsapp-panel,
.v451-professional-ui .v451-agenda-settings,
.v451-professional-ui .v451-program-panel{gap:10px!important;padding:14px!important}
.v451-professional-ui .v451-whatsapp-panel .v451-whatsapp-message{
  min-height:0!important;margin:5px 0!important;padding:8px 11px!important;border-radius:10px!important;
}
.v451-professional-ui .v451-whatsapp-panel .v451-whatsapp-message>*{margin-top:2px!important;margin-bottom:2px!important}
.v451-professional-ui .v451-whatsapp-panel table{border-collapse:separate!important;border-spacing:0 4px!important}
.v451-professional-ui .v451-whatsapp-panel th,.v451-professional-ui .v451-whatsapp-panel td{padding-top:7px!important;padding-bottom:7px!important}
.v451-professional-ui .v451-whatsapp-panel [class*="message-list"],
.v451-professional-ui .v451-whatsapp-panel [class*="messages-list"],
.v451-professional-ui .v451-whatsapp-panel [class*="event-list"]{gap:5px!important;row-gap:5px!important}
.v451-professional-ui .v451-whatsapp-panel p,
.v451-professional-ui .v451-agenda-settings p{margin-top:4px!important;margin-bottom:7px!important;line-height:1.35!important}
.v451-professional-ui .v451-whatsapp-panel .form-row,
.v451-professional-ui .v451-agenda-settings .form-row,
.v451-professional-ui .v451-whatsapp-panel .setting-row,
.v451-professional-ui .v451-agenda-settings .setting-row{margin-block:6px!important;gap:8px!important}
.v451-legacy-hidden{display:none!important}

/* Agenda principal: conserva legibilidad pero reduce aire vertical. */
body.v451-agenda-active .v451-agenda-cell{min-height:42px!important;height:auto!important;padding-top:4px!important;padding-bottom:4px!important}
body.v451-agenda-active [class*="agenda-slot"],
body.v451-agenda-active [class*="calendar-slot"],
body.v451-agenda-active [class*="time-slot"],
body.v451-agenda-active [class*="agenda-cell"],
body.v451-agenda-active [class*="agenda-row"],
body.v451-agenda-active [class*="calendar-row"],
body.v451-agenda-active [class*="schedule-row"]{min-height:42px!important;padding-top:4px!important;padding-bottom:4px!important}
body.v451-agenda-active [class*="appointment-card"],
body.v451-agenda-active [class*="agenda-appointment"],
body.v451-agenda-active [class*="appointment-item"]{padding:5px 8px!important;min-height:0!important}
body.v451-agenda-active table th,body.v451-agenda-active table td{padding-top:5px!important;padding-bottom:5px!important}
body.v451-agenda-active [class*="agenda-grid"],body.v451-agenda-active [class*="calendar-grid"]{row-gap:3px!important;grid-auto-rows:minmax(42px,auto)!important}

/* Bloque Programa: una sola acción clara para actualizar. */
.v451-update-box{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:11px 12px;border:1px solid #dfe6ee;border-radius:12px;background:#f8fafc}
.v451-update-copy{display:flex;flex-direction:column;gap:2px;min-width:0}.v451-update-copy b{font-size:12px}.v451-update-copy span{font-size:10.5px;color:#738096}
.v451-update-btn{border:0;border-radius:10px;padding:9px 13px;background:#173b68;color:#fff;font-weight:800;font-size:11px;cursor:pointer;white-space:nowrap}
.v451-update-btn:hover{filter:brightness(1.05)}.v451-update-btn:disabled{opacity:.65;cursor:wait}
@media(max-width:720px){.v451-update-box{align-items:stretch;flex-direction:column}.v451-update-btn{width:100%}}
'''

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name(path.name+".v451_tmp")
    tmp.write_bytes(data); os.replace(tmp,path)

def fetch_v450():
    req=urllib.request.Request(V450_URL,headers={"User-Agent":"Recepcion-Dr-Revelo-v451"})
    with urllib.request.urlopen(req,timeout=20) as r:data=r.read(100000)
    if git_blob_sha(data)!=V450_GIT_BLOB: raise RuntimeError("No se pudo verificar el puente v4.3.50.")
    return data

def ensure_v450():
    p=ROOT/"app.py"
    try: head=p.read_text(encoding="utf-8-sig",errors="ignore")[:500]
    except Exception: head=""
    if 'APP_VERSION = "4.3.50"' in head or "APP_VERSION='4.3.50'" in head or 'APP_VERSION="4.3.50"' in head:
        return
    helper=ROOT/"_v450_bridge.py"; atomic_write(helper,fetch_v450())
    env=dict(os.environ); env["RP_V450_NO_EXEC"]="1"
    try:
        r=subprocess.run([sys.executable,str(helper)],cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=120)
        if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout or "falló el puente v4.3.50")[-1400:])
    finally:
        try: helper.unlink()
        except Exception: pass

def backup(paths):
    BACKUP.mkdir(parents=True,exist_ok=True)
    z=BACKUP/("v451_antes_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as q:
        for p in paths:
            if p.exists(): q.write(p,p.relative_to(ROOT).as_posix())
    return z

def restore(z):
    try:
        with zipfile.ZipFile(z) as q:
            for n in q.namelist(): atomic_write(ROOT/n,q.read(n))
    except Exception: pass

def patch_app(data: bytes) -> bytes:
    text=data.decode("utf-8")
    if APP_MARKER in text:
        return data
    text2,n=re.subn(r'APP_VERSION\s*=\s*["\']4\.3\.50["\']','APP_VERSION = "4.3.51"',text,count=1)
    if n!=1: raise RuntimeError("app.py no está en la versión 4.3.50 esperada")
    m=re.search(r'(?m)^if\s+__name__\s*==\s*["\']__main__["\']\s*:',text2)
    if not m: raise RuntimeError("No encontré el arranque principal de app.py")
    text2=text2[:m.start()]+PROGRAM_API+"\n"+text2[m.start():]
    compile(text2,"app.py","exec")
    return text2.encode("utf-8")

def append_once(data: bytes, marker: str, addon: str) -> bytes:
    text=data.decode("utf-8")
    if marker in text:return data
    return (text.rstrip()+"\n"+addon.strip()+"\n").encode("utf-8")

def main():
    ensure_v450()
    ap=ROOT/"app.py"; jp=ROOT/"static"/"app.js"; cp=ROOT/"static"/"style.css"
    if not jp.exists() or not cp.exists(): raise RuntimeError("No encontré los recursos de interfaz del programa")
    fa=patch_app(ap.read_bytes()); fj=append_once(jp.read_bytes(),JS_MARKER,JS_ADDON); fc=append_once(cp.read_bytes(),CSS_MARKER,CSS_ADDON)
    z=backup([ap,jp,cp])
    try:
        atomic_write(jp,fj); atomic_write(cp,fc); atomic_write(ap,fa)
        if APP_MARKER not in ap.read_text(encoding="utf-8",errors="ignore"): raise RuntimeError("No se activó la actualización del programa")
        if JS_MARKER not in jp.read_text(encoding="utf-8",errors="ignore"): raise RuntimeError("No se activó la interfaz profesional")
        if CSS_MARKER not in cp.read_text(encoding="utf-8",errors="ignore"): raise RuntimeError("No se activaron los estilos compactos")
    except Exception:
        restore(z); raise
    if os.getenv("RP_V451_NO_EXEC")=="1":
        print("v4.3.51 reconstruida y verificada")
        return 0
    os.execv(sys.executable,[sys.executable,str(ap),*sys.argv[1:]])

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as e:
        print("No se pudo completar v4.3.51:",e,file=sys.stderr)
        raise
