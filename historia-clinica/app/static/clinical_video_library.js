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
        player.addEventListener('error',()=>{meta.textContent='No se pudo reproducir el original. Comprueba que Recepción siga encendida y conectada a la LAN.'});
        row.append(title,meta,player);list.append(row);
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
