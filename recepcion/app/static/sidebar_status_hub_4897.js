/* Recepción 4.8.97 — panel lateral únicamente visual.
 * Sistema/Historia/versión provienen de sus monitores originales. TV consulta
 * exclusivamente el servicio local existente; jamás Neon ni la BD clínica. */
;(()=>{
  'use strict';
  if(window.__r497StatusHub)return;
  window.__r497StatusHub=true;
  const get=id=>document.getElementById(id);
  function paint(id,state,value,title){
    const row=get(id),out=row?.querySelector('.r497-status-value');
    if(!row||!out)return;
    const kind=state||'unknown',label=String(value||'Comprobando…');
    if(row.dataset.state!==kind)row.dataset.state=kind;
    if(out.textContent!==label)out.textContent=label;
    if(title&&row.title!==title)row.title=title;
  }
  function renderOriginals(){
    const source=get('connectionBadge');
    if(source){
      const label=source.querySelector('.connection-label')?.textContent?.trim()||'Comprobando…';
      const kind=['online','offline','warning','idle','syncing','local']
        .find(x=>source.classList.contains(x))||'unknown';
      const state=kind==='online'?'online':kind==='offline'?'offline':
        kind==='warning'?'warning':'unknown';
      paint('r497SystemRow',state,label,source.title||'Estado de conexión y protección');
    }
    const lan=get('historiaDoctorBadge');
    if(lan){
      const sourceLabel=lan.textContent||'';
      const connected=lan.classList.contains('lan');
      const pending=sourceLabel.match(/(\d+)\s+pendientes?/i);
      const count=pending?Number(pending[1]):0;
      const onlineLabel='Conectada'+(count>0?' · '+count+' pend.':'');
      const offlineLabel='Sin conexión'+(count>0?' · '+count+' pend.':'');
      const waiting=sourceLabel.includes('sin comprobar')?'Sin comprobar':'Comprobando…';
      const kind=connected?'online':lan.classList.contains('error')?'offline':'unknown';
      paint('r497HistoryRow',kind,connected?onlineLabel:kind==='offline'?offlineLabel:waiting,
        lan.title||'Estado de comunicación con Historia Clínica por LAN');
    }
    const version=get('sidebarRealVersion');
    if(version){
      const raw=(version.textContent||'').trim().replace(/^Recepci[oó]n\s*v/i,'');
      const valid=/^\d+\.\d+\.\d+$/.test(raw);
      const text=valid?'v'+raw:'Comprobando…';
      const row=get('r497VersionRow'),el=get('r497VersionValue');
      if(el&&el.textContent!==text)el.textContent=text;
      if(row&&version.title&&row.title!==version.title)row.title=version.title;
    }
  }
  let reading=false,lastReading=0,lastControlSignalAt=0;
  function freshControlSignal(){
    return lastControlSignalAt>0&&Date.now()-lastControlSignalAt<10000;
  }
  function paintTv(data,origin){
    const reachable=data?.ok===true;
    const online=reachable&&data?.tv_online===true;
    const title=online?'Pantalla TV confirmada por '+origin:
      reachable?'Servicio TV activo, pero el televisor no envía señal reciente':
      'No se pudo comprobar el estado TV local';
    paint('r497TvRow',online?'online':reachable?'offline':'unknown',
      online?'Conectada':reachable?'Sin conexión':'Sin comprobar',title);
  }
  function onTvMessage(event){
    const frame=get('r486TvFrame');
    if(!frame||event.source!==frame.contentWindow)return;
    const src=frame.getAttribute('src');
    if(!src)return;
    let allowedOrigin='';
    try{allowedOrigin=new URL(src,document.baseURI).origin}catch(_e){return}
    if(event.origin!==allowedOrigin)return;
    const data=event.data;
    if(!data||data.type!=='reception-tv-heartbeat-v1'
      ||data.ok!==true||typeof data.tv_online!=='boolean')return;
    lastControlSignalAt=Date.now();
    paintTv({ok:true,tv_online:data.tv_online},'el panel TV');
  }
  async function getTvStatus(url){
    const response=await fetch(url,{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)throw Error('HTTP '+response.status+' al consultar TV');
    const data=await response.json();
    if(!data||typeof data!=='object'||typeof data.tv_online!=='boolean')
      throw Error('Estado TV inválido');
    return data;
  }
  async function refreshTv(force=false){
    const app=get('app');
    if(!app||app.classList.contains('hidden')||document.hidden||reading)return;
    const now=Date.now();
    if(!force&&now-lastReading<30000)return;
    lastReading=now;reading=true;
    try{
      let data;
      try{
        data=await getTvStatus('/api/reception/tv/status');
        if(data.ok!==true)throw Error('Servicio TV sin respuesta');
      }catch(firstError){
        // Misma instancia TV, segunda ruta autenticada; nunca consulta Neon.
        try{data=await getTvStatus('/api/tv-turnos/health')}
        catch(secondError){
          if(!freshControlSignal()){
            paint('r497TvRow','unknown','Sin comprobar',
              'Estado TV no disponible: '+String(secondError?.message||firstError?.message||'error'));
          }
          return;
        }
      }
      if(data.ok!==true&&freshControlSignal())return;
      paintTv(data,'el servicio local');
    }catch(error){
      if(!freshControlSignal())
        paint('r497TvRow','unknown','Sin comprobar',
          'Error al consultar TV: '+String(error?.message||'desconocido'));
    }finally{reading=false;}
  }
  function boot(){
    const sources=document.querySelector('.r497-status-sources');
    if(!sources)return;
    const observer=new MutationObserver(renderOriginals);
    observer.observe(sources,{subtree:true,attributes:true,childList:true,characterData:true});
    renderOriginals();
    window.addEventListener('message',onTvMessage);
    refreshTv(true);
    const app=get('app');
    if(app){
      const authState=new MutationObserver(()=>{
        if(!app.classList.contains('hidden'))refreshTv(true);
      });
      authState.observe(app,{attributes:true,attributeFilter:['class']});
    }
    setInterval(()=>refreshTv(false),30000);
    document.addEventListener('visibilitychange',()=>{
      if(!document.hidden){renderOriginals();refreshTv(true);}
    });
    window.addEventListener('focus',()=>{renderOriginals();refreshTv(true);});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
