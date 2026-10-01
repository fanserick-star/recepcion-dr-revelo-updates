from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _db_path() -> Path:
    return ROOT / "data" / "historia_clinica.db"


def _patient_and_encounter(patient_id: str, encounter_id: str) -> tuple[dict, dict]:
    patient = {}
    encounter = {}
    path = _db_path()
    if not path.is_file():
        return patient, encounter
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            if patient_id:
                row = conn.execute(
                    "SELECT id,name,national_id,birth_date,sex FROM patients WHERE id=? LIMIT 1",
                    (patient_id,),
                ).fetchone()
                if row:
                    patient = dict(row)
            if encounter_id:
                row = conn.execute(
                    "SELECT id,patient_id,encounter_date,encounter_time,diagnosis,clinical_note,treatment "
                    "FROM encounters WHERE id=? LIMIT 1",
                    (encounter_id,),
                ).fetchone()
                if row:
                    encounter = dict(row)
                    if not patient and row["patient_id"]:
                        prow = conn.execute(
                            "SELECT id,name,national_id,birth_date,sex FROM patients WHERE id=? LIMIT 1",
                            (row["patient_id"],),
                        ).fetchone()
                        if prow:
                            patient = dict(prow)
    except Exception:
        pass
    return patient, encounter


def _split_name(full_name: str) -> tuple[str, str]:
    """Prellenado editable. No intenta alterar la ficha clínica."""
    parts = [p for p in re.split(r"\s+", str(full_name or "").strip()) if p]
    if len(parts) >= 4:
        return " ".join(parts[:2]), " ".join(parts[2:])
    if len(parts) == 3:
        return " ".join(parts[:2]), parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def _line(value: str = "", cls: str = "", title: str = "") -> str:
    title_attr = f" title='{_e(title)}'" if title else ""
    return f"<input class='fill-line {cls}' value='{_e(value)}'{title_attr}>"


def _render_consent(
    patient_id: str = "",
    encounter_id: str = "",
    queue_id: str = "",
    encounter_date: str = "",
    encounter_time: str = "",
    print_now: int = 0,
) -> str:
    patient, encounter = _patient_and_encounter(patient_id, encounter_id)
    full_name = str(patient.get("name") or "")
    surnames, names = _split_name(full_name)
    national_id = str(patient.get("national_id") or "")
    date_value = str(encounter.get("encounter_date") or encounter_date or datetime.now().date().isoformat())
    time_value = str(encounter.get("encounter_time") or encounter_time or datetime.now().strftime("%H:%M"))[:5]
    diagnosis = str(encounter.get("diagnosis") or "")

    # El documento fuente no tiene un campo clínico estructurado de “procedimiento recomendado”.
    # Se deja editable y en blanco para no inventar información médica.
    procedure = ""

    auto = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),350),{once:true});</script>" if int(print_now or 0) else ""
    return f"""<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Consentimiento Informado · Historia Clínica</title>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;background:#eef2f6;color:#111;font-family:Arial,Helvetica,sans-serif}}
.toolbar{{position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 16px;background:#173b66;color:white;box-shadow:0 2px 10px #0002}}
.toolbar strong{{margin-right:auto}}.toolbar button{{border:0;border-radius:9px;padding:9px 14px;font-weight:800;cursor:pointer;background:#fff;color:#173b66}}.toolbar .primary{{background:#2b6aa7;color:white;border:1px solid #8eb9df}}
.note{{width:210mm;max-width:100%;margin:10px auto 0;background:#fff7d6;border:1px solid #efd57a;border-radius:8px;padding:9px 12px;font-size:12px;color:#664d03}}
.sheet{{position:relative;width:210mm;height:297mm;margin:10px auto;background:#fff;box-shadow:0 8px 28px #0f172a24;overflow:hidden;font-size:9.35pt;line-height:1.2}}
.sheet.page2,.sheet.page3{{border:.25mm solid #777}}
.content{{position:absolute;left:24mm;right:17mm;top:24mm;bottom:17mm}}
.page1 .content{{left:24mm;right:17mm;top:27mm}}
.center{{text-align:center}}.title{{font-size:10.2pt;font-weight:700;margin:0 0 7mm}}.doctor{{font-size:10pt;font-weight:700;margin:0 0 7mm}}
.row{{display:flex;align-items:flex-end;min-height:7.5mm;white-space:nowrap}}
.label{{display:inline-block}}.bold{{font-weight:700}}
.fill-line{{border:0;border-bottom:.28mm solid #222;background:transparent;font:inherit;min-width:20mm;height:5.5mm;padding:0 1mm;outline:none}}
.fill-line:focus{{background:#fffbe6;border-bottom-color:#2b6aa7}}
.w20{{width:20mm}}.w25{{width:25mm}}.w30{{width:30mm}}.w35{{width:35mm}}.w40{{width:40mm}}.w45{{width:45mm}}.w50{{width:50mm}}.w55{{width:55mm}}.w60{{width:60mm}}.w65{{width:65mm}}.w70{{width:70mm}}.w80{{width:80mm}}.w90{{width:90mm}}.w100{{width:100mm}}.w115{{width:115mm}}.w130{{width:130mm}}
.block{{margin-top:2.2mm}}.block-label{{display:block;margin-bottom:1.2mm}}.longline{{width:100%;height:6mm;border:0;border-bottom:.28mm solid #222;background:transparent;font:inherit;outline:none;padding:0 1mm}}
.shortline{{width:24mm;height:6mm;border:0;border-bottom:.28mm solid #222;background:transparent;font:inherit;outline:none;padding:0 1mm}}
.fixed-text{{margin:3.8mm 0 0;line-height:1.45;text-align:left}}
.fixed-text + .fixed-text{{margin-top:4mm}}
.section-bold{{font-weight:700;margin-top:3.2mm}}
.two-col{{display:grid;grid-template-columns:auto 1fr auto 1fr;align-items:end;column-gap:1.5mm}}
.page2 .content,.page3 .content{{left:17mm;right:17mm;top:18mm}}
.page2 .fixed-text{{font-size:9.05pt;line-height:1.42}}
.page3 .fixed-text{{font-size:9.05pt;line-height:1.42}}
.small{{font-size:8.9pt}}
.sp2{{margin-top:2mm}}.sp3{{margin-top:3mm}}.sp4{{margin-top:4mm}}
@page{{size:A4 portrait;margin:0}}
@media print{{html,body{{background:#fff}}.toolbar,.note{{display:none!important}}.sheet{{margin:0;box-shadow:none;page-break-after:always}}.sheet:last-of-type{{page-break-after:auto}}input{{color:#000!important}}}}
</style>
</head>
<body>
<div class='toolbar'><strong>Consentimiento informado · Historia Clínica</strong><button class='primary' onclick='window.print()'>Imprimir</button><button onclick='window.close()'>Cerrar</button></div>
<div class='note'>Los espacios subrayados son editables antes de imprimir. El texto fijo se conserva íntegro según el documento original.</div>

<section class='sheet page1'>
  <div class='content'>
    <div class='center title'>Consentimiento Informado</div>
    <div class='center doctor'>DR. REVELO CASTILLO ARMANDO ARTURO</div>

    <div class='row'><span class='label'>2. Consultorio de cirugía general:&nbsp;</span>{_line('', 'w35')}</div>
    <div class='row'><span class='label'>3. Servicio del establecimiento de salud:&nbsp;</span>{_line('', 'w45')}</div>
    <div class='row'><span class='label bold'>4. NÚMERO DE CÉDULA/HCU DEL PACIENTE:&nbsp;</span>{_line(national_id, 'w50')}</div>
    <div class='row'><span class='label bold'>5. FECHA:&nbsp;</span>{_line(date_value, 'w55')}</div>
    <div class='row'><span class='label bold'>6. HORA:&nbsp;</span>{_line(time_value, 'w30')}</div>
    <div class='two-col row'><span>7. Apellidos</span>{_line(surnames,'w70')}<span>Nombres:</span>{_line(names,'w55')}</div>
    <div class='row'><span>8. TIPO DE ATENCIÓN: Ambulatoria:&nbsp;</span>{_line('', 'w60')}<span style='margin-left:2mm'>Hospitalización:</span></div>
    <div class='row'>{_line('', 'w65')}</div>

    <div class='block'><span class='block-label'>9. NOMBRE DEL DIAGNÓSTICO (codificación CIE10)</span>{_line(diagnosis,'w130')}</div>
    <div class='block'><span class='block-label'>10. NOMBRE DEL PROCEDIMIENTO RECOMENDADO</span>{_line(procedure,'w130')}</div>
    <div class='block'><span class='block-label'>11. ¿EN QUÉ CONSISTE?</span><input class='longline'></div>
    <div class='block'><span class='block-label'>12. ¿CÓMO SE REALIZA?</span><input class='longline'></div>
    <div class='block sp3'>13. GRÁFICO DE LA INTERVENCIÓN (incluya un gráfico previamente seleccionado que facilite la<br>comprensión al paciente)</div>
    <div class='block'><span class='block-label'>14. DURACIÓN ESTIMADA DE LA INTERVENCIÓN:</span>{_line('', 'w100')}</div>
    <div class='block'><span class='block-label'>15. BENEFICIOS DEL PROCEDIMIENTO:</span>{_line('', 'w115')}</div>
    <div class='block'><span class='block-label'>16. RIESGOS FRECUENTES (POCO GRAVES):</span>{_line('', 'w105')}</div>
    <div class='block'><span class='block-label'>17. RIESGOS POCO FRECUENTES (GRAVES):</span>{_line('', 'w105')}</div>
    <div class='block small'>18. DE EXISTIR, ESCRIBA LOS RIESGOS ESPECÍFICOS RELACIONADOS CON EL PACIENTE (edad, estado de<br>salud, creencias, valores, etc.):<input class='longline'><input class='shortline'></div>
    <div class='block'><span class='block-label'>19. ALTERNATIVAS AL PROCEDIMIENTO:</span>{_line('', 'w115')}</div>
  </div>
</section>

<section class='sheet page2'>
  <div class='content'>
    <div class='block'><span class='block-label'>20. DESCRIPCIÓN DEL MANEJO POSTERIOR AL PROCEDIMIENTO:</span>{_line('', 'w90')}</div>
    <div class='block'><span class='block-label'>21. CONSECUENCIAS POSIBLES SI NO SE REALIZA EL PROCEDIMIENTO:</span>{_line('', 'w80')}</div>
    <div class='block sp3'>22. DECLARACIÓN DE CONSENTIMIENTO INFORMADO&nbsp; Fecha: Hora:</div>
    <p class='fixed-text'>He facilitado la información completa que conozco, y me ha sido solicitada, sobre los antecedentes personales, familiares y de mi estado de salud. Soy consciente de que omitir estos datos puede afectar los resultados del tratamiento. Estoy de acuerdo con el procedimiento que se me ha propuesto; he sido informado de las ventajas e inconvenientes del mismo; se me ha explicado de forma clara en qué consiste, los beneficios y posibles riesgos del procedimiento.</p>
    <p class='fixed-text'>He escuchado, leído y comprendido la información recibida y se me ha dado la oportunidad de preguntar sobre el procedimiento. He tomado consciente y libremente la decisión de autorizar el procedimiento. Consiento que, durante la intervención, me realicen otro procedimiento adicional, si es considerado necesario según el juicio del profesional de la salud, para mi beneficio. También conozco que puedo retirar mi consentimiento cuando lo estime oportuno.</p>

    <div class='row'><span>Nombre completo del paciente&nbsp;</span>{_line(full_name,'w90')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line(national_id,'w45')}</div>
    <div class='row'><span>Firma del paciente o huella, según el caso&nbsp;</span>{_line('', 'w70')}</div>
    <div class='row'><span>Nombre de profesional que realiza el procedimiento&nbsp;</span>{_line('', 'w60')}</div>
    <div class='row small'><span>Firma, sello y código del profesional de la salud que realizará el procedimiento&nbsp;</span>{_line('', 'w40')}</div>

    <div class='section-bold'>Si el paciente no está en capacidad para firmar el consentimiento informado:</div>
    <div class='row'><span>Nombre del representante legal&nbsp;</span>{_line('', 'w55')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line('', 'w55')}</div>
    <div class='row'><span>Firma del representante legal&nbsp;</span>{_line('', 'w55')}</div>
    <div class='row'><span>Parentesco:&nbsp;</span>{_line('', 'w65')}</div>

    <div class='row section-bold'><span>23. NEGATIVA DEL CONSENTIMIENTO INFORMADO</span><span style='margin-left:auto'>Fecha:&nbsp;</span>{_line('', 'w40')}</div>
    <p class='fixed-text'>Una vez que he entendido claramente el procedimiento propuesto, así como las consecuencias posibles si no se realiza la intervención, no autorizo y me niego a que se me realice el procedimiento propuesto y desvinculo de responsabilidades futuras de cualquier índole al establecimiento de salud y al profesional sanitario que me atiende, por no realizar la intervención sugerida.</p>
    <div class='row'><span>Nombre completo del paciente&nbsp;</span>{_line(full_name,'w65')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line(national_id,'w55')}</div>
    <div class='row'><span>Firma del paciente o huella, según el caso&nbsp;</span>{_line('', 'w65')}</div>
  </div>
</section>

<section class='sheet page3'>
  <div class='content'>
    <div class='row'><span>Nombre del profesional tratante&nbsp;</span>{_line('', 'w70')}</div>
    <div class='row'><span>Firma, sello y código del profesional tratante&nbsp;</span>{_line('', 'w65')}</div>

    <div class='section-bold'>Si el paciente no está en capacidad para firmar el consentimiento informado:</div>
    <div class='row'><span>Nombre del representante legal&nbsp;</span>{_line('', 'w50')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line('', 'w55')}</div>
    <div class='row'><span>Firma del representante legal&nbsp;</span>{_line('', 'w60')}</div>
    <div class='row'><span>Parentesco:&nbsp;</span>{_line('', 'w65')}</div>

    <div class='section-bold sp4'>Si el paciente no acepta el procedimiento sugerido por el profesional y se niega a firmar este acápite:</div>
    <div class='row'><span>Nombre completo de testigo&nbsp;</span>{_line('', 'w65')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line('', 'w60')}</div>
    <div class='row'><span>Firma del testigo&nbsp;</span>{_line('', 'w60')}</div>

    <div class='section-bold sp4'>24. REVOCATORIA DE CONSENTIMIENTO INFORMADO</div>
    <p class='fixed-text'>De forma libre y voluntaria, revoco el consentimiento realizado en fecha y manifiesto expresamente mi deseo de no continuar con el procedimiento médico que doy por finalizado en esta fecha: Libero de responsabilidades futuras de cualquier índole al establecimiento de salud y al profesional sanitario que me atiende.</p>
    <div class='row'><span>Nombre completo del paciente&nbsp;</span>{_line(full_name,'w70')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line(national_id,'w70')}</div>
    <div class='row'><span>Firma del paciente o huella, según el caso&nbsp;</span>{_line('', 'w75')}</div>

    <div class='section-bold sp4'>Si el paciente no está en capacidad de firmar la negativa del consentimiento informado:</div>
    <div class='row'><span>Nombre del representante legal&nbsp;</span>{_line('', 'w65')}</div>
    <div class='row'><span>Cédula de ciudadanía&nbsp;</span>{_line('', 'w65')}</div>
    <div class='row'><span>Firma del representante legal&nbsp;</span>{_line('', 'w70')}</div>
  </div>
</section>
{auto}
</body></html>"""


def _inject_existing_html(text: str, request_path: str) -> str:
    # Botón dentro de una consulta activa. Mantiene el flujo actual y no finaliza la consulta.
    if request_path.startswith("/paciente/") and "/nueva" in request_path and "id='open-consent'" not in text and 'id="open-consent"' not in text:
        button = "<button id='open-consent' class='secondary document-action consent-action' type='button'>Consentimiento informado</button>"
        cert_marker = "<button id='open-certificate' class='secondary document-action' type='button'>Certificado médico</button>"
        if cert_marker in text:
            text = text.replace(cert_marker, cert_marker + button, 1)
        else:
            tools_marker = "<button id='toggle-macros' class='secondary'>Frases rápidas</button>"
            if tools_marker in text:
                text = text.replace(tools_marker, tools_marker + button, 1)
        helper = r"""
<script id='consent-consult-helper'>
(()=>{
  const b=document.getElementById('open-consent'); if(!b)return;
  b.addEventListener('click',async()=>{
    try{
      let encounterId='';
      if(typeof save==='function'){try{encounterId=await save(true)||'';}catch(_){}}
      let patientId=(typeof PATIENT_ID!=='undefined'&&PATIENT_ID)?String(PATIENT_ID):'';
      if(!patientId){const m=location.pathname.match(/^\/paciente\/([^/]+)/);if(m)patientId=decodeURIComponent(m[1]);}
      const qs=new URLSearchParams();
      if(patientId)qs.set('patient_id',patientId);
      if(encounterId)qs.set('encounter_id',encounterId);
      if(typeof QUEUE_ID!=='undefined'&&QUEUE_ID)qs.set('queue_id',String(QUEUE_ID));
      const d=document.getElementById('enc-date'); if(d&&d.value)qs.set('encounter_date',d.value);
      const t=document.getElementById('enc-time'); if(t&&t.value)qs.set('encounter_time',t.value);
      window.open('/consentimiento/nuevo?'+qs.toString(),'_blank');
    }catch(e){alert('No se pudo abrir el consentimiento informado.');}
  });
})();
</script>
"""
        if "</body>" in text:
            text = text.replace("</body>", helper + "</body>", 1)

    # Botón en la ficha del paciente, junto a Receta y Certificado.
    m = re.fullmatch(r"/paciente/([^/]+)", request_path.rstrip("/"))
    if m and "cp-consent" not in text:
        patient_id = m.group(1)
        button = (
            f"<a class='secondary btn-link cp-consent' target='_blank' "
            f"href='/consentimiento/nuevo?patient_id={_e(patient_id)}'>Consentimiento informado</a>"
        )
        marker = re.compile(r"(<a[^>]*class=['\"][^'\"]*cp-certificate[^'\"]*['\"][^>]*>Certificado médico</a>)", re.I)
        text, n = marker.subn(r"\1" + button, text, count=1)
        if n == 0:
            marker2 = "Editar datos</a>"
            if marker2 in text:
                text = text.replace(marker2, marker2 + button, 1)
    return text


def _install_on_app(app: FastAPI) -> None:
    if getattr(app.state, "consentimiento_informado_installed", False):
        return
    app.state.consentimiento_informado_installed = True

    @app.middleware("http")
    async def _consent_ui_middleware(request: Request, call_next):
        response = await call_next(request)
        content_type = str(response.headers.get("content-type") or "")
        if "text/html" not in content_type.lower():
            return response
        chunks = []
        try:
            async for chunk in response.body_iterator:
                chunks.append(bytes(chunk))
        except Exception:
            return response
        raw = b"".join(chunks)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return HTMLResponse(raw.decode("utf-8", errors="replace"), status_code=response.status_code)
        new_text = _inject_existing_html(text, request.url.path)
        headers = {k: v for k, v in dict(response.headers).items() if k.lower() not in {"content-length", "content-type"}}
        return HTMLResponse(new_text, status_code=response.status_code, headers=headers)

    @app.get("/consentimiento/nuevo", response_class=HTMLResponse)
    def consent_new(
        patient_id: str = "",
        encounter_id: str = "",
        queue_id: str = "",
        encounter_date: str = "",
        encounter_time: str = "",
        print_now: int = 0,
    ):
        return HTMLResponse(_render_consent(patient_id, encounter_id, queue_id, encounter_date, encounter_time, print_now))


def install_fastapi_hook() -> None:
    """Añade consentimiento informado sin alterar datos clínicos ni sincronización."""
    if getattr(FastAPI, "_historia_consentimiento_hook", False):
        return
    FastAPI._historia_consentimiento_hook = True
    original_init = FastAPI.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _install_on_app(self)
        except Exception:
            pass

    FastAPI.__init__ = patched_init
