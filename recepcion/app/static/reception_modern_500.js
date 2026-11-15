/* Recepción 5.0: safe, additive layout adapter.
   Does not call any clinical, billing, scheduling, Neon or TV endpoints.
   Existing runtime remains the only authority for all actions and data. */
;(()=>{
  'use strict';
  if(window.__receptionModern500)return;
  window.__receptionModern500=true;
  const byId=id=>document.getElementById(id);
  const $=selector=>document.querySelector(selector);
  const make=(tag,cls,text)=>{
    const el=document.createElement(tag);
    if(cls)el.className=cls;
    if(text!==undefined)el.textContent=String(text);
    return el;
  };

  function installNavigation(){
    const brand=$('#app>aside .brand-copy b');
    if(brand)brand.textContent='Recepción 5.0';
    document.title='Recepción 5.0 · Dr. Armando Revelo';
    const nav=$('#app>aside .side-nav');
    // 5.0.5: the old Activity shortcut is redundant. Keep the audit screen
    // reachable under Configuración > Registro de actividad and leave
    // the "Actividad reciente" card in Inicio untouched.
    if(nav){
      const removeSidebarActivity=()=>{
        for(const button of [...nav.children]){
          if(!button.classList?.contains('nav-btn'))continue;
          const section=String(button.dataset.section||'').toLowerCase();
          const action=String(button.getAttribute('onclick')||'');
          const label=String(button.querySelector('span:last-child')?.textContent||'').trim().toLowerCase();
          if(section==='actividad'||/show\(['"]actividad['"]\)/.test(action)||label==='actividad'||label==='actividades'){
            button.remove();
          }
        }
      };
      removeSidebarActivity();
      if(!nav.dataset.v505ActivityGuard){
        nav.dataset.v505ActivityGuard='1';
        new MutationObserver(removeSidebarActivity).observe(nav,{childList:true});
      }
    }
    const home=nav?.querySelector('[data-section="inicio"]');
    if(nav&&home&&!nav.querySelector('.v50-nav-attention')){
      const btn=make('button','nav-btn v50-nav-attention');
      btn.type='button';
      btn.innerHTML='<span class="nav-icon" aria-hidden="true">⊕</span><span>Nueva atención</span>';
      btn.addEventListener('click',()=>{
        if(typeof newAttention==='function')newAttention();
      });
      home.insertAdjacentElement('afterend',btn);
    }
  }
  function installHomeActions(){
    if(byId('v504HomeDashboard'))return;
    const title=$('#inicio .page-heading h1');
    if(title)title.textContent='Bienvenido a Recepción 5.0';
    const subtitle=$('#inicio .page-heading p');
    if(subtitle)subtitle.textContent='Atenciones del día, citas y actividad del consultorio.';
    const actions=$('#inicio .home-actions');
    if(!actions||actions.querySelector('.v50-secondary-action'))return;
    const patient=make('button','v50-secondary-action','＋ Nuevo paciente');
    patient.type='button';
    patient.addEventListener('click',()=>{
      if(typeof newPatient==='function')newPatient();
    });
    const agenda=make('button','v50-secondary-action','▦ Agendar cita');
    agenda.type='button';
    agenda.addEventListener('click',()=>{
      if(typeof show==='function')show('agenda');
      // The real agenda offers valid opening times; never invent a slot.
    });
    actions.append(patient,agenda);
  }
  function installSearchShortcut(){
    if(byId('v50SearchHelp'))return;
    const search=byId('globalSearch');
    if(!search)return;
    const wrap=search.closest('.global-search-wrap');
    const hint=make('span','v50-search-help','Ctrl + K');
    hint.id='v50SearchHelp';
    hint.setAttribute('aria-hidden','true');
    if(wrap){wrap.appendChild(hint);}
    document.addEventListener('keydown',event=>{
      if((event.ctrlKey||event.metaKey)&&String(event.key).toLowerCase()==='k'){
        const modal=byId('modal');
        if(modal&&!modal.classList.contains('hidden'))return;
        event.preventDefault();
        search.focus();
        if(typeof globalSearchPatients==='function')globalSearchPatients(true);
      }
    });
  }

  function installTopStatus(){
    const toolbar=$('#app>main .global-toolbar');
    if(!toolbar||byId('v50TopStatus'))return;
    const status=make('div','v50-top-status');
    status.id='v50TopStatus';
    const records=[
      ['v50Online','◉','Sistema','r497SystemRow','r497SystemValue'],
      ['v50History','⌁','Historia LAN','r497HistoryRow','r497HistoryValue'],
      ['v50TV','▣','TV','r497TvRow','r497TvValue'],
      ['v50Version','ⓘ','Versión','r497VersionRow','r497VersionValue']
    ];
    for(const [id,symbol,label] of records){
      const chip=make('span','v50-status-chip'+(id==='v50Version'?' v50-version':''));
      chip.id=id;
      chip.textContent=symbol+' '+label;
      status.append(chip);
    }
    toolbar.append(status);
    const source=$('#app>aside .r497-status-hub');
    const sync=()=>{
      for(const [id,symbol,label,rowId,valueId] of records){
        const chip=byId(id),row=byId(rowId),value=byId(valueId);
        if(!chip)continue;
        const state=String(row?.dataset.state||'').toLowerCase();
        const msg=String(value?.textContent||'').trim();
        const isOk=/online|connected|ok|ready|active|success/.test(state)
          || /^(en línea|conectad[oa]|activo|lista|listo|operativo)$/i.test(msg);
        const isFail=/offline|failed|error|disconnected/.test(state)
          || /sin conexión|desconectado|error/i.test(msg);
        chip.dataset.state=isOk?'online':isFail?'offline':'unknown';
        chip.textContent=symbol+' '+(id==='v50Version'?(msg||label):label);
        chip.title=label+': '+(msg||'Comprobando…');
      }
    };
    sync();
    if(source)new MutationObserver(sync).observe(source,{
      subtree:true,attributes:true,attributeFilter:['data-state','class'],childList:true,characterData:true
    });
  }

  function installPatientGuide(){
    const page=byId('pacientes');
    if(!page||byId('v50PatientGuide'))return;
    const guide=make('div','v50-patient-guide');
    guide.id='v50PatientGuide';
    guide.append(
      make('i','','♧'),
      make('strong','','Expediente del paciente'),
      make('span','','Busca un paciente y selecciona su ficha para consultar datos personales, atenciones, citas, facturación y documentos.'),
      make('span','','Los documentos clínicos continúan bajo las mismas protecciones de Historia Clínica.')
    );
    page.append(guide);
  }

  function installHomeRail(){
    if(byId('v504HomeDashboard'))return;
    const focus=$('#inicio .r494-attentions-primary');
    if(!focus||byId('v50HomeRail'))return;
    const rail=make('div','v50-home-rail');
    rail.id='v50HomeRail';
    const agenda=make('div','v50-rail-card');
    const aHead=make('div','v50-rail-head');
    aHead.append(make('h3','','▦ Agenda de hoy'));
    const aButton=make('button','','Ver agenda');
    aButton.type='button';
    aButton.addEventListener('click',()=>{if(typeof show==='function')show('agenda');});
    aHead.append(aButton);
    agenda.append(aHead);
    const hint=make('div','v50-rail-caption','Las citas se gestionan en la agenda unificada, con los horarios y estados reales.');
    hint.id='v50AgendaHint';
    agenda.append(hint);
    const activity=make('div','v50-rail-card');
    activity.append(make('div','v50-rail-head'));
    activity.firstElementChild.append(make('h3','','◷ Atenciones registradas'));
    const history=make('div','v50-rail-history');
    history.id='v50RailHistory';
    activity.append(history);
    const extras=make('div','v50-rail-extras');
    extras.id='v50RailExtras';
    activity.append(extras);
    rail.append(agenda,activity);
    focus.insertAdjacentElement('afterend',rail);
  }
  function renderHomeRail(){
    const rail=byId('v50HomeRail');
    if(!rail)return;
    const history=byId('v50RailHistory'), extras=byId('v50RailExtras');
    if(!history||!extras)return;
    try{
      const date=typeof selectedHomeDate==='string'&&selectedHomeDate
        ?selectedHomeDate:(typeof toISO==='function'?toISO(new Date()):'');
      const day=(typeof weeklyData!=='undefined'&&weeklyData&&weeklyData[date])||null;
      const visits=Array.isArray(day?.visits)?day.visits:[];
      // A compact projection of already loaded local data. No new network calls.
      const seen=new Set();
      const recent=[];
      for(const v of visits.slice().reverse()){
        const pid=String(v.patient?.id||v.patient_id||v.id||'');
        if(seen.has(pid))continue;
        seen.add(pid);
        recent.push(v);
        if(recent.length>=4)break;
      }
      history.replaceChildren();
      if(!recent.length){
        history.append(make('p','v50-rail-caption','Todavía no hay atenciones registradas para el día seleccionado.'));
      }else{
        for(const v of recent){
          const item=make('div','v50-rail-item');
          const name=String(v.patient?.nombre||'Paciente registrado');
          const detail=String(v.procedimiento||'Consulta')+' · '+(v.tipo==='N'?'Nuevo':v.tipo==='S'?'Subsecuente':'Atención');
          item.append(make('b','',name),make('span','',detail));
          history.append(item);
        }
      }
      extras.replaceChildren();
      const values=byId('r486Metrics');
      if(values){
        for(const [index,label] of [[2,'Revisiones'],[5,'Total del día']]){
          const value=values.children[index]?.querySelector('strong')?.textContent?.trim();
          if(value)extras.append(make('span','v50-rail-extra',label+': '+value));
        }
      }
    }catch(error){console.warn('Recepción 5.0: panel de información no disponible',error);}
  }
  function observeHomeRail(){
    const table=byId('todayTable'),metrics=byId('r486Metrics');
    if(!table&&!metrics)return;
    let scheduled=false;
    const schedule=()=>{
      if(scheduled)return;
      scheduled=true;
      requestAnimationFrame(()=>{scheduled=false;renderHomeRail();});
    };
    for(const node of [table,metrics]){
      if(node)new MutationObserver(schedule).observe(node,{childList:true,subtree:true,characterData:true});
    }
    const week=byId('homeWeekNav');
    if(week)new MutationObserver(schedule).observe(week,{childList:true,subtree:true});
    schedule();
  }

  function installAgendaRail(){
    const page=byId('agenda');
    const grid=byId('agendaNativeGrid');
    if(!page||!grid||byId('v50AgendaRail'))return;
    const rail=make('aside','v50-agenda-rail');
    rail.id='v50AgendaRail';
    const summary=make('div','v50-rail-card');
    const head=make('div','v50-rail-head');
    head.append(make('h3','','▦ Resumen de agenda'));
    summary.append(head);
    const counts=make('div','v50-agenda-stat-list');
    counts.id='v50AgendaStats';
    summary.append(counts);
    const upcoming=make('div','v50-rail-card');
    const upHead=make('div','v50-rail-head');
    upHead.append(make('h3','','◷ Próximas citas'));
    upcoming.append(upHead);
    const listing=make('div','v50-agenda-upcoming');
    listing.id='v50AgendaUpcoming';
    upcoming.append(listing);
    const tools=make('div','v50-agenda-tools');
    const newBtn=make('button','','＋ Nueva cita');
    newBtn.type='button';
    newBtn.addEventListener('click',()=>{if(typeof openAgendaNewPicker==='function')openAgendaNewPicker();});
    const todayBtn=make('button','','Esta semana');
    todayBtn.type='button';
    todayBtn.addEventListener('click',()=>{if(typeof nativeAgendaToday==='function')nativeAgendaToday();});
    tools.append(newBtn,todayBtn);
    upcoming.append(tools);
    rail.append(summary,upcoming);
    grid.insertAdjacentElement('afterend',rail);
    let scheduled=false;
    new MutationObserver(()=>{
      if(scheduled)return;
      scheduled=true;
      requestAnimationFrame(()=>{scheduled=false;renderAgendaRail();});
    }).observe(grid,{childList:true,subtree:false});
    renderAgendaRail();
  }
  function renderAgendaRail(){
    const stats=byId('v50AgendaStats'),list=byId('v50AgendaUpcoming');
    if(!stats||!list)return;
    const week=typeof agendaNativeWeek!=='undefined'?agendaNativeWeek:null;
    const days=Array.isArray(week?.days)?week.days:[];
    const today=typeof toISO==='function'?toISO(new Date()):'';
    const day=days.find(x=>x.date===today)||days[0];
    stats.replaceChildren();
    list.replaceChildren();
    if(!day){
      stats.append(make('div','v50-rail-caption','Abre una semana para consultar sus citas.'));
      return;
    }
    const all=Array.isArray(day.appointments)?day.appointments:[];
    const counts={total:all.length,confirmed:0,pending:0,cancelled:0,rescheduled:0};
    for(const row of all){
      const state=String(row.appointment?.estado||row.staged?.estado||'PENDIENTE');
      const status=typeof agendaStatusInfo==='function'?agendaStatusInfo(state):{cls:'pending'};
      if(Object.hasOwn(counts,status.cls))counts[status.cls]+=1;
    }
    const rows=[
      ['Total de citas',counts.total,''],
      ['Confirmadas',counts.confirmed,'green'],
      ['Pendientes',counts.pending,'amber'],
      ['No asistirá',counts.cancelled,'red'],
      ['Reagendadas',counts.rescheduled,'']
    ];
    for(const [label,n,tone] of rows){
      const row=make('div','v50-agenda-stat-row');
      if(tone)row.dataset.tone=tone;
      row.append(make('span','',label),make('strong','',n));
      stats.append(row);
    }
    const selectedDate=make('p','v50-rail-caption','Día seleccionado: '+String(day.label||day.date||''));
    stats.prepend(selectedDate);
    const ordered=all.slice().sort((a,b)=>String(a.appointment?.hora||a.staged?.hora||'').localeCompare(String(b.appointment?.hora||b.staged?.hora||'')));
    for(const entry of ordered.slice(0,5)){
      const row=make('div','v50-rail-item');
      const name=String(entry.patient?.nombre||entry.staged?.nombre||'Paciente pendiente de vincular');
      const time=String(entry.appointment?.hora||entry.staged?.hora||'');
      const format=typeof agendaTime12==='function'?agendaTime12(time):time;
      const state=String(entry.appointment?.estado||entry.staged?.estado||'Pendiente');
      row.append(make('b','',name),make('span','',format+' · '+state));
      list.append(row);
    }
    if(!ordered.length)list.append(make('div','v50-rail-caption','No hay citas registradas en este día.'));
  }
  function watchModal(){
    const modal=byId('modal');
    if(!modal)return;
    const refresh=()=>{
      const visible=!modal.classList.contains('hidden');
      const newAttention=visible&&!!modal.querySelector('.new-attention-start-modal,.attention-form-modal');
      const dossier=visible&&!!modal.querySelector('.v4100-dossier');
      if(modal.classList.contains('v50-attention-open')!==newAttention)modal.classList.toggle('v50-attention-open',newAttention);
      if(modal.classList.contains('v50-dossier-open')!==dossier)modal.classList.toggle('v50-dossier-open',dossier);
      const nav=$('.v50-nav-attention');
      if(nav)nav.classList.toggle('active',newAttention);
    };
    new MutationObserver(refresh).observe(modal,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    refresh();
  }
  function boot(){
    document.body.classList.add('v50-ui');
    installNavigation();
    installHomeActions();
    installSearchShortcut();
    installTopStatus();
    installPatientGuide();
    installHomeRail();
    installAgendaRail();
    observeHomeRail();
    watchModal();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
