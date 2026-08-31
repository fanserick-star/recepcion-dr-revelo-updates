from __future__ import annotations
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_22_whatsapp_audio_blob'
OUT=ROOT/'updates/v4_4_23_agenda_whatsapp'
VERSION='4.4.23'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')
assert 'APP_VERSION = "4.4.22"' in app
assert "const VERSION=\\'4.4.22\\';" in app
assert '/static/app.js?v=4.4.22' in html

app=app.replace('APP_VERSION = "4.4.22"','APP_VERSION = "4.4.23"',1)
app=app.replace("const VERSION=\\'4.4.22\\';","const VERSION=\\'4.4.23\\';",1)
html=html.replace('/static/app.js?v=4.4.22','/static/app.js?v=4.4.23',1)

# ------------------------------------------------------------------
# HTML: Agenda pasa a ser el centro de WhatsApp.
# ------------------------------------------------------------------
nav='''      <button class="nav-btn whatsapp-responses-nav-btn" data-section="whatsappRespuestas" onclick="show('whatsappRespuestas')"><span class="nav-icon nav-brand-icon whatsapp"><img src="/static/whatsapp_mark.svg" alt=""></span><span>Respuestas WhatsApp</span><span id="whatsappResponsesNavBadge" class="nav-count-badge hidden">0</span></button>\n'''
assert nav in html
html=html.replace(nav,'',1)

wa_start=html.index('    <section id="whatsappRespuestas"')
wa_end=html.index('    <section id="config"',wa_start)
html=html[:wa_start]+html[wa_end:]

old_title='''      <div class="agenda-native-title-row">\n        <div class="section-title-with-brand"><div><div class="title-brand-line"><h1>Agenda</h1><span class="section-brand-chip whatsapp"><img src="/static/whatsapp_mark.svg" alt="">WhatsApp</span></div><p class="muted">Toca un horario disponible para agendar · jueves, viernes y sábado · citas de 20 minutos.</p></div></div>\n\n      </div>'''
new_title='''      <div class="agenda-native-title-row agenda-wa-title-row">\n        <div class="section-title-with-brand"><div><div class="title-brand-line"><h1>Agenda</h1><span class="section-brand-chip whatsapp"><img src="/static/whatsapp_mark.svg" alt="">WhatsApp</span></div><p class="muted">Toca un horario disponible para agendar · jueves, viernes y sábado · citas de 20 minutos.</p></div></div>\n        <div id="agendaWhatsappToolbar" class="agenda-wa-toolbar">\n          <button id="agendaWhatsappReviewBtn" class="agenda-wa-pill clear" onclick="toggleAgendaWhatsappReviewPanel()"><span id="agendaWhatsappReviewIcon">✓</span><b id="agendaWhatsappReviewText">WhatsApp al día</b></button>\n          <button class="agenda-wa-refresh" onclick="refreshAgendaWhatsapp()">↻ Actualizar WhatsApp</button>\n        </div>\n      </div>'''
assert old_title in html
html=html.replace(old_title,new_title,1)

grid_needle='''      <div id="agendaNativeGrid" class="agenda-native-grid"><div class="panel muted">Cargando agenda…</div></div>'''
assert grid_needle in html
html=html.replace(grid_needle,'''      <div id="agendaWhatsappReviewPanel" class="agenda-wa-review-panel hidden"></div>\n      <div id="agendaNativeGrid" class="agenda-native-grid"><div class="panel muted">Cargando agenda…</div></div>''',1)

agenda_css=r'''
<style id="v4423-agenda-whatsapp-style">
.agenda-wa-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.agenda-wa-toolbar{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap}.agenda-wa-pill,.agenda-wa-refresh{min-height:36px;border-radius:11px;font-weight:850}.agenda-wa-pill{display:inline-flex;align-items:center;gap:7px;border:1px solid #c9dfd2;background:#edf8f1;color:#2e6f49;padding:7px 11px}.agenda-wa-pill>span{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#58a878;color:#fff}.agenda-wa-pill.review{border-color:#e5c35f;background:#fff8df;color:#74580e}.agenda-wa-pill.review>span{background:#e0aa21}.agenda-wa-pill.offline{border-color:#d9e0e8;background:#f4f6f8;color:#748292}.agenda-wa-pill.offline>span{background:#9aa7b4}.agenda-wa-refresh{border:1px solid #d9e3ed;background:#fff;color:#536b84;padding:7px 10px}.agenda-wa-review-panel{margin:0 0 10px;border:1px solid #ecd073;border-radius:14px;background:#fffaf0;padding:10px}.agenda-wa-review-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:7px}.agenda-wa-review-head b{font-size:11px;color:#624b10}.agenda-wa-review-head small{font-size:8.5px;color:#8b762f}.agenda-wa-review-list{display:grid;gap:6px}.agenda-wa-review-item{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;width:100%;border:1px solid #eadcae;border-radius:10px;background:#fff;padding:8px 10px;text-align:left}.agenda-wa-review-item:hover{background:#fffdf7}.agenda-wa-review-main{min-width:0}.agenda-wa-review-main b,.agenda-wa-review-main span,.agenda-wa-review-main small{display:block}.agenda-wa-review-main b{font-size:10.5px;color:#2e4055}.agenda-wa-review-main span{margin-top:2px;font-size:9px;color:#6c5a26;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.agenda-wa-review-main small{margin-top:2px;font-size:8px;color:#8290a0}.agenda-wa-review-arrow{font-size:21px;color:#b18b1f}.native-slot .agenda-wa-chip{display:inline-flex;align-items:center;gap:3px;width:max-content;max-width:100%;margin-top:3px;border-radius:999px;padding:2px 5px;font-size:7px;font-weight:900;line-height:1.15;white-space:nowrap}.agenda-wa-chip.confirmed{background:#e5f6eb;color:#2d7549}.agenda-wa-chip.no-show{background:#fff0ef;color:#954a44}.agenda-wa-chip.review{background:#fff3c9;color:#7a5d0f}.agenda-wa-chip.resolved{background:#edf1f5;color:#617284}.native-slot.wa-review{box-shadow:inset 0 0 0 2px #e1b32a}.agenda-wa-detail{margin-top:12px;border-top:1px solid #e2e9f1;padding-top:12px}.agenda-wa-detail-loading{padding:13px;border-radius:11px;background:#f6f8fa;color:#74869a;font-size:9.5px}.agenda-wa-detail-card{display:grid;gap:9px;border:1px solid #dce6ef;border-radius:12px;padding:11px;background:#fbfcfe}.agenda-wa-detail-card.review{border-color:#e7cd79;background:#fffaf0}.agenda-wa-detail-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.agenda-wa-detail-head>div>b{display:block;font-size:10px;color:#314a64}.agenda-wa-detail-head>div>small{display:block;margin-top:2px;font-size:8px;color:#8391a1}.agenda-wa-latest{border-radius:10px;background:#f4f7fa;padding:9px 10px}.agenda-wa-latest>span{display:block;font-size:7.5px;font-weight:900;letter-spacing:.06em;color:#74869a}.agenda-wa-latest>p{margin:4px 0 0;font-size:10.5px;line-height:1.42;color:#32475e;white-space:pre-wrap}.agenda-wa-history{border-top:1px solid #e3eaf1;padding-top:8px}.agenda-wa-history summary{cursor:pointer;font-size:9px;font-weight:850;color:#536b83}.agenda-wa-history-list{display:grid;gap:5px;margin-top:7px}.agenda-wa-history-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:7px;align-items:center;padding:6px 7px;border-radius:8px;background:#f5f7f9;font-size:8.5px;color:#586d83}.agenda-wa-history-row b{font-size:9px;color:#304860}.agenda-wa-empty{padding:11px;border:1px dashed #d6e0ea;border-radius:10px;background:#fafbfd;color:#718398;font-size:9.5px}.agenda-wa-detail .wa-audio-card{margin-top:0}.agenda-wa-detail .wa-review-actions{margin-top:2px}@media(max-width:760px){.agenda-wa-title-row{display:grid}.agenda-wa-toolbar{justify-content:flex-start}.agenda-wa-review-item{grid-template-columns:minmax(0,1fr) 18px}.agenda-wa-detail-head{display:grid}}
</style>
'''
html=html.replace('</head>',agenda_css+'</head>',1)

# ------------------------------------------------------------------
# JS: superposición ligera de WhatsApp sobre agenda local.
# ------------------------------------------------------------------
show_sig="function show(id,configTab=null){\n"
assert show_sig in js
js=js.replace(show_sig,"function show(id,configTab=null){\n  if(id==='whatsappRespuestas')id='agenda';\n",1)
js=js.replace("onclick=\"show('whatsappRespuestas')\"","onclick=\"openAgendaWhatsappReviewFromHome()\"")

slot_globals='''const agendaAppointmentById=new Map();\nconst agendaSlotsCache=new Map();'''
assert slot_globals in js
js=js.replace(slot_globals,'''const agendaAppointmentById=new Map();\nconst agendaSlotsCache=new Map();\nlet agendaWhatsappItems=[];\nlet agendaWhatsappLoadedAt=0;\nlet agendaWhatsappWeekKey='';\nlet agendaWhatsappAvailable=true;\nlet agendaWhatsappReviewPanelOpen=false;''',1)

old_load='''async function loadAgenda(){\n  const box=$('#agendaNativeGrid');if(box)box.innerHTML='<div class="panel muted">Cargando agenda…</div>';\n  try{\n    const d=await api('/api/agenda/week?anchor='+encodeURIComponent(agendaNativeAnchor));agendaNativeWeek=d;\n    $('#agendaNativeWeekLabel').textContent=agendaWeekLabel(d);\n    const visibleAnchor=(d.days||[])[0]?.date||agendaNativeAnchor;\n    syncNativeAgendaMonthControl(visibleAnchor);\n    syncNativeAgendaWeekControl(visibleAnchor);\n    renderNativeAgenda(d);\n    const pending=(d.days||[]).flatMap(x=>x.appointments||[]).filter(x=>agendaStatusInfo(x.appointment?.estado).cls==='pending').length;setAgendaPendingBadge(pending);\n  }catch(e){if(box)box.innerHTML=`<div class="panel err">${esc(e.message)}</div>`}\n}'''
new_load='''async function loadAgenda(){\n  const box=$('#agendaNativeGrid');if(box)box.innerHTML='<div class="panel muted">Cargando agenda…</div>';\n  try{\n    const d=await api('/api/agenda/week?anchor='+encodeURIComponent(agendaNativeAnchor));agendaNativeWeek=d;\n    $('#agendaNativeWeekLabel').textContent=agendaWeekLabel(d);\n    const visibleAnchor=(d.days||[])[0]?.date||agendaNativeAnchor;\n    syncNativeAgendaMonthControl(visibleAnchor);\n    syncNativeAgendaWeekControl(visibleAnchor);\n    renderNativeAgenda(d);\n    const pending=(d.days||[]).flatMap(x=>x.appointments||[]).filter(x=>agendaStatusInfo(x.appointment?.estado).cls==='pending').length;setAgendaPendingBadge(pending);\n    loadAgendaWhatsappOverlay(d,false);\n  }catch(e){if(box)box.innerHTML=`<div class="panel err">${esc(e.message)}</div>`}\n}'''
assert old_load in js
js=js.replace(old_load,new_load,1)

old_cell='''function nativeAgendaRowCell(row,date,time){\n  if(!row)return `<button class="native-slot free" onclick="openAgendaSlotPicker('${date}','${time}')"><b class="native-free-time">${esc(fmtTime(time))}</b><span>Disponible</span></button>`;\n  const a=row.appointment||{},p=row.patient||{},staged=row.staged||{},source=String(row.source_type||''),unlinked=source==='MOBILE_UNLINKED'||source==='LEGACY_UNLINKED'||source==='CONFIRMAFY_STAGED'||source==='CONFIRMAFY_LEGACY';\n  const name=staged.nombre||p.nombre||'PACIENTE';const status=agendaStatusInfo(a.estado);const sourceBadge=unlinked?'<small class="native-unlinked">SIN VINCULAR</small>':'';\n  const action=unlinked\n    ?`openUnlinkedAgendaDetail(${Number(staged.id||0)},'${date}')`\n    :`openLinkedAgendaDetail(${Number(a.id||0)},${Number(p.id||0)},'${date}')`;\n  return `<button class="native-slot occupied ${status.cls}" onclick="${action}"><b>${esc(name)}</b><span>${esc(status.label)}</span>${sourceBadge}</button>`;\n}'''
new_cell='''function nativeAgendaRowCell(row,date,time){\n  if(!row)return `<button class="native-slot free" onclick="openAgendaSlotPicker('${date}','${time}')"><b class="native-free-time">${esc(fmtTime(time))}</b><span>Disponible</span></button>`;\n  const a=row.appointment||{},p=row.patient||{},staged=row.staged||{},source=String(row.source_type||''),unlinked=source==='MOBILE_UNLINKED'||source==='LEGACY_UNLINKED'||source==='CONFIRMAFY_STAGED'||source==='CONFIRMAFY_LEGACY';\n  const name=staged.nombre||p.nombre||'PACIENTE';const status=agendaStatusInfo(a.estado);const sourceBadge=unlinked?'<small class="native-unlinked">SIN VINCULAR</small>':'';\n  const wa=!unlinked?agendaWhatsappBadgeHtml(a):{html:'',cls:''};\n  const action=unlinked\n    ?`openUnlinkedAgendaDetail(${Number(staged.id||0)},'${date}')`\n    :`openLinkedAgendaDetail(${Number(a.id||0)},${Number(p.id||0)},'${date}')`;\n  return `<button class="native-slot occupied ${status.cls} ${wa.cls?`wa-${wa.cls}`:''}" onclick="${action}"><b>${esc(name)}</b><span>${esc(status.label)}</span>${wa.html}${sourceBadge}</button>`;\n}'''
assert old_cell in js
js=js.replace(old_cell,new_cell,1)

old_detail='''async function openLinkedAgendaDetail(appointmentId,patientId,fecha){\n  try{let row=agendaAppointmentById.get(Number(appointmentId));if(!row){const d=await api(`/api/agenda/appointments/${appointmentId}`);row=d}const a=row.appointment||{},p=row.patient||await api('/api/patients/'+patientId),st=agendaStatusInfo(a.estado);agendaAppointmentById.set(Number(appointmentId),row);agendaPatientById.set(Number(p.id),p);\n    openModal(`<div class="native-appointment-detail"><div class="modal-form-heading"><h2>${esc(p.nombre)}</h2><p>${fmtDate(a.fecha)} · ${esc(fmtTime(a.hora))}</p></div><div class="native-detail-status ${st.cls}">${esc(st.label)}</div>${a.nota?`<div class="native-detail-note">${esc(a.nota)}</div>`:''}<div class="actions wrap-actions"><button onclick="openPatient(${Number(p.id)},'patients')">Ver paciente</button><button onclick="attendFromAgenda(${Number(p.id)},'${String(fecha).slice(0,10)}')">✓ Atender</button><button onclick="openAgendaPatient(${Number(p.id)},${Number(a.id)})">✎ Editar cita</button><button class="danger ghost" onclick="deleteAgendaAppointment(${Number(a.id)})">Eliminar cita</button></div></div>`);\n  }catch(e){alert(e.message)}\n}'''
new_detail='''async function openLinkedAgendaDetail(appointmentId,patientId,fecha){\n  try{let row=agendaAppointmentById.get(Number(appointmentId));if(!row){const d=await api(`/api/agenda/appointments/${appointmentId}`);row=d}const a=row.appointment||{},p=row.patient||await api('/api/patients/'+patientId),st=agendaStatusInfo(a.estado);agendaAppointmentById.set(Number(appointmentId),row);agendaPatientById.set(Number(p.id),p);\n    openModal(`<div class="native-appointment-detail"><div class="modal-form-heading"><h2>${esc(p.nombre)}</h2><p>${fmtDate(a.fecha)} · ${esc(fmtTime(a.hora))}</p></div><div class="native-detail-status ${st.cls}">${esc(st.label)}</div>${a.nota?`<div class="native-detail-note">${esc(a.nota)}</div>`:''}<div id="agendaWhatsappDetail${Number(a.id)}" class="agenda-wa-detail"><div class="agenda-wa-detail-loading">Cargando confirmación de WhatsApp…</div></div><div class="actions wrap-actions"><button onclick="openPatient(${Number(p.id)},'patients')">Ver paciente</button><button onclick="attendFromAgenda(${Number(p.id)},'${String(fecha).slice(0,10)}')">✓ Atender</button><button onclick="openAgendaPatient(${Number(p.id)},${Number(a.id)})">✎ Editar cita</button><button class="danger ghost" onclick="deleteAgendaAppointment(${Number(a.id)})">Eliminar cita</button></div></div>`);\n    loadAgendaWhatsappAppointmentPanel(Number(a.id),Number(p.id),String(a.fecha||fecha).slice(0,10));\n  }catch(e){alert(e.message)}\n}'''
assert old_detail in js
js=js.replace(old_detail,new_detail,1)

# La resolución manual ya no intenta recargar una página eliminada.
old_resolve='''      closeModal();\n      await loadWhatsappResponses(whatsappResponseScope,true);\n      await refreshWhatsappReviewBadge(true);'''
new_resolve='''      closeModal();\n      agendaWhatsappLoadedAt=0;\n      if(agendaNativeWeek)await loadAgendaWhatsappOverlay(agendaNativeWeek,true);\n      await refreshWhatsappReviewBadge(true);'''
assert old_resolve in js
js=js.replace(old_resolve,new_resolve,1)

helpers=r'''

// ---------------------------------------------------------------------------
// v4.4.23 — WhatsApp integrado dentro de la Agenda
// La agenda sigue siendo local-first. WhatsApp se superpone después y se cachea.
// ---------------------------------------------------------------------------
function agendaWhatsappMatchesAppointment(item,a={}){
  const sid=String(item?.source_id??'').trim(),aid=String(a?.id??'').trim();
  if(sid&&aid)return sid===aid;
  if(sid)return false;
  const d=String(item?.appointment_date||'').slice(0,10),t=String(item?.appointment_time||'').slice(0,5);
  return !!d&&d===String(a?.fecha||'').slice(0,10)&&t===String(a?.hora||'').slice(0,5);
}
function agendaWhatsappItemsForAppointment(a={}){
  return (agendaWhatsappItems||[]).filter(item=>agendaWhatsappMatchesAppointment(item,a));
}
function agendaWhatsappStateForAppointment(a={}){
  const items=agendaWhatsappItemsForAppointment(a),latest=items[0];
  if(!latest)return {kind:'none',items:[],latest:null};
  const interpretation=String(latest.interpretation||'REVISAR').toUpperCase(),unresolved=!latest.resolved_at;
  if(unresolved&&interpretation==='REVISAR')return {kind:'review',items,latest};
  if(interpretation==='CONFIRMADO')return {kind:'confirmed',items,latest};
  if(interpretation==='NO_ASISTIRA')return {kind:'no-show',items,latest};
  return {kind:'resolved',items,latest};
}
function agendaWhatsappBadgeHtml(a={}){
  const st=agendaWhatsappStateForAppointment(a);if(st.kind==='none')return {html:'',cls:''};
  const audio=String(st.latest?.message_type||'').toLowerCase()==='audio',mic=audio?'🎙 ':'';
  if(st.kind==='review')return {cls:'review',html:`<small class="agenda-wa-chip review">⚠ ${mic}WhatsApp: revisar</small>`};
  if(st.kind==='confirmed')return {cls:'confirmed',html:`<small class="agenda-wa-chip confirmed">✓ ${mic}WhatsApp</small>`};
  if(st.kind==='no-show')return {cls:'no-show',html:`<small class="agenda-wa-chip no-show">× ${mic}WhatsApp</small>`};
  return {cls:'resolved',html:`<small class="agenda-wa-chip resolved">💬 ${mic}Revisado</small>`};
}
function agendaWhatsappWeekKeyFor(week={}){
  const days=week.days||[];return days.length?`${days[0].date}|${days[days.length-1].date}`:'';
}
function agendaWhatsappFindVisibleRow(item,week=agendaNativeWeek){
  for(const day of week?.days||[])for(const row of day.appointments||[]){
    const a=row.appointment||{};if(a.id&&agendaWhatsappMatchesAppointment(item,a))return {row,day};
  }
  return null;
}
function renderAgendaWhatsappToolbar(week=agendaNativeWeek,data=null){
  const btn=$('#agendaWhatsappReviewBtn'),icon=$('#agendaWhatsappReviewIcon'),label=$('#agendaWhatsappReviewText'),panel=$('#agendaWhatsappReviewPanel');if(!btn)return;
  if(!agendaWhatsappAvailable){btn.className='agenda-wa-pill offline';if(icon)icon.textContent='☁';if(label)label.textContent='WhatsApp sin conexión';if(panel){panel.classList.add('hidden');panel.innerHTML=''}return}
  const pendingItems=(agendaWhatsappItems||[]).filter(i=>!i.resolved_at&&String(i.interpretation||'').toUpperCase()==='REVISAR');
  const pending=Number(data?.pending??whatsappReviewPendingValue??pendingItems.length)||0;
  btn.className=`agenda-wa-pill ${pending>0?'review':'clear'}`;if(icon)icon.textContent=pending>0?'!':'✓';if(label)label.textContent=pending>0?`${pending} ${pending===1?'respuesta por revisar':'respuestas por revisar'}`:'WhatsApp al día';
  if(!panel)return;
  if(!agendaWhatsappReviewPanelOpen||pendingItems.length===0){panel.classList.add('hidden');panel.innerHTML='';return}
  const rows=pendingItems.map(item=>{
    const found=agendaWhatsappFindVisibleRow(item,week),msg=waMessageBody(item),meta=item.appointment_date?`${fmtDate(item.appointment_date)} · ${fmtTimeCompact(item.appointment_time||'')}`:'Sin cita vinculada';
    const action=found?`openLinkedAgendaDetail(${Number(found.row.appointment.id)},${Number(found.row.patient?.id||0)},'${String(found.day.date).slice(0,10)}')`:`openWhatsappResponse(${Number(item.id)})`;
    return `<button class="agenda-wa-review-item" onclick="${action}"><span class="agenda-wa-review-main"><b>${esc(item.patient_name||item.phone||'Paciente')}</b><span>${esc(msg)}</span><small>${esc(meta)}</small></span><span class="agenda-wa-review-arrow">›</span></button>`;
  }).join('');
  panel.innerHTML=`<div class="agenda-wa-review-head"><div><b>Respuestas que necesitan intervención</b><small>Solo aparecen aquí los casos que la IA no decidió con seguridad.</small></div></div><div class="agenda-wa-review-list">${rows}</div>`;panel.classList.remove('hidden');
}
async function loadAgendaWhatsappOverlay(week=agendaNativeWeek,force=false){
  if(!week||appIdleMode)return null;
  const key=agendaWhatsappWeekKeyFor(week),fresh=agendaWhatsappLoadedAt&&Date.now()-agendaWhatsappLoadedAt<120000;
  if(!force&&fresh&&key===agendaWhatsappWeekKey){renderNativeAgenda(week);renderAgendaWhatsappToolbar(week);return {items:agendaWhatsappItems}}
  try{
    const d=await api('/api/whatsapp-responses?scope=all&limit=200');
    if(d?.available===false){agendaWhatsappAvailable=false;renderAgendaWhatsappToolbar(week,d);return d}
    agendaWhatsappAvailable=true;agendaWhatsappItems=Array.isArray(d?.items)?d.items:[];agendaWhatsappLoadedAt=Date.now();agendaWhatsappWeekKey=key;
    whatsappResponseItems=agendaWhatsappItems;whatsappReviewLastCheck=Date.now();setWhatsappReviewBadge(d?.pending||0);
    renderNativeAgenda(week);renderAgendaWhatsappToolbar(week,d);return d;
  }catch(e){agendaWhatsappAvailable=false;renderAgendaWhatsappToolbar(week);return null}
}
async function refreshAgendaWhatsapp(){agendaWhatsappLoadedAt=0;if(agendaNativeWeek)await loadAgendaWhatsappOverlay(agendaNativeWeek,true)}
function toggleAgendaWhatsappReviewPanel(){
  if(!agendaWhatsappAvailable)return;agendaWhatsappReviewPanelOpen=!agendaWhatsappReviewPanelOpen;renderAgendaWhatsappToolbar(agendaNativeWeek);
}
function openAgendaWhatsappReviewFromHome(){
  agendaWhatsappReviewPanelOpen=true;show('agenda');setTimeout(()=>{renderAgendaWhatsappToolbar(agendaNativeWeek);$('#agendaWhatsappReviewPanel')?.scrollIntoView({behavior:'smooth',block:'start'})},120);
}
function agendaWhatsappDetailTag(item){
  const v=String(item?.interpretation||'REVISAR').toUpperCase();
  if(!item?.resolved_at&&v==='REVISAR')return {text:'Por revisar',cls:'review',icon:'!'};
  if(v==='CONFIRMADO')return {text:'Confirmado',cls:'confirmed',icon:'✓'};
  if(v==='NO_ASISTIRA')return {text:'No asistirá',cls:'no-show',icon:'×'};
  return {text:'Revisado',cls:'muted',icon:'✓'};
}
async function loadAgendaWhatsappAppointmentPanel(appointmentId,patientId,fecha){
  const box=$('#agendaWhatsappDetail'+Number(appointmentId));if(!box)return;
  if(!agendaWhatsappLoadedAt||Date.now()-agendaWhatsappLoadedAt>120000){await loadAgendaWhatsappOverlay(agendaNativeWeek,true);if(!box.isConnected)return}
  if(!agendaWhatsappAvailable){box.innerHTML='<div class="agenda-wa-empty">☁ WhatsApp no está disponible sin conexión. La cita y la agenda local siguen funcionando normalmente.</div>';return}
  const row=agendaAppointmentById.get(Number(appointmentId))||{},a=row.appointment||{id:appointmentId,fecha};
  const items=agendaWhatsappItemsForAppointment(a);
  if(!items.length){box.innerHTML='<div class="agenda-wa-empty"><b>WhatsApp</b><br>No hay una respuesta de confirmación registrada para esta cita.</div>';return}
  const latest=items[0],tag=agendaWhatsappDetailTag(latest),audio=String(latest.message_type||'').toLowerCase()==='audio',body=waMessageBody(latest),unresolved=!latest.resolved_at;
  const audioBlock=audio?`<div class="wa-audio-card"><div><b>🎙 Audio del paciente</b><span>${latest.transcription?'Transcripción disponible':'Sin transcripción automática'}</span></div><audio id="waAudioPlayer${Number(latest.id)}" controls preload="none"></audio><small id="waAudioStatus${Number(latest.id)}" class="wa-audio-error">Cargando audio…</small></div>`:'';
  const actions=unresolved&&String(latest.interpretation||'').toUpperCase()==='REVISAR'?`<div class="wa-review-actions"><button class="primary wa-confirm-btn" onclick="resolveAgendaWhatsappResponse(${Number(latest.id)},'CONFIRMAR',${Number(appointmentId)},${Number(patientId)},'${String(fecha).slice(0,10)}')">✓ Confirmar</button><button class="wa-no-btn" onclick="resolveAgendaWhatsappResponse(${Number(latest.id)},'CANCELAR',${Number(appointmentId)},${Number(patientId)},'${String(fecha).slice(0,10)}')">× No asistirá</button><button class="wa-resolved-btn" onclick="resolveAgendaWhatsappResponse(${Number(latest.id)},'RESUELTO',${Number(appointmentId)},${Number(patientId)},'${String(fecha).slice(0,10)}')">Marcar resuelto</button></div>`:'';
  const history=items.length>1?`<details class="agenda-wa-history"><summary>Historial WhatsApp (${items.length})</summary><div class="agenda-wa-history-list">${items.map(it=>{const t=agendaWhatsappDetailTag(it);return `<div class="agenda-wa-history-row"><span>${String(it.message_type||'').toLowerCase()==='audio'?'🎙':'💬'}</span><span><b>${esc(t.text)}</b> · ${esc(waMessageBody(it))}</span><small>${esc(fmtDateTime(it.received_at))}</small></div>`}).join('')}</div></details>`:'';
  box.innerHTML=`<div class="agenda-wa-detail-card ${tag.cls==='review'?'review':''}"><div class="agenda-wa-detail-head"><div><b>Confirmación por WhatsApp</b><small>Última respuesta: ${esc(fmtDateTime(latest.received_at))} · confianza ${Number(latest.confidence||0)}%</small></div><span class="wa-response-state ${tag.cls}"><b>${tag.icon}</b>${tag.text}</span></div>${audioBlock}<div class="agenda-wa-latest"><span>${audio?'TRANSCRIPCIÓN':'MENSAJE RECIBIDO'}</span><p>${esc(body)}</p></div>${actions}${history}</div>`;
  if(audio)setTimeout(()=>loadWhatsappAudioBlob(Number(latest.id)),0);
}
async function resolveAgendaWhatsappResponse(id,action,appointmentId,patientId,fecha){
  const labels={CONFIRMAR:'Confirmar asistencia',CANCELAR:'Marcar que no asistirá',RESUELTO:'Marcar como resuelto'};
  if(action!=='RESUELTO'&&!confirm(`${labels[action]} para esta cita?`))return;
  await singleFlightMutation(`agenda-wa-${id}`,async()=>{
    try{
      await api(`/api/whatsapp-responses/${Number(id)}/resolve`,{method:'POST',body:JSON.stringify({action})});
      agendaWhatsappLoadedAt=0;if(agendaNativeWeek)await loadAgendaWhatsappOverlay(agendaNativeWeek,true);await refreshWhatsappReviewBadge(true);await openLinkedAgendaDetail(Number(appointmentId),Number(patientId),String(fecha).slice(0,10));
    }catch(e){alert(e.message||'No se pudo resolver la respuesta')}
  },'Guardando…');
}
'''
marker='// ---------------------------------------------------------------------------\n// v4.4.18 — Respuestas WhatsApp: texto, audio y revisión humana\n// ---------------------------------------------------------------------------\n'
assert marker in js
js=js.replace(marker,helpers+'\n'+marker,1)

manifest={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
 'copy':['app.py','static/app.js','static/index.html','update_manifest.json']}
if OUT.exists():shutil.rmtree(OUT)
write(OUT/'app.py',app);write(OUT/'static/app.js',js);write(OUT/'static/index.html',html)
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_23_agenda_whatsapp'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel;files.append({'path':rel,'url':f'{base}/{rel}','sha256':sha(p),'encoding':'utf-8'})
channel={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'mandatory':True,'channel':'files-v3',
 'message':'v4.4.23: fusiona Respuestas WhatsApp con la Agenda. Cada cita muestra su estado de confirmación; los casos Por revisar aparecen arriba de la agenda y la ficha de cita incluye mensaje, transcripción, audio, historial y acciones rápidas. La agenda sigue local-first y WhatsApp se carga después con caché para no ralentizar la PC.',
 'files':files}
write(ROOT/'build/v4423_agenda_whatsapp/candidate_latest.json',json.dumps(channel,ensure_ascii=False,indent=2)+'\n')

assert 'APP_VERSION = "4.4.23"' in app
assert 'data-section="whatsappRespuestas"' not in html
assert '<section id="whatsappRespuestas"' not in html
assert 'agendaWhatsappToolbar' in html and 'agendaWhatsappReviewPanel' in html
assert 'v4423-agenda-whatsapp-style' in html
assert 'loadAgendaWhatsappOverlay' in js and 'loadAgendaWhatsappAppointmentPanel' in js
assert 'agendaWhatsappBadgeHtml' in js and 'openAgendaWhatsappReviewFromHome' in js
assert "if(id==='whatsappRespuestas')id='agenda'" in js
assert '/static/app.js?v=4.4.23' in html
print('V4423_BUILD_OK')
