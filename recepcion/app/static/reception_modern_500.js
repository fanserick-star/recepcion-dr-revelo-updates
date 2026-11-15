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
    observeHomeRail();
    watchModal();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
