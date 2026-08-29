from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_SRC = ROOT / "updates" / "v474"
LAUNCHER_SRC = ROOT / "updates" / "v457"
OUT_DIR = ROOT / "updates" / "v475"
VERSION = "4.3.75"
LAUNCHER_VERSION = "4.3.75-standalone-2"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def joined_parts(folder: Path, prefix: str, expected: int) -> str:
    parts = sorted(folder.glob(prefix + "*"), key=lambda p: int(p.name.replace(prefix, "")))
    if len(parts) != expected:
        raise SystemExit(f"Se esperaban {expected} partes {prefix} en {folder} y hay {len(parts)}")
    return "".join(p.read_text(encoding="utf-8") for p in parts)


BILLING_APPROVE_ONE_STEP = r'''@app.post("/api/billing/approve")
def billing_approve(data: BillingGroupIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """v4.3.75: revisar + aprobar + enviar a AZUR en una sola operación.

    La interfaz ya no expone un estado APROBADA intermedio. Internamente las
    líneas quedan APROBADA únicamente después de que AZUR acepta el comprobante,
    mientras la autorización del SRI se consulta con el flujo existente. Si AZUR
    falla, las líneas permanecen como estaban para poder corregir/reintentar sin
    dejar una pre-factura atrapada a mitad del proceso.
    """
    if not AZUR_LIVE_EMISSION:
        raise HTTPException(403, "La emisión real de AZUR está desactivada")
    if is_offline_db(db):
        raise HTTPException(503, "Revisar y emitir requiere conexión a Internet")
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "AZUR todavía no está configurado")

    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    data = _apply_billing_preference(data, db)
    validate_billing_recipient(data, p)

    rows = billing_group_records(db, data.patient_id, data.fecha)
    if not rows:
        raise HTTPException(404, "No hay atenciones por facturar para ese día")
    invalid = [str(b.estado or "").upper() for b, _v in rows if str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"}]
    if invalid:
        raise HTTPException(409, "Esta factura ya no está disponible para emitir")

    group_key = _azur_group_key_for_rows(int(data.patient_id), data.fecha, rows)
    existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
    if existing and existing.clave_acceso:
        raise HTTPException(409, "Esta factura ya fue enviada a AZUR. Usa Actualizar estado para consultar el SRI.")

    payload = _azur_payload_for_group(data, p, rows)
    request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    try:
        result = azur_emit_invoice(AZUR_BASE_URL, AZUR_API_KEY, payload, timeout=25)
        response = result.get("data") if isinstance(result, dict) else {}
        response = response if isinstance(response, dict) else {}
        access_key = str(response.get("claveacceso") or response.get("clave_acceso") or "").strip() or None
        invoice_number = str(response.get("numero_factura") or response.get("numero_comprobante") or response.get("numero") or "").strip() or None
        if response.get("creado") is not True or not access_key:
            raise AzurError("AZUR no devolvió creado=true con una clave de acceso")
    except AzurError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"No se pudo enviar la factura a AZUR: {str(exc)[:260]}")

    invoice_number = _azur_invoice_number_from_access_key(access_key) or invoice_number
    now = datetime.utcnow()
    record = existing or AzurEmission(group_key=group_key, patient_id=int(data.patient_id), fecha=data.fecha)
    if not existing:
        db.add(record)
    record.estado = "EN_PROCESO"
    record.clave_acceso = access_key
    record.numero_factura = invoice_number
    record.request_hash = request_hash
    record.updated_at = now
    record.response_json = _azur_pack_response(response, rows)

    touched = []
    for b, _v in rows:
        b.estado = "APROBADA"
        b.approved_at = now
        b.numero_factura = None
        b.emitted_at = None
        touched.append(b)

    audit(db, user, "revisar_emitir_factura_azur", f"Paciente {data.patient_id}, {data.fecha}, AZUR {invoice_number or access_key[-8:]}")
    db.commit()
    mirror_azur_emission_to_local(record)
    for b in touched:
        mirror_billing_to_local(b)
    return {
        "ok": True,
        "estado": "EN_PROCESO",
        "numero_factura": invoice_number,
        "clave_acceso": access_key,
        "message": "Factura revisada y enviada a AZUR. Queda EN PROCESO hasta confirmar autorización del SRI.",
    }


'''

MERGED_ACTION_COUNTS = r'''def _billing_action_counts(db: Session) -> dict[str, int]:
    """Cuenta una sola cola visible: POR EMITIR.

    PENDIENTE y APROBADA se conservan internamente por compatibilidad, pero desde
    v4.3.75 ambas significan una única acción para Recepción: revisar y emitir.
    """
    grouped = (
        select(
            Visit.patient_id.label("patient_id"),
            Visit.fecha.label("fecha"),
            func.max(case((BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]), 1), else_=0)).label("needs_action"),
        )
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE)
        .group_by(Visit.patient_id, Visit.fecha)
        .subquery()
    )
    total = int(db.scalar(select(func.coalesce(func.sum(grouped.c.needs_action), 0))) or 0)
    return {"pending": total, "approved": 0, "total": total}


'''

BILLING_UI_CSS = r'''
/* v4.3.75 — Facturación simplificada */
.v475-hidden{display:none!important}
.v475-sri-compact{background:transparent!important;border:0!important;border-top:1px solid #e5ebf2!important;border-radius:0!important;padding:10px 0 2px!important;margin:8px 0 0!important;box-shadow:none!important}
.v475-sri-line{display:flex;align-items:center;gap:8px;font-size:12px;color:#52647a;line-height:1.3}
.v475-sri-chip{display:inline-flex;align-items:center;justify-content:center;min-width:34px;padding:3px 7px;border-radius:999px;background:#eef3f8;color:#50657e;font-size:9px;font-weight:900;letter-spacing:.06em}
.v475-sri-line strong{font-size:12px;color:#344960;font-weight:800}
.v475-sri-compact.authorized .v475-sri-chip{background:#e7f6ec;color:#237045}
.v475-sri-compact.authorized .v475-sri-line strong{color:#286849}
.v475-sri-compact.process .v475-sri-chip{background:#eef4ff;color:#456b9c}
.v475-sri-compact.rejected .v475-sri-chip{background:#fff0ef;color:#a04a45}
.v475-action-button{font-weight:800!important}
'''

BILLING_UI_JS = r''';(()=>{
  if(window.__v475BillingUi)return;
  window.__v475BillingUi=true;
  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  let busy=false;

  function exactElements(text){
    const wanted=norm(text);
    return [...document.querySelectorAll('span,b,strong,label,small,option,button,h2,h3,p')].filter(el=>norm(el.textContent)===wanted);
  }
  function cardFor(el){
    return el?.closest?.('[class*="stat"],[class*="summary"],[class*="metric"],[class*="counter"],.card') || el?.parentElement?.parentElement || el?.parentElement;
  }
  function simplifyMetrics(){
    for(const el of exactElements('Pendientes')) el.textContent='Por emitir';
    for(const el of exactElements('Aprobadas')){
      const card=cardFor(el); if(card)card.classList.add('v475-hidden'); else el.classList.add('v475-hidden');
    }
  }
  function simplifySelects(){
    for(const sel of document.querySelectorAll('select')){
      const opts=[...sel.options], labels=opts.map(o=>norm(o.textContent));
      if(!labels.some(x=>x==='emitidas') || !labels.some(x=>x==='pendientes'))continue;
      for(const o of opts){
        const t=norm(o.textContent);
        if(t==='pendientes')o.textContent='Por emitir';
        if(t==='aprobadas')o.remove();
      }
      if(String(sel.value||'').toUpperCase()==='APROBADA'){
        sel.value='PENDIENTE';
        setTimeout(()=>sel.dispatchEvent(new Event('change',{bubbles:true})),0);
      }
    }
  }
  function simplifyActions(){
    for(const btn of document.querySelectorAll('button')){
      const t=norm(btn.textContent);
      if(t==='aprobar' || t==='aprobar factura' || t==='confirmar aprobacion' || t==='confirmar aprobación'){
        btn.textContent='Revisar y emitir';btn.classList.add('v475-action-button');
      }
      if(t.includes('aprobar todas') || t.includes('emitir todas') || t==='volver a pendiente')btn.classList.add('v475-hidden');
    }
    for(const el of [...document.querySelectorAll('span,b,strong,small')]){
      const t=norm(el.textContent);
      if(t==='pendiente' || t==='aprobada')el.textContent='POR EMITIR';
    }
  }
  function compactSri(){
    for(const label of [...document.querySelectorAll('b,strong,span')]){
      if(norm(label.textContent)!=='estado azur / sri')continue;
      let box=label.parentElement;
      if(!box)continue;
      if(box.parentElement && /actualizar estado|consulta nuevamente|autorizada por sri|en proceso|rechaz/i.test(norm(box.parentElement.textContent)))box=box.parentElement;
      if(box.dataset.v475Sri==='1')continue;
      const txt=norm(box.textContent);
      let state='Estado registrado', cls='process';
      if(txt.includes('autorizada')){state='Autorizada por SRI';cls='authorized'}
      else if(txt.includes('rechaz')){state='Rechazada por SRI';cls='rejected'}
      else if(txt.includes('proceso')){state='En proceso en SRI';cls='process'}
      else if(txt.includes('devuelta')){state='Devuelta por SRI';cls='rejected'}
      box.dataset.v475Sri='1';
      box.classList.add('v475-sri-compact',cls);
      box.innerHTML=`<div class="v475-sri-line"><span class="v475-sri-chip">SRI</span><strong>${state}</strong></div>`;
    }
  }
  function copyText(){
    for(const p of [...document.querySelectorAll('p')]){
      const t=norm(p.textContent);
      if(t==='revisa, aprueba y emite directamente en azur.')p.textContent='Revisa los datos y emite directamente en AZUR.';
    }
  }
  function apply(){if(busy)return;busy=true;try{copyText();simplifySelects();simplifyMetrics();simplifyActions();compactSri()}finally{busy=false}}

  // El endpoint /api/billing/approve ahora realiza toda la operación. Solo
  // adaptamos mensajes viejos de la interfaz para que no diga "aprobada".
  const oldNotice=window.rpNotice;
  if(typeof oldNotice==='function')window.rpNotice=function(msg,title){
    let text=String(msg||'');
    if(/factura.+aprob/i.test(text))text='Factura revisada y enviada a AZUR.';
    return oldNotice.call(this,text,title);
  };

  const observer=new MutationObserver(()=>queueMicrotask(apply));
  observer.observe(document.documentElement,{childList:true,subtree:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply,{once:true});else apply();
  setTimeout(apply,250);setTimeout(apply,900);
})();'''


def patch_app(app: str) -> str:
    if app.count('APP_VERSION = "4.3.74"') != 1:
        raise SystemExit('No se encontró exactamente APP_VERSION 4.3.74')
    app = app.replace('APP_VERSION = "4.3.74"', f'APP_VERSION = "{VERSION}"', 1)
    visual = "const VERSION=\\'4.3.74\\';"
    if visual not in app:
        raise SystemExit('No se encontró versión visual 4.3.74')
    app = app.replace(visual, "const VERSION=\\'4.3.75\\';", 1)

    # Reemplaza aprobación individual por revisar+emitir atómico.
    start = app.find('@app.post("/api/billing/approve")\ndef billing_approve(')
    end = app.find('@app.post("/api/billing/approve-all-pending")', start)
    if start < 0 or end < 0:
        raise SystemExit('No se pudo localizar billing_approve')
    app = app[:start] + BILLING_APPROVE_ONE_STEP + app[end:]

    # Unifica contadores PENDIENTE/APROBADA en una sola cola visible.
    cstart = app.find('def _billing_action_counts(db: Session) -> dict[str, int]:')
    cend = app.find('def _billing_pending_count(db: Session) -> int:', cstart)
    if cstart < 0 or cend < 0:
        raise SystemExit('No se pudo localizar _billing_action_counts')
    app = app[:cstart] + MERGED_ACTION_COUNTS + app[cend:]

    old_counts = '''    counts = {\n        "PENDIENTE": sum(1 for st in states.values() if "PENDIENTE" in st),\n        "APROBADA": sum(1 for st in states.values() if "PENDIENTE" not in st and "APROBADA" in st),\n        "EMITIDA": sum(1 for st in states.values() if "EMITIDA" in st),\n        "RECHAZADA": sum(1 for key in groups if any(str(x.estado or "").upper() == "RECHAZADA" for x in emission_groups.get(key, []))),\n    }'''
    new_counts = '''    counts = {\n        "PENDIENTE": sum(1 for st in states.values() if "PENDIENTE" in st or "APROBADA" in st),\n        "APROBADA": 0,\n        "EMITIDA": sum(1 for st in states.values() if "EMITIDA" in st),\n        "RECHAZADA": sum(1 for key in groups if any(str(x.estado or "").upper() == "RECHAZADA" for x in emission_groups.get(key, []))),\n    }'''
    if old_counts not in app:
        raise SystemExit('No se encontró bloque counts de billing_list')
    app = app.replace(old_counts, new_counts, 1)

    old_filter = '''    if requested == "PENDIENTE":\n        rows = [r for r in all_rows if str(r[0].estado or "").upper() == "PENDIENTE"]\n    elif requested == "APROBADA":\n        rows = [r for r in all_rows if str(r[0].estado or "").upper() == "APROBADA"]'''
    new_filter = '''    if requested in {"PENDIENTE", "APROBADA"}:\n        # Compatibilidad: ambos filtros antiguos muestran la única cola POR EMITIR.\n        for key, grouped_rows in groups.items():\n            st = states[key]\n            if "PENDIENTE" in st:\n                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "PENDIENTE")\n            elif "APROBADA" in st:\n                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "APROBADA")'''
    if old_filter not in app:
        raise SystemExit('No se encontró filtro PENDIENTE/APROBADA')
    app = app.replace(old_filter, new_filter, 1)

    route_marker='@app.get("/v460/overlay.css")'
    if app.count(route_marker)!=1:
        raise SystemExit('No se encontró punto del overlay')
    injected=(
        'V475_BILLING_CSS = r"""'+BILLING_UI_CSS+'"""\n'
        'V475_BILLING_JS = r"""'+BILLING_UI_JS+'"""\n'
        'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V475_BILLING_CSS\n'
        'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V475_BILLING_JS\n\n'
        + route_marker
    )
    app = app.replace(route_marker, injected, 1)
    return app


def patch_launcher(src: str) -> str:
    old='LAUNCHER_VERSION = "4.3.57-standalone-1"'
    if src.count(old)!=1:
        raise SystemExit('No se encontró LAUNCHER_VERSION base')
    src=src.replace(old,f'LAUNCHER_VERSION = "{LAUNCHER_VERSION}"',1)
    old_logo='''            c = tk.Canvas(top, width=54, height=54, bg="#ffffff", highlightthickness=0)\n            c.pack(side="left", padx=(0, 13))\n            c.create_oval(8, 8, 24, 34, fill="#70b957", outline="")\n            c.create_oval(30, 8, 46, 34, fill="#70b957", outline="")\n            c.create_arc(16, 22, 38, 48, start=200, extent=140, style="arc", width=3, outline="#0d6d88")\n            c.create_oval(18, 38, 36, 49, outline="#1683ad", width=2)'''
    new_logo='''            # Marca limpia para el splash. El icono real de la ventana sigue\n            # usando static/doctor_icon.ico; evitamos redibujarlo a mano porque\n            # el dibujo anterior se deformaba y parecía una cara.\n            c = tk.Canvas(top, width=54, height=54, bg="#13213c", highlightthickness=0)\n            c.pack(side="left", padx=(0, 13))\n            c.create_oval(4, 4, 50, 50, fill="#ffffff", outline="#d8e3f0", width=1)\n            c.create_text(27, 23, text="AR", font=("Segoe UI", 13, "bold"), fill="#13213c")\n            c.create_line(15, 37, 39, 37, fill="#1683ad", width=3)'''
    if old_logo not in src:
        raise SystemExit('No se encontró el dibujo antiguo del splash')
    return src.replace(old_logo,new_logo,1)


def write_parts(text: str, prefix: str, count: int) -> list[str]:
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    for p in OUT_DIR.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/count); names=[]
    for i in range(count):
        name=f'{prefix}{i+1}'
        (OUT_DIR/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    rebuilt=''.join((OUT_DIR/n).read_text(encoding='utf-8') for n in names)
    if rebuilt!=text: raise SystemExit(f'Las partes {prefix} no reconstruyen el archivo')
    return names


def main() -> None:
    app=patch_app(joined_parts(APP_SRC,'app.part',7))
    launcher=patch_launcher(joined_parts(LAUNCHER_SRC,'ABRIR_RECEPCION.part',4))
    compile(app,'app.py','exec'); compile(launcher,'ABRIR_RECEPCION.py','exec')

    tree=ast.parse(app)
    billing_fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='billing_approve')
    billing_src=ast.get_source_segment(app,billing_fn) or ''
    required=['azur_emit_invoice','validate_billing_recipient','EN_PROCESO','mirror_azur_emission_to_local','APROBADA']
    for token in required:
        if token not in billing_src: raise SystemExit(f'billing_approve no contiene {token}')
    if 'add_queue' in billing_src: raise SystemExit('billing_approve no debe crear aprobación offline')
    if 'APP_VERSION = "4.3.75"' not in app: raise SystemExit('Versión app incorrecta')
    if "const VERSION=\\'4.3.75\\';" not in app: raise SystemExit('Versión visual incorrecta')
    if 'V475_BILLING_JS' not in app or 'V475_BILLING_CSS' not in app: raise SystemExit('Falta UI v475')
    if 'create_arc(16, 22, 38, 48' in launcher: raise SystemExit('Sigue el pseudo-logo viejo')
    if 'text="AR"' not in launcher: raise SystemExit('Falta monograma limpio')

    app_parts=write_parts(app,'app.part',7)
    launcher_parts=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    app_bytes=app.encode('utf-8'); launcher_bytes=launcher.encode('utf-8')

    manifest={
      'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
      'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher',
      'copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (OUT_DIR/'update_manifest.json').write_bytes(manifest_bytes)

    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v475/'
    latest={
      'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3',
      'message':'v4.3.75: simplifica Facturación a Revisar y emitir, unifica Por emitir, compacta el estado AZUR/SRI y corrige la marca visual del launcher.',
      'files':[
        {'path':'ABRIR_RECEPCION.py','parts':[base+n for n in launcher_parts],'sha256':sha(launcher_bytes),'encoding':'utf-8'},
        {'path':'app.py','parts':[base+n for n in app_parts],'sha256':sha(app_bytes),'encoding':'utf-8'},
        {'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(manifest_bytes),'encoding':'utf-8'}]}
    text=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'
    (ROOT/'latest.json').write_text(text,encoding='utf-8',newline='')
    (ROOT/'latest-v3.json').write_text(text,encoding='utf-8',newline='')
    print('OK',VERSION,'APP',sha(app_bytes),'LAUNCHER',sha(launcher_bytes))

if __name__=='__main__': main()
