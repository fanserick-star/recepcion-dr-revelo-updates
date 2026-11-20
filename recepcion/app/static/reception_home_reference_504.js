/* Recepción 5.0.4 — Inicio-only Moderno Profesional reconstruction.
 * Keeps all registration, receipt, visit deletion and patient navigation functions
 * in the existing app.js controller. No mutations or timers are added.
 *
 * Important honesty: /api/home/week contains no per-patient clinical progress
 * or exact registration time. We never invent "en consulta"/"finalizado"
 * or a visit clock; appointment times appear only on an ID-matched booking.
 */
;(()=>{
  'use strict';
  if(window.__receptionHomeReference504)return;
  window.__receptionHomeReference504=true;
  const $=s=>document.querySelector(s);
  const by=id=>document.getElementById(id);
  const home=by('inicio');
  if(!home)return;
  home.classList.add('v504-home');
  const escapeText=value=>String(value??'').replace(/[&<>"']/g,ch=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const node=(tag,cls,text)=>{
    const el=document.createElement(tag);
    if(cls)el.className=cls;
    if(text!==undefined)el.textContent=String(text);
    return el;
  };
  const localDate=()=>typeof toISO==='function'?toISO(new Date()):'';
  const label12=value=>{
    const t=String(value||'').trim().slice(0,5);
    if(!/^\d{1,2}:[0-5]\d$/.test(t))return '—';
    if(typeof agendaTime12==='function')return agendaTime12(t);
    const [h,m]=t.split(':').map(Number);
    if(h>23)return '—';
    return (h%12||12)+':'+String(m).padStart(2,'0')+' '+(h<12?'a. m.':'p. m.');
  };
  let lastDay=null;
  let agendaCache=null;
  let agendaRequest=null;
  let agendaRequestKey='';
  let agendaCacheAt=0;
  const CACHE_MS=120000;

  function setMetricsText(){
    const cards=by('r486Metrics');
    if(!cards)return;
    const labels={
      0:['En espera','Consultas en Historia','♧'],
      1:['Atenciones de hoy','Pacientes registrados hoy','♧'],
      3:['Agendados','Citas programadas hoy','▦'],
      4:['Facturas pendientes','Por revisar o emitir','▤']
    };
    for(const [index,values] of Object.entries(labels)){
      const card=cards.children[Number(index)];
      if(!card)continue;
      card.dataset.v504Kpi='1';
      const head=card.querySelector('.r486-metric-head');
      if(head){
        const icon=head.querySelector('.r486-metric-icon');
        if(icon&&icon.textContent!==values[2])icon.textContent=values[2];
        const label=head.querySelector('span:not(.r486-metric-icon)');
        if(label&&label.textContent!==values[0])label.textContent=values[0];
      }
      const caption=card.querySelector('small');
      if(caption&&caption.textContent!==values[1])caption.textContent=values[1];
    }
    // "En espera" remains unavailable when Historia is not verified:
    // the original metric already shows a dash in that case.
  }

  function selectedAgendaEntries(date){
    const week=agendaCache?.week;
    const day=(Array.isArray(week?.days)?week.days:[]).find(row=>row.date===date);
    if(!day)return null;
    return (day.appointments||[]).slice().sort((a,b)=>{
      const t=x=>String(x?.appointment?.hora||x?.staged?.hora||'');
      return t(a).localeCompare(t(b));
    });
  }
  function appointmentForPatient(date,patientId){
    const rows=selectedAgendaEntries(date);
    if(!rows||!patientId)return null;
    return rows.find(row=>String(row.appointment?.patient_id||'')===String(patientId))||null;
  }

  // Reference of the SECOND screenshot: retain the real reception day table
  // (N.º, Paciente, Atención, Valor, Acciones), not the alternate 5.0 preview.
  // homeTable groups all visits by patient and never slices to four rows.
  function renderModernTable(date,payload){
    const target=by('todayTable'),footer=by('v504DayFooter');
    if(!target||!payload||typeof homeTable!=='function')return false;
    const all=Array.isArray(payload.visits)?payload.visits:[];
    const groups=typeof groupHomeVisits==='function'?groupHomeVisits(all):[];
    const shown=groups.length;
    const declared=Number(payload.count);
    const expected=Number.isFinite(declared)&&declared>=0?Math.max(shown,declared):shown;
    try{
      target.innerHTML=homeTable(all);
    }catch(error){
      console.error('Inicio: no se pudo dibujar la tabla completa',error);
      return false; // original controller's safe table fallback
    }
    if(footer){
      footer.replaceChildren();
      footer.append(node('span','', 'Mostrando '+shown+' de '+expected+' pacientes registrados.'));
      if(expected>shown){
        const warning=node('span','v504-day-count-warning',
          ' ⚠ El resumen indica '+expected+' pacientes, pero llegaron '+shown+' a esta vista.');
        const reload=node('button','v504-day-reload','Recargar atenciones');
        reload.type='button';
        reload.addEventListener('click',()=>{
          if(typeof loadWeek==='function')
            void loadWeek(typeof currentHomeAnchor==='string'&&currentHomeAnchor?currentHomeAnchor:date,date);
        });
        footer.append(warning,reload);
      }
    }
    renderActivity(date,payload);
    return true;
  }
  function renderActivity(date,payload){
    const host=by('v504ActivityList');
    if(!host)return;
    const visits=Array.isArray(payload?.visits)?payload.visits.slice():[];
    visits.sort((a,b)=>Number(b.id||0)-Number(a.id||0));
    const latest=[];
    const seen=new Set();
    for(const v of visits){
      const id=String(v.patient?.id||v.patient_id||v.id||'');
      if(seen.has(id))continue;
      seen.add(id);latest.push(v);
      if(latest.length===4)break;
    }
    host.replaceChildren();
    if(!latest.length){
      host.append(node('div','v504-empty-state','Sin movimientos registrados en el día seleccionado.'));
      return;
    }
    for(const v of latest){
      const item=node('div','v504-activity-entry');
      const symbol=node('span','v504-activity-symbol','✓');
      const info=node('div','');
      const isProc=!!String(v.procedimiento||'').trim();
      const name=String(v.patient?.nombre||'Paciente registrado');
      const action=isProc?'Procedimiento registrado':'Atención registrada';
      info.append(node('b','v504-entry-name',action),
                  node('span','v504-entry-detail',name));
      item.append(symbol,info);host.append(item);
    }
  }
  function renderAgenda(date){
    const host=by('v504AgendaList');
    if(!host)return;
    host.replaceChildren();
    const rows=selectedAgendaEntries(date);
    if(rows===null){
      host.append(node('div','v504-empty-state','Consultando citas de la agenda…'));return;
    }
    if(!rows.length){
      host.append(node('div','v504-empty-state','No hay citas registradas para este día.'));return;
    }
    for(const item of rows.slice(0,5)){
      const ap=item.appointment||item.staged||{};
      const time=label12(ap.hora);
      const patient=String(item.patient?.nombre||item.staged?.nombre||'Paciente sin vincular');
      const state=String(ap.estado||'PENDIENTE');
      const itemRow=node('div','v504-agenda-entry');
      const pill=node('span','v504-time-pill',time);
      const details=node('div','');
      const name=node('b','v504-entry-name',patient);
      const info=typeof agendaStatusInfo==='function'?agendaStatusInfo(state):{label:'Pendiente'};
      details.append(name,node('span','v504-entry-detail',info.label));
      itemRow.append(pill,details);
      host.append(itemRow);
    }
    if(rows.length>5){
      host.append(node('div','v504-empty-state','Y '+(rows.length-5)+' cita(s) más. Abre Agenda para verlas todas.'));
    }
  }
  async function ensureAgenda(date){
    if(!date||typeof api!=='function')return;
    const today=Date.now();
    const anchor=date;
    if(agendaCache?.anchor===anchor&&today-agendaCacheAt<CACHE_MS){
      renderAgenda(date);
      if(lastDay?.date===date)renderModernTable(date,lastDay.payload);
      return;
    }
    if(agendaRequest&&agendaRequestKey===anchor)return;
    if(agendaRequest)return; // no competing requests for different weeks
    agendaRequestKey=anchor;
    const request=api('/api/agenda/week?anchor='+encodeURIComponent(anchor));
    agendaRequest=request;
    try{
      const week=await request;
      agendaCache={anchor,week};
      agendaCacheAt=Date.now();
      const selected=lastDay?.date||date;
      renderAgenda(selected);
      if(lastDay)renderModernTable(lastDay.date,lastDay.payload);
    }catch(error){
      const host=by('v504AgendaList');
      if(host)host.replaceChildren(node('div','v504-empty-state','Agenda temporalmente no disponible. Puedes abrir la agenda completa.'));
      console.warn('Recepción Inicio: la agenda local no está disponible',error);
    }finally{agendaRequest=null;agendaRequestKey='';}
  }
  // El indicador superior cuenta siempre HOY. La tabla puede mostrar otro
  // día elegido en el calendario semanal: nunca ocultar esa diferencia.
  function clarifySelectedDate(date){
    const caption=by('selectedDayTitle');
    if(!caption)return;
    const row=caption.querySelector('div');
    const title=caption.querySelector('h2');
    if(!row||!title)return;
    const selected=String(date||'').slice(0,10);
    const today=localDate();
    // Returning from the sidebar can repaint without replacing the title.
    // Keep the prefix and the "Ver hoy" control idempotent.
    const baseTitle=title.textContent.replace(/^(?:HOY|FECHA SELECCIONADA)\s*·\s*/i,'');
    title.textContent=(selected===today?'HOY · ':'FECHA SELECCIONADA · ')+baseTitle;
    row.querySelector('.v504-back-today')?.remove();
    if(selected!==today){
      const button=node('button','v504-back-today','Ver hoy');
      button.type='button';
      button.addEventListener('click',()=>{
        if(typeof homeThisWeek==='function')void homeThisWeek();
      });
      row.append(button);
    }
  }
  function paint(date,payload){
    lastDay={date,payload};
    setMetricsText();
    clarifySelectedDate(date);
    const painted=renderModernTable(date,payload);
    renderAgenda(date);
    if(!home.classList.contains('hidden')&&!by('app')?.classList.contains('hidden')){
      void ensureAgenda(date);
    }
    return painted;
  }
  // 5.0.6: the ORIGINAL app.js calls this bridge after every real weekly/day
  // render. No shadowing or monkey-patching of the original page function.
  window.__r504PaintHome=(date,payload)=>{
    try{return paint(date,payload)===true}catch(error){
      console.error('Inicio: se conserva la tabla de respaldo al fallar el diseño moderno',error);
      return false;
    }
  };
  window.__r504HomeEnter=()=>{
    const chosen=(typeof selectedHomeDate==='string'&&selectedHomeDate)||lastDay?.date||localDate();
    if(!chosen)return;
    // Returning through the left menu must restore the same reference table
    // as selecting a day from "Ver resumen de los cuatro días de consulta".
    // Reuse weeklyData: never trigger a Neon fetch just to restore the view.
    if(typeof weeklyData!=='undefined'&&weeklyData[chosen]){
      if(typeof renderHomeDayFromCache==='function')renderHomeDayFromCache(chosen);
      else paint(chosen,weeklyData[chosen]);
      return;
    }
    if(lastDay?.date===chosen){paint(chosen,lastDay.payload);return;}
    renderAgenda(chosen);
    void ensureAgenda(chosen);
  };
  const metrics=by('r486Metrics');
  if(metrics){
    let queued=false;
    new MutationObserver(()=>{
      if(queued)return;
      queued=true;
      queueMicrotask(()=>{queued=false;setMetricsText();});
    }).observe(metrics,{childList:true});
  }
  const dayTable=by('todayTable');
  if(dayTable){
    dayTable.addEventListener('toggle',event=>{
      const details=event.target.closest?.('.v504-actions');
      if(details?.open){
        dayTable.querySelectorAll('.v504-actions[open]').forEach(el=>{if(el!==details)el.open=false;});
      }
    },true);
    document.addEventListener('click',event=>{
      if(!event.target.closest?.('.v504-actions'))dayTable.querySelectorAll('.v504-actions[open]').forEach(el=>{el.open=false;});
    });
  }
  if(!home.classList.contains('hidden')&&typeof selectedHomeDate==='string'&&typeof weeklyData!=='undefined'&&weeklyData[selectedHomeDate]){
    window.__r504PaintHome(selectedHomeDate,weeklyData[selectedHomeDate]);
  }else setMetricsText();
  // 1600x900 operational viewport: disable accidental Ctrl+wheel/keyboard
  // zoom in Edge fallback. The native WebView2 launcher separately locks
  // its effective zoom to 100%; Windows DPI scaling remains untouched.
  const preventZoom=event=>{
    if(event.ctrlKey){
      event.preventDefault();
    }
  };
  document.addEventListener('wheel',preventZoom,{capture:true,passive:false});
  document.addEventListener('keydown',event=>{
    if(!event.ctrlKey||event.altKey||event.metaKey)return;
    if(['+','=','-','Add','Subtract','NumpadAdd','NumpadSubtract'].includes(event.key)){
      event.preventDefault();
      event.stopPropagation();
    }
  },true);
})();
