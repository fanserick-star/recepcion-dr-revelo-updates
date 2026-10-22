/* v4.8.58 · Reception-only patient clinical document delivery.
   No automatic sends, no exposure of medical content in search results. */
(()=>{
  'use strict';
  const $=(s,r=document)=>r.querySelector(s);
  const escText=v=>String(v==null?'':v);
  const safeId=v=>String(v||'').replace(/[^a-zA-Z0-9_-]/g,'');
  const state={pid:0,name:'',phone:'',documents:[],ready_document:false,ready_video:false,sending:false};
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
    block.append(cell('p','Esta prueba usa un PDF ficticio, sin datos de pacientes. Se envía únicamente al número autorizado para pruebas.','rp-clinical-help'));
    const preview=document.createElement('a');
    preview.href='https://fanserick-star.github.io/recepcion-dr-revelo-updates/prueba-envio-clinico.html';
    preview.target='_blank';preview.rel='noopener noreferrer';
    preview.textContent='Ver ejemplo en mi iPhone (no envía nada)';
    preview.className='rp-clinical-preview';
    block.append(preview);
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
    if(!allowed){
      const missing=(data.test_missing||[]);
      block.append(cell('p','Envío real aún bloqueado: '+(missing.length?missing.join('; '):'falta configurar Cloudflare R2 y WhatsApp')+'.','rp-clinical-warning'));
    }
    host.append(block);
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
      info.append(cell('strong',doc.label),cell('small',(doc.date||'')+' · El PDF original firmado se comprueba al abrir'));
      row.append(info);
      const actions=document.createElement('div');actions.className='rp-clinical-actions';
      const kind=safeId(doc.kind),id=safeId(doc.id),pid=Number(state.pid);
      addButton(actions,'Ver PDF',()=>window.open('/api/clinical-delivery/patients/'+pid+'/signed/'+kind+'/'+id,'_blank'));
      addButton(actions,'Enviar WhatsApp',()=>sendDoc(doc),!state.ready_document||state.sending);
      row.append(actions);host.append(row);
    }
    const section=document.createElement('div');section.className='rp-clinical-video';
    section.append(cell('strong','Videocistoscopía desde memoria USB'));
    section.append(cell('p','Selecciona el video MP4 original. Solo se subirá cuando confirmes el envío.','rp-clinical-help'));
    const file=document.createElement('input');file.type='file';file.accept='.mp4,video/mp4';
    file.id='rpClinicalVideoFile';file.disabled=!state.ready_video||state.sending;
    section.append(file);
    addButton(section,'Enviar video por WhatsApp',()=>sendVideo(file),!state.ready_video||state.sending);
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
      Object.assign(state,{documents:data.documents||[],ready_document:!!data.ready_document,ready_video:!!data.ready_video,ready_test:!!status.ready_test,test_missing:status.test_missing||[]});
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
  async function sendVideo(file){
    if(state.sending||!state.ready_video)return;
    const chosen=file.files&&file.files[0];
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
