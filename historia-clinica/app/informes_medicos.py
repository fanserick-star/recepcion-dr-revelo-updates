from __future__ import annotations

"""Informes clínicos A4: reutiliza certificados como almacén sincronizado de documentos.

Los tipos report_cystoscopy y report_ultrasound se distinguen siempre de los
certificados médicos. Sin migraciones destructivas ni contraseñas en SQLite/Neón.
"""
import hashlib
import html
import json
import re
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import documentos_clinicos as docs
import firma_electronica as firma

TYPES = {
    "cistoscopia": ("report_cystoscopy", "INFORME DE CISTOSCOPÍA", [
        ("equipo", "Equipo utilizado"), ("uretra", "Uretra"),
        ("cuello_vesical", "Cuello vesical"), ("vejiga", "Vejiga"),
        ("meatos_ureterales", "Meatos ureterales"), ("trigono", "Trígono"),
        ("otros_hallazgos", "Hallazgos adicionales"),
        ("diagnostico", "Diagnóstico cistoscópico"),
    ]),
    "ecografia": ("report_ultrasound", "INFORME DE ECOGRAFÍA", [
        ("estudio", "Tipo de estudio"), ("rinon_derecho", "Riñón derecho"),
        ("rinon_izquierdo", "Riñón izquierdo"), ("vejiga", "Vejiga"),
        ("prostata", "Próstata (si corresponde)"),
        ("residuo", "Residuo postmiccional (si corresponde)"),
        ("otros_hallazgos", "Hallazgos adicionales"),
        ("conclusion", "Impresión diagnóstica"),
    ]),
}
BY_DB_TYPE = {v[0]: k for k, v in TYPES.items()}
EXAM_CHOICES = (
    "Renal", "Vesical", "Prostática", "Renovesicoprostática", "Otra"
)
DOCTOR_LEGAL_NAME = "Dr. Armando Arturo Revelo Castillo"
MAX_FIELD_CHARS = 4000


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _connect(db_path: Path):
    return docs._connect(db_path)


def _valid_day(value) -> str:
    raw = str(value or "").strip()
    try:
        return date.fromisoformat(raw).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Seleccione una fecha válida.")


def _years_old(born, on_day):
    try:
        dob = date.fromisoformat(str(born or "")[:10])
        day = date.fromisoformat(str(on_day or "")[:10])
        if dob > day:
            return ""
        return str(day.year - dob.year - ((day.month, day.day) < (dob.month, dob.day)))
    except (ValueError, TypeError):
        return ""


def _safe_fields(kind, raw):
    if kind not in TYPES or not isinstance(raw, dict):
        raise ValueError("Tipo de informe o campos inválidos.")
    fields = {}
    for key, _label in TYPES[kind][2]:
        value = str(raw.get(key) or "").strip()
        if len(value) > MAX_FIELD_CHARS:
            raise ValueError("Un apartado supera el límite permitido de texto.")
        fields[key] = value
    return fields


def _row(conn, report_id):
    return conn.execute(
        """SELECT * FROM certificates WHERE id=?
           AND certificate_type IN ('report_cystoscopy','report_ultrasound')
           AND COALESCE(deleted_at,'')=''""", (report_id,)
    ).fetchone()


def _signed_row(conn, report_id):
    return conn.execute(
        """SELECT relative_path,pdf_sha256 FROM electronic_signatures
           WHERE document_type='informe' AND document_id=?
           ORDER BY id DESC LIMIT 1""", (report_id,)
    ).fetchone()


def _payload(row):
    try:
        data = json.loads(str(row["extra_json"] or "{}"))
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _css():
    return """
<style>
.reports-wrap{max-width:1180px;margin:0 auto;padding:20px}
.reports-top{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.reports-top h1{font-size:29px;line-height:1.2;margin:5px 0}
.reports-top p{color:#5d7086;margin:0}
.reports-card{background:#fff;border:1px solid #dce5ee;border-radius:14px;padding:20px;margin-bottom:14px;box-shadow:0 8px 25px #18375009}
.reports-card h2{margin:0 0 12px;color:#153e62;font-size:18px}
.reports-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
.reports-grid label{display:block;font-size:15px;font-weight:750;color:#233c53}
.reports-grid input,.reports-grid textarea,.reports-grid select{display:block;width:100%;box-sizing:border-box;background:#fbfdff;border:1px solid #cad8e5;border-radius:9px;padding:12px;margin-top:7px;color:#18364d;font-size:16px}
.reports-grid textarea{min-height:92px;resize:vertical;line-height:1.5}
.reports-grid .span2{grid-column:1/-1}
.reports-actions{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-top:10px}
.reports-actions button,.reports-actions a{padding:11px 15px;min-height:42px;border:1px solid #c7d6e4;border-radius:9px;background:white;color:#173955;font-size:14px;font-weight:750;text-decoration:none;cursor:pointer}
.reports-actions .main{background:#114a74;color:white;border-color:#114a74}
.reports-actions button:disabled{opacity:.55}
.reports-note{color:#64758a;font-size:12px;line-height:1.5}
.reports-table{width:100%;border-collapse:collapse;font-size:14px}
.reports-table th,.reports-table td{padding:12px;border-bottom:1px solid #e5ebf1;text-align:left}
.reports-table th{color:#48627a}
@media(max-width:760px){.reports-grid{grid-template-columns:1fr}.reports-grid .span2{grid-column:auto}.reports-wrap{padding:12px}}
</style>"""


def _form_page(base, conn, patient, kind, report=None, encounter_id="", root=None):
    today = date.today().isoformat()
    info = _payload(report) if report else {}
    fields = info.get("fields", {}) if isinstance(info.get("fields", {}), dict) else {}
    report_id = str(report["id"]) if report else ""
    issued_day = str(report["issued_at"] or "")[:10] if report else today
    age = str(info.get("age") or "") if report else _years_old(patient["birth_date"], issued_day)
    title = TYPES[kind][1]
    signed = bool(report and _signed_row(conn, report_id))
    field_html = []
    for key, label in TYPES[kind][2]:
        value = esc(fields.get(key, ""))
        if kind == "ecografia" and key == "estudio":
            choices = "".join(
                '<option value="' + esc(c) + '"' +
                (' selected' if str(fields.get(key) or "") == c else "") +
                '>' + esc(c) + '</option>' for c in ("",) + EXAM_CHOICES
            )
            field_html.append('<label class="span2">' + esc(label) +
                              '<select data-field="estudio">' + choices + '</select></label>')
        else:
            field_html.append('<label class="span2">' + esc(label) +
                              '<textarea data-field="' + esc(key) +
                              '" rows="' + ("2" if key in {"equipo","estudio","residuo"} else "3") +
                              '" maxlength="4000">' + value + '</textarea></label>')
    status = "<strong>Firmado electrónicamente · edición bloqueada</strong>" if signed else "Sin cambios guardados"
    other_kind = "ecografia" if kind == "cistoscopia" else "cistoscopia"
    buttons = (
        '<a href="/informes/' + esc(report_id) + '/vista" target="_blank">Ver informe</a>'
        '<a href="/informes/' + esc(report_id) + '/firmado" target="_blank">Ver PDF firmado</a>'
        if signed else
        '<button id="report-save" class="main">Guardar informe</button>'
        '<button id="report-preview">Vista previa</button>'
        '<button id="report-print">Guardar e imprimir</button>'
        '<button id="report-sign">PDF firmado</button>'
    )
    body = f"""{_css()}<section class="reports-wrap">
      <div class="reports-top"><div>
        <span class="eyebrow">DOCUMENTOS / INFORMES CLÍNICOS</span>
        <h1>{esc(title)}</h1>
        <p>{esc(patient['name'])} · {esc(age)} años</p></div>
        <div class="reports-actions">
          <a href="/informes?patient_id={esc(patient['id'])}">Historial de informes</a>
          <a href="/informes/nuevo?patient_id={esc(patient['id'])}&tipo={other_kind}">Otro tipo de informe</a>
        </div>
      </div>
      <div class="reports-card"><h2>Datos del paciente</h2><div class="reports-grid">
        <label class="span2">Apellidos y nombres<input value="{esc(patient['name'])}" readonly></label>
        <label>Identificación<input value="{esc(patient['national_id'])}" readonly></label>
        <label>Edad (años)<input value="{esc(age)}" readonly></label>
        <label>Fecha del estudio<input id="report-date" type="date" value="{esc(issued_day)}" {"disabled" if signed else ""}></label>
      </div></div>
      <div class="reports-card"><h2>Hallazgos del estudio</h2>
        <p class="reports-note">Escriba únicamente hallazgos comprobados. No se insertan resultados normales automáticamente.</p>
        <div class="reports-grid">{''.join(field_html)}</div></div>
      <div class="reports-card">
        <div class="reports-actions">{buttons}</div>
        <p id="report-status" class="reports-note" role="status">{status}</p>
        <p class="reports-note">La firma PAdES utiliza el certificado local del doctor. Si está bloqueada, puede activarla aquí sin perder lo escrito. Una vez firmado, el informe es inmutable: para corregirlo debe emitirse uno nuevo.</p>
      </div>
    </section>"""
    if signed:
        return base(title, body, "informes")
    body += docs._inline_signature_activation_dialog()
    js = """
<script>
(function(){
const reportId=INITIAL_ID, patientId=PATIENT_ID, kind=REPORT_KIND, encounterId=ENCOUNTER_ID;
const byId=id=>document.getElementById(id), state=byId('report-status');
let savedId=reportId, busy=false, modified=false;
function value(){let f={};document.querySelectorAll('[data-field]').forEach(n=>f[n.dataset.field]=n.value);return f;}
document.querySelectorAll('[data-field],#report-date').forEach(n=>n.addEventListener('input',()=>{modified=true;state.textContent='Cambios sin guardar';}));
async function save(){
 const response=await fetch('/api/informes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
  report_id:savedId,patient_id:patientId,encounter_id:encounterId,tipo:kind,fecha:byId('report-date').value,campos:value()
 })});
 const data=await response.json().catch(()=>({}));
 if(!response.ok||!data.ok)throw new Error(data.error||'No se pudo guardar el informe.');
 savedId=data.id;modified=false;state.textContent='Guardado correctamente';
 try{window.opener?.postMessage({type:'clinical-document-saved',encounter_id:encounterId},location.origin)}catch(_e){}
 history.replaceState(null,'','/informes/'+encodeURIComponent(savedId)+'/editar');
 return data;
}
async function act(mode){
 if(busy)return;busy=true;
 document.querySelectorAll('.reports-actions button').forEach(x=>x.disabled=true);
 try{
  if((mode==='sign'||mode==='print')&&!(await window.historiaEnsureSignatureReady()))return;
  const d=await save();
  if(mode==='preview'){window.open(d.preview_url,'_blank');return;}
  if(mode==='sign'||mode==='print'){
   const url='/api/firma/documento/informe/'+encodeURIComponent(d.id);
   const r=await fetch(url,{cache:'no-store'});
   if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.error||j.detail||'No se pudo firmar el informe.');}
   const signed='/informes/'+encodeURIComponent(d.id)+'/firmado';
   state.textContent='PDF firmado y archivado';
   if(mode==='print'&&window.historiaNativePrint){
     try{await window.historiaNativePrint(signed,'certificate');return;}
     catch(_e){state.textContent='PDF firmado; impresión directa no disponible, abra el PDF.';}
   }
   window.open(signed,'_blank');return;
  }
 }catch(e){state.textContent='Error: '+(e.message||e);alert(e.message||e);}
 finally{busy=false;document.querySelectorAll('.reports-actions button').forEach(x=>x.disabled=false);}
}
byId('report-save').onclick=()=>act('save');
byId('report-preview').onclick=()=>act('preview');
byId('report-print').onclick=()=>act('print');
byId('report-sign').onclick=()=>act('sign');
window.addEventListener('beforeunload',e=>{if(modified){e.preventDefault();e.returnValue='';}});
})();
</script>
"""
    js = js.replace("INITIAL_ID", json.dumps(report_id)).replace("PATIENT_ID", json.dumps(str(patient["id"]))).replace("REPORT_KIND", json.dumps(kind)).replace("ENCOUNTER_ID", json.dumps(encounter_id))
    return base(title, body + js, "informes")


def _preview_html(conn, row):
    payload = _payload(row)
    kind = BY_DB_TYPE[str(row["certificate_type"])]
    title = TYPES[kind][1]
    fields = payload.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    settings = docs._settings(conn)
    patient = docs._patient(conn, str(row["patient_id"]))
    name = str(payload.get("patient_name") or (patient["name"] if patient else ""))
    national_id = str(payload.get("national_id") or (patient["national_id"] if patient else ""))
    age = str(payload.get("age") or "")
    rows = []
    for key, label in TYPES[kind][2]:
        value = str(fields.get(key) or "").strip()
        if value:
            rows.append('<div class="finding"><div class="label">'+esc(label)+'</div><div class="value">'+esc(value).replace("\n","<br>")+'</div></div>')
    rows_html = "".join(rows)
    issued_day = str(row["issued_at"] or "")[:10]
    formatted_day = docs._date_natural_es(issued_day)
    doctor = str(settings.get("doctor_name") or DOCTOR_LEGAL_NAME)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{esc(title)} · {esc(name)}</title>
<style>
@page{{size:A4 portrait;margin:0}}
*{{box-sizing:border-box}}
body{{margin:0;background:#e6ecf1;color:#172c3e;font:13px/1.5 Arial,sans-serif}}
.sheet{{position:relative;background:white;margin:15px auto;width:210mm;min-height:297mm;padding:17mm 17mm 44mm;box-shadow:0 10px 40px #0002}}
.brand{{display:flex;gap:13px;align-items:center;padding-bottom:11px;border-bottom:2px solid #174f77}}
.brand img{{width:59px;height:59px;object-fit:contain}}.brand h1{{margin:0;font-size:18px;color:#174f77}}
.brand small{{display:block;color:#64788b;font-size:10px}}
.title{{text-align:center;font-size:17px;font-weight:800;letter-spacing:.045em;margin:21px 0 16px}}
.meta{{display:grid;grid-template-columns:1fr 1fr;gap:10px 15px;padding:12px 15px;background:#f4f8fb;border:1px solid #e2ebf2;border-radius:6px}}
.meta b{{font-size:10px;color:#4b647a;text-transform:uppercase;display:block}}.meta span{{font-size:12px;font-weight:700}}
.finding{{padding:10px 0;border-bottom:1px solid #e6eef4;break-inside:avoid}}
.finding .label{{font-weight:800;font-size:11px;text-transform:uppercase;color:#234f70;margin-bottom:3px}}
.finding .value{{white-space:normal;overflow-wrap:anywhere;font-size:13px}}
.signature{{position:absolute;bottom:16mm;left:17mm;right:17mm;display:flex;justify-content:space-between;align-items:end;gap:10px}}
.signature .doc{{max-width:58%;border-top:1px solid #9aafc1;padding-top:4px;font-size:10px}}
.signature .reserve{{min-width:35%;min-height:28mm;text-align:right;color:#74879b;font-size:9px}}
.tools{{padding:10px;text-align:center}}.tools button{{background:#174f77;color:white;border:0;padding:9px 15px;border-radius:6px}}
@media print{{body{{background:white}}.sheet{{box-shadow:none;margin:0;width:210mm;min-height:297mm}}.tools{{display:none}}}}
</style></head><body><div class="tools"><button onclick="window.print()">Imprimir / Guardar PDF</button></div>
<article class="sheet">
<header class="brand"><img src="/static/doctor_logo.png" alt=""><div>
<h1>{esc(doctor)}</h1><small>{esc(settings.get("specialty") or "Cirujano Urólogo")}</small>
<small>{esc(settings.get("center_name") or "Centro de Urología")} · {esc(settings.get("phones") or "")}</small></div></header>
<div class="title">{esc(title)}</div>
<div class="meta"><div><b>Paciente</b><span>{esc(name)}</span></div><div><b>Fecha del estudio</b><span>{esc(formatted_day)}</span></div>
<div><b>Identificación</b><span>{esc(national_id)}</span></div><div><b>Edad</b><span>{esc(age)} años</span></div></div>
<section class="findings">{rows_html}</section>
<footer class="signature"><div class="doc"><strong>{esc(DOCTOR_LEGAL_NAME)}</strong>
<div>Cirujano Urólogo</div>
<div>Registro SENESCYT: {esc(settings.get("senescyt_registration") or "")}</div></div>
<div class="reserve">Espacio reservado para firma electrónica verificable</div></footer>
</article></body></html>"""


def install(app, context):
    root = Path(context["ROOT"])
    db_path = Path(context["DB_PATH"])
    base = context["base"]

    @app.get("/informes", response_class=HTMLResponse)
    def list_reports(patient_id: str = ""):
        with _connect(db_path) as conn:
            if patient_id:
                patient_id = docs._canonical_patient_id(conn, patient_id)
                rows = conn.execute(
                    """SELECT c.id,c.issued_at,c.certificate_type,p.name FROM certificates c
                     JOIN patients p ON p.id=c.patient_id
                     WHERE c.certificate_type IN ('report_cystoscopy','report_ultrasound')
                     AND COALESCE(c.deleted_at,'')='' AND c.patient_id=?
                     ORDER BY c.issued_at DESC LIMIT 200""", (patient_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT c.id,c.issued_at,c.certificate_type,p.name FROM certificates c
                     JOIN patients p ON p.id=c.patient_id
                     WHERE c.certificate_type IN ('report_cystoscopy','report_ultrasound')
                     AND COALESCE(c.deleted_at,'')=''
                     ORDER BY c.issued_at DESC LIMIT 200"""
                ).fetchall()
        trs = "".join(
            "<tr><td>"+esc(str(r["issued_at"] or "")[:10])+"</td><td>"+esc(r["name"])+"</td><td>"+
            esc(TYPES[BY_DB_TYPE[r["certificate_type"]]][1])+"</td><td>"+
            '<a href="/informes/'+esc(r["id"])+'/vista" target="_blank">Ver</a> · '+
            '<a href="/informes/'+esc(r["id"])+'/editar">Abrir</a></td></tr>' for r in rows
        ) or '<tr><td colspan="4">No existen informes guardados.</td></tr>'
        body = _css()+f"""<section class="reports-wrap"><div class="reports-top"><div>
        <span class="eyebrow">HISTORIA CLÍNICA</span><h1>Informes médicos</h1>
        <p>Cistoscopía y ecografía, asociados a la ficha del paciente.</p></div></div>
        <div class="reports-card"><table class="reports-table"><thead><tr>
        <th>Fecha</th><th>Paciente</th><th>Tipo</th><th>Documento</th></tr></thead><tbody>{trs}</tbody></table></div></section>"""
        return HTMLResponse(base("Informes médicos", body, "informes"))

    @app.get("/informes/nuevo", response_class=HTMLResponse)
    def new_report(patient_id: str, tipo: str = "cistoscopia", encounter_id: str = ""):
        if tipo not in TYPES:
            raise HTTPException(status_code=400, detail="Tipo de informe no soportado.")
        with _connect(db_path) as conn:
            patient_id = docs._canonical_patient_id(conn, patient_id)
            patient = docs._patient(conn, patient_id)
            if patient is None:
                raise HTTPException(status_code=404, detail="Paciente no encontrado.")
            return HTMLResponse(_form_page(base, conn, patient, tipo, encounter_id=encounter_id))

    @app.get("/informes/{report_id}/editar", response_class=HTMLResponse)
    def edit_report(report_id: str):
        with _connect(db_path) as conn:
            row = _row(conn, report_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Informe no encontrado.")
            patient = docs._patient(conn, row["patient_id"])
            if patient is None:
                raise HTTPException(status_code=404, detail="Paciente no encontrado.")
            return HTMLResponse(_form_page(base, conn, patient, BY_DB_TYPE[row["certificate_type"]], row, str(row["encounter_id"] or "")))

    @app.post("/api/informes")
    async def save_report(request: Request):
        try:
            p = await request.json()
            kind = str(p.get("tipo") or "").strip().lower()
            fields = _safe_fields(kind, p.get("campos"))
            exam_date = _valid_day(p.get("fecha"))
            if not any(fields.values()):
                raise ValueError("Escriba los hallazgos antes de guardar.")
            report_id = str(p.get("report_id") or "").strip() or str(uuid.uuid4())
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", report_id):
                raise ValueError("Identificador de informe inválido.")
            patient_id = str(p.get("patient_id") or "").strip()
            requested_encounter_id = str(p.get("encounter_id") or "").strip()
            with _connect(db_path) as conn:
                patient_id = docs._canonical_patient_id(conn, patient_id)
                patient = docs._patient(conn, patient_id)
                if patient is None:
                    raise ValueError("Paciente no encontrado.")
                current = _row(conn, report_id)
                if current:
                    if str(current["patient_id"]) != patient_id or current["certificate_type"] != TYPES[kind][0]:
                        raise ValueError("El informe no pertenece a este paciente o cambió de tipo.")
                    if _signed_row(conn, report_id):
                        return JSONResponse({"ok": False, "error": "Informe ya firmado: emita un nuevo informe para corregirlo."}, status_code=409)
                else:
                    collision = conn.execute("SELECT 1 FROM certificates WHERE id=?", (report_id,)).fetchone()
                    if collision:
                        raise ValueError("Ese identificador pertenece a otro documento.")
                encounter_id = str(current["encounter_id"] or "") if current else ""
                if not encounter_id and requested_encounter_id:
                    enc = conn.execute("SELECT patient_id FROM encounters WHERE id=?", (requested_encounter_id,)).fetchone()
                    if not enc or str(enc["patient_id"] or "") != patient_id:
                        raise ValueError("La consulta no corresponde al paciente.")
                    encounter_id = requested_encounter_id
                snapshot = _payload(current) if current else {}
                snapshot.update({
                    "schema": 1,
                    "fields": fields,
                    "patient_name": snapshot.get("patient_name") or str(patient["name"] or ""),
                    "national_id": snapshot.get("national_id") or str(patient["national_id"] or ""),
                    "age": _years_old(patient["birth_date"], exam_date),
                })
                stamp = datetime.now().isoformat(timespec="seconds")
                issued = exam_date+"T"+stamp.split("T")[1]
                diagnostic = fields.get("diagnostico" if kind=="cistoscopia" else "conclusion", "")
                values = (issued,diagnostic,json.dumps(snapshot, ensure_ascii=False),
                          stamp,report_id)
                if current:
                    conn.execute(
                        """UPDATE certificates SET issued_at=?,diagnosis=?,extra_json=?,updated_at=?
                           WHERE id=? AND COALESCE(deleted_at,'')=''""", values
                    )
                else:
                    conn.execute(
                        """INSERT INTO certificates(id,patient_id,encounter_id,issued_at,
                            diagnosis,body_text,certificate_type,extra_json,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (report_id,patient_id,encounter_id or None,issued,diagnostic,
                         diagnostic,TYPES[kind][0],json.dumps(snapshot,ensure_ascii=False),stamp,stamp)
                    )
                conn.commit()
            return JSONResponse({"ok": True, "id": report_id, "preview_url": "/informes/"+report_id+"/vista"})
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.get("/informes/{report_id}/vista", response_class=HTMLResponse)
    def report_preview(report_id: str):
        with _connect(db_path) as conn:
            row = _row(conn, report_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Informe no encontrado.")
            return HTMLResponse(_preview_html(conn, row), headers={"Cache-Control":"no-store"})

    @app.get("/informes/{report_id}/firmado")
    def archived_signed_report(request: Request, report_id: str):
        firma._require_local(request)
        with _connect(db_path) as conn:
            if not _row(conn, report_id):
                raise HTTPException(status_code=404, detail="Informe no encontrado.")
            signed = _signed_row(conn, report_id)
        if signed is None:
            raise HTTPException(status_code=404, detail="Todavía no existe una copia electrónica firmada.")
        path = (root / str(signed["relative_path"])).resolve()
        allowed = (root / "data" / "documentos_firmados").resolve()
        if not path.is_relative_to(allowed) or not path.is_file():
            raise HTTPException(status_code=404, detail="Archivo firmado no disponible en esta PC.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != str(signed["pdf_sha256"] or ""):
            raise HTTPException(status_code=409, detail="El PDF firmado no coincide con su huella original.")
        return FileResponse(path, media_type="application/pdf",
                            filename="Informe_medico_firmado.pdf",
                            headers={"Cache-Control":"no-store"},
                            content_disposition_type="inline")
