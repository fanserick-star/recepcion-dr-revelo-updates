/* Historia clinical videocystoscopy browser, served only on the doctor's localhost.
   Videos stay on Reception; this page never sends video to Neon or R2. */
(()=>{
  'use strict';
  if(window.__reveloVideoLibraryInstalled)return;
  window.__reveloVideoLibraryInstalled=true;
  const host=document.querySelector('[data-clinical-video-patient]');
  const open=document.getElementById('patient-docs-open');
  if(!host||!open)return;
  const id=host.getAttribute('data-clinical-video-patient');
  const status=host.querySelector('.cp-video-status');
  const list=host.querySelector('.cp-video-list');
  const refresh=host.querySelector('.cp-video-refresh');
  const url='/api/clinical-videos/patient/'+encodeURIComponent(id);
  let busy=false, loaded=false;
  // This tests synthetic traffic only; never downloads patient data.
  const diag=document.createElement('button');
  diag.type='button';
  diag.className='cp-video-diagnostic';
  diag.textContent='Medir velocidad Wi-Fi';
  diag.style.cssText='margin:8px 0 10px;padding:8px 13px;border:1px solid #bad1e8;border-radius:8px;background:#f6fbff;color:#1e537d;font-weight:bold;cursor:pointer';
  host.querySelector('.cp-video-status')?.before(diag);
  diag.addEventListener('click',async()=>{
    diag.disabled=true;
    const original=diag.textContent;
    diag.textContent='Midiendo LAN sin usar videos clínicos…';
    try{
      const r=await fetch('/api/clinical-videos/diagnostic',{cache:'no-store'});
      const d=await r.json();
      if(!r.ok||!d.ok)throw new Error(d.error||'Medición incompleta');
      diag.textContent='Velocidad LAN: '+d.megabits_per_second+' Mbps ('+d.megabytes_per_second+' MB/s)';
      diag.title='Transferencia de 8 MB ficticios en '+d.seconds+' segundos';
    }catch(e){
      diag.textContent='No se pudo medir la LAN';
      diag.title=String(e.message||'Error de red');
    }finally{diag.disabled=false;}
  });
  async function load(force=false){
    if(busy||(loaded&&!force))return;
    busy=true;
    status.textContent='Consultando archivos de Recepción…';
    try{
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'application/json'}});
      const media=(response.headers.get('Content-Type')||'').toLowerCase();
      // An older installation may send a plain-text 500 instead of JSON.
      // Never display a raw parser error or the server's internal contents.
      let data=null;
      if(media.includes('application/json')){
        try{data=await response.json();}catch(_ignored){}
      }
      if(!data||typeof data!=='object'){
        throw new Error(response.ok?
          'Historia devolvió una respuesta inesperada. Actualiza Historia y vuelve a intentarlo.':
          'Historia no pudo consultar las videocistoscopías (HTTP '+response.status+'). Actualiza Historia y pulsa Actualizar.');
      }
      if(!response.ok||!data.ok)throw new Error(data.error||data.detail||'No se pudo consultar Recepción.');
      list.replaceChildren();
      const videos=Array.isArray(data.videos)?data.videos:[];
      status.textContent=videos.length?videos.length+' videocistoscopía(s) archivadas en Recepción':
        'Este paciente aún no tiene videocistoscopías guardadas en Recepción.';
      videos.forEach((item,index)=>{
        if(!/^[A-Za-z0-9_-]{1,100}$/.test(item.id))return;
        const row=document.createElement('section');row.className='cp-video-item';
        row.style.cssText='padding:12px 0;border-bottom:1px solid #e5ebf0';
        const title=document.createElement('strong');
        const when=String(item.recorded_at||'').slice(0,16).replace('T',' ');
        title.textContent='Videocistoscopía '+(when||('#'+(index+1)));
        const meta=document.createElement('div');
        const megabytes=(Number(item.size_bytes||0)/1048576).toFixed(1);
        meta.style.cssText='font-size:12px;color:#657080;margin:5px 0';
        meta.textContent=megabytes+' MB · Guardada en Recepción · '+(item.backup?'Respaldo disponible':'Respaldo externo pendiente');
        const player=document.createElement('video');
        player.controls=true;
        player.preload='none';
        player.playsInline=true;
        player.style.cssText='display:block;width:100%;max-width:820px;max-height:420px;background:#121923;border-radius:8px';
        player.setAttribute('aria-label','Reproducir '+title.textContent);
        const source=document.createElement('source');
        source.src=url+'/play/'+encodeURIComponent(item.id);
        source.type='video/mp4';
        player.append(source,document.createTextNode('Esta PC no permite reproducir el formato de video.'));
        player.addEventListener('error',()=>{meta.textContent='No se pudo reproducir el video. Comprueba la conexión y el códec compatible con esta PC.'});
        const buttons=document.createElement('div');
        buttons.style.cssText='display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:10px 0';
        const prepare=document.createElement('button');
        prepare.type='button';
        prepare.textContent='Preparar video para reproducir sin cortes';
        prepare.style.cssText='padding:10px 13px;border:1px solid #1a6a9d;border-radius:9px;background:#1c6ea4;color:white;font-weight:bold;cursor:pointer';
        const progress=document.createElement('span');
        progress.style.cssText='font-size:12px;line-height:1.5;color:#58748c';
        progress.textContent='Reproducción por LAN disponible, o descarga una copia temporal para verla sin depender del Wi-Fi.';
        const itemUrl=url+'/prepare/'+encodeURIComponent(item.id);
        const statusUrl=url+'/cache-status/'+encodeURIComponent(item.id);
        const localUrl=url+'/cached-play/'+encodeURIComponent(item.id);
        let requestInProgress=false;
        let lastTimer=null;
        const mb=(n)=>Math.max(0,Number(n)||0)/1048576;
        async function checkCached(){
          const r=await fetch(statusUrl,{cache:'no-store'});
          const d=await r.json();
          if(!r.ok)throw new Error(d.detail||'No se pudo consultar la descarga');
          if(d.state==='ready'){
            if(lastTimer){clearTimeout(lastTimer);lastTimer=null;}
            prepare.disabled=false;
            prepare.textContent='Video preparado localmente';
            progress.textContent='Listo: '+mb(d.total_bytes).toFixed(1)+' MB verificados. Reproduce sin depender del Wi-Fi.';
            if(source.src!==new URL(localUrl,location.href).href){
              source.src=localUrl;
              player.load();
            }
            return;
          }
          if(d.state==='error'){
            if(lastTimer){clearTimeout(lastTimer);lastTimer=null;}
            prepare.disabled=false;
            prepare.textContent='Reintentar descarga temporal';
            progress.textContent=d.error||'Error de Wi-Fi. Puedes reintentar.';
            return;
          }
          if(d.state==='downloading'){
            prepare.disabled=true;
            const total=Math.max(1,Number(d.total_bytes)||1);
            const percent=Math.min(100,Math.round(100*(Number(d.downloaded_bytes)||0)/total));
            progress.textContent='Descargando '+percent+' % · '+mb(d.downloaded_bytes).toFixed(1)+' / '+mb(d.total_bytes).toFixed(1)+' MB · '+(Number(d.speed_mbps)||0).toFixed(1)+' Mbps';
            lastTimer=setTimeout(()=>checkCached().catch(showError),900);
            return;
          }
          prepare.disabled=false;
        }
        function showError(e){
          prepare.disabled=false;
          progress.textContent=String(e.message||'No fue posible descargar el video temporalmente.');
        }
        prepare.addEventListener('click',async()=>{
          if(requestInProgress)return;
          requestInProgress=true;
          prepare.disabled=true;
          progress.textContent='Verificando que la grabación pertenezca a esta ficha…';
          player.pause();
          try{
            const r=await fetch(itemUrl,{method:'POST',cache:'no-store',headers:{Accept:'application/json'}});
            const d=await r.json();
            if(!r.ok)throw new Error(d.detail||'Recepción no autorizó la descarga');
            await checkCached();
          }catch(e){showError(e);}
          finally{requestInProgress=false;}
        });
        buttons.append(prepare,progress);
        row.append(title,meta,player,buttons);list.append(row);
        // If already cached in the current consultation, restore local play.
        checkCached().catch(()=>{});
      });
      loaded=true;
    }catch(error){
      status.textContent=(error&&error.message)||'No se pudo conectar con Recepción. Pulsa Actualizar para reintentar.';
      list.replaceChildren();
      loaded=false;
    }finally{busy=false}
  }
  open.addEventListener('click',()=>load());
  refresh?.addEventListener('click',()=>load(true));
})();
