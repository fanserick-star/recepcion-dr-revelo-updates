"""Informes urológicos de ecografía y cistoscopia.

Se almacenan como documentos clínicos tipados dentro de certificates para usar
la sincronización y protección transaccional ya probadas, sin nuevas tablas Neon.
Nunca se convierten en certificados médicos ni generan diagnósticos automáticos.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import quote
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from documentos_clinicos import (
    _age, _canonical_patient_id, _connect, _e, _id, _now,
    _patient, _row_value, _settings, _styles, _inline_signature_activation_dialog,
)

REPORT_TYPES = {
    "cistoscopia": {
        "storage": "report_cystoscopy",
        "title": "INFORME DE CISTOSCOPIA",
        "description": "Registrar los hallazgos endoscópicos sin texto clínico predefinido.",
        "fields": (
            ("equipo", "Equipo e instrumental utilizado", "Ej. modelo y óptica; completar si corresponde"),
            ("uretra", "Uretra", "Descripción de los hallazgos"),
            ("cuello", "Cuello vesical", "Descripción de los hallazgos"),
            ("vejiga", "Vejiga y paredes vesicales", "Descripción de los hallazgos"),
            ("meatos", "Meatos ureterales", "Descripción de los hallazgos"),
            ("trigono", "Trígono vesical", "Descripción de los hallazgos"),
            ("otros", "Otros hallazgos / observaciones", "Opcional"),
            ("conclusion", "Diagnóstico / conclusión cistoscópica", "Conclusión redactada por el médico"),
        ),
    },
    "ecografia": {
        "storage": "report_ultrasound",
        "title": "INFORME DE ECOGRAFÍA",
        "description": "Informe urológico flexible; completar solo las estructuras examinadas.",
        "fields": (
            ("estudio", "Tipo de ecografía / región evaluada", "Ej. renal, vesical, prostática, testicular"),
            ("tecnica", "Técnica / equipo", "Opcional"),
            ("rinon_derecho", "Riñón derecho", "Hallazgos y medidas, si se evaluó"),
            ("rinon_izquierdo", "Riñón izquierdo", "Hallazgos y medidas, si se evaluó"),
            ("vejiga", "Vejiga / residuo posmiccional", "Hallazgos y medidas, si se evaluó"),
            ("prostata", "Próstata u otros órganos", "Solo si corresponde"),
            ("otros", "Otros hallazgos / medidas", "Opcional"),
            ("conclusion", "Impresión diagnóstica / conclusión", "Conclusión redactada por el médico"),
        ),
    },
}
TYPE_BY_STORAGE = {v["storage"]: k for k, v in REPORT_TYPES.items()}


def _report_row(conn, report_id: str):
    return conn.execute(
        """SELECT c.*, p.name, p.national_id, p.birth_date, p.sex
           FROM certificates c JOIN patients p ON p.id=c.patient_id
           WHERE c.id=? AND c.certificate_type IN ('report_cystoscopy','report_ultrasound')
             AND COALESCE(c.deleted_at,'')='' LIMIT 1""",
        (report_id,),
    ).fetchone()


def _report_fields(row, kind: str) -> dict:
    try:
        data = json.loads(str(row["extra_json"] or "{}")) if row else {}
        raw = data.get("fields", {}) if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        raw = {}
    return {key: str(raw.get(key) or "") for key, _, _ in REPORT_TYPES[kind]["fields"]}


def _valid_date(value: str) -> bool:
    try:
        parsed = date.fromisoformat(value)
        return 1900 <= parsed.year <= 2200 and parsed.isoformat() == value
    except (TypeError, ValueError):
        return False


def _age_at(birth: str, issued: str) -> str:
    try:
        dob = date.fromisoformat(str(birth or "")[:10])
        when = date.fromisoformat(issued)
        years = when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))
        return str(years) if 0 <= years < 130 else ""
    except (ValueError, TypeError):
        return ""


def _body_from_fields(kind: str, values: dict) -> str:
    return "\n\n".join(
        f"{label.upper()}: {str(values.get(key) or '').strip()}"
        for key, label, _ in REPORT_TYPES[kind]["fields"]
        if str(values.get(key) or "").strip()
    )


def _form(base, conn, patient, kind: str, row=None, encounter_id="", queue_id="", from_consultation=0) -> HTMLResponse:
    config = REPORT_TYPES[kind]
    patient_id = str(patient["id"])
    report_id = str(row["id"]) if row else ""
    if row:
        encounter_id = str(row["encounter_id"] or "")
    stored = _report_fields(row, kind)
    issued = str(row["issued_at"] or "")[:10] if row else date.today().isoformat()
    if not _valid_date(issued):
        issued = date.today().isoformat()
    fields_markup = "".join(
        "<label class='full'>" + _e(label) +
        ("<input" if key in {"estudio", "equipo", "tecnica"} else "<textarea") +
        " class='report-input' data-field='" + _e(key) + "' " +
        ("type='text' value='" + _e(stored[key]) + "' placeholder='" + _e(hint) + "'>" if key in {"estudio", "equipo", "tecnica"}
         else "rows='3' placeholder='" + _e(hint) + "'>" + _e(stored[key]) + "</textarea>") +
        "</label>"
        for key, label, hint in config["fields"]
    )
    status_text = "Editando informe guardado" if row else "Sin guardar"
    report_json = json.dumps({
        "id": report_id, "patient_id": patient_id, "type": kind,
        "encounter_id": encounter_id, "queue_id": queue_id,
        "from_consultation": bool(from_consultation),
    }, ensure_ascii=False)
    body = f"""
{_styles()}
<style>
.report-intro{{margin:0 0 14px;color:#526781;line-height:1.5}}
.report-card{{border-top:4px solid #1a789f}}
.report-card .report-input{{font-size:16px;line-height:1.5;min-height:50px}}
.report-card textarea.report-input{{min-height:85px}}
.report-actions{{position:sticky;bottom:0;background:#f7fafddf;backdrop-filter:blur(7px);padding:14px;border:1px solid #dce5ed;border-radius:12px;z-index:4}}
.report-state{{font-size:13px;color:#536779;align-self:center;font-weight:700}}
@media(max-width:700px){{.report-actions{{position:static}}}}
</style>
<section class='docs-wrap'>
 <div class='docs-head'><div><span class='eyebrow'>DOCUMENTOS / INFORMES</span>
 <h1>{_e(config["title"].title())}</h1>
 <p class='report-intro'>{_e(config["description"])}</p>
 </div></div>
 <div class='docs-grid'>
  <div class='docs-card'><h3>Paciente</h3><div class='docs-fields'>
   <label class='full'>Apellidos y nombres<input readonly value='{_e(patient["name"])}'></label>
   <label>Identificación<input readonly value='{_e(_row_value(patient,"national_id"))}'></label>
   <label>Edad<input readonly value='{_e(_age_at(_row_value(patient,"birth_date"),issued))}'></label>
   <label>Sexo<input readonly value='{_e(_row_value(patient,"sex"))}'></label>
   <label>Fecha del estudio<input id='report-date' type='date' value='{_e(issued)}'></label>
  </div></div>
  <div class='docs-card'><h3>Indicaciones</h3>
   <p class='report-intro'>Describa únicamente los hallazgos reales del procedimiento. Ningún hallazgo ni diagnóstico se rellena automáticamente.</p>
   <p class='report-intro'>Los campos no utilizados se omiten del documento impreso. Guarde solo cuando esté listo.</p>
   <a class='doc-light' style='display:inline-block;padding:10px;border-radius:8px;text-decoration:none'
      href='/informes?patient_id={_e(patient_id)}'>Ver informes de este paciente</a>
  </div>
 </div>
 <div class='docs-card report-card' style='margin-top:16px'><h3>Descripción del estudio</h3>
 <div class='docs-fields'>{fields_markup}</div></div>
 <div class='doc-actions report-actions'>
  <button id='report-save' class='doc-primary' type='button'>Guardar informe</button>
  <button id='report-preview' class='doc-light' type='button'>Vista previa</button>
  <button id='report-print' class='doc-primary' type='button'>Guardar e imprimir</button>
  <button id='report-sign' class='doc-light' type='button'>PDF firmado</button>
  <span class='report-state' id='report-state'>{_e(status_text)}</span>
 </div>
</section>
{_inline_signature_activation_dialog()}
"""
    script = """
<script>
(()=>{
const state = REPORT_CONTEXT;
const buttons = ['report-save','report-preview','report-print','report-sign'].map(x=>document.getElementById(x));
const marker = document.getElementById('report-state');
const reportDate = document.getElementById('report-date');
const dataFields = [...document.querySelectorAll('[data-field]')];
function unsaved(){marker.textContent='Cambios sin guardar';}
reportDate.addEventListener('change', unsaved);
dataFields.forEach(el=>el.addEventListener('input', unsaved));
function payload(){
  const fields={};dataFields.forEach(el=>fields[el.dataset.field]=el.value);
  return {...state,issued_date:reportDate.value,fields:fields,report_id:state.id};
}
async function saveReport(){
  const response=await fetch('/api/informes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});
  const data=await response.json().catch(()=>({}));
  if(!response.ok||!data.ok)throw Error(data.error||'No se pudo guardar el informe');
  state.id=data.id;state.encounter_id=data.encounter_id||state.encounter_id;
  marker.textContent='Guardado';
  try{if(window.opener&&!window.opener.closed)window.opener.postMessage({type:'clinical-document-saved',encounter_id:state.encounter_id||''},location.origin)}catch(_e){}
  return data;
}
async function act(mode){
  buttons.forEach(x=>x.disabled=true);
  try{
    if(mode==='sign'&&window.historiaEnsureSignatureReady && !(await window.historiaEnsureSignatureReady()))return;
    const data=await saveReport();
    if(mode==='print'){
      if(!window.historiaNativePrint)throw Error('Reabra Historia Clínica para habilitar la impresión directa.');
      await window.historiaNativePrint(data.preview_url,'certificate');
    }else if(mode==='sign'){
      window.open('/api/firma/documento/informe/'+encodeURIComponent(data.id),'_blank');
    }else if(mode==='preview'){
      window.open(data.preview_url,'_blank');
    }
  }catch(e){alert(e.message||String(e));}
  finally{buttons.forEach(x=>x.disabled=false);}
}
document.getElementById('report-save').onclick=()=>act('save');
document.getElementById('report-preview').onclick=()=>act('preview');
document.getElementById('report-print').onclick=()=>act('print');
document.getElementById('report-sign').onclick=()=>act('sign');
})();
</script>
""".replace("REPORT_CONTEXT", report_json)
    return HTMLResponse(base("Informes médicos", body + script, "informes"))


def _print_html(row, settings, print_now: bool) -> str:
    kind = TYPE_BY_STORAGE[str(row["certificate_type"])]
    config = REPORT_TYPES[kind]
    fields = _report_fields(row, kind)
    # El contenido almacenado se muestra exactamente como lo redactó el médico.
    sections = "".join(
        f"<section class='finding'><h3>{_e(label)}</h3><div>{_e(fields[key])}</div></section>"
        for key, label, _ in config["fields"] if str(fields.get(key) or "").strip()
    )
    patient_name = _e(row["name"])
    national_id = _e(row["national_id"])
    issued = str(row["issued_at"] or "")[:10]
    try:
        d = date.fromisoformat(issued)
        fecha = f"{d.day:02d}/{d.month:02d}/{d.year}"
    except ValueError:
        fecha = issued
    age = _age_at(row["birth_date"], issued)
    doctor = _e(settings.get("doctor_name") or "Dr. Armando Revelo")
    logo = "/static/doctor_logo.png"
    js = """<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),450),{once:true});</script>""" if print_now else ""
    return f"""<!doctype html>
<html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{_e(config["title"].title())} · {patient_name}</title>
<style>
:root{{--navy:#173b66;--blue:#1595c6;--green:#45972f;--muted:#53677d}}
*{{box-sizing:border-box}}
body{{margin:0;background:#e8edf2;color:#17253b;font-family:Arial,Helvetica,sans-serif}}
.toolbar{{max-width:210mm;margin:12px auto;display:flex;justify-content:flex-end;gap:12px}}
.toolbar button{{background:var(--navy);color:white;border:0;border-radius:8px;padding:11px 18px;font-weight:800;cursor:pointer}}
.sheet{{max-width:210mm;min-height:297mm;margin:0 auto 20px;background:white;padding:14mm 15mm 16mm;box-shadow:0 6px 28px #14283a33;display:flex;flex-direction:column;position:relative}}
.brand{{border-bottom:2px solid var(--blue);display:flex;align-items:center;gap:16px;padding-bottom:12px}}
.brand img{{height:22mm;width:22mm;object-fit:contain;flex-shrink:0}}
.brand-main{{flex:1;text-align:center}}
.brand h1{{font-family:Georgia,serif;margin:0;color:var(--navy);font-size:19pt;letter-spacing:.4px}}
.brand h2{{margin:4px 0;font-size:12pt}}
.brand small{{color:var(--muted);line-height:1.4;font-size:8pt}}
.band{{height:4px;background:linear-gradient(90deg,var(--green) 0 42%,var(--blue) 42% 100%);border-radius:2px;margin-top:6px}}
.report-title{{text-align:center;margin:13mm 0 9mm;font-size:16pt;letter-spacing:1px;color:var(--navy)}}
.patient{{border:1px solid #d6e3ed;background:#f8fbfd;display:grid;grid-template-columns:1.2fr 1fr;gap:8px 18px;padding:12px 16px;border-radius:8px;font-size:10pt}}
.patient b{{color:var(--navy)}}
.findings{{padding-top:9mm;position:relative;z-index:1;flex:1}}
.finding{{margin:0 0 8mm;break-inside:avoid;page-break-inside:avoid;line-height:1.6;font-size:11pt}}
.finding h3{{margin:0 0 3mm;color:var(--navy);font-size:10.2pt;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #dfe7f0;padding-bottom:2mm}}
.finding div{{white-space:pre-wrap;overflow-wrap:anywhere;text-align:justify}}
.finding:last-child{{margin-bottom:3mm}}
.signature{{margin:17mm auto 7mm 0;max-width:80mm;text-align:center;font-size:10pt;line-height:1.45;break-inside:avoid}}
.signature .line{{border-top:1px solid #6d8294;padding-top:3mm}}
.signature b{{font-size:11pt;color:var(--navy)}}
.footer{{border-top:1px solid #d5e3eb;padding-top:4mm;text-align:center;color:var(--muted);font-size:8pt;line-height:1.35;break-inside:avoid}}
.watermark{{position:absolute;z-index:0;top:48%;left:50%;width:70mm;transform:translate(-50%,-50%);opacity:.055;pointer-events:none}}
@page{{size:A4;margin:0}}
@media print{{
 body{{background:white}}
 .toolbar{{display:none!important}}
 .sheet{{width:210mm;max-width:none;min-height:297mm;margin:0;box-shadow:none}}
 .patient,.finding{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
}}
</style></head><body>
<div class='toolbar'><button onclick='window.print()'>Imprimir / Guardar PDF</button></div>
<main class='sheet'>
<header><div class='brand'><img src='{logo}' alt='Logo'><div class='brand-main'>
<h1>DR. ARMANDO REVELO</h1><h2>Cirujano Urólogo</h2>
<small>{_e(settings.get("center_name"))}<br>{_e(settings.get("address"))}</small>
</div></div><div class='band'></div></header>
<h2 class='report-title'>{_e(config["title"])}</h2>
<div class='patient'>
<div><b>PACIENTE:</b> {patient_name}</div>
<div><b>FECHA:</b> {_e(fecha)}</div>
<div><b>IDENTIFICACIÓN:</b> {national_id or "—"}</div>
<div><b>EDAD:</b> {_e(age) + " años" if age else "—"}</div>
</div>
<img class='watermark' src='{logo}' alt=''>
<div class='findings'>{sections}</div>
<div class='signature'><div class='line'><b>{doctor}</b><div>{_e(settings.get("specialty"))}</div>
<div>Reg. Senescyt: {_e(settings.get("senescyt_registration"))}</div>
<div>Reg. M.S.P.: {_e(settings.get("msp_registration"))}</div>
</div></div>
<footer class='footer'>{_e(settings.get("address"))}<br>Tel.: {_e(settings.get("phones"))}</footer>
</main>{js}</body></html>"""


def install(app, context: dict) -> None:
    db_path = context["DB_PATH"]
    base = context["base"]

    @app.get("/informes", response_class=HTMLResponse)
    def list_reports(patient_id: str = "", encounter_id: str = "", queue_id: str = "", from_consultation: int = 0):
        with _connect(db_path) as conn:
            args = []
            where = "WHERE c.certificate_type IN ('report_cystoscopy','report_ultrasound') AND COALESCE(c.deleted_at,'')=''"
            if patient_id:
                patient_id = _canonical_patient_id(conn, patient_id)
                where += " AND c.patient_id=?"
                args.append(patient_id)
            rows = conn.execute(
                f"""SELECT c.id,c.issued_at,c.certificate_type,p.name
                    FROM certificates c JOIN patients p ON p.id=c.patient_id
                    {where} ORDER BY c.issued_at DESC LIMIT 300""", args,
            ).fetchall()
        table_rows = "".join(
            "<tr><td>"+_e(str(r["issued_at"] or "")[:10])+"</td>"
            "<td>"+_e(r["name"])+"</td>"
            "<td>"+_e(REPORT_TYPES[TYPE_BY_STORAGE[str(r["certificate_type"])]]["title"].title())+"</td>"
            "<td><a href='/informes/"+quote(r["id"])+"/vista' target='_blank'>Ver</a>"
            " · <a href='/informes/"+quote(r["id"])+"/editar'>Editar</a>"
            " · <a href='/informes/"+quote(r["id"])+"/vista?print_now=1' target='_blank'>Imprimir</a></td></tr>"
            for r in rows
        ) or "<tr><td colspan='4'>No existen informes guardados.</td></tr>"
        context = "&encounter_id="+quote(encounter_id)+"&queue_id="+quote(queue_id)+"&from_consultation="+str(int(bool(from_consultation)))
        start = (
            "<div class='doc-actions'>"
            "<a class='doc-light' href='/informes/nuevo?patient_id="+quote(patient_id)+"&tipo=cistoscopia"+context+"'>+ Cistoscopia</a>"
            "<a class='doc-light' href='/informes/nuevo?patient_id="+quote(patient_id)+"&tipo=ecografia"+context+"'>+ Ecografía</a>"
            "</div>" if patient_id else ""
        )
        body = _styles() + "<section class='docs-wrap'><div class='docs-head'><div><span class='eyebrow'>DOCUMENTOS</span><h1>Informes médicos</h1><p>Ecografías y cistoscopias del paciente.</p>"+start+"</div></div><div class='docs-card'><table class='list-table'><thead><tr><th>Fecha</th><th>Paciente</th><th>Estudio</th><th>Acciones</th></tr></thead><tbody>"+table_rows+"</tbody></table></div></section>"
        return HTMLResponse(base("Informes médicos", body, "informes"))

    @app.get("/informes/nuevo", response_class=HTMLResponse)
    def new_report(patient_id: str, tipo: str = "cistoscopia", encounter_id: str = "", queue_id: str = "", from_consultation: int = 0):
        if tipo not in REPORT_TYPES:
            return HTMLResponse("Tipo de informe no válido.", status_code=400)
        with _connect(db_path) as conn:
            patient_id = _canonical_patient_id(conn, patient_id)
            patient = _patient(conn, patient_id)
            if not patient:
                return HTMLResponse("Paciente no encontrado.", status_code=404)
            if encounter_id:
                enc = conn.execute("SELECT patient_id FROM encounters WHERE id=? AND COALESCE(deleted_at,'')=''", (encounter_id,)).fetchone()
                if not enc or str(enc["patient_id"]) != patient_id:
                    return HTMLResponse("La consulta no pertenece al paciente.", status_code=409)
            return _form(base, conn, patient, tipo, encounter_id=encounter_id, queue_id=queue_id, from_consultation=from_consultation)

    @app.get("/informes/{report_id}/editar", response_class=HTMLResponse)
    def edit_report(report_id: str):
        with _connect(db_path) as conn:
            row = _report_row(conn, report_id)
            if not row:
                return HTMLResponse("Informe no encontrado.", status_code=404)
            patient = _patient(conn, str(row["patient_id"]))
            if not patient:
                return HTMLResponse("Paciente no encontrado.", status_code=404)
            kind = TYPE_BY_STORAGE[str(row["certificate_type"])]
            return _form(base, conn, patient, kind, row=row)

    @app.post("/api/informes")
    async def save_report(request: Request):
        payload = await request.json()
        kind = str(payload.get("type") or "")
        if kind not in REPORT_TYPES:
            return JSONResponse({"ok":False,"error":"Tipo de informe no válido."}, status_code=400)
        issued_date = str(payload.get("issued_date") or "")
        if not _valid_date(issued_date):
            return JSONResponse({"ok":False,"error":"Fecha del estudio no válida."}, status_code=400)
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            return JSONResponse({"ok":False,"error":"Hallazgos no válidos."}, status_code=400)
        allowed = {k for k, _, _ in REPORT_TYPES[kind]["fields"]}
        if any(k not in allowed for k in fields):
            return JSONResponse({"ok":False,"error":"Campos no válidos."}, status_code=400)
        values = {k: str(fields.get(k) or "").strip() for k in allowed}
        if any(len(v) > 12000 for v in values.values()):
            return JSONResponse({"ok":False,"error":"Un campo del informe es demasiado extenso."}, status_code=400)
        if not any(values.values()):
            return JSONResponse({"ok":False,"error":"Escriba al menos un hallazgo o conclusión."}, status_code=400)
        patient_id = str(payload.get("patient_id") or "").strip()
        report_id = str(payload.get("report_id") or "").strip() or _id()
        encounter_id = str(payload.get("encounter_id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", report_id):
            return JSONResponse({"ok":False,"error":"Identificador del informe no válido."}, status_code=400)
        stamp = _now()
        with _connect(db_path) as conn:
            patient_id = _canonical_patient_id(conn, patient_id)
            if not _patient(conn, patient_id):
                return JSONResponse({"ok":False,"error":"Paciente no encontrado."}, status_code=404)
            if encounter_id:
                enc = conn.execute("SELECT patient_id FROM encounters WHERE id=? AND COALESCE(deleted_at,'')=''", (encounter_id,)).fetchone()
                if not enc or str(enc["patient_id"]) != patient_id:
                    return JSONResponse({"ok":False,"error":"La consulta no pertenece a este paciente."}, status_code=409)
            if payload.get("from_consultation") and not encounter_id:
                return JSONResponse({"ok":False,"error":"Guarde primero la consulta antes de crear el informe."}, status_code=409)
            current = conn.execute("SELECT patient_id,certificate_type,encounter_id FROM certificates WHERE id=? AND COALESCE(deleted_at,'')=''",(report_id,)).fetchone()
            storage = REPORT_TYPES[kind]["storage"]
            if current and (str(current["patient_id"]) != patient_id or str(current["certificate_type"]) != storage):
                return JSONResponse({"ok":False,"error":"El informe pertenece a otro paciente o tiene otro tipo."},status_code=409)
            if current and current["encounter_id"] and encounter_id and str(current["encounter_id"]) != encounter_id:
                return JSONResponse({"ok":False,"error":"No se puede cambiar la consulta asociada."},status_code=409)
            if current and not encounter_id:
                encounter_id = str(current["encounter_id"] or "")
            issued_at = issued_date + "T" + datetime.now().strftime("%H:%M:%S")
            details = json.dumps({"version":1,"report_type":kind,"fields":values}, ensure_ascii=False)
            body_text = _body_from_fields(kind, values)
            conclusion = values.get("conclusion", "")
            if current:
                conn.execute(
                    """UPDATE certificates SET issued_at=?,diagnosis=?,body_text=?,extra_json=?,updated_at=?
                       WHERE id=? AND certificate_type=?""",
                    (issued_at,conclusion,body_text,details,stamp,report_id,storage),
                )
            else:
                conn.execute(
                    """INSERT INTO certificates
                       (id,patient_id,encounter_id,issued_at,diagnosis,cie10,additional_diagnosis,
                        additional_cie10,procedure_text,rest_days,rest_from,rest_to,body_text,
                        certificate_no,certificate_type,extra_json,created_at,updated_at,deleted_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (report_id,patient_id,encounter_id or None,issued_at,conclusion,"","","",
                     REPORT_TYPES[kind]["title"],0,"","",body_text,"",storage,details,stamp,stamp),
                )
            conn.commit()
        return JSONResponse({"ok":True,"id":report_id,"encounter_id":encounter_id,"preview_url":f"/informes/{report_id}/vista"})

    @app.get("/informes/{report_id}/vista", response_class=HTMLResponse)
    def preview_report(report_id: str, print_now: int = 0):
        with _connect(db_path) as conn:
            row = _report_row(conn, report_id)
            if not row:
                return HTMLResponse("Informe no encontrado.", status_code=404)
            settings = _settings(conn)
        return HTMLResponse(_print_html(row, settings, bool(print_now)))
