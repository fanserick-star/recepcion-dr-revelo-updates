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
    const list=voices().slice(0,64).map(cleanVoice),payload={supported:('speechSynthesis' in window),voices:list};
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
  function speak(turn,cfg,delay){
    const n=parseInt(turn||0,10);if(!n||!('speechSynthesis' in window)||typeof window.SpeechSynthesisUtterance!=='function')return;
    clearTimeout(voiceTimer);
    voiceTimer=setTimeout(()=>{
      try{
        const synth=window.speechSynthesis;synth.cancel();
        const u=new SpeechSynthesisUtterance('Turno número '+n+', por favor pasar a consulta.');
        const v=configuredVoice(cfg);if(v){u.voice=v;u.lang=v.lang||'es-EC'}else u.lang='es-EC';
        const rate=Number(cfg&&cfg.rate);u.rate=Number.isFinite(rate)?Math.max(.6,Math.min(1.3,rate)):.9;
        const pitch=Number(cfg&&cfg.pitch);u.pitch=Number.isFinite(pitch)?Math.max(.7,Math.min(1.3,pitch)):1;
        u.volume=1;synth.speak(u);
      }catch(_){ }
    },Math.max(0,Number(delay||0)));
  }

  // Sustituye únicamente la fuente de voz. El evento de llamado/ding original no cambia.
  try{window.announceTurn=function(turn){let cfg=null;try{cfg=state&&state.voice}catch(_){ }speak(turn,cfg,650)}}catch(_){ }
  try{announceTurn=function(turn){let cfg=null;try{cfg=state&&state.voice}catch(_){ }speak(turn,cfg,650)}}catch(_){ }

  try{
    const originalRender=render;
    render=function(s){
      originalRender(s);
      const id=Number(s&&s.voice_test_id||0);
      if(lastVoiceTest===null){lastVoiceTest=id;return}
      if(id&&id!==lastVoiceTest){lastVoiceTest=id;speak(Number(s.voice_test_turn||6),s.voice||null,0)}
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
   c.innerHTML='<h2 style="margin-top:0">🗣️ Voz de llamado en el televisor</h2><p class="muted">Estas son las voces que realmente ofrece el navegador del televisor. La selección se guarda en Recepción y no modifica pacientes ni turnos.</p><div class="voicegrid"><label>Voz del televisor<select id="voiceSelect"><option value="">Automática · mejor voz en español disponible</option></select></label><label>Velocidad <span id="voiceRateLabel">90%</span><input id="voiceRate" type="range" min="60" max="130" step="5" value="90"></label><label>Tono <span id="voicePitchLabel">100%</span><input id="voicePitch" type="range" min="70" max="130" step="5" value="100"></label></div><div class="buttons"><button class="primary" id="voiceSave">💾 Guardar voz</button><button class="green" id="voiceTest">🔊 Probar voz en TV</button><button id="voiceRefresh">↻ Actualizar voces</button></div><div class="voicestatus" id="voiceStatus">Esperando información del televisor…</div><div class="help">La prueba usa el turno ficticio 6 y es independiente de EN VIVO / PRUEBAS. Si acabas de actualizar el programa, recarga una vez la página del televisor para que reporte sus voces.</div>';
   host.appendChild(c);
   el('voiceRate').oninput=()=>el('voiceRateLabel').textContent=el('voiceRate').value+'%';
   el('voicePitch').oninput=()=>el('voicePitchLabel').textContent=el('voicePitch').value+'%';
   el('voiceRefresh').onclick=load;
   el('voiceSave').onclick=()=>save(false);
   el('voiceTest').onclick=()=>save(true);
 }
 function render(d){
   card();const sel=el('voiceSelect'),current=String((d.config||{}).voice_uri||'');
   const all=Array.isArray(d.voices)?d.voices:[],spanish=all.filter(v=>String(v.lang||'').toLowerCase().startsWith('es')),list=spanish.length?spanish:all;
   sel.innerHTML='<option value="">Automática · mejor voz en español disponible</option>'+list.map(v=>'<option value="'+esc(v.voiceURI||v.name||'')+'">'+esc((v.name||'Voz')+' · '+(v.lang||'sin idioma')+(v.default?' · predeterminada':'')+(v.localService?' · local':''))+'</option>').join('');
   if(current&&Array.from(sel.options).some(o=>o.value===current))sel.value=current;else sel.value='';
   el('voiceRate').value=Math.round(Number((d.config||{}).rate||.9)*100);el('voiceRateLabel').textContent=el('voiceRate').value+'%';
   el('voicePitch').value=Math.round(Number((d.config||{}).pitch||1)*100);el('voicePitchLabel').textContent=el('voicePitch').value+'%';
   const st=el('voiceStatus');
   if(!d.tv_voice_supported){st.className='voicestatus';st.textContent=d.tv_voice_reported?'El televisor reporta que no dispone de síntesis de voz.':'La TV todavía no ha reportado sus voces. Recarga una vez su página y pulsa “Actualizar voces”.'}
   else{st.className='voicestatus ok';st.textContent='TV detectada · '+all.length+' voz(es), '+spanish.length+' en español.'}
 }
 function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
 function load(){request('/api/voice-settings?t='+Date.now()).then(render).catch(()=>{card();el('voiceStatus').textContent='No se pudo leer la configuración de voz.'})}
 function save(test){
   const payload={voice_uri:el('voiceSelect').value,rate:Number(el('voiceRate').value)/100,pitch:Number(el('voicePitch').value)/100};
   request('/api/voice/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(d=>{render(d);if(test)return request('/api/voice/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({turn:6})})}).then(x=>{if(test&&x){el('voiceStatus').className='voicestatus ok';el('voiceStatus').textContent='Prueba enviada a la TV: “Turno número seis, por favor pasar a consulta.”'}}).catch(e=>alert(String(e)));
 }
 card();load();
})();
</script>
"""


def inject_display(html: bytes) -> bytes:
    return _inject_before_body(html, DISPLAY_VOICE_SCRIPT)


def inject_control(html: bytes) -> bytes:
    return _inject_before_body(html, CONTROL_VOICE_UI)
