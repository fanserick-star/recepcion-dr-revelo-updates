from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v477'
OUT=ROOT/'updates'/'v478'
VERSION='4.3.78'
LAUNCHER_VERSION='4.3.76-standalone-3'


def joined(prefix,n):
    ps=sorted(SRC.glob(prefix+'*'),key=lambda p:int(p.name.replace(prefix,'')))
    if len(ps)!=n: raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(ps)}')
    return ''.join(p.read_text(encoding='utf-8') for p in ps)

def sha(b): return hashlib.sha256(b).hexdigest()

def write_parts(text,prefix,n):
    OUT.mkdir(parents=True,exist_ok=True)
    for p in OUT.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/n); names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text:
        raise SystemExit(f'{prefix}: reconstrucción inválida')
    return names

REMIX_CSS=r'''
/* v4.3.78 — Inicio compacto + Agenda mañana/tarde */
#inicio .home-title-row{align-items:center!important;margin:0 0 7px!important;gap:16px!important}
#inicio .page-heading{gap:1px!important}
#inicio .page-eyebrow{font-size:8px!important;letter-spacing:.11em!important}
#inicio .page-heading h1{font-size:25px!important;line-height:1.05!important;margin:1px 0!important}
#inicio .page-heading p{font-size:10px!important;margin:2px 0 0!important}
#inicio .new-attention-main{min-height:43px!important;padding:10px 20px!important;border-radius:12px!important;font-size:12px!important}
#inicio .home-week-nav{justify-content:flex-end!important;margin:0 0 6px!important;gap:5px!important}
#inicio .tiny-week-label{font-size:9px!important;padding:4px 8px!important}
#inicio .tiny-week-btn{min-width:29px!important;min-height:28px!important;padding:4px 7px!important;font-size:9px!important;border-radius:9px!important}
#inicio .week-cards{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr)) minmax(190px,.85fr)!important;gap:8px!important;margin:0 0 8px!important}
#inicio .week-card.v478-week-chip{min-height:58px!important;padding:9px 11px!important;border-radius:12px!important;display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;grid-template-areas:'day count' 'meta total'!important;gap:2px 9px!important;align-items:center!important;box-shadow:none!important;transform:none!important}
#inicio .v478-week-chip .week-day{grid-area:day;font-size:12px!important;font-weight:900!important;line-height:1.1!important}
#inicio .v478-week-chip .v478-week-count{grid-area:count;font-size:20px!important;line-height:1!important;color:#1f5fbf!important;font-weight:900!important}
#inicio .v478-week-chip .v478-week-meta{grid-area:meta;font-size:8.5px!important;color:#748297!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
#inicio .v478-week-chip .v478-week-total{grid-area:total;font-size:10px!important;font-weight:850!important;color:#304760!important;white-space:nowrap!important}
#inicio .week-card.v478-week-chip.active{background:#edf5ff!important;border-color:#75a2d7!important;box-shadow:inset 0 0 0 1px #bad2ec!important}
#inicio .week-card.v478-week-chip.active:after{left:11px!important;right:11px!important;height:2px!important}
#inicio .v478-week-total-card{min-height:58px;border:1px solid #dbe4ee;border-radius:12px;background:#f7f9fc;padding:9px 12px;display:grid;grid-template-columns:1fr auto;grid-template-areas:'kicker money' 'patients money';gap:2px 10px;align-items:center}
#inicio .v478-week-total-card span{grid-area:kicker;font-size:8px;font-weight:900;letter-spacing:.11em;color:#738197}
#inicio .v478-week-total-card strong{grid-area:patients;font-size:11px;color:#293e5b}
#inicio .v478-week-total-card b{grid-area:money;font-size:15px;color:#214f84;white-space:nowrap}
#inicio #weekSummary{display:none!important}
#inicio .selected-day-title{margin:2px 0 6px!important;padding:0!important}
#inicio .v478-day-head{width:100%;display:flex;align-items:end;justify-content:space-between;gap:12px}
#inicio .v478-day-head-main{display:grid;gap:1px}
#inicio .v478-day-kicker{font-size:8px;font-weight:900;letter-spacing:.1em;color:#7b8798;text-transform:uppercase}
#inicio .v478-day-head h2{font-size:17px!important;line-height:1.1!important;margin:0!important}
#inicio .v478-day-stats{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
#inicio .v478-day-stats span,#inicio .v478-day-stats b{border:1px solid #dfe6ef;background:#f8fafc;border-radius:999px;padding:5px 8px;font-size:9px;color:#53667f;white-space:nowrap}
#inicio .v478-day-stats b{color:#214f84;background:#edf5ff;border-color:#d3e2f4}
#inicio #todayTable{overflow:visible!important;border-radius:13px!important;box-shadow:none!important}
#inicio .home-patient-table{font-size:12px!important}
#inicio .home-patient-table thead th{position:sticky!important;top:0;z-index:4;background:#edf3f9!important;padding:7px 8px!important;font-size:8.5px!important;letter-spacing:.055em!important}
#inicio .home-patient-table td{padding:6px 8px!important;vertical-align:middle!important}
#inicio .home-patient-table th:nth-child(1){width:5%!important}#inicio .home-patient-table th:nth-child(2){width:42%!important}#inicio .home-patient-table th:nth-child(3){width:18%!important}#inicio .home-patient-table th:nth-child(4){width:11%!important}#inicio .home-patient-table th:nth-child(5){width:24%!important}
#inicio .row-number{font-size:11px!important}.v478-home-table .patient-name-line>a{font-size:12px!important;line-height:1.15!important}.v478-home-table .new-patient-badge{font-size:7px!important;padding:2px 5px!important}.v478-home-table .service-badge{font-size:8.5px!important;padding:4px 7px!important}.v478-home-table .money-pill{font-size:9px!important;min-width:58px!important;padding:4px 6px!important}
.v478-home-actions{display:flex;align-items:center;justify-content:flex-end;gap:4px;white-space:nowrap}.v478-home-actions>button,.v478-more-summary{border:1px solid #dbe3ed!important;background:#fff!important;color:#425774!important;border-radius:8px!important;padding:5px 7px!important;font-size:8px!important;font-weight:800!important;min-height:27px!important;line-height:1!important}.v478-home-actions>button:hover,.v478-more-summary:hover{background:#f3f7fb!important}.v478-home-more{position:relative;display:inline-block}.v478-home-more>summary{list-style:none;cursor:pointer}.v478-home-more>summary::-webkit-details-marker{display:none}.v478-home-more-menu{display:none;position:absolute;right:0;top:31px;z-index:20;min-width:132px;padding:5px;border:1px solid #dbe3ed;border-radius:9px;background:#fff;box-shadow:0 8px 24px rgba(35,55,80,.15)}.v478-home-more[open] .v478-home-more-menu{display:block}.v478-home-more-menu button{width:100%;border:0;background:#fff4f3;color:#9a3f38;border-radius:7px;padding:7px 8px;font-size:8.5px;font-weight:850;text-align:left}.v478-home-more-menu button:hover{background:#ffe9e7}
#inicio .sub-visit-row td{padding-top:4px!important;padding-bottom:4px!important}.v478-home-table .sub-visit-label{font-size:9px!important}

/* Nueva atención — AGENDA grande y separación por jornada */
.modalbox.modalbox-wide.v477-attention-modalbox{width:min(820px,94vw)!important;padding:19px 21px 18px!important}
.v478-attention .v477-attention-top{margin-bottom:0!important}.v478-attention .v477-attention-top .modal-form-heading h2{font-size:21px!important}.v478-attention .attention-start-search .search{height:44px!important}
.v478-agenda-shell{border:1px solid #dce5ef;border-radius:14px;background:#fff;overflow:hidden}
.v478-agenda-brand{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px;border-bottom:1px solid #dfe8f2;background:linear-gradient(90deg,#edf5ff,#f9fbfe)}
.v478-agenda-title{display:flex;align-items:baseline;gap:9px;min-width:0}.v478-agenda-title span{font-size:8px;font-weight:900;letter-spacing:.11em;color:#708098;white-space:nowrap}.v478-agenda-title strong{font-size:24px;line-height:1;color:#1d4f86;letter-spacing:-.025em}.v478-agenda-date{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}.v478-agenda-date b{font-size:10px;color:#344b69}.v478-agenda-date span{border:1px solid #cedced;background:#fff;border-radius:999px;padding:4px 7px;font-size:8.5px;font-weight:850;color:#536a86;white-space:nowrap}
.v478-shifts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0}.v478-shift{min-width:0}.v478-shift+ .v478-shift{border-left:1px solid #e2e9f1}.v478-shift-head{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;background:#fafbfd;border-bottom:1px solid #e7ecf2}.v478-shift-head b{font-size:10px;letter-spacing:.09em;color:#475d78}.v478-shift-head span{font-size:8px;font-weight:850;color:#74849a;background:#eef2f7;border-radius:999px;padding:3px 6px}.v478-shift-list{display:grid;gap:5px;padding:7px;align-content:start}.v478-shift .attention-week-row{grid-template-columns:48px minmax(0,1fr)!important;min-height:46px!important;padding:7px 9px!important;margin:0!important;border-radius:9px!important}.v478-shift .attention-week-time{font-size:11px!important}.v478-shift .attention-week-person b{font-size:10.5px!important}.v478-shift .attention-week-person small{font-size:8.5px!important}.v478-shift-empty{padding:18px 10px;text-align:center;font-size:9px;color:#8995a5}.v478-agenda-conflict{margin-left:6px;color:#995b16!important;background:#fff5e8!important;border-color:#f1d3a9!important}
@media(max-width:900px){#inicio .week-cards{grid-template-columns:repeat(2,minmax(0,1fr))!important}.v478-home-actions{flex-wrap:wrap}.v478-shifts{grid-template-columns:1fr}.v478-shift+.v478-shift{border-left:0;border-top:1px solid #e2e9f1}}
@media(max-width:620px){#inicio .week-cards{grid-template-columns:1fr!important}#inicio .v478-day-head{align-items:flex-start;flex-direction:column}.v478-agenda-brand{align-items:flex-start;flex-direction:column}.v478-agenda-date{justify-content:flex-start}.v478-agenda-title strong{font-size:21px}.v478-home-actions>button,.v478-more-summary{padding:5px 6px!important}}
'''

REMIX_JS=r''';(()=>{
  if(window.__v478Remix)return;window.__v478Remix=true;
  const eh=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  window.renderWeekCards=function(days){
    const totalPatients=(days||[]).reduce((s,d)=>s+Number(weeklyData[d.iso]?.count||0),0);
    const totalMoney=(days||[]).reduce((s,d)=>s+Number(weeklyData[d.iso]?.total||0),0);
    const box=$('#weekCards');if(!box)return;
    box.innerHTML=(days||[]).map(d=>{const info=weeklyData[d.iso]||{count:0,total:0};return `<button class="week-card v478-week-chip ${selectedHomeDate===d.iso?'active':''}" data-date="${d.iso}" onclick="selectHomeDay('${d.iso}')"><span class="week-day">${eh(d.label)}</span><strong class="v478-week-count">${Number(info.count||0)}</strong><span class="v478-week-meta">${fmtDate(d.iso)} · ${Number(info.count||0)===1?'paciente':'pacientes'}</span><span class="v478-week-total">${money(info.total||0)}</span></button>`}).join('')+`<div class="v478-week-total-card"><span>TOTAL SEMANA</span><strong>${totalPatients} ${totalPatients===1?'paciente':'pacientes'}</strong><b>${money(totalMoney)}</b></div>`;
    const old=$('#weekSummary');if(old)old.innerHTML='';
  };

  function homeMore(v){const id=Number(v?.id||0),fecha=String(v?.fecha||selectedHomeDate||'').slice(0,10);return `<details class="v478-home-more"><summary class="v478-more-summary" title="Más acciones">•••</summary><div class="v478-home-more-menu"><button type="button" onclick="event.preventDefault();event.stopPropagation();deleteVisitFromHome(${id},'${eh(fecha)}')">🗑 Borrar atención</button></div></details>`}
  function homeActions(g,fecha,primary){const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||'').trim());const pid=Number(g.patient?.id||0);return `<div class="v478-home-actions">${hasConsultation?`<button type="button" onclick="viewReceiptFromHome(${pid},'${eh(fecha)}')">Recibo</button><button type="button" onclick="reprintReceiptFromHome(${pid},'${eh(fecha)}')">Imprimir</button>`:''}${homeMore(primary)}</div>`}
  function remasterHomeTable(rows){
    if(!rows?.length)return '<div class="panel muted empty-state">No hay pacientes registrados en este día.</div>';
    const groups=groupHomeVisits(rows);const head='<tr><th class="number-col">N.º</th><th>Paciente</th><th>Atención</th><th>Valor</th><th class="home-actions-col">Acciones</th></tr>';
    const body=groups.map((g,index)=>{const consultations=g.visits.filter(v=>!String(v.procedimiento||'').trim()),proceduresOnly=g.visits.filter(v=>String(v.procedimiento||'').trim()),primary=consultations[0]||proceduresOnly[0],extras=consultations.length?[...consultations.slice(1),...proceduresOnly]:proceduresOnly.slice(1),num=groups.length-index,fecha=String(primary?.fecha||selectedHomeDate||'').slice(0,10),main=`<tr class="patient-main-row"><td class="row-number" rowspan="${1+extras.length}">${num}.</td><td class="patient-cell" rowspan="${1+extras.length}">${patientNameCell(primary,true,g.isNew)}</td><td>${serviceBadge(primary)}</td><td class="money-cell"><span class="money-pill">${money(primary.valor)}</span></td><td class="home-action-cell">${homeActions(g,fecha,primary)}</td></tr>`,sub=extras.map(v=>`<tr class="sub-visit-row"><td><span class="sub-visit-label">↳</span> ${serviceBadge(v)}</td><td class="money-cell sub-money"><span class="money-pill subtle">${money(v.valor)}</span></td><td class="home-action-cell sub-actions"><div class="v478-home-actions">${homeMore(v)}</div></td></tr>`).join('');return main+sub}).join('');
    return `<table class="home-patient-table v478-home-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  window.renderHomeDayPayload=function(iso,d){
    if(!d)return;const label=d.label||weeklyData[iso]?.label||'Día',count=Number(d.count||0),today=toISO(new Date())===String(iso).slice(0,10),title=$('#selectedDayTitle');
    if(title)title.innerHTML=`<div class="v478-day-head"><div class="v478-day-head-main"><span class="v478-day-kicker">${today?'HOY':'DÍA SELECCIONADO'}</span><h2>${eh(label)} ${fmtDate(iso)}</h2></div><div class="v478-day-stats"><span>${count} ${count===1?'paciente':'pacientes'}</span><b>${money(d.total||0)}</b></div></div>`;
    const tableBox=$('#todayTable');if(tableBox){try{tableBox.innerHTML=remasterHomeTable(d.visits||[])}catch(err){console.error(err);tableBox.innerHTML='<div class="panel home-render-error">No se pudo dibujar este día.</div>'}tableBox.scrollLeft=0;tableBox.scrollTop=0}
  };

  function apptMinutes(row){const raw=String(row?.appointment?.hora||row?.staged?.hora||'00:00').slice(0,5),m=/^(\d{1,2}):(\d{2})$/.exec(raw);return m?Number(m[1])*60+Number(m[2]):0}
  function shiftBlock(title,rows){return `<section class="v478-shift"><div class="v478-shift-head"><b>${title}</b><span>${rows.length} ${rows.length===1?'cita':'citas'}</span></div><div class="v478-shift-list">${rows.length?rows.map(attentionWeekRow).join(''):'<div class="v478-shift-empty">Sin citas en esta jornada.</div>'}</div></section>`}
  window.renderAttentionWeek=function(d={}){
    const box=$('#attentionWeekCalendar');if(!box)return;const today=toISO(new Date()),days=d.days||[],day=days.find(x=>String(x?.date||'').slice(0,10)===today)||null;
    if(!day){box.innerHTML='<div class="attention-week-empty wide v477-no-clinic"><b>Hoy no hay consulta programada</b><span>Puedes buscar un paciente arriba para registrar una atención manualmente.</span></div>';return}
    const rows=day.appointments||[],morning=rows.filter(x=>apptMinutes(x)<14*60),afternoon=rows.filter(x=>apptMinutes(x)>=14*60),conflicts=rows.filter(x=>x?.conflict).length;
    box.innerHTML=`<div class="v478-agenda-shell"><div class="v478-agenda-brand"><div class="v478-agenda-title"><span>PACIENTES DE HOY</span><strong>AGENDA</strong></div><div class="v478-agenda-date"><b>${eh(day.label)} · ${fmtDate(day.date)}</b><span>${rows.length} ${rows.length===1?'cita':'citas'}</span>${conflicts?`<span class="v478-agenda-conflict">⚠ ${conflicts} duplicada${conflicts===1?'':'s'}</span>`:''}</div></div><div class="v478-shifts">${shiftBlock('MAÑANA',morning)}${shiftBlock('TARDE',afternoon)}</div></div>`;
  };

  window.newAttention=async function(){
    currentPatientSource='general';attentionSearchSeq++;attentionWeekAnchor=toISO(new Date());
    openModal(`<div class="new-attention-start-modal v477-attention-remaster v478-attention"><div class="v477-attention-top"><div class="modal-form-heading"><h2>Nueva atención</h2><p>Selecciona un paciente de la agenda de hoy o búscalo por sus datos.</p></div><button class="primary v477-new-patient-btn" onclick="newPatient(true)">＋ Paciente nuevo</button></div><div class="attention-start-search"><label for="aSearch">Buscar paciente</label><input id="aSearch" class="search uppercase-search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Cédula, apellidos y nombres, celular o correo" oninput="upperSearchInput(this);attentionSearch()"></div><div id="attentionWeekBlock" class="attention-week-block"><div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda de hoy…</div></div></div><div id="aResults" class="results attention-results hidden"></div></div>`);
    requestAnimationFrame(()=>document.querySelector('#modal .modalbox')?.classList.add('v477-attention-modalbox'));
    loadAttentionWeek(false,attentionWeekAnchor);setTimeout(()=>$('#aSearch')?.focus(),0);
  };
})();'''


def patch_app(s):
    base=s
    if s.count('APP_VERSION = "4.3.77"')!=1: raise SystemExit('APP_VERSION 4.3.77 no encontrado')
    s=s.replace('APP_VERSION = "4.3.77"','APP_VERSION = "4.3.78"',1)
    visual="const VERSION=\\'4.3.77\\';"
    if visual not in s: raise SystemExit('versión visual 4.3.77 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.78\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('punto overlay no encontrado')
    injected=('V478_REMIX_CSS = r"""'+REMIX_CSS+'"""\n'+'V478_REMIX_JS = r"""'+REMIX_JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V478_REMIX_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V478_REMIX_JS\n\n'+marker)
    s=s.replace(marker,injected,1)
    if s.count('@app.')!=base.count('@app.'): raise SystemExit('el remaster no debe cambiar rutas API')
    return s


def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V478_REMIX_JS' in names: js=ast.literal_eval(node.value)
            if 'V478_REMIX_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('remaster v478 no encontrado')
    for token in ['TOTAL SEMANA','remasterHomeTable','position:sticky','PACIENTES DE HOY','AGENDA','MAÑANA','TARDE','apptMinutes','Recibo','Imprimir','Borrar atención']:
        if token not in (js+css): raise SystemExit(f'falta {token}')
    if 'days.map(attentionWeekRow)' in js: raise SystemExit('Nueva atención no debe volver a tres días')
    for token in ['V476_JS','V477_ATTENTION_JS','b.estado = "EMITIDA"','doctor_isotype.png']:
        if token not in app+launcher: raise SystemExit(f'regresión detectada: {token}')
    if 'APP_VERSION = "4.3.78"' not in app or "const VERSION=\\'4.3.78\\';" not in app: raise SystemExit('versiones incorrectas')

    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4);ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    baseurl='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v478/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.78: remasteriza Inicio para mostrar más pacientes y divide la Agenda de Nueva atención en mañana y tarde.','files':[{'path':'ABRIR_RECEPCION.py','parts':[baseurl+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[baseurl+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':baseurl+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
