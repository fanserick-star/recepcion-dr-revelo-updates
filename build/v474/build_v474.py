from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "updates" / "v473"
OUT_DIR = ROOT / "updates" / "v474"
VERSION = "4.3.74"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_app() -> str:
    parts = sorted(SRC_DIR.glob("app.part*"), key=lambda p: int(p.name.replace("app.part", "")))
    if len(parts) != 7:
        raise SystemExit(f"Se esperaban 7 partes de v4.3.73 y hay {len(parts)}")
    return "".join(p.read_text(encoding="utf-8") for p in parts)


CAPTURE_JS = r''';(()=>{
  if(window.__v474CaptureFix)return;
  window.__v474CaptureFix=true;
  let billingBusy=false, deleteBusy=false;

  async function req(url, options={}){
    const opts={credentials:'same-origin',...options};
    if(options.body && !opts.headers)opts.headers={'Content-Type':'application/json'};
    const r=await fetch(url,opts);
    let data={};
    try{data=await r.json()}catch(_e){}
    if(!r.ok)throw new Error(data?.detail||data?.message||`Error HTTP ${r.status}`);
    return data;
  }
  function notice(msg,title='Recepción'){
    if(typeof window.rpNotice==='function')window.rpNotice(String(msg||''),title);
    else window.alert(String(msg||''));
  }
  async function ask(msg,title){
    if(typeof window.rpConfirm==='function')return !!(await window.rpConfirm(msg,title));
    return window.confirm(msg);
  }

  async function emitAll(btn){
    if(billingBusy)return;
    billingBusy=true;
    const old=btn?.textContent;
    try{
      if(btn){btn.disabled=true;btn.textContent='Revisando…'}
      const pre=await req('/api/billing/azur/batch-preview');
      const c=pre.counts||{}, ready=Number(c.ready||0), skipped=Number(c.skipped||0);
      if(!ready){notice(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`,'Facturación');return}
      const text=`¿Emitir ${ready} factura${ready===1?'':'s'} aprobada${ready===1?'':'s'} en AZUR?\n\nSe enviarán una por una para evitar duplicados. Las enviadas quedarán EN PROCESO hasta consultar la autorización del SRI.`;
      if(!(await ask(text,'Confirmar emisión en AZUR')))return;
      if(btn)btn.textContent='Enviando…';
      const result=await req('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}',headers:{'Content-Type':'application/json'}});
      const r=result.counts||{};
      let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
      const failed=(result.failed||[]).slice(0,5);
      if(failed.length)detail+='\n\nFallidas:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      notice('Lote procesado. Las enviadas quedan EN PROCESO hasta confirmar autorización SRI.\n\n'+detail,'AZUR');
      try{if(typeof window.loadBilling==='function')await window.loadBilling()}catch(_e){}
      try{if(typeof window.refreshPendingBadges==='function')await window.refreshPendingBadges()}catch(_e){}
    }catch(e){notice(e?.message||'No se pudo completar la emisión masiva.','Error de AZUR')}
    finally{billingBusy=false;if(btn){btn.disabled=false;btn.textContent=old||'Emitir todas'}}
  }

  async function removeAppointment(btn, kind, id){
    if(deleteBusy)return;
    deleteBusy=true;
    try{
      if(!(await ask('¿Eliminar esta cita y liberar el horario? La ficha del paciente no se borrará.','Eliminar cita')))return;
      if(btn)btn.disabled=true;
      const url=kind==='staged'?`/api/agenda/confirmafy-staged/${id}`:`/api/agenda/appointments/${id}`;
      await req(url,{method:'DELETE'});
      try{if(typeof window.closeModal==='function')window.closeModal()}catch(_e){}
      try{
        if(typeof window.loadAgendaWeek==='function')await window.loadAgendaWeek();
        else if(typeof window.loadAgenda==='function')await window.loadAgenda();
        else location.reload();
      }catch(_e){location.reload()}
    }catch(e){notice(e?.message||'No se pudo eliminar la cita.','Agenda')}
    finally{deleteBusy=false;if(btn)btn.disabled=false}
  }

  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('button');
    if(!btn)return;
    const label=String(btn.textContent||'').replace(/\s+/g,' ').trim();
    if(/emitir\s+todas/i.test(label)){
      e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
      void emitAll(btn);return;
    }
    if(/^eliminar cita$/i.test(label)){
      const onclick=String(btn.getAttribute('onclick')||'');
      let m=onclick.match(/deleteAgendaAppointment\((\d+)\)/i), kind='appointment';
      if(!m){m=onclick.match(/deleteUnlinkedAppointment\((\d+)\)/i);kind='staged'}
      if(!m)return;
      e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
      void removeAppointment(btn,kind,Number(m[1]));
    }
  },true);
})();'''


def patch_app(app: str) -> str:
    if app.count('APP_VERSION = "4.3.73"') != 1:
        raise SystemExit('No se encontró exactamente APP_VERSION 4.3.73')
    app = app.replace('APP_VERSION = "4.3.73"', f'APP_VERSION = "{VERSION}"', 1)

    old_visual = "const VERSION=\\'4.3.72\\';"
    if old_visual not in app:
        raise SystemExit('No se encontró la versión visual 4.3.72 del overlay')
    app = app.replace(old_visual, "const VERSION=\\'4.3.74\\';", 1)

    # CANCELADA histórica no equivale a una respuesta real NO_ASISTIRA.
    app = app.replace(
        "elif appointment_state in {\"NO_ASISTIRA\", \"CANCELADA\", \"CANCELADO\"}:\n                item[\"response\"] = \"Paciente indicó que no asistirá\"",
        "elif appointment_state == \"NO_ASISTIRA\":\n                item[\"response\"] = \"Paciente indicó que no asistirá\"",
        1,
    )

    route_marker='@app.get("/v460/overlay.css")'
    if app.count(route_marker)!=1:
        raise SystemExit('No se encontró el punto de inserción del overlay')
    injected=(
        'V474_CAPTURE_FIX_JS = r"""'+CAPTURE_JS+'"""\n'
        'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V474_CAPTURE_FIX_JS\n\n'
        + route_marker
    )
    app=app.replace(route_marker,injected,1)
    return app


def write_parts(app: str) -> list[str]:
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    for p in OUT_DIR.glob('app.part*'): p.unlink()
    n=7; step=math.ceil(len(app)/n); names=[]
    for i in range(n):
        name=f'app.part{i+1}'
        (OUT_DIR/name).write_text(app[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    rebuilt=''.join((OUT_DIR/n).read_text(encoding='utf-8') for n in names)
    if rebuilt!=app: raise SystemExit('Las partes no reconstruyen app.py')
    return names


def main() -> None:
    app=patch_app(read_app())
    compile(app,'app.py','exec')
    tree=ast.parse(app)
    hotfix=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='V474_CAPTURE_FIX_JS' for t in node.targets):
            hotfix=ast.literal_eval(node.value);break
    if not hotfix: raise SystemExit('No quedó V474_CAPTURE_FIX_JS')
    assert "document.addEventListener('click'" in hotfix and '},true);' in hotfix
    assert '/api/billing/azur/emit-all-pending' in hotfix
    assert 'stopImmediatePropagation' in hotfix
    assert "window.rpConfirm" in hotfix
    assert 'APP_VERSION = "4.3.74"' in app
    assert "const VERSION=\\'4.3.74\\';" in app
    assert "const VERSION=\\'4.3.72\\';" not in app

    parts=write_parts(app); app_bytes=app.encode('utf-8')
    manifest={
      'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
      'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher',
      'copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (OUT_DIR/'update_manifest.json').write_bytes(manifest_bytes)

    current=json.loads((ROOT/'latest.json').read_text(encoding='utf-8'))
    launcher=next(x for x in current['files'] if x.get('path')=='ABRIR_RECEPCION.py')
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v474/'
    latest={
      'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3',
      'message':'v4.3.74: corrige el número visual de versión, elimina los cuadros nativos de Agenda y ejecuta Emitir todas en AZUR por una ruta directa sin rebotes.',
      'files':[launcher,
        {'path':'app.py','parts':[base+n for n in parts],'sha256':sha(app_bytes),'encoding':'utf-8'},
        {'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(manifest_bytes),'encoding':'utf-8'}]}
    text=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'
    (ROOT/'latest.json').write_text(text,encoding='utf-8',newline='')
    (ROOT/'latest-v3.json').write_text(text,encoding='utf-8',newline='')
    print('OK',VERSION,sha(app_bytes),len(app_bytes))

if __name__=='__main__': main()
