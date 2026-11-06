from __future__ import annotations


def _inject_before_body(html: bytes, fragment: str) -> bytes:
    text = html.decode("utf-8", errors="replace")
    marker = "</body>"
    if marker in text:
        text = text.replace(marker, fragment + marker, 1)
    else:
        text += fragment
    return text.encode("utf-8")


DISPLAY_VOICE_SCRIPT = r"""
<script id="tvVoiceSelectorRuntime">
;(()=>{
  if(window.__tvVoiceSelectorRuntime)return;
  window.__tvVoiceSelectorRuntime=true;
  let lastVoiceTest=null;
  let lastReport='';
  let voiceTimer=0;

  function voices(){
    try{return ('speechSynthesis' in window)?(window.speechSynthesis.getVoices()||[]):[]}catch(_){return []}
  }
  function cleanVoice(v){
    return {voiceURI:String(v.voiceURI||v.name||'').slice(0,240),name:String(v.name||'').slice(0,180),lang:String(v.lang||'').slice(0,40),default:!!v.default,localService:!!v.localService};
  }
  function reportVoices(){
    const list=voices().slice(0,64).map(cleanVoice),payload={supported:('speechSynthesis' in window)&&list.length>0,voices:list};
    const signature=JSON.stringify(payload);
    if(signature===lastReport)return;
    lastReport=signature;
    fetch('/api/tv/voices',{method:'POST',headers:{'Content-Type':'application/json'},body:signature,cache:'no-store'}).catch(()=>{});
  }
  function fallbackVoice(list){
    return list.find(v=>String(v.lang||'').toLowerCase()==='es-ec')||list.find(v=>String(v.lang||'').toLowerCase().startsWith('es-'))||list.find(v=>String(v.lang||'').toLowerCase().startsWith('es'))||null;
  }
  function configuredVoice(cfg){
    const list=voices();
    if(cfg){
      const uri=String(cfg.voice_uri||'');
      if(uri){const exact=list.find(v=>String(v.voiceURI||v.name||'')===uri);if(exact)return exact}
      const name=String(cfg.voice_name||''),lang=String(cfg.voice_lang||'');
      if(name){const named=list.find(v=>String(v.name||'')===name&&(!lang||String(v.lang||'')===lang));if(named)return named}
    }
    return fallbackVoice(list);
  }
  function showAudioUnlock(){
    try{const button=document.getElementById('audioEnable');if(button)button.style.display='block'}catch(_){ }
  }
  function playReceptionVoice(turn,review,fromCall,sampleEvent){
    try{
      const audio=document.getElementById('voiceAudio');
      if(!audio)return;
      audio.onerror=showAudioUnlock;
      // Names never enter the URL: only the live call event counter does.
      const callEvent=(fromCall&&state&&state.display_mode==='live'&&state.mode==='calling'&&!state.sound_test)?Number(state.event_id||0):0;
      const sampleId=Number(sampleEvent||0);
      // Never place a real or fictitious surname in the public URL.
      audio.src='/api/turn-voice.wav?turn='+encodeURIComponent(turn)+'&review='+(review?'1':'0')+'&event='+encodeURIComponent(callEvent)+'&sample_test='+encodeURIComponent(sampleId)+'&t='+Date.now();
      const result=audio.play();
      if(result&&typeof result.catch==='function')result.catch(showAudioUnlock);
    }catch(_){showAudioUnlock()}
  }
  function speak(turn,cfg,delay,fromCall,sampleEvent){
    const n=parseInt(turn||0,10);if(!n)return;
    clearTimeout(voiceTimer);
    voiceTimer=setTimeout(()=>{
      const isExamReview=false; // The public TV only announces the turn number.
      const nativeVoices=voices();
      // Chromium WebView 52 in Fully can have no speech engine at all.
      // A self-contained WAV generated on Reception then works in every browser.
      if(Number(sampleEvent||0)>0||!!(cfg&&cfg.announce_surnames)||!('speechSynthesis' in window)||typeof window.SpeechSynthesisUtterance!=='function'||!nativeVoices.length){
        playReceptionVoice(n,isExamReview,fromCall,sampleEvent);return;
      }
      try{
        const synth=window.speechSynthesis;synth.cancel();
        const u=new SpeechSynthesisUtterance('Turno número '+n+', por favor pasar a consulta.');
        const v=configuredVoice(cfg);if(v){u.voice=v;u.lang=v.lang||'es-EC'}else u.lang='es-EC';
        const rate=Number(cfg&&cfg.rate);u.rate=Number.isFinite(rate)?Math.max(.6,Math.min(1.3,rate)):.9;
        const pitch=Number(cfg&&cfg.pitch);u.pitch=Number.isFinite(pitch)?Math.max(.7,Math.min(1.3,pitch)):1;
        u.volume=1;u.onerror=()=>playReceptionVoice(n,isExamReview,fromCall,sampleEvent);
        synth.speak(u);
      }catch(_){playReceptionVoice(n,isExamReview,fromCall,sampleEvent)}
    },Math.max(0,Number(delay||0)));
  }

  // Sustituye únicamente la fuente de voz. El evento de llamado/ding original no cambia.
  try{window.announceTurn=function(turn){let cfg=null;try{cfg=state&&state.voice}catch(_){ }speak(turn,cfg,650,true)}}catch(_){ }
  try{announceTurn=function(turn){let cfg=null;try{cfg=state&&state.voice}catch(_){ }speak(turn,cfg,650,true)}}catch(_){ }

  try{
    const originalRender=render;
    render=function(s){
      originalRender(s);
      const id=Number(s&&s.voice_test_id||0);
      if(lastVoiceTest===null){lastVoiceTest=id;return}
      if(id&&id!==lastVoiceTest){
        lastVoiceTest=id;
        // Fictitious surname tests always play the exact Reception-generated WAV,
        // even if announcing real patients' surnames is currently disabled.
        speak(Number(s.voice_test_turn||6),s.voice||null,0,false,s.voice_test_has_surnames?id:0);
      }
    };
  }catch(_){ }

  try{
    if('speechSynthesis' in window){
      if(typeof window.speechSynthesis.addEventListener==='function')window.speechSynthesis.addEventListener('voiceschanged',reportVoices);
      else window.speechSynthesis.onvoiceschanged=reportVoices;
    }
  }catch(_){ }
  setTimeout(reportVoices,250);setTimeout(reportVoices,1200);setTimeout(reportVoices,3000);setInterval(()=>{lastReport='';reportVoices()},10000);
})();
</script>
"""


CONTROL_VOICE_UI = r"""
<style id="tvVoiceControlStyle">
#voiceCard select{width:100%;background:#08151c;border:1px solid #365968;border-radius:11px;color:#fff;padding:11px;font-size:15px;font-weight:700}#voiceCard .voicegrid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;align-items:end}#voiceCard .voicestatus{margin-top:10px;padding:10px 12px;border-radius:10px;background:#0a1a22;border:1px solid #294b59;color:#a9bec8;font-size:12px}#voiceCard .voicestatus.ok{color:#79d7a4}@media(max-width:800px){#voiceCard .voicegrid{grid-template-columns:1fr}}
</style>
<script id="tvVoiceControlRuntime">
;(()=>{
 if(window.__tvVoiceControlRuntime)return;window.__tvVoiceControlRuntime=true;
 function el(id){return document.getElementById(id)}
 function request(url,opts){return fetch(url,Object.assign({cache:'no-store'},opts||{})).then(r=>r.json())}
 function pct(v){return Math.round(Number(v||0)*100)+'%'}
 function card(){
   const host=document.querySelector('.wrap')||document.body;if(el('voiceCard'))return;
   const c=document.createElement('div');c.className='card';c.id='voiceCard';
   c.innerHTML='<h2 style="margin-top:0">🗣️ Voz de llamado en el televisor</h2><p class="muted">Para Fully Kiosk se utiliza una voz instalada en Windows (Recepción); Chrome puede usar voces del navegador. Los cambios se guardan sin alterar los pacientes ni los turnos.</p><div class="voicegrid"><label>Voz del navegador (Chrome)<select id="voiceSelect"><option value="">Automática · mejor voz en español disponible</option></select></label><label>Velocidad <span id="voiceRateLabel">90%</span><input id="voiceRate" type="range" min="60" max="130" step="5" value="90"></label><label>Tono <span id="voicePitchLabel">100%</span><input id="voicePitch" type="range" min="70" max="130" step="5" value="100"></label></div><div class="buttons"><button class="primary" id="voiceSave">💾 Guardar voz</button><button class="green" id="voiceTest">🔊 Probar voz en TV</button><button id="voiceRefresh">↻ Actualizar voces</button></div><div class="voicestatus" id="voiceStatus">Esperando información del televisor…</div><div class="help">Puedes probar la voz con un número o con apellidos ficticios sin crear pacientes. En la TV se conserva el número visible: los apellidos solo se oyen. Esta prueba no cambia los turnos ni la configuración de privacidad de pacientes reales.</div>';
   host.appendChild(c);
   const fallbackLabel=document.createElement('label');
   fallbackLabel.innerHTML='<b>Voz de Windows (Fully Kiosk)</b><select id="windowsVoiceSelect"><option value="">Automática · voz disponible en Recepción</option></select>';
   const grid=c.querySelector('.voicegrid');
   if(grid)grid.insertBefore(fallbackLabel,grid.firstChild);
   const privacy=document.createElement('label');
   privacy.style.cssText='display:block;margin-top:12px;padding:12px;border:1px solid #b9cfe0;border-radius:10px';
   privacy.innerHTML='<input type="checkbox" id="voiceAnnounceSurnames"> <b>Anunciar únicamente dos apellidos por voz</b><div class="help">En la pantalla seguirá apareciendo solo el número. Se pronuncian las primeras dos palabras de «Apellidos y nombres» únicamente al llamar a un paciente real. Esta opción divulga apellidos de forma audible en la sala: utilízala solo conforme a las políticas y autorizaciones de privacidad del consultorio. Si no hay coincidencia segura, se anunciará solo el número.</div>';
   const buttons=c.querySelector('.buttons');
   if(buttons)c.insertBefore(privacy,buttons);
   const examples=document.createElement('div');
   examples.style.cssText='margin-top:12px;padding:12px;border:1px solid #b9cfe0;border-radius:10px';
   examples.innerHTML='<label><b>Prueba de apellidos ficticios (sin paciente)</b><select id="voiceSampleSelect"><option value="perez_garcia">Pérez García</option><option value="zambrano_velez">Zambrano Vélez</option><option value="lopez_mendoza">López Mendoza</option><option value="rodriguez_andrade">Rodríguez Andrade</option></select></label><div class="help">La TV dirá: “Turno número seis, [apellidos elegidos], por favor pasar a consulta”. Esta prueba usa la voz de Windows y no anuncia pacientes reales.</div><button type="button" class="green" id="voiceSampleTest" style="margin-top:10px">🗣️ Probar apellidos en TV</button>';
   if(buttons)c.insertBefore(examples,buttons);
   el('voiceRate').oninput=()=>el('voiceRateLabel').textContent=el('voiceRate').value+'%';
   el('voicePitch').oninput=()=>el('voicePitchLabel').textContent=el('voicePitch').value+'%';
   el('voiceRefresh').onclick=load;
   el('voiceSave').onclick=()=>save(false);
   el('voiceTest').onclick=()=>save('number');
   el('voiceSampleTest').onclick=()=>save('sample');
 }
 function render(d){
   card();const sel=el('voiceSelect'),current=String((d.config||{}).voice_uri||'');
   const all=Array.isArray(d.voices)?d.voices:[],spanish=all.filter(v=>String(v.lang||'').toLowerCase().startsWith('es')),list=spanish.length?spanish:all;
   sel.innerHTML='<option value="">Automática · mejor voz en español disponible</option>'+list.map(v=>'<option value="'+esc(v.voiceURI||v.name||'')+'">'+esc((v.name||'Voz')+' · '+(v.lang||'sin idioma')+(v.default?' · predeterminada':'')+(v.localService?' · local':''))+'</option>').join('');
   if(current&&Array.from(sel.options).some(o=>o.value===current))sel.value=current;else sel.value='';
   const windowsSelect=el('windowsVoiceSelect'),windowsItems=Array.isArray(d.windows_voices)?d.windows_voices:[],selected=String((d.config||{}).windows_voice_name||'');
   windowsSelect.innerHTML='<option value="">Automática · voz disponible en Recepción</option>'+windowsItems.map(v=>'<option value="'+esc(v.name||'')+'">'+esc((v.name||'Voz de Windows')+' · '+(v.lang||'sin idioma'))+'</option>').join('');
   if(selected&&Array.from(windowsSelect.options).some(o=>o.value===selected))windowsSelect.value=selected;else windowsSelect.value='';
   el('voiceAnnounceSurnames').checked=!!((d.config||{}).announce_surnames);
   el('voiceRate').value=Math.round(Number((d.config||{}).rate||.9)*100);el('voiceRateLabel').textContent=el('voiceRate').value+'%';
   el('voicePitch').value=Math.round(Number((d.config||{}).pitch||1)*100);el('voicePitchLabel').textContent=el('voicePitch').value+'%';
   const st=el('voiceStatus');
   if(!d.tv_voice_supported){st.className='voicestatus'+(windowsItems.length?' ok':'');st.textContent=windowsItems.length?'Fully Kiosk usa una voz de Windows en Recepción · '+windowsItems.length+' voz(es) detectada(s). Velocidad y tono ajustables.':'No se enumeraron voces de Windows. El sonido actual conserva la voz automática; si instalas otras voces en Windows, reinicia Recepción.'}
   else{st.className='voicestatus ok';st.textContent='TV detectada · '+all.length+' voz(es), '+spanish.length+' en español.'}
 }
 function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
 function load(){request('/api/voice-settings?t='+Date.now()).then(render).catch(()=>{card();el('voiceStatus').textContent='No se pudo leer la configuración de voz.'})}
 function save(test){
   const testing=!!test;
   const sample=test==='sample'?el('voiceSampleSelect').value:'';
   const selectedLabel=test==='sample'?el('voiceSampleSelect').options[el('voiceSampleSelect').selectedIndex].text:'';
   const payload={voice_uri:el('voiceSelect').value,windows_voice_name:el('windowsVoiceSelect').value,announce_surnames:el('voiceAnnounceSurnames').checked,rate:Number(el('voiceRate').value)/100,pitch:Number(el('voicePitch').value)/100};
   request('/api/voice/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(d=>{render(d);if(testing)return request('/api/voice/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({turn:6,sample:sample})})}).then(x=>{if(testing&&x&&x.ok){el('voiceStatus').className='voicestatus ok';el('voiceStatus').textContent=sample?'Prueba de apellidos ficticios enviada: “Turno número seis, '+selectedLabel+', por favor pasar a consulta.”':'Prueba enviada a la TV: “Turno número seis, por favor pasar a consulta.”'}}).catch(e=>alert(String(e)));
 }
 card();load();
})();
</script>
"""


def inject_display(html: bytes) -> bytes:
    return _inject_before_body(html, DISPLAY_VOICE_SCRIPT)


def inject_control(html: bytes) -> bytes:
    return _inject_before_body(html, CONTROL_VOICE_UI)
