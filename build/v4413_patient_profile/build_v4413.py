from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = "updates/v4_4_12_badge"
OUT = ROOT / "updates/v4_4_13_patient_profile"
VERSION = "4.4.13"


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)


def text(path: str) -> str:
    return git_bytes(path).decode("utf-8-sig")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "static").mkdir(parents=True, exist_ok=True)

app = text(f"{SRC}/app.py")
js = text(f"{SRC}/static/app.js")
index = text(f"{SRC}/static/index.html")

# Base exacta que acabamos de validar en producción.
assert 'APP_VERSION = "4.4.12"' in app
assert 'const VERSION=' in app and '4.4.12' in app
assert '/static/app.js?v=4.4.12' in index
assert "function attentionSearch(immediate=false)" in js
assert "async function openPatient(id,source='general'){" in js

# ---------------------------------------------------------------------------
# Backend: versión + ficha integral local-first por paciente.
# ---------------------------------------------------------------------------
app = app.replace('APP_VERSION = "4.4.12"', 'APP_VERSION = "4.4.13"', 1)
# El badge vive dentro del overlay Python; sustituimos únicamente su constante.
app, n_badge = re.subn(r"(const VERSION=.*?)4\.4\.12(.*?;)", r"\g<1>4.4.13\g<2>", app, count=1)
assert n_badge == 1, "No se pudo actualizar VERSION del overlay"

# Bug visual pendiente: el traductor PENDIENTE -> POR EMITIR debe actuar SOLO en Facturación.
old_scope = "for(const el of [...document.querySelectorAll('span,b,strong,small')]){\n      const t=norm(el.textContent);\n      if(t==='pendiente' || t==='aprobada')el.textContent='POR EMITIR';\n    }"
new_scope = "const billingScope=document.querySelector('#facturacion');\n    if(billingScope){\n      for(const el of [...billingScope.querySelectorAll('span,b,strong,small')]){\n        const t=norm(el.textContent);\n        if(t==='pendiente' || t==='aprobada')el.textContent='POR EMITIR';\n      }\n    }"
assert app.count(old_scope) == 1, "No se encontró exactamente el traductor global de Facturación"
app = app.replace(old_scope, new_scope, 1)

profile_endpoint = r'''

@app.get("/api/patients/{pid}/profile")
def patient_profile(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Ficha integral de un paciente.

    Se consulta únicamente cuando Recepción abre una ficha: el buscador general
    sigue devolviendo un resumen liviano. No modifica datos ni fuerza una sonda
    extra a Neon; usa la misma sesión local-first que el resto de la aplicación.
    """
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")

    visits = list(db.scalars(
        select(Visit)
        .where(Visit.patient_id == pid)
        .order_by(Visit.fecha.desc(), Visit.id.desc())
    ))
    appointments = list(db.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == pid,
            Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN,
        )
        .order_by(Appointment.fecha.desc(), Appointment.hora.desc(), Appointment.id.desc())
    ))
    billing_rows = db.execute(
        select(BillingRecord, Visit)
        .join(Visit, BillingRecord.visit_id == Visit.id)
        .where(Visit.patient_id == pid)
        .order_by(Visit.fecha.desc(), Visit.id.desc())
    ).all()
    emissions = list(db.scalars(
        select(AzurEmission)
        .where(AzurEmission.patient_id == pid)
        .order_by(AzurEmission.fecha.desc(), AzurEmission.id.desc())
    ))

    historical = historical_summary_for_patient(p)
    return {
        **p_dict(p),
        "visits": [v_dict(v) for v in visits],
        "ultima_atencion": visits[0].fecha if visits else None,
        "historical": historical,
        "appointments": [
            {
                "id": a.id,
                "fecha": a.fecha,
                "hora": a.hora,
                "duracion": a.duracion,
                "nota": a.nota,
                "estado": a.estado,
                "origen": a.origen,
                "created_at": a.created_at,
            }
            for a in appointments
        ],
        "billing": [
            {
                "id": b.id,
                "visit_id": v.id,
                "fecha": v.fecha,
                "estado": b.estado,
                "numero_factura": b.numero_factura,
                "valor": float(v.valor or 0),
                "tipo": v.tipo,
                "procedimiento": v.procedimiento,
                "approved_at": b.approved_at,
                "emitted_at": b.emitted_at,
            }
            for b, v in billing_rows
        ],
        "emissions": [
            {
                "id": x.id,
                "fecha": x.fecha,
                "estado": x.estado,
                "numero_factura": x.numero_factura,
                "has_clave_acceso": bool(x.clave_acceso),
                "updated_at": x.updated_at,
            }
            for x in emissions
        ],
    }
'''
anchor = '@app.post("/api/historical/{hid}/activate")'
assert app.count(anchor) == 1, "No se encontró ancla para ficha integral"
app = app.replace(anchor, profile_endpoint + "\n\n" + anchor, 1)

# ---------------------------------------------------------------------------
# Frontend: resultados clickeables con última atención y advertencias.
# ---------------------------------------------------------------------------
search_start = js.index("      box.innerHTML=usable.length?usable.map(p=>{")
search_end_marker = "      }).join(''):'<div class=\"panel muted\">No encontramos coincidencias. Revisa nombre, cédula, celular o correo.</div>';"
search_end = js.index(search_end_marker, search_start) + len(search_end_marker)
new_search_block = r'''      box.innerHTML=usable.length?usable.map(p=>{
        const missing=typeof missingPatientFields==='function'?missingPatientFields(p):[];
        const warning=missing.length?`<span class="v4413-result-warning">⚠ Datos incompletos</span>`:'';
        if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)){
          const years=typeof historicalYears==='function'?historicalYears(p):'2020–2025';
          const last=p.historical_last_visit_date||p.ultima_atencion;
          const lastText=last?`Última atención histórica: ${fmtDate(last)}`:`Paciente histórico ${years}`;
          return `<article class="v4413-attention-result historical-result" data-v4413-profile-card="1" role="button" tabindex="0" onclick="openHistoricalPatientProfile(${Number(p.historical_id)})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openHistoricalPatientProfile(${Number(p.historical_id)})}"><div class="v4413-result-main"><div class="v4413-result-name-row"><b>${esc(p.nombre||'')}</b><span class="historical-badge">HISTÓRICO ${esc(years)}</span>${warning}</div><span class="v4413-result-meta">${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}${p.correo?` · ${esc(p.correo)}`:''}</span><strong class="v4413-result-last historical">${esc(lastText)}</strong></div><span class="v4413-result-chevron">›</span></article>`;
        }
        const lastText=p.ultima_atencion?`Última atención: ${fmtDate(p.ultima_atencion)}`:'Sin atención registrada desde 2026';
        return `<article class="v4413-attention-result" data-v4413-profile-card="1" role="button" tabindex="0" onclick="openPatient(${Number(p.id)},'attention-search')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPatient(${Number(p.id)},'attention-search')}"><div class="v4413-result-main"><div class="v4413-result-name-row"><b>${esc(p.nombre||'')}</b>${warning}</div><span class="v4413-result-meta">${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}${p.correo?` · ${esc(p.correo)}`:''}</span><strong class="v4413-result-last ${p.ultima_atencion?'has-date':'empty'}">${esc(lastText)}</strong></div><span class="v4413-result-chevron">›</span></article>`;
      }).join(''):'<div class="panel muted">No encontramos coincidencias. Revisa nombre, cédula, celular o correo.</div>';'''
js = js[:search_start] + new_search_block + js[search_end:]

# Modal ancho únicamente para la ficha integral, sin afectar Nueva atención ni otros modales.
old_modal = "function openModal(html){$('#modalBody').innerHTML=html;const box=$('#modal .modalbox');if(box)box.classList.toggle('modalbox-wide',String(html||'').includes('new-attention-start-modal'));$('#modal').classList.remove('hidden')}\nfunction closeModal(){$('#modal').classList.add('hidden');$('#modal .modalbox')?.classList.remove('modalbox-wide');attentionContext=null}"
new_modal = "function openModal(html){$('#modalBody').innerHTML=html;const box=$('#modal .modalbox');if(box){box.classList.toggle('modalbox-wide',String(html||'').includes('new-attention-start-modal'));box.classList.toggle('v4413-profile-shell',String(html||'').includes('v4413-patient-profile'))}$('#modal').classList.remove('hidden')}\nfunction closeModal(){$('#modal').classList.add('hidden');const box=$('#modal .modalbox');box?.classList.remove('modalbox-wide');box?.classList.remove('v4413-profile-shell');attentionContext=null}"
assert js.count(old_modal) == 1, "No se encontró openModal estable"
js = js.replace(old_modal, new_modal, 1)

profile_start = js.index("async function openPatient(id,source='general'){")
profile_end = js.index("\nasync function editPatient(", profile_start)
new_profile = r'''async function openHistoricalPatientProfile(hid){
  try{
    const p=await api(`/api/historical/${Number(hid)}/activate`,{method:'POST'});
    return openPatient(Number(p.id),'attention-search');
  }catch(e){alert(e.message||'No se pudo abrir el paciente histórico.')}
}
function setPatientProfileTab(tab){
  const wanted=String(tab||'resumen');
  document.querySelectorAll('#v4413ProfileTabs [data-profile-tab]').forEach(b=>b.classList.toggle('active',b.dataset.profileTab===wanted));
  document.querySelectorAll('#v4413ProfilePanels [data-profile-panel]').forEach(p=>p.classList.toggle('hidden',p.dataset.profilePanel!==wanted));
}
function patientProfileWarningHtml(p){
  const missing=missingPatientFields(p);
  if(!missing.length)return `<div class="v4413-profile-complete"><span>✓</span><div><b>Datos principales completos</b><small>Cédula, celular y correo registrados.</small></div></div>`;
  const labels=missing.join(', ');
  return `<div class="v4413-profile-warning"><span class="v4413-warning-icon">⚠</span><div><b>Datos incompletos</b><small>Falta completar: ${esc(labels)}.</small></div><button type="button" onclick="editPatient(${Number(p.id)},currentPatientSource)">Completar datos</button></div>`;
}
function patientProfileAgendaHtml(rows=[]){
  if(!rows.length)return '<div class="v4413-profile-empty">No hay citas de Agenda registradas para esta ficha.</div>';
  return `<div class="v4413-profile-timeline">${rows.map(a=>{const st=agendaStatusInfo(a.estado);return `<article class="v4413-timeline-row"><div class="v4413-timeline-date"><b>${fmtDate(a.fecha)}</b><span>${esc(fmtTime(a.hora))}</span></div><div class="v4413-timeline-main"><strong>${esc(st.label)}</strong><small>${a.origen?esc(String(a.origen).replaceAll('_',' ')):'Agenda'}${a.nota?` · ${esc(a.nota)}`:''}</small></div><span class="native-detail-status ${esc(st.cls)}">${esc(st.label)}</span></article>`}).join('')}</div>`;
}
function patientProfileBillingHtml(p){
  const emissions=Array.isArray(p.emissions)?p.emissions:[];
  const lines=Array.isArray(p.billing)?p.billing:[];
  const invoices=emissions.length?`<div class="v4413-profile-subhead"><b>Comprobantes AZUR / SRI</b><span>${emissions.length}</span></div><div class="v4413-profile-timeline">${emissions.map(x=>{const st=String(x.estado||'EN PROCESO').toUpperCase();const cls=st==='AUTORIZADA'?'ok':(['RECHAZADA','DEVUELTA'].includes(st)?'bad':'wait');return `<article class="v4413-timeline-row"><div class="v4413-timeline-date"><b>${fmtDate(x.fecha)}</b><span>${x.numero_factura?`Factura ${esc(x.numero_factura)}`:'Sin número todavía'}</span></div><div class="v4413-timeline-main"><strong>${esc(st.replaceAll('_',' '))}</strong><small>${x.has_clave_acceso?'Enviada a AZUR':'Registro de facturación'}</small></div><span class="v4413-invoice-state ${cls}">${esc(st.replaceAll('_',' '))}</span></article>`}).join('')}</div>`:'';
  const billing=lines.length?`<div class="v4413-profile-subhead"><b>Atenciones en facturación</b><span>${lines.length}</span></div><div class="v4413-profile-timeline">${lines.map(x=>{const service=String(x.procedimiento||'').trim()||'CONSULTA';return `<article class="v4413-timeline-row"><div class="v4413-timeline-date"><b>${fmtDate(x.fecha)}</b><span>${esc(serviceLabel(service))}</span></div><div class="v4413-timeline-main"><strong>${esc(String(x.estado||'PENDIENTE').replaceAll('_',' '))}</strong><small>${x.numero_factura?`Factura ${esc(x.numero_factura)}`:'Sin número de factura'}</small></div><b class="v4413-profile-money">${money(x.valor)}</b></article>`}).join('')}</div>`:'';
  return invoices+billing||'<div class="v4413-profile-empty">No hay registros de facturación para esta ficha.</div>';
}
async function openPatient(id,source='general'){
  currentPatientSource=source;
  const p=await api('/api/patients/'+Number(id)+'/profile');
  const visits=Array.isArray(p.visits)?p.visits:[];
  const appointments=Array.isArray(p.appointments)?p.appointments:[];
  const emissions=Array.isArray(p.emissions)?p.emissions:[];
  const canDelete=source==='patients';
  const history=visits.length?`<div class="patient-history-wrap"><table class="patient-history-table"><thead><tr><th>Fecha</th><th>Estado</th><th>Atención</th><th>Valor</th>${canDelete?'<th class="delete-col">Acción</th>':''}</tr></thead><tbody>${visits.map(v=>`<tr><td>${fmtDate(v.fecha)}</td><td>${esc(statusLabel(v.tipo))}</td><td>${serviceBadge(v)}</td><td><span class="money-pill">${money(v.valor)}</span></td>${canDelete?`<td><button class="danger ghost small-delete" onclick="deleteVisit(${Number(v.id)},${Number(id)})">Borrar</button></td>`:''}</tr>`).join('')}</tbody></table></div>`:'<div class="v4413-profile-empty">Todavía no tiene atenciones registradas desde 2026.</div>';
  const historical=p.historical?`<div class="patient-historical-summary"><div><span>PACIENTE ANTERIOR</span><b>${esc(historicalLastLabel(p.historical))}</b></div><small>Figura en el archivo histórico ${esc(historicalYears(p.historical))}. El histórico anterior a 2026 se conserva como referencia.</small></div>`:'';
  const missing=missingPatientFields(p);
  const last=p.ultima_atencion?fmtDate(p.ultima_atencion):(p.historical?.historical_last_visit_date?fmtDate(p.historical.historical_last_visit_date):'Sin fecha registrada');
  const deleteButton=canDelete?`<button class="danger ghost patient-delete-compact" onclick="deletePatient(${Number(id)},${visits.length})">🗑 Borrar paciente</button>`:'';
  const birth=p.fecha_nacimiento?fmtDate(p.fecha_nacimiento):'Sin registrar';
  const notes=String(p.notas||'').trim();
  openModal(`<div class="patient-profile-modal v4413-patient-profile"><div class="v4413-profile-head"><div class="v4413-profile-name"><span>FICHA DEL PACIENTE</span><h2>${esc(p.nombre)}</h2><div class="v4413-profile-identity"><b>${esc(p.cedula||'Sin cédula')}</b><span>${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</span>${p.correo?`<span>${esc(p.correo)}</span>`:''}</div></div><div class="v4413-profile-actions"><button class="primary" onclick="attentionFor(${Number(id)})">＋ Nueva atención</button><button onclick="openAgendaPatient(${Number(id)})">＋ Agendar cita</button><button class="patient-edit-btn" onclick="editPatient(${Number(id)},'${esc(source)}')">Editar datos</button>${deleteButton}</div></div>${patientProfileWarningHtml(p)}<div class="v4413-profile-kpis"><div><span>Última atención</span><b>${esc(last)}</b></div><div><span>Atenciones</span><b>${visits.length}</b></div><div><span>Citas en Agenda</span><b>${appointments.length}</b></div><div><span>Facturas / envíos</span><b>${emissions.length}</b></div></div><div id="v4413ProfileTabs" class="v4413-profile-tabs"><button class="active" data-profile-tab="resumen" onclick="setPatientProfileTab('resumen')">Datos</button><button data-profile-tab="atenciones" onclick="setPatientProfileTab('atenciones')">Atenciones <span>${visits.length}</span></button><button data-profile-tab="agenda" onclick="setPatientProfileTab('agenda')">Agenda <span>${appointments.length}</span></button><button data-profile-tab="facturacion" onclick="setPatientProfileTab('facturacion')">Facturación <span>${emissions.length||p.billing?.length||0}</span></button></div><div id="v4413ProfilePanels" class="v4413-profile-panels"><section data-profile-panel="resumen"><div class="v4413-data-grid"><div><span>Cédula / identificación</span><b>${esc(p.cedula||'Sin registrar')}</b></div><div><span>Celular</span><b>${esc(formatPhoneValue(p.celular||'')||'Sin registrar')}</b></div><div><span>Correo</span><b>${esc(p.correo||'Sin registrar')}</b></div><div><span>Fecha de nacimiento</span><b>${esc(birth)}</b></div><div><span>Lugar</span><b>${esc(p.lugar||'Sin registrar')}</b></div><div><span>Estado de ficha</span><b>${missing.length?'Datos por completar':'Completa'}</b></div></div>${notes?`<div class="v4413-profile-notes"><span>Notas</span><p>${esc(notes)}</p></div>`:''}${historical}</section><section class="hidden" data-profile-panel="atenciones"><div class="v4413-profile-section-title"><h3>Historial de atenciones</h3><span>Más reciente primero</span></div>${history}</section><section class="hidden" data-profile-panel="agenda"><div class="v4413-profile-section-title"><h3>Historial de Agenda</h3><span>Citas registradas en esta ficha</span></div>${patientProfileAgendaHtml(appointments)}</section><section class="hidden" data-profile-panel="facturacion"><div class="v4413-profile-section-title"><h3>Historial de Facturación</h3><span>Registros vinculados a este paciente</span></div>${patientProfileBillingHtml(p)}</section></div></div>`);
}'''
js = js[:profile_start] + new_profile + js[profile_end:]

# ---------------------------------------------------------------------------
# CSS específico + cache-bust. No se toca el resto del diseño.
# ---------------------------------------------------------------------------
profile_css = r'''
<style id="v4413-patient-profile-css">
.v4413-attention-result{display:flex;align-items:center;gap:14px;padding:13px 10px;border-bottom:1px solid #e6edf5;cursor:pointer;transition:background .12s ease,border-color .12s ease;border-radius:10px}.v4413-attention-result:hover,.v4413-attention-result:focus{background:#f4f8ff;outline:none}.v4413-result-main{min-width:0;flex:1;display:grid;gap:5px}.v4413-result-name-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.v4413-result-name-row>b{font-size:14px;color:#17263d}.v4413-result-meta{font-size:11px;color:#637995}.v4413-result-last{font-size:12px;color:#245b91}.v4413-result-last.empty{color:#7a8898;font-weight:700}.v4413-result-last.historical{color:#87651d}.v4413-result-warning{font-size:9px;font-weight:900;color:#9a6400;background:#fff5d7;border:1px solid #f0d68e;border-radius:999px;padding:3px 7px}.v4413-result-chevron{font-size:27px;color:#8aa4c3;font-weight:300}.modalbox.v4413-profile-shell{width:min(930px,96vw)!important;max-width:930px!important;max-height:92vh!important;overflow:auto!important}.v4413-patient-profile{display:grid;gap:14px}.v4413-profile-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.v4413-profile-name>span{font-size:9px;font-weight:950;letter-spacing:.08em;color:#5e7da0}.v4413-profile-name h2{margin:3px 0 7px;font-size:24px;color:#172b46}.v4413-profile-identity{display:flex;gap:8px;flex-wrap:wrap;color:#627892;font-size:11px}.v4413-profile-identity>*{background:#f2f6fb;border-radius:999px;padding:4px 8px}.v4413-profile-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.v4413-profile-warning,.v4413-profile-complete{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;border-radius:13px;padding:10px 12px}.v4413-profile-warning{background:#fff7df;border:1px solid #f0d58a;color:#6f5311}.v4413-profile-complete{grid-template-columns:auto 1fr;background:#eef9f2;border:1px solid #c9e9d3;color:#2c6740}.v4413-profile-warning b,.v4413-profile-complete b{display:block;font-size:12px}.v4413-profile-warning small,.v4413-profile-complete small{display:block;font-size:10px;margin-top:2px}.v4413-warning-icon{font-size:20px}.v4413-profile-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.v4413-profile-kpis>div{border:1px solid #dce6f1;background:#f8fbff;border-radius:12px;padding:10px}.v4413-profile-kpis span{display:block;font-size:9px;font-weight:850;text-transform:uppercase;color:#70849b}.v4413-profile-kpis b{display:block;margin-top:4px;font-size:15px;color:#17385f}.v4413-profile-tabs{display:flex;gap:5px;border-bottom:1px solid #dde6ef;padding-bottom:7px;overflow:auto}.v4413-profile-tabs button{border:0;background:transparent;padding:8px 11px;border-radius:9px;font-weight:800;color:#5a708b;white-space:nowrap}.v4413-profile-tabs button.active{background:#eaf3ff;color:#245b96}.v4413-profile-tabs button span{display:inline-flex;min-width:20px;justify-content:center;background:#fff;border-radius:999px;margin-left:4px;padding:1px 5px;font-size:9px}.v4413-profile-panels>section{padding-top:2px}.v4413-data-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.v4413-data-grid>div{border:1px solid #e2e9f1;border-radius:11px;padding:10px 12px}.v4413-data-grid span{display:block;font-size:9px;font-weight:850;text-transform:uppercase;color:#72849a}.v4413-data-grid b{display:block;margin-top:4px;font-size:12px;color:#263a53;overflow-wrap:anywhere}.v4413-profile-notes{margin-top:9px;padding:10px 12px;border-radius:11px;background:#f7f8fa}.v4413-profile-notes span{font-size:9px;font-weight:900;color:#6b7c90;text-transform:uppercase}.v4413-profile-notes p{margin:4px 0 0;font-size:11px;color:#394b60}.v4413-profile-section-title,.v4413-profile-subhead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 0 9px}.v4413-profile-section-title h3{margin:0;font-size:15px;color:#243950}.v4413-profile-section-title span,.v4413-profile-subhead span{font-size:10px;color:#788a9d}.v4413-profile-subhead{margin-top:14px;border-bottom:1px solid #e6edf4;padding-bottom:6px}.v4413-profile-subhead>b{font-size:11px;color:#354c67}.v4413-profile-timeline{display:grid;gap:7px}.v4413-timeline-row{display:grid;grid-template-columns:125px minmax(0,1fr) auto;gap:12px;align-items:center;border:1px solid #e2e9f1;border-radius:11px;padding:9px 11px;background:#fff}.v4413-timeline-date b,.v4413-timeline-date span,.v4413-timeline-main strong,.v4413-timeline-main small{display:block}.v4413-timeline-date b{font-size:11px;color:#2d4867}.v4413-timeline-date span{font-size:10px;color:#75889e;margin-top:2px}.v4413-timeline-main strong{font-size:11px;color:#263d57}.v4413-timeline-main small{font-size:9px;color:#73869b;margin-top:2px}.v4413-invoice-state{border-radius:999px;padding:4px 7px;font-size:8px;font-weight:900}.v4413-invoice-state.ok{background:#e9f7ee;color:#297246}.v4413-invoice-state.wait{background:#edf4ff;color:#426c9d}.v4413-invoice-state.bad{background:#fff0ef;color:#9c4a44}.v4413-profile-money{font-size:12px;color:#254b76}.v4413-profile-empty{padding:18px;border:1px dashed #cfdae6;border-radius:11px;text-align:center;color:#71849a;font-size:11px}@media(max-width:720px){.v4413-profile-head{display:grid}.v4413-profile-actions{justify-content:flex-start}.v4413-profile-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.v4413-data-grid{grid-template-columns:1fr}.v4413-timeline-row{grid-template-columns:100px minmax(0,1fr)}.v4413-timeline-row>:last-child{grid-column:2}.v4413-profile-warning{grid-template-columns:auto 1fr}.v4413-profile-warning button{grid-column:1/-1}.modalbox.v4413-profile-shell{width:97vw!important}}
</style>
'''
assert '<style id="v4413-patient-profile-css">' not in index
index = index.replace('</head>', profile_css + '\n</head>', 1)
index = index.replace('/static/app.js?v=4.4.12', '/static/app.js?v=4.4.13', 1)

# Marcadores de seguridad funcional.
assert "data-v4413-profile-card" in js
assert "Última atención:" in js
assert "Datos incompletos" in js and "Completar datos" in js
assert "Historial de Agenda" in js and "Historial de Facturación" in js
assert "/api/patients/'+Number(id)+'/profile" in js
assert "billingScope.querySelectorAll('span,b,strong,small')" in app
assert "document.querySelectorAll('span,b,strong,small')" not in app
assert 'RP_PORT' in app and 'pg8000' in app

app_bytes = app.encode('utf-8')
js_bytes = js.encode('utf-8')
index_bytes = index.encode('utf-8')
(OUT / 'app.py').write_bytes(app_bytes)
(OUT / 'static/app.js').write_bytes(js_bytes)
(OUT / 'static/index.html').write_bytes(index_bytes)

inner = {
    "product": "recepcion-pacientes",
    "version": VERSION,
    "app_version": VERSION,
    "runtime_version": VERSION,
    "launcher_version": "4.3.100-standalone-7",
    "updater_version": "integrado-en-launcher",
    "copy": ["app.py", "static/app.js", "static/index.html", "update_manifest.json"],
}
inner_bytes = (json.dumps(inner, ensure_ascii=False, indent=2) + "\n").encode('utf-8')
(OUT / 'update_manifest.json').write_bytes(inner_bytes)

base_url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_13_patient_profile"
files = []
for rel, data in [
    ("app.py", app_bytes),
    ("static/app.js", js_bytes),
    ("static/index.html", index_bytes),
    ("update_manifest.json", inner_bytes),
]:
    files.append({"path": rel, "url": f"{base_url}/{rel}", "sha256": sha(data), "encoding": "utf-8"})
latest = {
    "product": "recepcion-pacientes",
    "version": VERSION,
    "app_version": VERSION,
    "runtime_version": VERSION,
    "mandatory": True,
    "channel": "files-v3",
    "message": "v4.4.13: ficha integral al tocar un paciente, última atención visible en Nueva atención, advertencias de datos incompletos e historial de atenciones, Agenda y Facturación. Corrige POR EMITIR fuera de Facturación.",
    "files": files,
}
(ROOT / 'build/v4413_patient_profile/candidate_latest.json').write_text(json.dumps(latest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({"version": VERSION, "app_sha256": sha(app_bytes), "js_sha256": sha(js_bytes), "index_sha256": sha(index_bytes), "files": len(files)}, indent=2))
