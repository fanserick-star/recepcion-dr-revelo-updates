/* v4.8.68 · Reception-only patient clinical document delivery.
   No automatic sends, no exposure of medical content in search results. */
(()=>{
  'use strict';
  const $=(s,r=document)=>r.querySelector(s);
  const escText=v=>String(v==null?'':v);
  const safeId=v=>String(v||'').replace(/[^a-zA-Z0-9_-]/g,'');
  const state={pid:0,name:'',phone:'',documents:[],videos:[],ready_document:false,ready_video:false,ready_r2:false,sending:false,saving_video:false,benchmarking:false};
  async function api(path,options={}){
    const response=await fetch(path,{cache:'no-store',...options});
    const data=await response.json().catch(()=>({}));
    if(!response.ok||data.ok===false)throw Error(data.error||data.detail||'No se pudo completar la operación');
    return data;
  }
  function notice(value,type='info'){
    if(typeof window.showAppToast==='function')window.showAppToast(value,type);
    else window.alert(value);
  }
  let closeClinicalPreview=null;
  function showSignedPdf(blob,label,unsigned=false){
    // PDF stays in browser memory; never upload or alter the signed original.
    if(closeClinicalPreview)closeClinicalPreview();
    const blobUrl=URL.createObjectURL(blob);
    const shade=document.createElement('div');
    shade.style.cssText='position:fixed;inset:0;z-index:2147483000;background:rgba(12,23,38,.77);display:flex;align-items:center;justify-content:center;padding:12px;box-sizing:border-box';
    shade.setAttribute('role','dialog');
    shade.setAttribute('aria-modal','true');
    shade.setAttribute('aria-label',unsigned?'Vista previa sin firma electrónica':'Vista previa de PDF firmado');
    const panel=document.createElement('div');
    panel.style.cssText='width:min(1100px,98vw);height:min(900px,94vh);background:#fff;border-radius:12px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 14px 65px #0008';
    const bar=document.createElement('div');
    bar.style.cssText='padding:12px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;border-bottom:1px solid #d8e0ea';
    const caption=cell('strong',(unsigned?'SIN FIRMA ELECTRÓNICA · Solo consulta · ':'PDF firmado · ')+label);
    caption.style.cssText='flex:1;font-size:15px;color:#18273d';
    const external=document.createElement('button');
    external.type='button';
    external.textContent=unsigned?'Abrir vista sin firma (opcional)':'Abrir en visor externo (opcional)';
    external.onclick=()=>window.open(blobUrl,'_blank','noopener,noreferrer');
    const close=document.createElement('button');
    close.type='button';
    close.textContent='Cerrar PDF';
    close.style.cssText='font-weight:700';
    const frame=document.createElement('iframe');
    frame.title=unsigned?'Documento guardado sin firma electrónica':'Documento PDF firmado';
    if(unsigned)frame.setAttribute('sandbox','');
    frame.src=blobUrl;
    frame.style.cssText='width:100%;flex:1;border:0;min-height:200px';
    const help=cell('p',unsigned?'VISTA PREVIA SIN FIRMA ELECTRÓNICA. No es un PDF firmado, no tiene QR de validación y no puede enviarse desde aquí.':'Si el visor integrado de esta PC no admite PDF, usa «Abrir en visor externo». La consulta no firma ni envía documentos.','');
    help.style.cssText='margin:5px 12px 9px;font-size:12px;color:#5d6777';
    let closed=false;
    function dismiss(){
      if(closed)return;
      closed=true;
      document.removeEventListener('keydown',onKey);
      frame.removeAttribute('src');
      shade.remove();
      URL.revokeObjectURL(blobUrl);
      if(closeClinicalPreview===dismiss)closeClinicalPreview=null;
    }
    function onKey(e){if(e.key==='Escape')dismiss();}
    close.onclick=dismiss;
    bar.append(caption);
    if(!unsigned)bar.append(external);
    bar.append(close);
    panel.append(bar,frame,help);
    shade.append(panel);
    document.body.append(shade);
    document.addEventListener('keydown',onKey);
    closeClinicalPreview=dismiss;
    close.focus();
  }
  async function previewSignedPdf(kind,id,pid,button,row,label){
    if(state.pid!==pid||button.disabled)return;
    const original=button.textContent;
    button.disabled=true;
    button.textContent='Consultando documento…';
    try{
      const path='/api/clinical-delivery/patients/'+pid+'/signed/'+kind+'/'+id;
      let response=await fetch(path,{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/pdf'}});
      let unsigned=false;
      if(!response.ok){
        const data=await response.json().catch(()=>({}));
        const message=data.detail||data.error||'No fue posible recuperar el documento firmado.';
        if(response.status===404 && /todavía no tiene PDF firmado/i.test(message)){
          // Only a proven unsigned document may use the isolated HTML preview.
          response=await fetch('/api/clinical-delivery/patients/'+pid+'/unsigned/'+kind+'/'+id,{cache:'no-store',credentials:'same-origin',headers:{Accept:'text/html'}});
          unsigned=true;
          if(!response.ok){const problem=await response.json().catch(()=>({}));throw Error(problem.detail||problem.error||'Historia no pudo generar la vista sin firma.');}
        }else throw Error(message);
      }
      const media=(response.headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
      if(media!==(unsigned?'text/html':'application/pdf'))throw Error('Historia no devolvió una vista válida.');
      if(unsigned && response.headers.get('X-Clinical-Preview-Unsigned')!=='1')throw Error('La vista no está identificada como sin firma.');
      const blob=await response.blob();
      if(blob.size<5||blob.size>(unsigned?2:20)*1024*1024)throw Error('La vista no supera la verificación de tamaño.');
      if(state.pid!==pid)return;
      showSignedPdf(blob,label,unsigned);
      const note=row.querySelector('.rp-clinical-signature-state');
      if(note)note.textContent=unsigned?'Sin firma electrónica · Solo vista previa':'Firmado electrónicamente · PDF original';
      const send=row.querySelector('.rp-clinical-send-document');
      if(unsigned && send)send.disabled=true;
    }catch(e){
      const message=e.message||'No se pudo abrir el PDF firmado.';
      const previous=row.querySelector('.rp-clinical-pdf-error');
      if(previous)previous.remove();
      const error=cell('p',message,'rp-clinical-pdf-error');
      error.style.cssText='color:#ad3e2c;font-size:13px;font-weight:650;margin:8px 12px';
      row.append(error);
      notice(message,'error');
    }finally{
      button.disabled=false;
      button.textContent=original;
    }
  }
  function container(){return $('#rpClinicalDocs');}
  function cell(tag,text,cls=''){
    const node=document.createElement(tag);if(cls)node.className=cls;
    node.textContent=escText(text);return node;
  }
  function addButton(parent,text,fn,disabled=false){
    const b=document.createElement('button');b.type='button';b.textContent=text;
    b.disabled=disabled;b.addEventListener('click',fn);parent.appendChild(b);return b;
  }
  function addSelfTest(host,data){
    const block=document.createElement('div');block.className='rp-clinical-test';
    block.append(cell('strong','📱 Prueba de WhatsApp en mi celular'));
    block.append(cell('p','Esta prueba usa un PDF ficticio y solo podrá enviarse al número configurado como WHATSAPP_TEST_PHONE en la PC. No incluye datos de pacientes.','rp-clinical-help'));
    const preview=document.createElement('a');
    preview.href='https://fanserick-star.github.io/recepcion-dr-revelo-updates/prueba-envio-clinico.html';
    preview.target='_blank';preview.rel='noopener noreferrer';
    preview.textContent='Ver ejemplo en mi iPhone (no envía nada)';
    preview.className='rp-clinical-preview';
    block.append(preview);
    addButton(block,'Comprobar Cloudflare R2 sin pacientes',async()=>{
      try{
        const r=await api('/api/clinical-delivery/check-r2',{method:'POST'});
        notice(r.lifecycle_7_day_header_verified?
          'Cloudflare R2 correcto: subida, descarga y regla de 7 días detectadas.':
          'Subida y descarga R2 correctas, pero no se confirmó la regla de borrado desde la cabecera del objeto. Revisa Cloudflare.',r.lifecycle_7_day_header_verified?'success':'info');
      }catch(e){notice(e.message||'No se pudo comprobar R2','error');}
    },!data.ready_r2);
    block.append(cell('p','Motor de envío: Worker WhatsApp de Cloudflare (el mismo de las citas), con autorización clínica independiente. No requiere token Meta local.','rp-clinical-help'));
    const input=document.createElement('input');
    input.type='tel';input.inputMode='tel';input.autocomplete='off';
    input.placeholder='Tu número de prueba: 09XXXXXXXX';
    input.maxLength=20;input.setAttribute('aria-label','Celular propio autorizado para prueba');
    block.append(input);
    const allowed=!!data.ready_test;
    addButton(block,'Enviar PRUEBA REAL a mi WhatsApp',async()=>{
      if(!window.confirm('Se enviará un mensaje real al número de prueba autorizado. El archivo contiene solo texto ficticio y puede generar un cargo de WhatsApp. ¿Continuar?'))return;
      const number=String(input.value||'').trim();
      if(!number){notice('Ingresa el número de tu celular de prueba','error');return;}
      try{
        const response=await api('/api/clinical-delivery/send-self-test',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({phone:number,confirmation:'ENVIAR PRUEBA'})
        });
        notice('Meta aceptó la prueba. Abre WhatsApp en tu iPhone y revisa el PDF. Vence el '+new Date(response.expires_at).toLocaleString('es-EC')+'.','success');
      }catch(e){notice(e.message||'No se pudo enviar la prueba','error');}
    },!allowed);
    block.append(cell('p','🎬 Video de prueba: MP4 sintético de 2 segundos (sin pacientes). Se envía con la plantilla de documento aprobada para comprobar la descarga y reproducción; no mide aún los videos de 500 MB.','rp-clinical-help'));
    const videoButton=addButton(block,'Enviar VIDEO DE PRUEBA a mi WhatsApp',async()=>{
      if(!window.confirm('Se enviará un video ficticio de 2 segundos al celular autorizado. No se utilizará ningún video de pacientes. ¿Continuar?'))return;
      const number=String(input.value||'').trim();
      if(!number){notice('Ingresa el número autorizado para pruebas','error');return;}
      videoButton.disabled=true;
      try{
        const result=await api('/api/clinical-delivery/send-self-test-video',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({phone:number,confirmation:'ENVIAR PRUEBA'})
        });
        notice('Meta aceptó el MP4 ficticio. Abre el enlace corto en WhatsApp y verifica el video de 2 segundos. Caduca el '+new Date(result.expires_at).toLocaleString('es-EC')+'.','success');
      }catch(err){notice(err.message||'No se pudo enviar el MP4 de prueba','error');}
      finally{videoButton.disabled=!allowed;}
    },!allowed);
    if(!allowed){
      const missing=(data.test_missing||[]);
      block.append(cell('p','Envío real aún bloqueado: '+(missing.length?missing.join('; '):'falta configurar Cloudflare R2 y WhatsApp')+'.','rp-clinical-warning'));
    }
    host.append(block);
  }
  function addPrivateVideoLanTools(section){
    const box=document.createElement('div');
    box.className='rp-clinical-lan-video-tools';
    const stateLine=cell('p','Comprobando el servicio privado de reproducción LAN…','rp-clinical-help');
    box.append(stateLine);
    const btn=addButton(box,'Habilitar acceso de Historia (Windows)',async()=>{
      btn.disabled=true;
      try{
        const answer=await api('/api/clinical-videos/lan-firewall',{method:'POST'});
        stateLine.textContent=answer.message||'Permiso de red solicitado a Windows.';
        notice(answer.message||'Confirma el permiso de Windows.','success');
      }catch(e){
        stateLine.textContent=e.message||'No se pudo pedir el permiso de Windows.';
        notice(stateLine.textContent,'error');
      }finally{btn.disabled=false;}
    });
    section.append(box);
    api('/api/clinical-videos/lan-status').then(data=>{
      if(!box.isConnected)return;
      const status=data.ready?'Servicio privado de videos activo en el puerto '+data.port+'.':
        'El servicio privado de videos no pudo iniciarse en esta PC.';
      if(data.firewall_rule===true){
        stateLine.textContent=status+' Permiso privado de Windows registrado.';
      }else if(data.firewall_rule===false){
        stateLine.textContent=status+' Falta permitir videos al doctor desde Windows. Pulsa «Habilitar acceso de Historia» y acepta la ventana de Windows.';
      }else{
        stateLine.textContent=status+' Comprueba que el puerto de videos esté permitido en la red privada.';
      }
      btn.disabled=!data.ready;
    }).catch(()=>{
      if(box.isConnected)stateLine.textContent='No se pudo comprobar el acceso privado de Historia. Reinicia Recepción.';
      btn.disabled=true;
    });
  }
  function draw(data={}){
    const host=container();if(!host)return;
    host.replaceChildren();
    const top=cell('div','Documentos realizados por el doctor en Historia Clínica','rp-clinical-subtitle');
    host.append(top);
    addSelfTest(host,data);
    if(!data.ok){host.append(cell('p',data.error||'No se pudo consultar la ficha clínica.','rp-clinical-error'));return;}
    const docs=Array.isArray(data.documents)?data.documents:[];
    host.append(cell('p',docs.length?docs.length+' documento(s) guardado(s), del más reciente al más antiguo.':'No hay recetas, informes ni certificados guardados para esta ficha.','rp-clinical-help'));
    for(const doc of docs){
      const row=document.createElement('div');row.className='rp-clinical-row';
      const info=document.createElement('div');info.className='rp-clinical-info';
      info.append(cell('strong',doc.label),cell('small',(doc.date||'')+' · Firma electrónica: se comprueba al abrir','rp-clinical-signature-state'));
      row.append(info);
      const actions=document.createElement('div');actions.className='rp-clinical-actions';
      const kind=safeId(doc.kind),id=safeId(doc.id),pid=Number(state.pid);
      const view=addButton(actions,'Ver documento',()=>previewSignedPdf(kind,id,pid,view,row,doc.label));
      const send=addButton(actions,'Enviar WhatsApp',()=>sendDoc(doc),!state.ready_document||state.sending);
      send.classList.add('rp-clinical-send-document');
      row.append(actions);host.append(row);
    }
    const section=document.createElement('div');section.className='rp-clinical-video';
    section.append(cell('strong','🎥 Archivo de videocistoscopías del paciente'));
    section.append(cell('p','Selecciona uno o varios archivos MP4 desde la memoria USB (hasta 20 por lote). Se guardarán los originales, uno por uno, en esta PC y aparecerán en la ficha de Historia. No se envían a internet.','rp-clinical-help'));
    const file=document.createElement('input');file.type='file';file.accept='.mp4,video/mp4';
    file.id='rpClinicalVideoFile';file.multiple=true;file.disabled=state.sending||state.saving_video||state.benchmarking;
    section.append(file);
    addButton(section,'Guardar videos en Recepción',()=>saveVideo(file),state.sending||state.saving_video||state.benchmarking);
    addButton(section,'Enviar un video por WhatsApp (no guarda)',()=>sendVideo(file),!state.ready_video||state.sending||state.saving_video||state.benchmarking);
    addButton(section,'Medir subida REAL a Cloudflare R2',()=>benchmarkVideo(file),!data.ready_r2||state.sending||state.saving_video||state.benchmarking);
    section.append(cell('p','Mide una videocistoscopía real de hasta 550 MiB, con porcentaje y velocidad. Tras verificarla, elimina la copia temporal de R2. NO envía WhatsApp ni activa envíos a pacientes. Requiere autorización para la prueba.','rp-clinical-help'));
    addPrivateVideoLanTools(section);
    const archived=Array.isArray(data.videos)?data.videos:state.videos;
    section.append(cell('p',archived.length+' video(s) guardado(s) para este paciente.','rp-clinical-help'));
    if(archived.length){
      section.append(cell('p','PRUEBA PRIVADA: para enviar una videocistoscopía archivada a tu propio WhatsApp, introduce el número autorizado de pruebas. Este contenido es REAL: confirma permiso del paciente para compartirlo contigo. El enlace vence a los 7 días.','rp-clinical-help'));
    }
    const testPhone=document.createElement('input');
    testPhone.type='tel';testPhone.inputMode='tel';testPhone.autocomplete='off';
    testPhone.placeholder='TU WhatsApp autorizado: 09XXXXXXXX';testPhone.maxLength=20;
    testPhone.setAttribute('aria-label','Número personal autorizado para recibir prueba clínica');
    if(archived.length)section.append(testPhone);
    archived.forEach(v=>{
      const stamp=String(v.recorded_at||'').slice(0,16).replace('T',' ');
      const mb=(Number(v.size_bytes||0)/1048576).toFixed(1);
      section.append(cell('p','🎬 Videocistoscopía · '+stamp+' · '+mb+' MB · '+(v.backup?'Respaldo externo disponible':'Respaldo externo pendiente'),'rp-clinical-help'));
      const btn=addButton(section,'Enviar ESTE video a MI WhatsApp de pruebas',()=>sendArchivedVideoTest(v,testPhone),
        !state.ready_test||state.sending||state.saving_video||state.benchmarking);
      btn.classList.add('rp-clinical-send-archived-test');
    });
    host.append(section);
    const warning=data.missing||[];
    if(warning.length){
      host.append(cell('p','Envíos desactivados hasta completar configuración: '+warning.join('; ')+'. Los documentos se pueden consultar sin activar los envíos.','rp-clinical-warning'));
    }
    host.append(cell('p','Las copias temporales de entrega vencen a los 7 días. Los originales de Historia nunca se eliminan. El enlace firmado es confidencial: quien lo reciba podrá usarlo durante su vigencia.','rp-clinical-footnote'));
  }
  async function load(pid,phone,name){
    const root=container();if(!root)return;
    state.pid=Number(pid);state.phone=String(phone||'');state.name=String(name||'');
    root.replaceChildren(cell('p','Consultando documentos de Historia Clínica...','rp-clinical-help'));
    let status={ready_test:false,test_missing:[]};
    try{status=await api('/api/clinical-delivery/status');}catch(_ignored){}
    try{
      const data=await api('/api/clinical-delivery/patients/'+state.pid+'/documents');
      if(!container()||state.pid!==Number(pid))return;
      Object.assign(state,{documents:data.documents||[],videos:data.videos||[],ready_document:!!data.ready_document,ready_video:!!data.ready_video,ready_r2:!!data.ready_r2,ready_test:!!status.ready_test,test_missing:status.test_missing||[]});
      draw({...status,...data});
    }catch(e){
      draw({...status,ok:false,error:e.message||'Historia no está disponible'});
    }
  }
  function confirmDelivery(label){
    const raw=String(state.phone||'').replace(/\D/g,'');
    const phone=raw.startsWith('09')?'593'+raw.slice(1):raw;
    if(!/^5939\d{8}$/.test(phone)){notice('Primero verifica el número del paciente en su ficha.','error');return null;}
    // Deliberate two independent operator confirmations to prevent misdelivery.
    if(!window.confirm('PACIENTE: '+state.name+'\nNÚMERO: +'+phone+'\nARCHIVO: '+label+'\n\n¿Verificaste personalmente que el número pertenece al paciente?'))return null;
    if(!window.confirm('¿El paciente autorizó recibir este contenido médico confidencial mediante WhatsApp y conoce que el enlace vence en 7 días?'))return null;
    return {confirmed_phone:phone,identity_confirmed:true,consent_confirmed:true};
  }
  async function sendDoc(doc){
    if(state.sending||!state.ready_document)return;
    const approval=confirmDelivery(doc.label);if(!approval)return;
    state.sending=true;
    try{
      const r=await api('/api/clinical-delivery/patients/'+state.pid+'/send-document',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...approval,kind:doc.kind,document_id:doc.id})
      });
      notice('Mensaje aceptado por WhatsApp. Vence el '+new Date(r.expires_at).toLocaleString('es-EC')+'.','success');
    }catch(e){notice(e.message||'No se envió el documento','error');}
    finally{state.sending=false;draw({ok:true,documents:state.documents,missing:[],...state});}
  }
  // Independent patient-identity gate for local MP4 archive. Never uses the
  // browser's native confirm/alert or sends data until the operator accepts.
  let archiveConfirmationOpen=false;
  function confirmVideoArchive(chosen){
    // FileList is snapshotted before the operator is allowed to proceed.
    if(!Array.isArray(chosen)||!chosen.length)return Promise.resolve(false);
    if(archiveConfirmationOpen)return Promise.resolve(false);
    archiveConfirmationOpen=true;
    const currentPatientId=state.pid;
    const opener=document.activeElement;
    return new Promise(resolve=>{
      const shade=document.createElement('div');
      shade.className='rp-video-confirm-shade';
      shade.setAttribute('role','presentation');
      const dialog=document.createElement('section');
      dialog.className='rp-video-confirm-dialog';
      dialog.setAttribute('role','dialog');
      dialog.setAttribute('aria-modal','true');
      dialog.setAttribute('aria-labelledby','rpVideoArchiveTitle');
      dialog.setAttribute('aria-describedby','rpVideoArchiveDesc');
      const head=document.createElement('div');
      head.className='rp-video-confirm-head';
      const mark=cell('div','🎥','rp-video-confirm-icon');
      mark.setAttribute('aria-hidden','true');
      const intro=document.createElement('div');
      intro.append(
        cell('span','ARCHIVO CLÍNICO · RECEPCIÓN','rp-video-confirm-kicker'),
        cell('h2',chosen.length===1?'Guardar videocistoscopía':'Guardar '+chosen.length+' videocistoscopías','rp-video-confirm-title')
      );
      intro.lastChild.id='rpVideoArchiveTitle';
      head.append(mark,intro);
      const info=cell('p','Antes de guardar, verifica que '+(chosen.length===1?'esta grabación pertenece':'todas las grabaciones pertenecen')+' a la ficha clínica indicada.','rp-video-confirm-desc');
      info.id='rpVideoArchiveDesc';
      const details=document.createElement('div');
      details.className='rp-video-confirm-details';
      const appendDetail=(label,value)=>{
        const group=document.createElement('div');
        group.className='rp-video-confirm-detail';
        group.append(cell('span',label),cell('strong',value));
        details.append(group);
      };
      appendDetail('PACIENTE',state.name||'Paciente sin nombre');
      appendDetail(chosen.length===1?'ARCHIVO ORIGINAL':'ARCHIVOS ORIGINALES ('+chosen.length+')',chosen.map((f,i)=>(chosen.length>1?(i+1)+'. ':'')+f.name).join('\n'));
      const totalBytes=chosen.reduce((sum,f)=>sum+f.size,0);
      appendDetail('TAMAÑO TOTAL',(totalBytes/(1024*1024)).toLocaleString('es-EC',{maximumFractionDigits:1})+' MB');
      const local=cell('p','Se guardará únicamente en esta PC. No se enviará por WhatsApp ni se subirá a Cloudflare o Neon.','rp-video-confirm-local');
      const checkLine=document.createElement('label');
      checkLine.className='rp-video-confirm-checkbox';
      const check=document.createElement('input');
      check.type='checkbox';
      const checkCopy=cell('span',chosen.length===1?'Confirmo que el video corresponde a este paciente y que revisé la ficha correcta.':'Confirmo que TODOS los videos corresponden a este mismo paciente y que revisé la ficha correcta.');
      checkLine.append(check,checkCopy);
      const actions=document.createElement('div');
      actions.className='rp-video-confirm-actions';
      const cancel=cell('button','Cancelar','rp-video-confirm-cancel');
      cancel.type='button';
      const accept=cell('button',chosen.length===1?'Guardar video en Recepción':'Guardar '+chosen.length+' videos en Recepción','rp-video-confirm-accept');
      accept.type='button';
      accept.disabled=true;
      check.addEventListener('change',()=>{accept.disabled=!check.checked;});
      actions.append(cancel,accept);
      dialog.append(head,info,details,local,checkLine,actions);
      shade.append(dialog);
      let settled=false;
      function finish(approved){
        if(settled)return;
        settled=true;
        document.removeEventListener('keydown',onKey,true);
        shade.remove();
        archiveConfirmationOpen=false;
        if(opener && opener.isConnected && typeof opener.focus==='function')opener.focus();
        resolve(Boolean(approved&&check.checked&&currentPatientId===state.pid));
      }
      function onKey(e){
        if(e.key==='Escape'){e.preventDefault();finish(false);return;}
        if(e.key!=='Tab')return;
        const focusable=[check,cancel,accept].filter(el=>!el.disabled);
        if(!focusable.length)return;
        const first=focusable[0],last=focusable[focusable.length-1];
        if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
        else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
      }
      cancel.addEventListener('click',()=>finish(false));
      accept.addEventListener('click',()=>finish(true));
      shade.addEventListener('click',e=>{if(e.target===shade)finish(false);});
      document.body.append(shade);
      document.addEventListener('keydown',onKey,true);
      check.focus();
    });
  }
  function createSpeedProgress(host){
    const wrap=document.createElement('div');
    wrap.setAttribute('role','status');wrap.setAttribute('aria-live','polite');
    wrap.style.cssText='border:1px solid #9cbad6;border-radius:13px;background:#f3f8ff;color:#173550;padding:16px;margin:14px 0;max-width:780px';
    const label=cell('strong','Preparando la prueba de velocidad…');
    label.style.cssText='display:block;font-size:16px;margin-bottom:12px';
    const track=document.createElement('div');
    track.style.cssText='height:18px;border-radius:16px;background:#dce8f4;overflow:hidden;width:100%';
    const fill=document.createElement('div');
    fill.style.cssText='height:100%;width:0%;border-radius:16px;background:linear-gradient(90deg,#1765b3,#2aab9f);transition:width .25s';
    track.append(fill);
    const detail=cell('p','0 % · 0 / 0 MiB','rp-clinical-help');
    detail.style.cssText='margin:12px 0 4px;font-size:14px;font-weight:700;font-variant-numeric:tabular-nums';
    const help=cell('p','El porcentaje indica bytes transmitidos. Cloudflare debe confirmar la carga antes de declararla completa.','rp-clinical-help');
    wrap.append(label,track,detail,help);
    host.append(wrap);
    return {
      update(stage,bytes,total,elapsed,rate,mode='velocidad'){
        const mib=v=>(Math.max(0,Number(v)||0)/1048576).toFixed(1);
        const percent=total?Math.max(0,Math.min(100,Math.floor(bytes/total*100))):0;
        fill.style.width=percent+'%';
        const titles={
          preparando:'Preparando prueba…',
          recibiendo_archivo:'Copiando el video desde el selector a Recepción…',
          preparando_r2:'Archivo recibido. Conectando con Cloudflare R2…',
          subiendo_r2:'Enviando videocistoscopía a Cloudflare R2…',
          verificando_r2:'100 % enviado. Confirmando la copia en R2…',
          eliminando_copia:'Copia confirmada. Eliminando video temporal de la nube…',
          preparando_enlace:'Video verificado. Creando enlace corto seguro…',
          enviando_whatsapp:'Solicitando a Meta el envío a tu WhatsApp de pruebas…',
          complete:'Prueba completada: R2 confirmó el video y eliminó la copia.',
          error:'Prueba incompleta'
        };
        label.textContent=stage==='complete'&&mode==='envio_prueba'?
          'Meta aceptó el envío: revisa tu WhatsApp de pruebas.':titles[stage]||'Procesando transferencia…';
        const active=['subiendo_r2','verificando_r2','eliminando_copia','preparando_enlace','enviando_whatsapp','complete'].includes(stage);
        const rateNum=Number(rate)||0;
        const extra=active?' · '+rateNum.toFixed(2)+' MiB/s':'';
        const eta=stage==='subiendo_r2'&&rateNum>0?' · faltan aprox. '+Math.ceil((total-bytes)/1048576/rateNum)+' s':'';
        detail.textContent=percent+' % · '+mib(bytes)+' / '+mib(total)+' MiB'+extra+
          (elapsed?' · '+Number(elapsed).toFixed(1)+' s':'')+eta;
        if(stage==='complete'){
          wrap.style.background='#edf9f3';wrap.style.borderColor='#83b99a';
          help.textContent=mode==='envio_prueba'?
            'Meta aceptó el mensaje, aún falta confirmar la recepción en tu celular. El archivo privado permanece disponible hasta 7 días y la copia local no cambia.':
            'El original sigue guardado en la PC. La copia temporal de la nube se eliminó. No se envió WhatsApp.';
        }else if(stage==='error'){
          wrap.style.background='#fff5f2';wrap.style.borderColor='#d28c81';
        }
      },
      fail(message){
        label.textContent='No se completó la prueba';
        help.textContent=message||'Comprueba la conexión a Cloudflare.';
        wrap.style.background='#fff5f2';wrap.style.borderColor='#d28c81';
      }
    };
  }
  async function benchmarkVideo(input){
    if(state.benchmarking||state.sending||state.saving_video||!state.ready_r2)return;
    const chosen=input.files&&input.files[0];
    if(!chosen||(input.files||[]).length!==1){
      notice('Selecciona exactamente un archivo MP4 para medir la subida.','error');return;
    }
    if(!/\.mp4$/i.test(chosen.name)||chosen.size<1024||chosen.size>550*1024*1024){
      notice('Selecciona un MP4 válido de hasta 550 MiB.','error');return;
    }
    if(!window.confirm('PRUEBA DE SUBIDA REAL\nPaciente: '+state.name+
      '\nArchivo: '+chosen.name+'\nTamaño: '+(chosen.size/1048576).toFixed(1)+
      ' MiB\n\n¿Confirmas que el video corresponde a la ficha correcta?'))return;
    if(!window.confirm('¿Existe autorización para subir temporalmente este video médico a Cloudflare R2 SOLO para medir la velocidad? Después se intentará borrar la copia. No se enviará WhatsApp.'))return;
    const pid=Number(state.pid),host=container();
    if(!host)return;
    state.benchmarking=true;
    const display=createSpeedProgress(host);
    let timer=null;
    try{
      const started=await api('/api/clinical-delivery/patients/'+pid+'/video-speed-test/start',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({size_bytes:chosen.size,confirmed_patient:true,upload_consent:true})
      });
      const progressUrl='/api/clinical-delivery/patients/'+pid+'/video-speed-test/'+encodeURIComponent(started.job_id);
      const refresh=async()=>{
        try{
          const progress=await api(progressUrl);
          const r2=['subiendo_r2','verificando_r2','eliminando_copia','complete'].includes(progress.stage);
          display.update(progress.stage,r2?progress.r2_bytes:progress.local_bytes,
            progress.total_bytes,progress.elapsed_seconds,progress.upload_mibps);
          if(progress.done&&timer){window.clearInterval(timer);timer=null;}
        }catch(_e){/* UI polling is local only; the upload continues independently. */}
      };
      timer=window.setInterval(refresh,1000);
      const result=await new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();
        xhr.open('POST',progressUrl+'/upload');
        xhr.setRequestHeader('Content-Type','video/mp4');
        xhr.upload.onprogress=e=>{
          if(e.lengthComputable)display.update('recibiendo_archivo',e.loaded,chosen.size,0,0);
        };
        xhr.onload=()=>{
          let payload={};
          try{payload=JSON.parse(xhr.responseText||'{}');}catch(_e){}
          if(xhr.status>=200&&xhr.status<300&&payload.ok!==false)resolve(payload);
          else reject(Error(payload.detail||payload.error||'No se completó la prueba'));
        };
        xhr.onerror=()=>reject(Error('Se interrumpió la conexión local'));
        xhr.onabort=()=>reject(Error('Se canceló el envío a Recepción'));
        xhr.send(chosen);
      });
      await refresh();
      if(result.stage!=='complete'||!result.r2_verified||!result.r2_deleted){
        throw Error('R2 no confirmó la verificación o eliminación de la copia temporal.');
      }
      notice('Subida comprobada: '+(chosen.size/1048576).toFixed(1)+' MiB a '+
        Number(result.upload_mibps).toFixed(2)+' MiB/s. Copia temporal eliminada.','success');
    }catch(e){
      display.fail(e.message||'No se pudo completar la prueba');
      notice(e.message||'Falló la subida de prueba','error');
    }finally{
      if(timer)window.clearInterval(timer);
      state.benchmarking=false;
    }
  }
  async function sendArchivedVideoTest(video,input){
    if(state.sending||state.saving_video||state.benchmarking||!state.ready_test)return;
    const id=safeId(video&&video.id),pid=Number(state.pid);
    const supplied=String(input.value||'').trim();
    const digits=supplied.replace(/\D/g,'');
    const phone=digits.startsWith('09')?'593'+digits.slice(1):digits;
    if(!/^[0-9a-f]{32}$/.test(id)||!/^5939\d{8}$/.test(phone)){
      notice('Selecciona una videocistoscopía archivada e ingresa tu celular autorizado de pruebas.','error');return;
    }
    const size=(Number(video.size_bytes||0)/1048576).toFixed(1);
    if(!window.confirm('CONFIRMAR FICHA Y VIDEO REAL\n\nPaciente: '+state.name+
      '\nVideocistoscopía archivada: '+size+' MiB\nDestino: +'+phone+
      '\n\n¿Confirmas que este video pertenece a la ficha del paciente y es exactamente el que deseas enviar?'))return;
    if(!window.confirm('CONFIDENCIALIDAD CLÍNICA\n\n¿El paciente autorizó expresamente que su videocistoscopía REAL se comparta a TU número WhatsApp +'+phone+
      ' para esta prueba?\n\nEl enlace podría abrirlo quien lo reciba y estará vigente hasta 7 días. No se enviará a otros pacientes.'))return;
    const host=container();if(!host)return;
    state.benchmarking=true;
    const display=createSpeedProgress(host);
    let timer=null;
    try{
      const res=await api('/api/clinical-delivery/patients/'+pid+'/archived-video/'+id+'/send-to-test-phone',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({phone,identity_confirmed:true,patient_authorized_staff_delivery:true})
      });
      const url='/api/clinical-delivery/patients/'+pid+'/video-speed-test/'+encodeURIComponent(res.job_id);
      const poll=async()=>{
        let progress;
        try{progress=await api(url);}
        catch(err){
          if(timer)window.clearInterval(timer);
          timer=null;state.benchmarking=false;
          display.fail('No se pudo consultar el resultado. Verifica primero tu WhatsApp antes de volver a intentar.');
          return;
        }
        display.update(progress.stage,progress.r2_bytes,progress.total_bytes,
          progress.elapsed_seconds,progress.upload_mibps,progress.mode);
        if(progress.done){
          if(timer)window.clearInterval(timer);
          timer=null;state.benchmarking=false;
          if(progress.stage==='complete'&&progress.whatsapp_accepted){
            notice('Meta aceptó la videocistoscopía para tu WhatsApp de prueba. Abre el enlace corto y comprueba la reproducción.','success');
          }else{
            display.fail(progress.error||'No se confirmó el envío. Antes de repetir, revisa tu WhatsApp.');
            notice('No se confirmó el mensaje. Revisa primero tu WhatsApp para evitar duplicados.','error');
          }
        }
      };
      timer=window.setInterval(poll,1000);
      await poll();
    }catch(err){
      if(timer)window.clearInterval(timer);
      display.fail(err.message||'No se inició el envío de prueba');
      notice(err.message||'Falló la autorización del envío','error');
      state.benchmarking=false;
    }
  }
  async function saveVideo(file){
    if(state.saving_video||state.sending||state.benchmarking)return;
    const selected=Array.from(file.files||[]);
    if(!selected.length){notice('Selecciona los videos MP4 que deseas archivar.','error');return;}
    if(selected.length>20){notice('Puedes guardar hasta 20 videos por lote.','error');return;}
    const invalid=selected.find(f=>!/\.mp4$/i.test(f.name)||f.size<1024||f.size>2*1024*1024*1024);
    if(invalid){notice('Hay un archivo no válido o que supera 2 GB. Selecciona únicamente MP4 de máximo 2 GB cada uno.','error');return;}
    const total=selected.reduce((sum,f)=>sum+f.size,0);
    if(total>10*1024*1024*1024){notice('Este lote supera 10 GB. Divídelo en dos grupos para proteger el espacio de esta PC.','error');return;}
    const pid=state.pid,phone=state.phone,name=state.name;
    if(!await confirmVideoArchive(selected))return;
    if(state.sending||state.saving_video||state.benchmarking||state.pid!==pid)return;
    state.saving_video=true;
    const host=container();
    const progress=document.createElement('div');
    progress.className='rp-clinical-batch-progress';
    progress.setAttribute('role','status');
    progress.setAttribute('aria-live','polite');
    const headline=cell('strong','Preparando '+selected.length+' video(s)…');
    const rows=selected.map((f,i)=>cell('div',(i+1)+'. '+f.name+' · Pendiente','rp-clinical-batch-row'));
    progress.append(headline,...rows);
    if(host)host.append(progress);
    let saved=0,duplicates=0;
    const failed=[];
    try{
      for(let i=0;i<selected.length;i++){
        if(state.pid!==pid){failed.push('Se cambió de ficha; los videos restantes no se guardaron.');break;}
        const chosen=selected[i];
        headline.textContent='Guardando video '+(i+1)+' de '+selected.length+' en Recepción…';
        rows[i].textContent=(i+1)+'. '+chosen.name+' · Guardando…';
        try{
          const url='/api/clinical-videos/patients/'+pid+'/import?filename='+encodeURIComponent(chosen.name);
          const result=await api(url,{method:'POST',headers:{'Content-Type':'video/mp4'},body:chosen});
          if(result.duplicate){duplicates++;rows[i].textContent=(i+1)+'. '+chosen.name+' · Ya estaba archivado';}
          else{saved++;rows[i].textContent=(i+1)+'. '+chosen.name+' · Guardado correctamente'+(result.backup?' con respaldo':' · Respaldo externo pendiente');}
        }catch(error){
          const reason=String(error.message||'No se pudo importar').slice(0,160);
          rows[i].textContent=(i+1)+'. '+chosen.name+' · Error: '+reason;
          failed.push((i+1)+'. '+chosen.name+': '+reason);
        }
      }
      headline.textContent='Lote finalizado: '+saved+' guardado(s), '+duplicates+' repetido(s), '+failed.length+' error(es).';
    }finally{
      state.saving_video=false;
      // The original stored files are never deleted or overwritten on a failed batch.
    }
    if(state.pid!==pid)return;
    await load(pid,phone,name);
    const report=cell('div','Resultado: '+saved+' nuevo(s), '+duplicates+' ya archivado(s) y '+failed.length+' error(es).','rp-clinical-batch-summary');
    if(failed.length){
      const details=cell('p',failed.join('\n'),'rp-clinical-batch-failures');
      report.append(details);
    }
    if(container()&&state.pid===pid)container().append(report);
    notice(failed.length?'Se completó el lote con errores. Revisa el resumen debajo.':'Videos procesados: '+saved+' nuevos y '+duplicates+' ya archivados.',failed.length?'error':'success');
  }
  async function sendVideo(file){
    if(state.sending||state.benchmarking||!state.ready_video)return;
    const chosen=file.files&&file.files[0];
    if((file.files||[]).length>1){
      notice('WhatsApp admite un video por envío. Para enviarlo, selecciona únicamente ese MP4.','error');
      return;
    }
    if(!chosen){notice('Selecciona primero un archivo MP4.','error');return;}
    if(!/\.mp4$/i.test(chosen.name)||chosen.size>550*1024*1024){notice('Archivo no válido. Selecciona un MP4 de hasta 550 MB.','error');return;}
    const approval=confirmDelivery('Videocistoscopía · '+chosen.name);
    if(!approval)return;
    const qs=new URLSearchParams(approval);
    state.sending=true;
    const host=container();
    const progress=cell('p','Subiendo video de forma segura… No cierres Recepción.','rp-clinical-help');
    if(host)host.append(progress);
    try{
      const r=await api('/api/clinical-delivery/patients/'+state.pid+'/send-video?'+qs,{
        method:'POST',headers:{'Content-Type':'video/mp4'},body:chosen
      });
      notice('Video enviado. Acceso temporal hasta '+new Date(r.expires_at).toLocaleString('es-EC')+'.','success');
    }catch(e){notice(e.message||'No se pudo completar la subida y el envío','error');}
    finally{state.sending=false;draw({ok:true,documents:state.documents,missing:[],...state});}
  }
  window.loadClinicalDelivery=load;
})();
