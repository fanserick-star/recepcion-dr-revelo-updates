/* Recepción 4.8.94 · Inicio limpio; TV solo en su módulo.
   Métricas siguen leyendo estados locales. Sin cambios de negocio o clínica. */
;(()=>{
  'use strict';
  if(window.__r486HomeMounted)return;
  window.__r486HomeMounted=true;
  const get=id=>document.getElementById(id);
  let todaySummary=null,tvState=null,lastTvRead=0,tvReading=false;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function getLocalDay(){
    try{
      const key=typeof toISO==='function'?toISO(new Date()):'';
      return typeof weeklyData!=='undefined'&&weeklyData&&weeklyData[key]?weeklyData[key]:null;
    }catch(_){return null;}
  }
  function countOrDash(value){return value===null||value===undefined?'—':String(Math.max(0,Number(value)||0));}
  function safeMoney(value){
    if(value===null||value===undefined)return '—';
    return typeof money==='function'?money(value):'$ '+Number(value||0).toFixed(2);
  }
  function metric(icon,label,value,description,variant){
    return '<article class="r486-metric '+esc(variant||'')+'"><div class="r486-metric-head"><span class="r486-metric-icon" aria-hidden="true">'+icon+'</span><span>'+esc(label)+'</span></div><strong>'+esc(value)+'</strong><small>'+esc(description)+'</small></article>';
  }
  function renderMetrics(){
    const root=get('r486Metrics');if(!root)return;
    const local=getLocalDay();
    const summary=todaySummary||(typeof homeDaySummaryCache!=='undefined'?homeDaySummaryCache:null)||{};
    let bills=null;
    try{
      if(typeof billingPendingApprovalValue!=='undefined'&&typeof billingApprovedValue!=='undefined')bills=Number(billingPendingApprovalValue||0)+Number(billingApprovedValue||0);
    }catch(_){}
    const linked=!!(tvState&&tvState.ok&&tvState.history_online);
    const waiting=linked?Number(tvState.waiting_count||0):null;
    const hasSummary=!!(summary&&summary.ok);
    root.innerHTML=[
      metric('♙','En espera',countOrDash(waiting),linked?'Consultas en Historia':'Sin conexión verificada','r486-waiting'),
      metric('✓','Atenciones hoy',countOrDash(local?.count),local?'Pacientes registrados':'Sin resumen del día','r486-attended'),
      metric('▣','Revisiones',countOrDash(hasSummary?summary.exam_reviews:null),'Sin cobro','r486-reviews'),
      metric('▦','Citas de hoy',countOrDash(hasSummary?summary.scheduled_today:null),'Agenda del consultorio','r486-appointments'),
      metric('$','Facturación',countOrDash(bills),'Pendientes por atender','r486-billing'),
      metric('▥','Total del día',safeMoney(local?.total),local?'Valor registrado':'Sin datos del día','r486-money')
    ].join('');
  }
  async function refreshTv(force=false){
    const now=Date.now();
    if(tvReading||(!force&&now-lastTvRead<45000))return;
    lastTvRead=now;tvReading=true;
    try{
      const r=await fetch('/api/reception/tv/status',{cache:'no-store',credentials:'same-origin'});
      if(!r.ok)throw new Error('Sin acceso al servicio TV');
      const value=await r.json();
      tvState=value&&typeof value==='object'?value:{ok:false};
    }catch(_){tvState={ok:false};}
    finally{tvReading=false;renderMetrics();}
  }
  function activateTv(){
    const frame=get('r486TvFrame');
    if(frame&&!frame.getAttribute('src'))frame.setAttribute('src','http://127.0.0.1:8899/control');
    refreshTv(true);
  }
  window.r486ReloadTv=function(){
    const frame=get('r486TvFrame');
    if(frame)frame.setAttribute('src','http://127.0.0.1:8899/control?r486='+Date.now());
    refreshTv(true);
  };
  function boot(){
    document.body.classList.add('r486-ui');
    // Las tarjetas semanales se ubican debajo de las atenciones. Al elegir
    // otro día, acercar la nueva lista, sin alterar el selector ni su API.
    document.addEventListener('click',event=>{
      const card=event.target?.closest?.('#weekCards .week-card[data-date]');
      if(!card)return;
      setTimeout(()=>{
        const block=get('selectedDayTitle');
        if(block && !get('inicio')?.classList.contains('hidden')){
          block.scrollIntoView({behavior:'smooth',block:'start'});
        }
      },120);
    });
    renderMetrics();
    if(!get('inicio')?.classList.contains('hidden'))refreshTv();
  }
  const originalLoad=window.loadDashboard;
  if(typeof originalLoad==='function')window.loadDashboard=function(){
    const result=originalLoad.apply(this,arguments);renderMetrics();refreshTv();return result;
  };
  const originalSummary=window.renderHomeDaySummary;
  if(typeof originalSummary==='function')window.renderHomeDaySummary=function(data){
    const result=originalSummary.apply(this,arguments);todaySummary=data;renderMetrics();return result;
  };
  const originalWeek=window.applyWeekPayload;
  if(typeof originalWeek==='function')window.applyWeekPayload=function(){
    const result=originalWeek.apply(this,arguments);renderMetrics();return result;
  };
  const originalPending=window.renderHomePendingStrip;
  if(typeof originalPending==='function')window.renderHomePendingStrip=function(){
    const result=originalPending.apply(this,arguments);renderMetrics();return result;
  };
  const originalShow=window.show;
  if(typeof originalShow==='function')window.show=function(id){
    const result=originalShow.apply(this,arguments);
    if(id==='tv')activateTv();
    else if(id==='inicio'){renderMetrics();refreshTv();}
    return result;
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();