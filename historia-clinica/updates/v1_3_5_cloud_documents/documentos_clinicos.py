from __future__ import annotations

import html
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse


SHARED_DEFAULTS = {
    "doctor_name": "Dr. Armando Revelo",
    "specialty": "Cirujano Urólogo",
    "msp_registration": "LIBRO V FOLIO 0052 No. 5888",
    "senescyt_registration": "1006-07-669163",
    "society_membership": "MIEMBRO DE LA SOCIEDAD ECUATORIANA DE UROLOGIA",
    "center_name": "CENTRO DE UROLOGIA",
    "address": "QUEVEDO, SAN CAMILO, AV. JOSÉ JOAQUÍN DE OLMEDO Y PANAMÁ",
    "phones": "0989286631",
    "email": "Urorevelo-95@hotmail.com",
    "services_line": "Riñones - Próstata - Vejiga - Cálculos - Impotencia - Venéreas",
    "prescription_series_start": "100",
    "prescription_footer": "Dirección: Quevedo, San Camilo Av. José Joaquín de Olmedo y Panamá. Telf: 0989286631",
    "certificate_closing": "ES TODO CUANTO PUEDO CERTIFICAR A PETICION DEL INTERESADO.",
}

LOCAL_DEFAULTS = {
    "prescription_printer": "",
    "certificate_printer": "",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _id() -> str:
    return str(uuid.uuid4())


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prescriptions(
              id TEXT PRIMARY KEY,
              patient_id TEXT NOT NULL,
              encounter_id TEXT,
              issued_at TEXT NOT NULL,
              series_no TEXT,
              diagnosis TEXT,
              cie10 TEXT,
              allergies TEXT,
              allergies_detail TEXT,
              items_json TEXT NOT NULL DEFAULT '[]',
              instructions TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_prescriptions_patient
              ON prescriptions(patient_id, issued_at DESC);

            CREATE TABLE IF NOT EXISTS certificates(
              id TEXT PRIMARY KEY,
              patient_id TEXT NOT NULL,
              encounter_id TEXT,
              issued_at TEXT NOT NULL,
              diagnosis TEXT,
              cie10 TEXT,
              additional_diagnosis TEXT,
              additional_cie10 TEXT,
              procedure_text TEXT,
              rest_days INTEGER NOT NULL DEFAULT 0,
              rest_from TEXT,
              rest_to TEXT,
              body_text TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_certificates_patient
              ON certificates(patient_id, issued_at DESC);

            CREATE TABLE IF NOT EXISTS clinic_settings(
              setting_key TEXT PRIMARY KEY,
              setting_value TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              deleted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS local_settings(
              setting_key TEXT PRIMARY KEY,
              setting_value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        stamp = _now()
        for key, value in SHARED_DEFAULTS.items():
            conn.execute(
                """INSERT OR IGNORE INTO clinic_settings(
                     setting_key,setting_value,updated_at,deleted_at
                   ) VALUES(?,?,?,NULL)""",
                (key, value, stamp),
            )
        for key, value in LOCAL_DEFAULTS.items():
            conn.execute(
                """INSERT OR IGNORE INTO local_settings(
                     setting_key,setting_value,updated_at
                   ) VALUES(?,?,?)""",
                (key, value, stamp),
            )
        conn.commit()
    finally:
        conn.close()


def _settings(conn: sqlite3.Connection) -> dict:
    out = dict(SHARED_DEFAULTS)
    for row in conn.execute(
        "SELECT setting_key,setting_value FROM clinic_settings WHERE deleted_at IS NULL"
    ).fetchall():
        out[str(row["setting_key"])] = str(row["setting_value"] or "")
    return out


def _local_settings(conn: sqlite3.Connection) -> dict:
    out = dict(LOCAL_DEFAULTS)
    for row in conn.execute(
        "SELECT setting_key,setting_value FROM local_settings"
    ).fetchall():
        out[str(row["setting_key"])] = str(row["setting_value"] or "")
    return out


def _age(birth_date: str | None) -> str:
    raw = str(birth_date or "").strip()
    if not raw:
        return ""
    try:
        born = date.fromisoformat(raw[:10])
        today = date.today()
        return str(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
    except Exception:
        return ""


def _patient(conn: sqlite3.Connection, patient_id: str):
    return conn.execute(
        "SELECT * FROM patients WHERE id=? AND COALESCE(deleted_at,'')=''",
        (patient_id,),
    ).fetchone()


def _encounter(conn: sqlite3.Connection, encounter_id: str | None):
    if not encounter_id:
        return None
    return conn.execute("SELECT * FROM encounters WHERE id=?", (encounter_id,)).fetchone()


def _series(conn: sqlite3.Connection, settings: dict) -> str:
    start = 100
    try:
        start = int(settings.get("prescription_series_start") or 100)
    except Exception:
        pass
    rows = conn.execute(
        "SELECT series_no FROM prescriptions WHERE COALESCE(deleted_at,'')='' ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    nums = []
    for row in rows:
        try:
            nums.append(int(str(row["series_no"] or "").strip()))
        except Exception:
            pass
    return f"{max([start - 1, *nums]) + 1:05d}"


def _date_words(value: str) -> str:
    months = [
        "", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    ]
    try:
        d = date.fromisoformat(value[:10])
        return f"{d.day} DE {months[d.month]} DEL {d.year}"
    except Exception:
        return value.upper()


def _certificate_body(patient, encounter, diagnosis: str, cie10: str,
                      additional: str, additional_cie10: str, procedure: str,
                      rest_days: int, rest_from: str, rest_to: str,
                      settings: dict) -> str:
    name = str(patient["name"] or "").upper()
    national_id = str(patient["national_id"] or "").strip()
    date_text = _date_words((encounter["encounter_date"] if encounter else "") or date.today().isoformat())
    time_text = str((encounter["encounter_time"] if encounter else "") or "").strip()
    dx = str(diagnosis or "").strip().upper()
    c10 = str(cie10 or "").strip().upper()
    adx = str(additional or "").strip().upper()
    ac10 = str(additional_cie10 or "").strip().upper()
    proc = str(procedure or "").strip().upper()

    pieces = []
    if dx:
        pieces.append(dx + (f" CIE 10 {c10}" if c10 else ""))
    if adx:
        pieces.append(adx + (f" CIE 10 {ac10}" if ac10 else ""))
    diagnoses = " + ".join(pieces) or "CUADRO CLÍNICO DESCRITO EN LA HISTORIA"

    text = (
        f"CERTIFICO, QUE {name} CON C.I# {national_id}, FUE ATENDIDO(A) EL DÍA "
        f"{date_text}"
    )
    if time_text:
        text += f" A LAS {time_text}"
    text += f", POR PRESENTAR: {diagnoses}."
    if proc:
        text += f" POR LO CUAL SE REALIZA: {proc}."
    if rest_days > 0:
        text += (
            f"\n\nSE EXTIENDE REPOSO MÉDICO EN CASA POR {rest_days} DÍA(S) "
            f"DESDE EL {_date_words(rest_from)} HASTA EL {_date_words(rest_to)}."
        )
    text += "\n\n" + str(settings.get("certificate_closing") or "").upper()
    return text


def _styles() -> str:
    return """
<style>
.docs-wrap{max-width:1180px;margin:0 auto;padding:24px}
.docs-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}
.docs-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.docs-card{background:#fff;border:1px solid #d9e1eb;border-radius:14px;padding:18px;box-shadow:0 4px 18px #173b6610}
.docs-card h2,.docs-card h3{margin-top:0;color:#173b66}
.docs-fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.docs-fields .full{grid-column:1/-1}
.docs-card label{display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:800;color:#44546a}
.docs-card input,.docs-card textarea,.docs-card select{padding:10px 11px;border:1px solid #cbd5e1;border-radius:9px;font:inherit;background:#fff}
.docs-card textarea{min-height:110px;resize:vertical}
.doc-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.doc-actions button,.doc-actions a{border:0;border-radius:9px;padding:10px 14px;font-weight:800;text-decoration:none;cursor:pointer}
.doc-primary{background:#2b6aa7;color:#fff}.doc-light{background:#edf3f9;color:#173b66}.doc-muted{background:#e5e7eb;color:#374151}
.med-table{width:100%;border-collapse:collapse}.med-table th,.med-table td{padding:6px;border-bottom:1px solid #e5e7eb}.med-table input{width:100%;box-sizing:border-box}
.list-table{width:100%;border-collapse:collapse}.list-table th,.list-table td{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left}
.config-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}.config-nav a{padding:8px 10px;border-radius:8px;background:#edf3f9;color:#173b66;text-decoration:none;font-weight:800}
@media(max-width:850px){.docs-grid,.docs-fields{grid-template-columns:1fr}.docs-fields .full{grid-column:auto}}
@media print{.no-print,header,footer{display:none!important}.print-sheet{box-shadow:none!important;border:0!important;margin:0!important}.docs-wrap{padding:0!important}}
</style>
"""


def install(app, context: dict) -> None:
    db_path = Path(context["DB_PATH"])
    base = context["base"]
    get_sync_status = context.get("get_sync_status")
    data_dir = Path(context["ROOT"]) / "data"

    @app.get("/recetas", response_class=HTMLResponse)
    def prescriptions_list(patient_id: str = ""):
        with _connect(db_path) as conn:
            args = []
            where = "WHERE COALESCE(r.deleted_at,'')=''"
            if patient_id:
                where += " AND r.patient_id=?"
                args.append(patient_id)
            rows = conn.execute(
                f"""SELECT r.*,p.name,p.national_id
                    FROM prescriptions r
                    JOIN patients p ON p.id=r.patient_id
                    {where}
                    ORDER BY r.issued_at DESC LIMIT 300""",
                args,
            ).fetchall()
        body_rows = "".join(
            f"<tr><td>{_e(r['issued_at'][:16].replace('T',' '))}</td>"
            f"<td>{_e(r['name'])}</td><td>{_e(r['series_no'])}</td>"
            f"<td>{_e(r['diagnosis'])}</td>"
            f"<td><a href='/recetas/{_e(r['id'])}/vista' target='_blank'>Ver / imprimir</a></td></tr>"
            for r in rows
        ) or "<tr><td colspan='5'>No hay recetas emitidas.</td></tr>"
        body = f"""
        {_styles()}
        <section class='docs-wrap'>
          <div class='docs-head'><div><span class='eyebrow'>DOCUMENTOS</span><h1>Recetas médicas</h1>
          <p>Recetas guardadas en la historia y sincronizadas con la nube.</p></div></div>
          <div class='docs-card'><table class='list-table'>
          <thead><tr><th>Fecha</th><th>Paciente</th><th>Serie</th><th>Diagnóstico</th><th></th></tr></thead>
          <tbody>{body_rows}</tbody></table></div>
        </section>"""
        return HTMLResponse(base("Recetas médicas", body, "recetas"))

    @app.get("/recetas/nueva", response_class=HTMLResponse)
    def prescription_new(patient_id: str, encounter_id: str = ""):
        with _connect(db_path) as conn:
            patient = _patient(conn, patient_id)
            if not patient:
                return HTMLResponse(base("Receta médica", "<p>Paciente no encontrado.</p>", "recetas"), status_code=404)
            encounter = _encounter(conn, encounter_id)
            settings = _settings(conn)
            series = _series(conn, settings)
        diagnosis = str((encounter["diagnosis"] if encounter else "") or "")
        issued = _now()
        body = f"""
        {_styles()}
        <section class='docs-wrap'>
          <div class='docs-head'><div><span class='eyebrow'>RECETA MÉDICA</span><h1>{_e(patient['name'])}</h1>
          <p>La consulta permanece abierta. Los datos del paciente se llenan automáticamente.</p></div></div>
          <div class='docs-grid'>
            <div class='docs-card'>
              <h3>Datos del paciente</h3>
              <div class='docs-fields'>
                <label class='full'>Nombre<input value='{_e(patient['name'])}' readonly></label>
                <label>Cédula<input value='{_e(patient['national_id'])}' readonly></label>
                <label>Edad<input value='{_e(_age(patient['birth_date']))}' readonly></label>
                <label>Sexo<input value='{_e(patient['sex'])}' readonly></label>
                <label>Fecha<input id='rx-date' type='date' value='{date.today().isoformat()}'></label>
                <label>Diagnóstico<input id='rx-dx' value='{_e(diagnosis)}'></label>
                <label>CIE-10<input id='rx-cie'></label>
                <label>Serie No.<input id='rx-series' value='{_e(series)}'></label>
                <label>Alergias<select id='rx-allergy'><option>NO</option><option>SÍ</option></select></label>
                <label class='full'>Detalle alergias<input id='rx-allergy-detail'></label>
              </div>
            </div>
            <div class='docs-card'>
              <h3>Medicamentos / Indicaciones</h3>
              <table class='med-table' id='med-table'><thead><tr><th>Medicamento</th><th>Dosis</th><th>Frecuencia</th><th>Duración</th></tr></thead><tbody>
                {''.join("<tr><td><input class='m-name'></td><td><input class='m-dose'></td><td><input class='m-freq'></td><td><input class='m-duration'></td></tr>" for _ in range(4))}
              </tbody></table>
              <div class='doc-actions'><button class='doc-light' type='button' id='add-med'>Agregar medicamento</button></div>
              <label>Indicaciones adicionales (Rp.)<textarea id='rx-instructions'></textarea></label>
            </div>
          </div>
          <div class='doc-actions'>
            <button class='doc-primary' id='rx-preview'>Vista previa</button>
            <button class='doc-primary' id='rx-print'>Imprimir</button>
            <button class='doc-primary' id='rx-pdf'>Guardar PDF</button>
            <button class='doc-muted' onclick='window.close()'>Cancelar</button>
          </div>
        </section>
        <script>
        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};
        function addRow(){{
          const tr=document.createElement('tr');
          tr.innerHTML="<td><input class='m-name'></td><td><input class='m-dose'></td><td><input class='m-freq'></td><td><input class='m-duration'></td>";
          document.querySelector('#med-table tbody').appendChild(tr);
        }}
        document.getElementById('add-med').onclick=addRow;
        function items(){{
          return [...document.querySelectorAll('#med-table tbody tr')].map(tr=>({{
            medication:tr.querySelector('.m-name').value.trim(),
            dose:tr.querySelector('.m-dose').value.trim(),
            frequency:tr.querySelector('.m-freq').value.trim(),
            duration:tr.querySelector('.m-duration').value.trim()
          }})).filter(x=>x.medication);
        }}
        async function saveRx(){{
          const r=await fetch('/api/recetas',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
            patient_id:patientId,encounter_id:encounterId,issued_date:document.getElementById('rx-date').value,
            series_no:document.getElementById('rx-series').value,diagnosis:document.getElementById('rx-dx').value,
            cie10:document.getElementById('rx-cie').value,allergies:document.getElementById('rx-allergy').value,
            allergies_detail:document.getElementById('rx-allergy-detail').value,items:items(),
            instructions:document.getElementById('rx-instructions').value
          }})}});
          if(!r.ok)throw new Error('No se pudo guardar la receta');
          return await r.json();
        }}
        async function openPreview(printNow=false){{
          try{{const j=await saveRx();const w=window.open(j.preview_url,'_blank');if(printNow&&w)setTimeout(()=>w.print(),700)}}catch(e){{alert(e.message)}}
        }}
        document.getElementById('rx-preview').onclick=()=>openPreview(false);
        document.getElementById('rx-print').onclick=()=>openPreview(true);
        document.getElementById('rx-pdf').onclick=()=>openPreview(true);
        </script>"""
        return HTMLResponse(base("Receta médica", body, "recetas"))

    @app.post("/api/recetas")
    async def prescription_save(request: Request):
        payload = await request.json()
        patient_id = str(payload.get("patient_id") or "").strip()
        if not patient_id:
            return JSONResponse({"ok": False, "error": "patient_id requerido"}, status_code=400)
        stamp = _now()
        issued_date = str(payload.get("issued_date") or date.today().isoformat())
        issued_at = issued_date + "T" + datetime.now().strftime("%H:%M:%S")
        rid = _id()
        with _connect(db_path) as conn:
            if not _patient(conn, patient_id):
                return JSONResponse({"ok": False, "error": "Paciente no encontrado"}, status_code=404)
            conn.execute(
                """INSERT INTO prescriptions(
                     id,patient_id,encounter_id,issued_at,series_no,diagnosis,cie10,
                     allergies,allergies_detail,items_json,instructions,created_at,updated_at,deleted_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (
                    rid, patient_id, str(payload.get("encounter_id") or "") or None, issued_at,
                    str(payload.get("series_no") or ""), str(payload.get("diagnosis") or "").upper(),
                    str(payload.get("cie10") or "").upper(), str(payload.get("allergies") or "NO").upper(),
                    str(payload.get("allergies_detail") or "").upper(),
                    json.dumps(payload.get("items") or [], ensure_ascii=False),
                    str(payload.get("instructions") or "").upper(), stamp, stamp,
                ),
            )
            conn.commit()
        return JSONResponse({"ok": True, "id": rid, "preview_url": f"/recetas/{rid}/vista"})

    @app.get("/recetas/{rx_id}/vista", response_class=HTMLResponse)
    def prescription_preview(rx_id: str):
        with _connect(db_path) as conn:
            row = conn.execute(
                """SELECT r.*,p.name,p.national_id,p.birth_date,p.sex
                   FROM prescriptions r JOIN patients p ON p.id=r.patient_id
                   WHERE r.id=?""",
                (rx_id,),
            ).fetchone()
            settings = _settings(conn)
        if not row:
            return HTMLResponse("Receta no encontrada", status_code=404)
        try:
            items = json.loads(row["items_json"] or "[]")
        except Exception:
            items = []
        meds = "".join(
            f"<div><b>{i+1}. {_e(x.get('medication'))}</b><br>"
            f"{_e(x.get('dose'))} {_e(x.get('frequency'))} {_e(x.get('duration'))}</div>"
            for i, x in enumerate(items)
        )
        one = f"""
        <section class='rx-copy'>
          <header><h2>{_e(settings.get('doctor_name'))}</h2><b>{_e(settings.get('specialty'))}</b>
          <small>Reg. Senescyt: {_e(settings.get('senescyt_registration'))}</small></header>
          <div class='rx-meta'><span>Fecha: {_e(row['issued_at'][:10])}</span><span>Serie No: {_e(row['series_no'])}</span></div>
          <p><b>Nombre:</b> {_e(row['name'])}</p>
          <p><b>Sexo:</b> {_e(row['sex'])} &nbsp; <b>Cédula:</b> {_e(row['national_id'])} &nbsp; <b>Edad:</b> {_e(_age(row['birth_date']))}</p>
          <p><b>Diagnóstico:</b> {_e(row['diagnosis'])} &nbsp; <b>CIE-10:</b> {_e(row['cie10'])}</p>
          <p><b>Alergias:</b> {_e(row['allergies'])} {_e(row['allergies_detail'])}</p>
          <h3>Rp.</h3><div class='rp'>{meds}<br>{_e(row['instructions']).replace(chr(10),'<br>')}</div>
          <footer>{_e(settings.get('prescription_footer'))}</footer>
        </section>"""
        html_doc = f"""<!doctype html><html><head><meta charset='utf-8'><title>Receta médica</title>
        <style>
        body{{font-family:Arial,sans-serif;margin:0;padding:12mm;background:#eee}}.sheet{{background:white;display:grid;grid-template-columns:1fr 1fr;gap:7mm;max-width:297mm;min-height:190mm;margin:auto;padding:8mm;box-sizing:border-box}}
        .rx-copy{{border:1px solid #b8c9d9;padding:8mm;position:relative;min-height:170mm;box-sizing:border-box;background:linear-gradient(145deg,#fff,#f9fcff)}}header{{border-bottom:4px solid #2b6aa7;padding-bottom:7px;margin-bottom:10px;color:#173b66}}header h2{{margin:0}}header small{{display:block}}.rx-meta{{display:flex;justify-content:space-between}}.rp{{min-height:65mm;line-height:1.45}}footer{{position:absolute;left:8mm;right:8mm;bottom:7mm;font-size:10px;color:#445}}
        .toolbar{{max-width:297mm;margin:0 auto 8px;display:flex;gap:8px}}button{{padding:8px 12px}}@media print{{body{{background:#fff;padding:0}}.toolbar{{display:none}}.sheet{{box-shadow:none;padding:5mm}}}}
        </style></head><body><div class='toolbar'><button onclick='window.print()'>Imprimir / Guardar PDF</button></div><main class='sheet'>{one}{one}</main></body></html>"""
        return HTMLResponse(html_doc)

    @app.get("/certificados", response_class=HTMLResponse)
    def certificates_list(patient_id: str = ""):
        with _connect(db_path) as conn:
            args = []
            where = "WHERE COALESCE(c.deleted_at,'')=''"
            if patient_id:
                where += " AND c.patient_id=?"
                args.append(patient_id)
            rows = conn.execute(
                f"""SELECT c.*,p.name,p.national_id
                    FROM certificates c JOIN patients p ON p.id=c.patient_id
                    {where} ORDER BY c.issued_at DESC LIMIT 300""",
                args,
            ).fetchall()
        body_rows = "".join(
            f"<tr><td>{_e(r['issued_at'][:16].replace('T',' '))}</td><td>{_e(r['name'])}</td>"
            f"<td>{_e(r['diagnosis'])}</td><td>{_e(r['rest_days'])}</td>"
            f"<td><a href='/certificados/{_e(r['id'])}/vista' target='_blank'>Ver / imprimir</a></td></tr>"
            for r in rows
        ) or "<tr><td colspan='5'>No hay certificados emitidos.</td></tr>"
        body = f"""{_styles()}<section class='docs-wrap'><div class='docs-head'><div>
        <span class='eyebrow'>DOCUMENTOS</span><h1>Certificados médicos</h1>
        <p>Certificados guardados y sincronizados con la nube.</p></div></div>
        <div class='docs-card'><table class='list-table'><thead><tr><th>Fecha</th><th>Paciente</th><th>Diagnóstico</th><th>Reposo</th><th></th></tr></thead><tbody>{body_rows}</tbody></table></div></section>"""
        return HTMLResponse(base("Certificados médicos", body, "certificados"))

    @app.get("/certificados/nuevo", response_class=HTMLResponse)
    def certificate_new(patient_id: str, encounter_id: str = ""):
        with _connect(db_path) as conn:
            patient = _patient(conn, patient_id)
            if not patient:
                return HTMLResponse(base("Certificado médico", "<p>Paciente no encontrado.</p>", "certificados"), status_code=404)
            encounter = _encounter(conn, encounter_id)
            settings = _settings(conn)
        dx = str((encounter["diagnosis"] if encounter else "") or "")
        today = date.today().isoformat()
        text = _certificate_body(patient, encounter, dx, "", "", "", "", 0, today, today, settings)
        body = f"""{_styles()}<section class='docs-wrap'><div class='docs-head'><div>
        <span class='eyebrow'>CERTIFICADO MÉDICO</span><h1>{_e(patient['name'])}</h1>
        <p>El texto se genera con los datos de la atención y puede editarse antes de emitir.</p></div></div>
        <div class='docs-grid'><div class='docs-card'><h3>Datos del paciente</h3><div class='docs-fields'>
        <label class='full'>Nombre<input value='{_e(patient['name'])}' readonly></label>
        <label>Cédula<input value='{_e(patient['national_id'])}' readonly></label>
        <label>Edad<input value='{_e(_age(patient['birth_date']))}' readonly></label>
        <label>Sexo<input value='{_e(patient['sex'])}' readonly></label>
        <label>Fecha de atención<input id='cert-date' type='date' value='{today}'></label>
        </div></div>
        <div class='docs-card'><h3>Detalles del certificado</h3><div class='docs-fields'>
        <label>Diagnóstico<input id='cert-dx' value='{_e(dx)}'></label><label>CIE-10<input id='cert-cie'></label>
        <label>Diagnóstico adicional<input id='cert-adx'></label><label>CIE-10 adicional<input id='cert-acie'></label>
        <label class='full'>Procedimiento realizado<input id='cert-proc'></label>
        <label>Días de reposo<input id='cert-rest' type='number' min='0' value='0'></label>
        <label>Desde<input id='cert-from' type='date' value='{today}'></label><label>Hasta<input id='cert-to' type='date' value='{today}'></label>
        </div></div></div>
        <div class='docs-card'><label>Texto del certificado (se puede editar)<textarea id='cert-body' rows='12'>{_e(text)}</textarea></label></div>
        <div class='doc-actions'><button class='doc-primary' id='cert-preview'>Vista previa</button><button class='doc-primary' id='cert-print'>Imprimir</button><button class='doc-primary' id='cert-pdf'>Guardar PDF</button><button class='doc-muted' onclick='window.close()'>Cancelar</button></div>
        </section>
        <script>
        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};
        async function saveCert(){{
          const r=await fetch('/api/certificados',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
            patient_id:patientId,encounter_id:encounterId,issued_date:document.getElementById('cert-date').value,
            diagnosis:document.getElementById('cert-dx').value,cie10:document.getElementById('cert-cie').value,
            additional_diagnosis:document.getElementById('cert-adx').value,additional_cie10:document.getElementById('cert-acie').value,
            procedure_text:document.getElementById('cert-proc').value,rest_days:Number(document.getElementById('cert-rest').value||0),
            rest_from:document.getElementById('cert-from').value,rest_to:document.getElementById('cert-to').value,
            body_text:document.getElementById('cert-body').value
          }})}});
          if(!r.ok)throw new Error('No se pudo guardar el certificado');return await r.json();
        }}
        async function openCert(printNow=false){{try{{const j=await saveCert();const w=window.open(j.preview_url,'_blank');if(printNow&&w)setTimeout(()=>w.print(),700)}}catch(e){{alert(e.message)}}}}
        document.getElementById('cert-preview').onclick=()=>openCert(false);
        document.getElementById('cert-print').onclick=()=>openCert(true);
        document.getElementById('cert-pdf').onclick=()=>openCert(true);
        </script>"""
        return HTMLResponse(base("Certificado médico", body, "certificados"))

    @app.post("/api/certificados")
    async def certificate_save(request: Request):
        p = await request.json()
        patient_id = str(p.get("patient_id") or "").strip()
        stamp = _now()
        cid = _id()
        with _connect(db_path) as conn:
            patient = _patient(conn, patient_id)
            if not patient:
                return JSONResponse({"ok": False, "error": "Paciente no encontrado"}, status_code=404)
            settings = _settings(conn)
            enc = _encounter(conn, str(p.get("encounter_id") or ""))
            rest_days = max(0, int(p.get("rest_days") or 0))
            body_text = str(p.get("body_text") or "").strip()
            if not body_text:
                body_text = _certificate_body(
                    patient, enc, str(p.get("diagnosis") or ""), str(p.get("cie10") or ""),
                    str(p.get("additional_diagnosis") or ""), str(p.get("additional_cie10") or ""),
                    str(p.get("procedure_text") or ""), rest_days,
                    str(p.get("rest_from") or date.today().isoformat()),
                    str(p.get("rest_to") or date.today().isoformat()), settings,
                )
            issued_at = str(p.get("issued_date") or date.today().isoformat()) + "T" + datetime.now().strftime("%H:%M:%S")
            conn.execute(
                """INSERT INTO certificates(
                   id,patient_id,encounter_id,issued_at,diagnosis,cie10,additional_diagnosis,
                   additional_cie10,procedure_text,rest_days,rest_from,rest_to,body_text,
                   created_at,updated_at,deleted_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (
                    cid, patient_id, str(p.get("encounter_id") or "") or None, issued_at,
                    str(p.get("diagnosis") or "").upper(), str(p.get("cie10") or "").upper(),
                    str(p.get("additional_diagnosis") or "").upper(), str(p.get("additional_cie10") or "").upper(),
                    str(p.get("procedure_text") or "").upper(), rest_days,
                    str(p.get("rest_from") or ""), str(p.get("rest_to") or ""),
                    body_text.upper(), stamp, stamp,
                ),
            )
            conn.commit()
        return JSONResponse({"ok": True, "id": cid, "preview_url": f"/certificados/{cid}/vista"})

    @app.get("/certificados/{cert_id}/vista", response_class=HTMLResponse)
    def certificate_preview(cert_id: str):
        with _connect(db_path) as conn:
            row = conn.execute(
                """SELECT c.*,p.name,p.national_id,p.birth_date,p.sex
                   FROM certificates c JOIN patients p ON p.id=c.patient_id
                   WHERE c.id=?""",
                (cert_id,),
            ).fetchone()
            settings = _settings(conn)
        if not row:
            return HTMLResponse("Certificado no encontrado", status_code=404)
        return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><title>Certificado médico</title>
        <style>body{{font-family:Arial,sans-serif;background:#eee;padding:12mm}}.toolbar,.sheet{{max-width:210mm;margin:auto}}.toolbar{{margin-bottom:8px}}.sheet{{background:white;min-height:270mm;padding:20mm;box-sizing:border-box}}h1,h2{{color:#173b66;margin:0}}.head{{border-bottom:5px solid #2b6aa7;padding-bottom:10px}}.meta{{font-size:12px;line-height:1.5}}.services{{border:1px solid #173b66;text-align:center;padding:7px;margin:16px 0;font-weight:bold}}.body{{font-size:14px;line-height:1.7;white-space:pre-wrap;margin-top:28px}}.sign{{margin-top:50px}}@media print{{body{{padding:0;background:white}}.toolbar{{display:none}}.sheet{{min-height:auto}}}}</style>
        </head><body><div class='toolbar'><button onclick='window.print()'>Imprimir / Guardar PDF</button></div><main class='sheet'>
        <div class='head'><h1>{_e(settings.get('doctor_name'))}</h1><h2>{_e(settings.get('specialty'))}</h2>
        <div class='meta'>REG. M.S.P. {_e(settings.get('msp_registration'))}<br>Reg. Senescyt {_e(settings.get('senescyt_registration'))}<br>{_e(settings.get('society_membership'))}<br><b>{_e(settings.get('center_name'))}</b><br>{_e(settings.get('address'))}<br>{_e(settings.get('phones'))}</div></div>
        <div class='services'>{_e(settings.get('services_line'))}</div>
        <p style='text-align:right'>Quevedo, {_e(row['issued_at'][:10])}</p>
        <div class='body'>{_e(row['body_text'])}</div>
        <div class='sign'><b>ATTE:</b><br><br><br><b>{_e(settings.get('doctor_name'))}</b><br>{_e(settings.get('specialty'))}<br>MSP. {_e(settings.get('msp_registration'))}<br>Reg. Senescyt: {_e(settings.get('senescyt_registration'))}<br>{_e(settings.get('email'))}<br>Teléfonos: {_e(settings.get('phones'))}</div>
        </main></body></html>""")

    @app.get("/configuracion", response_class=HTMLResponse)
    def configuration():
        with _connect(db_path) as conn:
            shared = _settings(conn)
            local = _local_settings(conn)
        sync = get_sync_status(data_dir) if get_sync_status else {}
        fields = [
            ("doctor_name","Nombre del médico"),("specialty","Especialidad"),
            ("msp_registration","Registro M.S.P."),("senescyt_registration","Registro Senescyt"),
            ("society_membership","Sociedad profesional"),("center_name","Centro / consultorio"),
            ("address","Dirección"),("phones","Teléfonos"),("email","Correo"),
            ("services_line","Línea de servicios"),("prescription_series_start","Serie inicial de recetas"),
            ("prescription_footer","Pie de receta"),("certificate_closing","Cierre del certificado"),
        ]
        shared_html = "".join(
            f"<label class='{'full' if k in {'address','services_line','prescription_footer','certificate_closing'} else ''}'>{_e(label)}"
            f"<input name='{_e(k)}' value='{_e(shared.get(k,''))}'></label>"
            for k,label in fields
        )
        body = f"""{_styles()}<section class='docs-wrap'><div class='docs-head'><div><span class='eyebrow'>CONFIGURACIÓN</span><h1>Historia Clínica</h1><p>Los datos y plantillas compartidos viajan por Neon. Las impresoras son locales de cada PC.</p></div></div>
        <div class='config-nav'><a href='#consultorio'>Datos del consultorio</a><a href='#plantillas'>Plantillas y formatos</a><a href='#usuarios'>Usuarios</a><a href='#impresoras'>Impresoras</a><a href='#sync'>Respaldo y sincronización</a><a href='#otros'>Otros ajustes</a></div>
        <form id='shared-form' class='docs-card'><h2 id='consultorio'>Datos del consultorio / plantillas</h2><div class='docs-fields'>{shared_html}</div><div class='doc-actions'><button class='doc-primary'>Guardar configuración compartida</button></div></form>
        <section class='docs-card'><h2 id='usuarios'>Usuarios</h2><p><b>Dr. Armando Revelo</b> · Usuario clínico principal. Esta actualización no agrega pantalla de login.</p></section>
        <form id='local-form' class='docs-card'><h2 id='impresoras'>Impresoras de esta PC</h2><div class='docs-fields'><label>Recetas<input name='prescription_printer' value='{_e(local.get('prescription_printer'))}'></label><label>Certificados<input name='certificate_printer' value='{_e(local.get('certificate_printer'))}'></label></div><div class='doc-actions'><button class='doc-primary'>Guardar en esta PC</button></div></form>
        <section class='docs-card'><h2 id='sync'>Respaldo y sincronización</h2><p>Estado: <b>{_e(sync.get('state',''))}</b></p><p>{_e(sync.get('message',''))}</p><p>Pendientes: {_e(sync.get('pending',0))} · Última sincronización: {_e(sync.get('last_sync',''))}</p></section>
        <section class='docs-card'><h2 id='otros'>Otros ajustes</h2><p>Las actualizaciones oficiales son obligatorias. La base local y .env permanecen protegidos por el launcher.</p></section>
        </section>
        <script>
        async function submitForm(form,url){{form.addEventListener('submit',async e=>{{e.preventDefault();const data=Object.fromEntries(new FormData(form).entries());const r=await fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});const j=await r.json();alert(j.ok?'Guardado correctamente':(j.error||'No se pudo guardar'));}})}}
        submitForm(document.getElementById('shared-form'),'/api/configuracion/compartida');
        submitForm(document.getElementById('local-form'),'/api/configuracion/local');
        </script>"""
        return HTMLResponse(base("Configuración", body, "configuracion"))

    @app.post("/api/configuracion/compartida")
    async def configuration_shared_save(request: Request):
        payload = await request.json()
        stamp = _now()
        allowed = set(SHARED_DEFAULTS)
        with _connect(db_path) as conn:
            for key, value in payload.items():
                if key not in allowed:
                    continue
                conn.execute(
                    """INSERT INTO clinic_settings(setting_key,setting_value,updated_at,deleted_at)
                       VALUES(?,?,?,NULL)
                       ON CONFLICT(setting_key) DO UPDATE SET
                         setting_value=excluded.setting_value,
                         updated_at=excluded.updated_at,
                         deleted_at=NULL""",
                    (key, str(value or ""), stamp),
                )
            conn.commit()
        return JSONResponse({"ok": True})

    @app.post("/api/configuracion/local")
    async def configuration_local_save(request: Request):
        payload = await request.json()
        stamp = _now()
        allowed = set(LOCAL_DEFAULTS)
        with _connect(db_path) as conn:
            for key, value in payload.items():
                if key not in allowed:
                    continue
                conn.execute(
                    """INSERT INTO local_settings(setting_key,setting_value,updated_at)
                       VALUES(?,?,?)
                       ON CONFLICT(setting_key) DO UPDATE SET
                         setting_value=excluded.setting_value,
                         updated_at=excluded.updated_at""",
                    (key, str(value or ""), stamp),
                )
            conn.commit()
        return JSONResponse({"ok": True})
