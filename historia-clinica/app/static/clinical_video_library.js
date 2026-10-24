/* Historia Clínica 1.4.42: safe, on-demand videocystoscopy gallery.
   Only the verified patient's localhost catalogue and existing LAN video stream.
   No image scraping or download of other MP4s just to render gallery cards. */
(()=>{
  'use strict';
  if(window.__reveloVideoLibraryInstalled)return;
  const host=document.querySelector('[data-clinical-video-patient]');
  const open=document.getElementById('patient-videos-open');
  const dialog=document.getElementById('patient-videos-dialog');
  if(!host||!open||!dialog)return;
  window.__reveloVideoLibraryInstalled=true;

  const id=host.getAttribute('data-clinical-video-patient');
  const status=host.querySelector('.cp-video-status');
  const list=host.querySelector('.cp-video-list');
  const refresh=host.querySelector('.cp-video-refresh');
  const label=host.querySelector('.cp-video-section-head strong');
  const url='/api/clinical-videos/patient/'+encodeURIComponent(id);
  const previewById=new Map(); // Session-only screenshots of a video *after* the doctor plays it.
  const durationById=new Map();
  let busy=false,loaded=false,activeVideo=null,activeId=null,activeCard=null;
  let activeCanvasCapture=false;

  const counter=document.createElement('strong');
  counter.className='cp-video-trigger-count';
  counter.setAttribute('aria-live','polite');
  open.append(counter);
  function setCount(count,unavailable=false){
    const available=!unavailable&&Number.isInteger(count)&&count>=0;
    const state=!available?'unavailable':count>0?'ready':'empty';
    open.dataset.videoState=state;
    counter.textContent=available?String(count):'—';
    open.setAttribute('aria-label',available?
      'Abrir videocistoscopías del paciente: '+count+' video'+(count===1?'':'s'):
      'Abrir videocistoscopías: recuento no disponible. Consultar Recepción.');
    counter.title=available?'Videos de esta ficha':'No se pudo consultar el catálogo';
    label.textContent=available?'🎥 Videocistoscopías ('+count+')':'🎥 Videocistoscopías';
  }
  open.dataset.videoState='loading';
  counter.textContent='…';

  const viewer=document.createElement('aside');
  viewer.className='cp-video-gallery-viewer';
  viewer.setAttribute('aria-label','Reproductor grande de videocistoscopía');
  const viewerHead=document.createElement('div');
  viewerHead.className='cp-video-gallery-viewer-head';
  const viewerTitle=document.createElement('strong');
  viewerTitle.className='cp-video-gallery-viewer-title';
  viewerTitle.textContent='Selecciona una videocistoscopía';
  const fullscreen=document.createElement('button');
  fullscreen.type='button';fullscreen.textContent='⛶ Pantalla completa';
  fullscreen.className='cp-video-gallery-fullscreen';fullscreen.hidden=true;
  viewerHead.append(viewerTitle,fullscreen);
  const viewerMeta=document.createElement('p');
  viewerMeta.className='cp-video-gallery-viewer-meta';
  viewerMeta.textContent='Elige un video de la galería para reproducirlo.';
  const stage=document.createElement('div');
  stage.className='cp-video-gallery-stage';
  const placeholder=document.createElement('div');
  placeholder.className='cp-video-gallery-placeholder';
  placeholder.textContent='▶';
  const bigPlay=document.createElement('button');
  bigPlay.className='cp-video-gallery-big-play';
  bigPlay.type='button';
  bigPlay.setAttribute('aria-label','Reproducir o pausar');
  bigPlay.textContent='▶';
  bigPlay.hidden=true;
  stage.append(placeholder,bigPlay);
  viewer.append(viewerHead,viewerMeta,stage);
  host.append(viewer);

  function stopPlayer(){
    if(activeVideo){
      activeVideo.pause();
      activeVideo.removeAttribute('src');
      const source=activeVideo.querySelector('source');
      if(source)source.removeAttribute('src');
      activeVideo.load();
      activeVideo.remove();
    }
    activeVideo=null;activeId=null;activeCanvasCapture=false;
    if(activeCard){activeCard.classList.remove('is-selected');activeCard.setAttribute('aria-pressed','false');}
    activeCard=null;
    fullscreen.hidden=true;
    bigPlay.hidden=true;
    bigPlay.textContent='▶';
    placeholder.hidden=false;
    viewerTitle.textContent='Selecciona una videocistoscopía';
    viewerMeta.textContent='Elige un video de la galería para reproducirlo.';
  }
  dialog.addEventListener('close',stopPlayer);
  dialog.addEventListener('cancel',()=>stopPlayer());

  function formatDuration(seconds){
    if(!Number.isFinite(seconds)||seconds<0)return '';
    const whole=Math.round(seconds);
    return String(Math.floor(whole/60)).padStart(2,'0')+':'+String(whole%60).padStart(2,'0');
  }
  function capturePreview(video,videoId){
    if(previewById.has(videoId)||activeCanvasCapture||!video.videoWidth||!video.videoHeight)return;
    activeCanvasCapture=true;
    try{
      const canvas=document.createElement('canvas');
      canvas.width=320;canvas.height=180;
      const ctx=canvas.getContext('2d');
      if(!ctx)return;
      ctx.fillStyle='#0c1925';ctx.fillRect(0,0,320,180);
      const scale=Math.min(320/video.videoWidth,180/video.videoHeight);
      const w=video.videoWidth*scale,h=video.videoHeight*scale;
      ctx.drawImage(video,(320-w)/2,(180-h)/2,w,h);
      const image=canvas.toDataURL('image/jpeg',0.68);
      previewById.set(videoId,image);
      const thumb=list.querySelector('[data-video-thumb="'+videoId+'"]');
      if(thumb){thumb.style.backgroundImage='url('+JSON.stringify(image)+')';thumb.classList.add('has-preview');}
    }catch(_ignored){
      // Canvas snapshot unsupported: leave the lightweight visual placeholder.
    }finally{activeCanvasCapture=false;}
  }

  function selectVideo(item,card){
    if(activeId===item.id&&activeVideo){
      if(activeVideo.paused)activeVideo.play().catch(()=>{bigPlay.hidden=false;});
      else activeVideo.pause();
      return;
    }
    stopPlayer();
    const when=String(item.recorded_at||'').slice(0,16).replace('T',' ');
    const title='Videocistoscopía '+(when||'sin fecha');
    const mb=(Math.max(0,Number(item.size_bytes)||0)/1048576).toFixed(1);
    activeId=item.id;
    activeCard=card;
    card.classList.add('is-selected');
    card.setAttribute('aria-pressed','true');
    viewerTitle.textContent=title;
    viewerMeta.textContent=mb+' MB · '+(when||'Grabación clínica')+' · Recepción (LAN)';
    const player=document.createElement('video');
    player.className='cp-video-gallery-player';
    player.controls=true;
    player.preload='none';
    player.playsInline=true;
    player.setAttribute('aria-label','Reproducir '+title);
    const source=document.createElement('source');
    source.src=url+'/play/'+encodeURIComponent(item.id);
    source.type='video/mp4';
    player.append(source);
    player.addEventListener('loadedmetadata',()=>{
      if(activeVideo!==player)return;
      durationById.set(item.id,player.duration);
      const badge=card.querySelector('.cp-video-card-duration');
      if(badge){badge.textContent=formatDuration(player.duration)||'▶';}
    });
    player.addEventListener('loadeddata',()=>{if(activeVideo===player)capturePreview(player,item.id);});
    player.addEventListener('timeupdate',()=>{
      if(activeVideo===player&&!previewById.has(item.id)&&player.currentTime>0.15)capturePreview(player,item.id);
    });
    player.addEventListener('play',()=>{if(activeVideo===player){bigPlay.hidden=true;bigPlay.textContent='Ⅱ';}});
    player.addEventListener('pause',()=>{if(activeVideo===player){bigPlay.hidden=false;bigPlay.textContent='▶';}});
    player.addEventListener('ended',()=>{if(activeVideo===player){bigPlay.hidden=false;bigPlay.textContent='▶';}});
    player.addEventListener('error',()=>{
      if(activeVideo!==player)return;
      viewerMeta.textContent='No se pudo reproducir. Comprueba la conexión LAN o el formato MP4.';
      bigPlay.hidden=false;bigPlay.textContent='▶';
    });
    activeVideo=player;
    placeholder.hidden=true;
    bigPlay.hidden=false;
    fullscreen.hidden=false;
    stage.prepend(player);
    player.play().catch(()=>{if(activeVideo===player)bigPlay.hidden=false;});
  }

  bigPlay.addEventListener('click',()=>{
    if(!activeVideo)return;
    if(activeVideo.paused)activeVideo.play().catch(()=>{bigPlay.hidden=false;});
    else activeVideo.pause();
  });
  fullscreen.addEventListener('click',()=>{
    if(!document.fullscreenElement&&stage.requestFullscreen)stage.requestFullscreen().catch(()=>{});
    else if(document.fullscreenElement&&document.exitFullscreen)document.exitFullscreen().catch(()=>{});
  });
  dialog.addEventListener('keydown',event=>{
    if(!activeVideo||event.code!=='Space')return;
    const tag=document.activeElement?.tagName||'';
    if(['BUTTON','INPUT','TEXTAREA','SELECT','VIDEO'].includes(tag))return;
    event.preventDefault();
    if(activeVideo.paused)activeVideo.play().catch(()=>{});
    else activeVideo.pause();
  });

  function makeCard(item,index){
    const when=String(item.recorded_at||'').slice(0,16).replace('T',' ');
    const button=document.createElement('button');
    button.type='button';
    button.className='cp-video-gallery-card';
    button.setAttribute('aria-pressed','false');
    button.setAttribute('aria-label','Abrir videocistoscopía '+(when||'#'+(index+1)));
    const thumbnail=document.createElement('span');
    thumbnail.className='cp-video-card-thumbnail';
    thumbnail.dataset.videoThumb=item.id;
    if(previewById.has(item.id)){
      thumbnail.style.backgroundImage='url('+JSON.stringify(previewById.get(item.id))+')';
      thumbnail.classList.add('has-preview');
    }
    const icon=document.createElement('span');
    icon.className='cp-video-card-play-icon';icon.textContent='▶';
    const duration=document.createElement('span');
    duration.className='cp-video-card-duration';
    duration.textContent=formatDuration(durationById.get(item.id))||'VIDEO';
    thumbnail.append(icon,duration);
    const info=document.createElement('span');info.className='cp-video-card-info';
    const name=document.createElement('strong');
    name.textContent='Videocistoscopía '+(when||'#'+(index+1));
    const meta=document.createElement('small');
    meta.textContent=(Math.max(0,Number(item.size_bytes)||0)/1048576).toFixed(1)+' MB · '+(when||'Fecha no disponible');
    info.append(name,meta);
    button.append(thumbnail,info);
    button.addEventListener('click',()=>selectVideo(item,button));
    return button;
  }

  async function load(force=false){
    if(busy||(loaded&&!force))return;
    busy=true;
    status.textContent='Consultando archivos de Recepción…';
    try{
      const response=await fetch(url,{cache:'no-store',headers:{Accept:'application/json'}});
      const media=(response.headers.get('Content-Type')||'').toLowerCase();
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
      const videos=(Array.isArray(data.videos)?data.videos:[]).filter(
        item=>item&&typeof item.id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(item.id)
      );
      setCount(videos.length);
      if(activeVideo)stopPlayer();
      list.replaceChildren();
      // Reception returns latest-first, but sort to keep visual order stable.
      videos.sort((a,b)=>String(b.recorded_at||'').localeCompare(String(a.recorded_at||'')));
      videos.forEach((item,index)=>list.append(makeCard(item,index)));
      status.textContent=videos.length?
        videos.length+' video'+(videos.length===1?'':'s')+' · Selecciona un cuadro para reproducir':
        'Este paciente aún no tiene videocistoscopías guardadas en Recepción.';
      loaded=true;
    }catch(error){
      status.textContent=(error&&error.message)||'No se pudo conectar con Recepción. Pulsa Actualizar para reintentar.';
      if(activeVideo)stopPlayer();
      list.replaceChildren();
      loaded=false;
      setCount(null,true);
    }finally{busy=false;}
  }
  open.addEventListener('click',()=>load(true));
  refresh?.addEventListener('click',()=>load(true));
  // Count read on entering a patient chart; no periodic catalogue or video polling.
  load();
})();
