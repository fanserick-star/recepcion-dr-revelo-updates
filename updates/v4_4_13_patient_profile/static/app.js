const $ = s => document.querySelector(s);
let procedures = [];
let weeklyData = {};
let selectedHomeDate = null;
let currentHomeAnchor = null;
let attentionContext = null;
let selectedServices = new Set();
let attentionServiceValues = {};
let currentPatientSource = 'general';
let attentionDraft = null;
let lastAttentionSlipData = null;
let globalSearchTimer = null;
let globalSearchCache = [];
let lastProtectionData = null;
let appPreferences = {print_mode:'PREVIEW',printer:'',show_blood_pressure:true,confirm_delete:true,auto_login:true,paper_width_mm:80};
const QUICK_PROCEDURES = ['FULGURACION','CISTOSCOPIA','DILATACION','CIRCUNSICION','INSTILACION','LAVADO'];
const SERVICE_LABELS = {
  CONSULTA:'CONSULTA', FULGURACION:'FULGURACIÓN', CISTOSCOPIA:'CISTOSCOPIA',
  DILATACION:'DILATACIÓN', 'CISTO Y DILATACION':'CISTO Y DILATACIÓN', CIRCUNSICION:'CIRCUNCISIÓN', INSTILACION:'INSTILACIÓN', LAVADO:'LAVADO'
};

// v4.3.15 — Protección contra dobles clics accidentales.
// El segundo clic sobre el MISMO botón dentro de una ventana corta se ignora.
// Esto evita que la costumbre de hacer doble clic dispare dos acciones web.
const RAPID_CLICK_GUARD_MS=700;
document.addEventListener('click',event=>{
  const button=event.target?.closest?.('button');
  if(!button||button.dataset.allowRapidClicks==='true')return;
  const now=Date.now(),last=Number(button.dataset.lastAcceptedClick||0);
  if(last&&now-last<RAPID_CLICK_GUARD_MS){
    event.preventDefault();
    event.stopImmediatePropagation();
    return;
  }
  button.dataset.lastAcceptedClick=String(now);
},true);

let attentionSaveInFlight=false;
const mutationLocks=new Set();
async function singleFlightMutation(key,work,label='Guardando…'){
  const k=String(key||'mutation');
  if(mutationLocks.has(k))return null;
  mutationLocks.add(k);
  const btn=document.activeElement?.closest?.('button');
  const oldText=btn?.textContent||'';
  if(btn){btn.disabled=true;if(label)btn.textContent=label}
  try{return await work()}
  finally{
    mutationLocks.delete(k);
    if(btn&&btn.isConnected){btn.disabled=false;if(oldText)btn.textContent=oldText}
  }
}

const inflightGets=new Map();
let wakePromise=null;
let appIdleMode=false;
let mutationConnectivityTimer=null;
function scheduleMutationConnectivityRefresh(delay=700){
  if(mutationConnectivityTimer)clearTimeout(mutationConnectivityTimer);
  mutationConnectivityTimer=setTimeout(()=>{mutationConnectivityTimer=null;updateConnectivity(false)},delay);
}
async function api(url,opt={}){
  const method=String(opt.method||'GET').toUpperCase();
  if(wakePromise && !url.startsWith('/api/power/')){
    try{await Promise.race([wakePromise,new Promise(resolve=>setTimeout(resolve,3000))])}catch{}
  }
  // Si dos partes de la pantalla piden exactamente lo mismo al mismo tiempo,
  // compartimos una sola petición en vez de golpear Neon dos veces.
  if(method==='GET' && inflightGets.has(url))return inflightGets.get(url);
  const run=(async()=>{
    const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
    if(r.status===401){showLogin();throw Error('No autenticado')}
    let data; try{data=await r.json()}catch{data={}}
    if(!r.ok)throw Error(data.detail||`Error del servidor (${r.status}). Intenta nuevamente.`);
    if(method!=='GET' && !url.includes('/api/connectivity') && !url.includes('/api/offline/sync') && !url.includes('/api/power/') && !url.includes('/api/open-external/')){
      scheduleMutationConnectivityRefresh(700);
    }
    return data;
  })();
  if(method==='GET')inflightGets.set(url,run);
  try{return await run}finally{if(method==='GET')inflightGets.delete(url)}
}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function pad(n){return String(n).padStart(2,'0')}
function toISO(d){return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`}
function parseISO(v){const [y,m,d]=String(v).slice(0,10).split('-').map(Number);return new Date(y,m-1,d)}
function fmtDate(v){if(!v)return '';const [y,m,d]=String(v).slice(0,10).split('-');return d&&m&&y?`${d}/${m}/${y}`:esc(v)}
function fmtTime(v){const m=String(v||'').match(/^(\d{1,2}):(\d{2})/);if(!m)return esc(v);let h=Number(m[1]),min=m[2];const ap=h>=12?'p. m.':'a. m.';h=h%12||12;return `${h}:${min} ${ap}`}
function fmtTimeCompact(v){const m=String(v||'').match(/^(\d{1,2}):(\d{2})/);if(!m)return esc(v);let h=Number(m[1]),min=m[2];h=h%12||12;return `${h}:${min}`}
function fmtDateTime(v){if(!v)return 'Aún no disponible';const d=new Date(v);if(Number.isNaN(d.getTime()))return esc(v);return `${pad(d.getDate())}/${pad(d.getMonth()+1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`}
function money(v){return v==null?'':`$${Number(v).toFixed(2)}`}
function digitsOnlyInput(el){
  el.value=String(el.value||'').replace(/[^0-9]/g,'');
}
function formatPhoneValue(value){
  const d=String(value||'').replace(/[^0-9]/g,'').slice(0,10);
  if(!d)return '';
  if(d.length<=3)return d;
  if(d.length<=6)return `${d.slice(0,3)} ${d.slice(3)}`;
  return `${d.slice(0,3)} ${d.slice(3,6)} ${d.slice(6)}`;
}
function formatPhoneInput(el){
  el.value=formatPhoneValue(el.value);
}
function lowerEmailInput(el){
  el.value=String(el.value||'').toLowerCase();
}
function upperNameInput(el){
  el.value=String(el.value||'').toUpperCase();
}
function upperSearchInput(el){
  const start=el.selectionStart,end=el.selectionEnd;
  el.value=String(el.value||'').toUpperCase();
  try{if(start!=null)el.setSelectionRange(start,end)}catch{}
}
function isForeignIdentificationValue(value){
  const raw=String(value||'').trim();
  return !!raw && !/^\d{10}$/.test(raw);
}
function validEcuadorianCedula(value){
  const d=String(value||'').replace(/\D/g,'');
  if(d.length!==10||Number(d[2])>5)return false;
  let total=0;
  for(let i=0;i<9;i++){
    let n=Number(d[i])*(i%2===0?2:1);if(n>=10)n-=9;total+=n;
  }
  return ((10-(total%10))%10)===Number(d[9]);
}
function clearPatientFieldError(id){
  const el=$('#'+id);el?.classList.remove('field-invalid');
  const msg=$('#'+id+'Error');if(msg){msg.textContent='';msg.classList.add('hidden')}
}
function setPatientFieldError(id,message){
  const el=$('#'+id);el?.classList.add('field-invalid');
  const msg=$('#'+id+'Error');if(msg){msg.textContent=message;msg.classList.remove('hidden')}
  el?.focus();
}
function identificationInput(el){
  const foreign=!!$('#fForeign')?.checked;
  if(foreign)el.value=String(el.value||'').toUpperCase().replace(/\s+/g,'').slice(0,30);
  else el.value=String(el.value||'').replace(/\D/g,'').slice(0,10);
  clearPatientFieldError('fCedula');
}
function toggleForeignIdentification(){
  const input=$('#fCedula'),foreign=!!$('#fForeign')?.checked,help=$('#fCedulaHelp');if(!input)return;
  input.maxLength=foreign?30:10;
  input.inputMode=foreign?'text':'numeric';
  input.placeholder=foreign?'Pasaporte o identificación':'Ingrese 10 dígitos';
  if(!foreign)input.value=String(input.value||'').replace(/\D/g,'').slice(0,10);
  else input.value=String(input.value||'').toUpperCase().replace(/\s+/g,'').slice(0,30);
  if(help)help.textContent=foreign?'Se permite otro formato de identificación.':'Cédula ecuatoriana: exactamente 10 dígitos.';
  clearPatientFieldError('fCedula');input.focus();
}
function completeEmailDomain(domain){
  const input=$('#fMail');if(!input)return;
  const current=String(input.value||'').trim().toLowerCase();
  const local=(current.includes('@')?current.split('@')[0]:current).trim();
  if(!local){input.focus();return}
  input.value=local+String(domain||'').toLowerCase();
  clearPatientFieldError('fMail');input.focus();
  try{input.setSelectionRange(input.value.length,input.value.length)}catch{}
}
function confirmDeletion(message){return appPreferences.confirm_delete===false?true:confirm(message)}

let connectivityTimer=null;
let connectivityBusy=false;
let lastConnectivityState='';
let lastBadgeRefreshAt=0;
let idleTimer=null;
let idleListenersStarted=false;
let lastLocalActivityNote=0;
const BADGE_REFRESH_MS=120000;
const IDLE_AFTER_MS=5*60*1000;
const PASSIVE_CONNECTIVITY_MS=600000;
function setConnectionBadge(kind,text,detail=''){
  const badge=$('#connectionBadge');if(!badge)return;
  badge.className=`connection-badge sidebar-status ${kind}`;
  badge.innerHTML=`<span class="connection-dot"></span><span class="connection-label">${esc(text)}</span>`;
  badge.title=detail?`${text} · ${detail}`:text;
}
function openProtectionStatus(){
  show('config','sistema');
  setTimeout(()=>document.querySelector('#protectionPanel')?.scrollIntoView({behavior:'smooth',block:'start'}),80);
}
const EXTERNAL_APP_URLS={
  confirmafy:'https://confirmafy.com/app/calendar',
  facturero:'https://app.factureromovil.com/documentos/facturas'
};
async function openExternalApp(target){
  const key=String(target||'').toLowerCase(),fallback=EXTERNAL_APP_URLS[key];
  if(!fallback)return;
  try{
    await api('/api/open-external/'+encodeURIComponent(key),{method:'POST'});
  }catch{
    window.open(fallback,'_blank','noopener');
  }
}
function stopConnectivityMonitor(){
  if(connectivityTimer){clearInterval(connectivityTimer);connectivityTimer=null}
}
function scheduleIdleCountdown(){
  if(idleTimer)clearTimeout(idleTimer);
  if(appIdleMode)return;
  idleTimer=setTimeout(()=>enterIdleMode(),IDLE_AFTER_MS);
}
async function enterIdleMode(){
  if(appIdleMode || $('#app')?.classList.contains('hidden'))return;
  appIdleMode=true;
  stopConnectivityMonitor();
  setConnectionBadge('idle','En espera','Ahorro de nube activo · Neon no se consulta mientras no uses Recepción');
  try{
    const r=await fetch('/api/power/idle',{method:'POST',headers:{'Content-Type':'application/json'}});
    if(r.ok){const d=await r.json();lastProtectionData=d;renderProtectionStatus(d)}
  }catch{}
}
async function refreshVisibleSectionLocal(){
  const active=document.querySelector('main section:not(.hidden)')?.id||'inicio';
  try{
    if(active==='inicio')await loadWeek(currentHomeAnchor||selectedHomeDate||toISO(new Date()),selectedHomeDate);
    else if(active==='pacientes')await searchPatients();
    else if(active==='agenda')await loadAgenda();
    else if(active==='facturacion')await loadBilling();
    else if(active==='reportes')await loadReport();
  }catch{}
}

async function wakeFromIdle(){
  if(wakePromise)return wakePromise;
  if(!appIdleMode){scheduleIdleCountdown();return null}
  appIdleMode=false;
  scheduleIdleCountdown();
  setConnectionBadge('syncing','Reanudando','Comprobando la nube solo porque volviste a usar Recepción…');
  wakePromise=(async()=>{
    try{
      const r=await fetch('/api/power/wake',{method:'POST',headers:{'Content-Type':'application/json'}});
      const d=await r.json().catch(()=>({configured:false,online:false,pending:0}));
      if(r.ok){
        lastProtectionData=d;renderProtectionStatus(d);
        if(d.pending>0)setConnectionBadge('warning','Sincronización pendiente',`${d.pending} cambio${d.pending===1?'':'s'} por revisar`);
        else if(d.online)setConnectionBadge('online','En línea','Datos protegidos en la nube');
        else if(d.configured)setConnectionBadge('offline','Sin Internet','Trabajando con la copia de emergencia');
        else setConnectionBadge('local','Modo local','La nube todavía no está configurada');
        if(d.cache_refresh_scheduled){
          setTimeout(()=>refreshVisibleSectionLocal(),2800);
          setTimeout(()=>refreshVisibleSectionLocal(),7500);
        }
      }
      return d;
    }catch{
      setConnectionBadge('offline','Sin conexión','La copia local sigue disponible');
      return null;
    }finally{
      wakePromise=null;
      startConnectivityMonitor(false);
    }
  })();
  return wakePromise;
}
function noteUserActivity(){
  const now=Date.now();
  if(!appIdleMode && now-lastLocalActivityNote<12000)return;
  lastLocalActivityNote=now;
  if(appIdleMode)wakeFromIdle();
  else scheduleIdleCountdown();
}
function startIdleMonitor(){
  scheduleIdleCountdown();
  if(idleListenersStarted)return;
  idleListenersStarted=true;
  ['pointerdown','keydown','wheel','touchstart'].forEach(name=>{
    window.addEventListener(name,noteUserActivity,{capture:true,passive:true});
  });
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden){
      noteUserActivity();
      const d=lastProtectionData||{};
      if(!appIdleMode && d.configured && !d.online && navigator.onLine!==false){
        setTimeout(()=>updateConnectivity(true),350);
      }
    }
  });
}
async function runPendingSync(){
  if(appIdleMode)return null;
  const modalOpen=!$('#modal')?.classList.contains('hidden');
  if(modalOpen)return null;
  try{
    setConnectionBadge('syncing','Sincronizando','Guardando cambios pendientes en la nube…');
    const r=await fetch('/api/offline/sync',{method:'POST',headers:{'Content-Type':'application/json'}});
    if(r.status===401)return null;
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(data.detail||'No se pudo sincronizar');
    if(data.pending===0){
      setConnectionBadge('online','En línea',data.processed?`${data.processed} cambio${data.processed===1?'':'s'} sincronizado${data.processed===1?'':'s'}`:'Todo sincronizado');
      setTimeout(()=>updateConnectivity(false),1800);refreshPendingBadges();
    }else{
      setConnectionBadge('warning','Sincronización pendiente',`${data.pending} cambio${data.pending===1?'':'s'} por revisar`);
    }
    return data;
  }catch(e){
    setConnectionBadge('warning','Sincronización pendiente',e.message||'Reintentaremos cuando vuelvas a usar la aplicación');
    return null;
  }
}
async function updateConnectivity(force=false){
  if(appIdleMode && !force){
    setConnectionBadge('idle','En espera','Ahorro de nube activo · Neon no se consulta mientras no uses Recepción');
    return;
  }
  if(connectivityBusy)return;
  connectivityBusy=true;
  try{
    const r=await fetch('/api/connectivity'+(force?'?force=true':'?lite=true'),{cache:'no-store'});
    const d=await r.json().catch(()=>({configured:false,online:false,pending:0}));
    lastProtectionData={...(lastProtectionData||{}),...d};if(force||Object.prototype.hasOwnProperty.call(d,'last_sync'))renderProtectionStatus(lastProtectionData);
    if(!d.idle)appIdleMode=false;
    const state=`${d.configured}-${d.online}-${d.idle}-${d.pending}-${(d.errors||[]).length}`;
    if(d.idle){
      appIdleMode=true;
      stopConnectivityMonitor();
      setConnectionBadge('idle','En espera','Ahorro de nube activo · Neon puede suspenderse mientras no trabajas');
    }else if(!d.configured){
      setConnectionBadge('local','Modo local','La nube todavía no está configurada');
    }else if(!d.online){
      const lastOk=d.last_success?new Date(d.last_success).getTime():0;
      const recentOk=lastOk && (Date.now()-lastOk<90000);
      const detail=d.pending?`${d.pending} cambio${d.pending===1?'':'s'} guardado${d.pending===1?'':'s'} en esta PC`:(recentOk?'Neon tardó en responder; usando la copia de emergencia':'Trabajando con la copia de emergencia');
      setConnectionBadge(recentOk?'warning':'offline',recentOk?'Conexión inestable':'Sin Internet',detail);
    }else if(d.pending>0){
      const modalOpen=!$('#modal')?.classList.contains('hidden');
      if(modalOpen){
        setConnectionBadge('warning','Internet restablecido',`${d.pending} cambio${d.pending===1?'':'s'} pendiente${d.pending===1?'':'s'} · se sincronizará cuando cierres esta ventana`);
      }else{
        connectivityBusy=false;
        await runPendingSync();
        return;
      }
    }else{
      setConnectionBadge('online','En línea','Datos protegidos en la nube');
      const now=Date.now();
      if(force || now-lastBadgeRefreshAt>BADGE_REFRESH_MS){
        lastBadgeRefreshAt=now;
        refreshPendingBadges();
      }
    }
    lastConnectivityState=state;
  }catch(e){
    setConnectionBadge('offline','Sin conexión','El programa seguirá usando la copia local');
  }finally{connectivityBusy=false}
}
let startupConnectivityRetryTimer=null;
let startupConnectivityStarted=false;
async function autoRecoverConnectivityOnBoot(isRetry=false){
  if(navigator.onLine===false){
    await updateConnectivity(false);
    return false;
  }
  if(startupConnectivityStarted && !isRetry)return false;
  startupConnectivityStarted=true;
  if(!isRetry)setConnectionBadge('syncing','Conectando','Comprobando automáticamente la conexión con Neon…');

  // El backend ya hace una única comprobación de Neon al arrancar. Primero
  // leemos ese estado LOCAL para no abrir una segunda conexión innecesaria.
  await updateConnectivity(false);
  let d=lastProtectionData||{};
  if(d.online){
    if(startupConnectivityRetryTimer){clearTimeout(startupConnectivityRetryTimer);startupConnectivityRetryTimer=null}
    return true;
  }

  if(!isRetry && d.configured!==false && navigator.onLine!==false){
    // Damos tiempo a que termine la comprobación iniciada por el servidor. Esta
    // espera no toca Neon; solo después, si sigue sin estado, hacemos un rescate.
    startupConnectivityRetryTimer=setTimeout(()=>autoRecoverConnectivityOnBoot(true),1800);
    return false;
  }

  await updateConnectivity(true);
  d=lastProtectionData||{};
  return !!d.online;
}

function startConnectivityMonitor(refresh=true){
  stopConnectivityMonitor();
  if(appIdleMode)return;
  if(refresh)updateConnectivity(false);
  // Este temporizador solo consulta el estado LOCAL del servidor. No ejecuta
  // SELECT 1 ni despierta Neon.
  connectivityTimer=setInterval(()=>updateConnectivity(false),PASSIVE_CONNECTIVITY_MS);
  if(!startConnectivityMonitor.bound){
    startConnectivityMonitor.bound=true;
    window.addEventListener('online',()=>{if(!appIdleMode)updateConnectivity(true)});
    window.addEventListener('offline',()=>{if(!appIdleMode)updateConnectivity(false)});
  }
}

async function login(){
  try{await api('/api/login',{method:'POST',body:JSON.stringify({username:$('#lu').value,password:$('#lp').value})});$('#login').classList.add('hidden');$('#app').classList.remove('hidden');await init()}
  catch(e){$('#loginErr').textContent=e.message}
}
async function logout(){await api('/api/logout',{method:'POST'});location.reload()}
function showLogin(){$('#login').classList.remove('hidden');$('#app').classList.add('hidden')}
let billingPendingValue=0;
let billingPendingApprovalValue=0;
let billingApprovedValue=0;
let agendaPendingValue=0;

function openBillingReminder(state){
  show('facturacion');
  setBillingStatus(state);
}
function renderHomePendingStrip(){
  const box=$('#homePendingStrip');if(!box)return;
  const pending=Number(billingPendingApprovalValue||0),approved=Number(billingApprovedValue||0);
  if(!pending&&!approved){box.classList.add('hidden');box.innerHTML='';return}
  const items=[];
  if(pending)items.push(`<button class="home-reminder-card pending" onclick="openBillingReminder('PENDIENTE')"><span class="home-reminder-icon">✓</span><div><small>FACTURACIÓN</small><b>${pending} ${pending===1?'factura necesita':'facturas necesitan'} aprobación</b><em>Revisar y aprobar</em></div><span class="home-reminder-arrow">›</span></button>`);
  if(approved)items.push(`<button class="home-reminder-card approved" onclick="openBillingReminder('APROBADA')"><span class="home-reminder-icon">⚡</span><div><small>LISTAS PARA AZUR</small><b>${approved} ${approved===1?'factura está':'facturas están'} lista${approved===1?'':'s'} para emitir</b><em>Emitir comprobante electrónico</em></div><span class="home-reminder-arrow">›</span></button>`);
  box.innerHTML=items.join('');box.classList.remove('hidden');
}

function setBillingPendingSummary(summary){
  const d=(summary&&typeof summary==='object')?summary:{billing:Number(summary||0)};
  billingPendingApprovalValue=Number(d.billing_pending??d.PENDIENTE??billingPendingApprovalValue??0);
  billingApprovedValue=Number(d.billing_approved??d.APROBADA??billingApprovedValue??0);
  billingPendingValue=Number((d.billing ?? (billingPendingApprovalValue+billingApprovedValue)) || 0);
  const badge=$('#billingNavBadge');
  if(badge){
    badge.textContent=String(billingPendingValue);
    badge.classList.toggle('hidden',billingPendingValue<=0);
    badge.title=`${billingPendingApprovalValue} por aprobar · ${billingApprovedValue} por emitir`;
  }
  const nav=document.querySelector('.billing-nav-btn');if(nav)nav.title=billingPendingValue?`Facturación · ${billingPendingApprovalValue} por aprobar · ${billingApprovedValue} por emitir`:'Facturación al día';
  renderHomePendingStrip();
}
function setBillingPendingBadge(n){
  billingPendingValue=Number(n||0);
  const badge=$('#billingNavBadge');if(badge){badge.textContent=String(billingPendingValue);badge.classList.toggle('hidden',billingPendingValue<=0)}
  renderHomePendingStrip();
}
async function refreshPendingBadges(){
  try{
    const d=await api('/api/pending-summary');
    setBillingPendingSummary(d);
    setAgendaPendingBadge(d.agenda);
    lastBadgeRefreshAt=Date.now();
    return d;
  }catch{
    return null;
  }
}
async function refreshBillingPendingBadge(){return refreshPendingBadges()}
function setAgendaPendingBadge(n){
  agendaPendingValue=Number(n||0);
}
async function refreshAgendaPendingBadge(){return refreshPendingBadges()}
function show(id,configTab=null){
  document.querySelectorAll('main section').forEach(x=>x.classList.add('hidden'));
  $('#'+id).classList.remove('hidden');
  document.querySelectorAll('.nav-btn[data-section]').forEach(x=>x.classList.toggle('active',x.dataset.section===id));
  const gs=$('#globalSearch');if(gs)gs.placeholder='Buscar paciente por nombre, cédula, celular o correo…';
  closeGlobalSearchResults();
  if(id==='inicio')loadDashboard();
  if(id==='pacientes')resetPatientsView();
  if(id==='agenda')loadAgenda();
  if(id==='facturacion')loadBilling();
  if(id==='reportes')loadReport();
  if(id==='config')showConfigTab(configTab||'general');
}
async function init(){
  const d=new Date(), iso=toISO(d);
  currentHomeAnchor=iso;
  $('#rDesde').value=`${d.getFullYear()}-${pad(d.getMonth()+1)}-01`;
  $('#rHasta').value=iso;
  // Una sola petición trae Inicio + procedimientos + pendientes. Esto evita varios
  // checkouts/pings a Neon justo al abrir el programa.
  let bootCacheStale=false;
  try{
    const boot=await api('/api/bootstrap?anchor='+encodeURIComponent(iso));
    bootCacheStale=!!boot.cache_stale;
    procedures=boot.procedures||[];
    applyWeekPayload(iso,boot.home||{},null);
    setBillingPendingSummary(boot.pending||{});
    setAgendaPendingBadge(boot.pending?.agenda||0);
    lastBadgeRefreshAt=Date.now();
  }catch{
    await Promise.all([loadWeek(iso),loadProcedures(),refreshPendingBadges()]);
  }
  await loadPreferences(false);
  startConnectivityMonitor(false);
  startIdleMonitor();
  loadDashboard();
  // Al abrir Recepción hacemos una sola comprobación real. Antes el indicador
  // podía quedarse en “Sin Internet” porque solo leía el estado local inicial.
  setTimeout(()=>autoRecoverConnectivityOnBoot(false),180);
  // v4.1: no hacemos un segundo viaje forzado a Neon al abrir. El servidor
  // refresca la copia local en segundo plano solo si realmente está vencida.
  // Esta segunda lectura es únicamente SQLite y recoge esa copia si ya terminó.
  if(bootCacheStale){
    setTimeout(async()=>{
      if(appIdleMode)return;
      try{
        const local=await api('/api/bootstrap?anchor='+encodeURIComponent(iso));
        procedures=local.procedures||procedures;
        applyWeekPayload(iso,local.home||{},selectedHomeDate);
        setBillingPendingSummary(local.pending||{});
        setAgendaPendingBadge(local.pending?.agenda||0);
        updateConnectivity(false);
      }catch{}
    },4200);
  }
}

function loadDashboard(){
  // v3.9: Inicio deja de usar un dashboard grande. Solo conserva pendientes operativos.
  renderHomePendingStrip();
}
async function goHomeToday(){
  const iso=toISO(new Date());
  currentHomeAnchor=iso;
  show('inicio');
  await loadWeek(iso,weeklyData[iso]?iso:null);
}
function shiftHomeWeek(delta){
  const anchor=parseISO(currentHomeAnchor||toISO(new Date()));
  anchor.setDate(anchor.getDate()+(delta*7));
  const iso=toISO(anchor);
  currentHomeAnchor=iso;
  show('inicio');
  return loadWeek(iso);
}
function homeThisWeek(){
  return goHomeToday();
}
function closeGlobalSearchResults(){const box=$('#globalSearchResults');if(box)box.classList.add('hidden')}
function clearGlobalSearch(){const input=$('#globalSearch');if(input)input.value='';const clear=$('#globalSearchClear');if(clear)clear.classList.add('hidden');closeGlobalSearchResults()}
function isHistoricalPatient(p={}){return !!p.historical&&p.historical_id!=null}
function historicalYears(p={}){const a=Number(p.historical_first_year||p.historical?.first_year||2020),b=Number(p.historical_last_year||p.historical?.last_year||2025);return a===b?String(a):`${a}–${b}`}
function historicalLastDate(p={}){return p.historical_last_visit_date||p.historical?.last_visit_date||null}
function historicalLastLabel(p={}){const d=historicalLastDate(p);return d?`Última atención histórica con fecha disponible: ${fmtDate(d)}`:`Paciente registrado en el histórico ${historicalYears(p)}`}
async function activateHistoricalPatient(hid,action='attention'){
  try{
    const p=await api(`/api/historical/${Number(hid)}/activate`,{method:'POST'});
    closeGlobalSearchResults();
    if(action==='open')return openPatient(p.id,'patients');
    if(action==='agenda')return openAgendaPatient(p.id);
    return attentionFor(p.id);
  }catch(e){alert(e.message)}
}
function globalSearchResultHtml(p){
  if(isHistoricalPatient(p)){
    const years=historicalYears(p);
    return `<article class="global-result historical-result"><div class="global-result-main"><div><b>${esc(p.nombre)}</b><span class="historical-badge">HISTÓRICO ${esc(years)}</span></div><span>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</span><small>${esc(historicalLastLabel(p))} · se activará solo si lo eliges</small></div><div class="global-result-actions"><button onclick="activateHistoricalPatient(${p.historical_id},'open')">Ver</button><button class="primary-soft" onclick="activateHistoricalPatient(${p.historical_id},'attention')">Atender</button><button class="primary" onclick="activateHistoricalPatient(${p.historical_id},'agenda')">Reagendar</button></div></article>`;
  }
  const last=p.ultima_atencion?`Última atención ${fmtDate(p.ultima_atencion)}`:'Sin atención registrada';
  return `<article class="global-result"><div class="global-result-main"><b>${esc(p.nombre)}</b><span>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</span><small>${esc(last)}</small></div><div class="global-result-actions"><button onclick="openPatient(${p.id},'general');closeGlobalSearchResults()">Ver</button><button class="primary-soft" onclick="attentionFor(${p.id});closeGlobalSearchResults()">Atender</button><button class="primary" onclick="openAgendaPatient(${p.id});closeGlobalSearchResults()">Reagendar</button></div></article>`;
}
async function globalSearchPatients(force=false){
  const input=$('#globalSearch'),box=$('#globalSearchResults'),clear=$('#globalSearchClear');if(!input||!box)return;
  const q=(input.value||'').trim();clear?.classList.toggle('hidden',!q);clearTimeout(globalSearchTimer);
  if(q.length<2){if(force&&globalSearchCache.length){box.innerHTML=globalSearchCache.map(globalSearchResultHtml).join('');box.classList.remove('hidden')}else closeGlobalSearchResults();return}
  globalSearchTimer=setTimeout(async()=>{
    try{const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=8');globalSearchCache=rows;cacheAgendaPatients(rows);box.innerHTML=rows.map(globalSearchResultHtml).join('')||'<div class="global-search-empty">Sin resultados</div>';box.classList.remove('hidden')}catch{closeGlobalSearchResults()}
  },140);
}

document.addEventListener('click',e=>{const wrap=e.target.closest?.('.global-search-wrap');if(!wrap)closeGlobalSearchResults()});

function nextClinicDate(anchorValue=null){
  // Próximo día de consultorio: jueves, viernes o sábado.
  // Si hoy ya es uno de esos días, usamos hoy para que Reagendar pueda
  // mostrar los horarios disponibles de la jornada actual.
  const start=anchorValue?parseISO(anchorValue):new Date();
  const base=new Date(start.getFullYear(),start.getMonth(),start.getDate());
  for(let offset=0;offset<=7;offset++){
    const d=new Date(base.getFullYear(),base.getMonth(),base.getDate()+offset);
    if([4,5,6].includes(d.getDay()))return toISO(d);
  }
  return toISO(base);
}
function weekDays(anchorValue){
  const anchor=anchorValue?parseISO(anchorValue):new Date();
  const day=anchor.getDay();
  const monday=new Date(anchor.getFullYear(),anchor.getMonth(),anchor.getDate()-((day+6)%7));
  return [
    {label:'Jueves',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+3)},
    {label:'Viernes',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+4)},
    {label:'Sábado',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+5)},
  ].map(x=>({...x,iso:toISO(x.date)}));
}
function defaultWeekSelection(days,anchorValue){
  const anchor=anchorValue?parseISO(anchorValue):new Date();
  const iso=toISO(anchor);
  if(days.some(x=>x.iso===iso))return iso;
  const dow=anchor.getDay();
  if(dow===0)return days[2].iso;
  if(dow<=3)return days[0].iso;
  return days[2].iso;
}
function renderHomeWeekNav(days){
  const box=$('#homeWeekNav');
  if(!box)return;
  const first=days?.[0]?.iso?fmtDate(days[0].iso):'';
  const last=days?.[2]?.iso?fmtDate(days[2].iso):'';
  box.innerHTML=`<button class="tiny-week-btn" onclick="shiftHomeWeek(-1)" title="Semana anterior">←</button><span class="tiny-week-label">${first&&last?`Semana ${first} · ${last}`:'Semana'}</span><button class="tiny-week-btn" onclick="homeThisWeek()" title="Volver a esta semana">Hoy</button><button class="tiny-week-btn" onclick="shiftHomeWeek(1)" title="Semana siguiente">→</button>`;
}
function applyWeekPayload(anchor,payload,preferredDate=null){
  currentHomeAnchor=anchor||currentHomeAnchor||toISO(new Date());
  const days=weekDays(anchor);
  weeklyData={};
  for(const row of (payload?.days||[])){
    const iso=String(row.date||'').slice(0,10);
    const base=days.find(x=>x.iso===iso)||{label:row.label,date:parseISO(iso),iso};
    weeklyData[iso]={...base,...(row.data||{})};
  }
  const preferred=preferredDate&&weeklyData[preferredDate]?preferredDate:null;
  selectedHomeDate=preferred||defaultWeekSelection(days,anchor);
  renderHomeWeekNav(days);
  renderWeekCards(days);
  renderHomeDayFromCache(selectedHomeDate);
}
async function loadWeek(anchorValue=null,preferredDate=null){
  const anchor=anchorValue||toISO(new Date());
  const payload=await api(`/api/home/week?anchor=${encodeURIComponent(anchor)}`);
  applyWeekPayload(anchor,payload,preferredDate);
}
function renderWeekCards(days){
  const totalPatients=days.reduce((s,d)=>s+(weeklyData[d.iso]?.count||0),0);
  const totalMoney=days.reduce((s,d)=>s+Number(weeklyData[d.iso]?.total||0),0);
  $('#weekCards').innerHTML=days.map(d=>{
    const info=weeklyData[d.iso]||{count:0,total:0};
    return `<button class="week-card ${selectedHomeDate===d.iso?'active':''}" data-date="${d.iso}" onclick="selectHomeDay('${d.iso}')"><span class="week-day">${d.label}</span><span class="week-date">${fmtDate(d.iso)}</span><strong>${info.count}</strong><span class="week-patients">${info.count===1?'paciente':'pacientes'}</span><span class="week-money"><span class="week-money-chip">💵 ${money(info.total||0)}</span></span></button>`;
  }).join('');
  $('#weekSummary').innerHTML=`<span>Total de la semana</span><strong>${totalPatients} ${totalPatients===1?'paciente':'pacientes'}</strong><b>${money(totalMoney)}</b>`;
}
function renderHomeDayPayload(iso,d){
  if(!d)return;
  const label=d.label||weeklyData[iso]?.label||(['4','5','6'].includes(String(parseISO(iso).getDay()))?['','','','','Jueves','Viernes','Sábado'][parseISO(iso).getDay()]:'Día');
  const count=Number(d.count||0);
  $('#selectedDayTitle').innerHTML=`<div><h2>${esc(label)} ${fmtDate(iso)}</h2><span>${count} ${count===1?'paciente':'pacientes'}</span></div>`;
  try{
    $('#todayTable').innerHTML=table(d.visits||[],{home:true});
  }catch(err){
    console.error('Error dibujando el día '+iso,err);
    $('#todayTable').innerHTML='<div class="panel home-render-error">No se pudo dibujar este día. Reinicia Recepción o instala la actualización más reciente.</div>';
  }
  const tableBox=$('#todayTable');
  if(tableBox){tableBox.scrollLeft=0;tableBox.scrollTop=0;}
}
function renderHomeDayFromCache(iso){
  selectedHomeDate=iso;
  document.querySelectorAll('.week-card').forEach(x=>x.classList.toggle('active',x.dataset.date===iso));
  const d=weeklyData[iso];
  if(d)renderHomeDayPayload(iso,d);
}
function selectHomeDay(iso){
  renderHomeDayFromCache(iso);
}

function missingPatientFields(p={}){
  const fields=[];
  if(!String(p.cedula||'').trim())fields.push('cédula');
  if(!String(p.celular||'').trim())fields.push('celular');
  if(!String(p.correo||'').trim())fields.push('correo');
  return fields;
}
function dataWarning(p={},compact=false){
  const missing=missingPatientFields(p);if(!missing.length)return '';
  const text=`Faltan datos: ${missing.join(', ')}`;
  return compact?`<span class="data-warning compact" title="${esc(text)}">⚠</span>`:`<div class="data-warning"><span class="warning-icon">⚠</span><span>${esc(text)}</span></div>`;
}
function patientIdentityHtml(p={},compact=false){
  const cedula=String(p.cedula||'').trim();
  const celular=String(p.celular||'').trim();
  const phone=celular?formatPhoneValue(celular):'Sin celular';
  const c=cedula?esc(cedula):'Sin cédula';
  if(compact)return `<div class="patient-identity compact"><span><b>Cédula:</b> ${c}</span><span><b>Celular:</b> ${esc(phone)}</span></div>`;
  return `<div class="patient-identity"><span class="patient-id-chip ${cedula?'':'missing'}"><span class="detail-icon">▣</span><span><small>Cédula</small><b>${c}</b></span></span><span class="patient-id-chip ${celular?'':'missing'}"><span class="detail-icon">☎</span><span><small>Celular</small><b>${esc(phone)}</b></span></span></div>`;
}
function completePatientButton(p={},source='patients'){
  const missing=missingPatientFields(p);
  if(!missing.length)return '';
  return `<button class="complete-patient-list-btn" onclick="editPatient(${p.id},'${source}')"><span class="edit-mini-icon">✎</span> Completar datos</button>`;
}
function patientQuickField(label,value,missing=false){
  return `<div class="patient-quick-item ${missing?'missing':''}"><span>${esc(label)}</span><b>${esc(value||'')}</b></div>`;
}
function patientCardDetails(p={}){
  const birth=p.fecha_nacimiento?fmtDate(p.fecha_nacimiento):'Sin fecha';
  const last=isHistoricalPatient(p)?`Histórico ${historicalYears(p)}`:(p.ultima_atencion?fmtDate(p.ultima_atencion):'Sin atenciones');
  const phone=formatPhoneValue(p.celular||'')||'Sin celular';
  const cards=[
    patientQuickField('Cédula',p.cedula||'Sin cédula',!p.cedula),
    patientQuickField('Celular',phone,!p.celular),
    patientQuickField('Correo',p.correo||'Sin correo',!p.correo),
    patientQuickField('Lugar',p.lugar||'Sin lugar',!p.lugar),
    patientQuickField('Nacimiento',birth,!p.fecha_nacimiento),
    patientQuickField('Última atención',last,!p.ultima_atencion),
  ];
  return `<div class="patient-quick-grid">${cards.join('')}</div>`;
}
function patientNameCell(r,home=false,isNewOverride=null){
  const p=r.patient||{};
  const isNew=isNewOverride===null?r.tipo==='N':!!isNewOverride;
  const n=isNew?'<span class="new-patient-badge" title="Paciente nuevo">NUEVO</span>':'';
  return `<div class="patient-name-line"><button type="button" class="patient-name-button" onclick="openPatient(${p.id},'home')">${esc(p.nombre||'')}</button>${home?n:''}${home?'':dataWarning(p,true)}</div>`;
}
function statusLabel(tipo){return tipo==='N'?'Nuevo':tipo==='S'?'Subsecuente':tipo==='P'?'Procedimiento (registro anterior)':tipo||''}
function serviceKey(name){return String(name||'').trim().toUpperCase()}
function serviceLabel(name){const key=serviceKey(name);return SERVICE_LABELS[key]||key}
function serviceTone(name){
  const key=serviceKey(name);
  if(!key||key==='CONSULTA')return 'consultation';
  if(key.includes('CISTOSCOP'))return 'cistoscopy';
  if(key.includes('FULGUR'))return 'fulguration';
  if(key.includes('DILAT'))return 'dilation';
  if(key.includes('INSTIL'))return 'instillation';
  if(key.includes('LAVADO'))return 'lavage';
  if(key.includes('CIRCUN'))return 'circumcision';
  return 'procedure-neutral';
}
function serviceBadge(r){
  const raw=serviceKey(r?.procedimiento||'');
  if(!raw)return '<span class="service-badge consultation">CONSULTA</span>';
  return `<span class="service-badge procedure ${serviceTone(raw)}">${esc(serviceLabel(raw))}</span>`;
}
function groupHomeVisits(rows=[]){
  const groups=[];
  const byPatient=new Map();
  rows.forEach(r=>{
    const pid=r.patient?.id??r.patient_id;
    if(!byPatient.has(pid)){
      const g={patient:r.patient||{},visits:[],isNew:false,firstVisitId:Number(r.id||0)};
      byPatient.set(pid,g);groups.push(g);
    }
    const g=byPatient.get(pid);g.visits.push(r);if(r.tipo==='N')g.isNew=true;
    const vid=Number(r.id||0);if(!g.firstVisitId||vid<g.firstVisitId)g.firstVisitId=vid;
  });
  // El número del paciente se basa en su primera atención del día, para que no cambie
  // si luego se registra un procedimiento adicional. La lista se muestra descendente.
  groups.sort((a,b)=>Number(b.firstVisitId||0)-Number(a.firstVisitId||0));
  return groups;
}
function homeDeleteButton(v){
  return `<button class="danger ghost home-delete-visit" title="Borrar esta atención" onclick="deleteVisitFromHome(${v.id},'${esc(v.fecha||selectedHomeDate||'')}')">🗑 Borrar</button>`;
}
function patientDayNumber(fecha,patientId){
  const rows=weeklyData[String(fecha||'').slice(0,10)]?.visits||[];
  const groups=groupHomeVisits(rows);
  const idx=groups.findIndex(g=>Number(g.patient?.id)===Number(patientId));
  return idx>=0?groups.length-idx:null;
}
function homeReceiptButtons(g,fecha,dayNumber){
  const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||'').trim());
  if(!hasConsultation)return '';
  const pid=Number(g.patient?.id||0);
  return `<div class="home-receipt-actions"><button class="home-view-receipt" onclick="viewReceiptFromHome(${pid},'${esc(fecha)}')">👁 Ver recibo</button><button class="home-print-receipt" onclick="reprintReceiptFromHome(${pid},'${esc(fecha)}')">🖨 Reimprimir</button></div>`;
}
function simpleHomeTable(rows){
  const head='<tr><th class="number-col">N.º</th><th>Paciente</th><th>Atención</th><th>Valor</th><th class="home-actions-col">Acciones</th></tr>';
  const body=(rows||[]).map((r,idx)=>{
    const descendingNumber=(rows||[]).length-idx;
    const fecha=String(r?.fecha||selectedHomeDate||'').slice(0,10);
    const pid=Number(r?.patient?.id||r?.patient_id||0);
    const receiptActions=!String(r?.procedimiento||'').trim()?`<div class="home-receipt-actions"><button class="home-view-receipt" onclick="viewReceiptFromHome(${pid},'${esc(fecha)}')">👁 Ver recibo</button><button class="home-print-receipt" onclick="reprintReceiptFromHome(${pid},'${esc(fecha)}')">🖨 Reimprimir</button></div>`:'';
    const actions=`${receiptActions}${homeDeleteButton(r)}`;
    return `<tr><td class="row-number">${descendingNumber}.</td><td class="patient-cell">${patientNameCell(r,true,r?.tipo==='N')}</td><td>${serviceBadge(r)}</td><td class="money-cell"><span class="money-pill">${money(r?.valor)}</span></td><td class="home-action-cell">${actions}</td></tr>`;
  }).join('');
  return `<table class="home-patient-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}
function homeTable(rows){
  if(!rows?.length)return '<div class="panel muted empty-state">No hay pacientes registrados en este día.</div>';
  try{
    const groups=groupHomeVisits(rows);
    const head='<tr><th class="number-col">N.º</th><th>Paciente</th><th>Atención</th><th>Valor</th><th class="home-actions-col">Acciones</th></tr>';
    const body=groups.map((g,index)=>{
      const consultations=g.visits.filter(v=>!String(v.procedimiento||'').trim());
      const proceduresOnly=g.visits.filter(v=>String(v.procedimiento||'').trim());
      const primary=consultations[0]||proceduresOnly[0];
      const extras=consultations.length?[...consultations.slice(1),...proceduresOnly]:proceduresOnly.slice(1);
      const descendingNumber=groups.length-index;
      const fecha=String(primary?.fecha||selectedHomeDate||'').slice(0,10);
      const mainActions=`${homeReceiptButtons(g,fecha,descendingNumber)}${homeDeleteButton(primary)}`;
      const main=`<tr class="patient-main-row"><td class="row-number" rowspan="${1+extras.length}">${descendingNumber}.</td><td class="patient-cell" rowspan="${1+extras.length}">${patientNameCell(primary,true,g.isNew)}</td><td>${serviceBadge(primary)}</td><td class="money-cell"><span class="money-pill">${money(primary.valor)}</span></td><td class="home-action-cell">${mainActions}</td></tr>`;
      const sub=extras.map(v=>`<tr class="sub-visit-row"><td><span class="sub-visit-label">↳</span> ${serviceBadge(v)}</td><td class="money-cell sub-money"><span class="money-pill subtle">${money(v.valor)}</span></td><td class="home-action-cell sub-actions">${homeDeleteButton(v)}</td></tr>`).join('');
      return main+sub;
    }).join('');
    return `<table class="home-patient-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }catch(err){
    console.error('No se pudo renderizar Inicio agrupado; se usará modo simple.',err);
    return simpleHomeTable(rows);
  }
}
async function deleteVisitFromHome(visitId,fecha){
  if(!confirmDeletion('¿Borrar esta atención?\n\nEsta acción eliminará también su pre-factura asociada.'))return;
  try{
    await singleFlightMutation(`visit:delete:${visitId}`,async()=>{
      await api('/api/visits/'+visitId,{method:'DELETE'});
      invalidateAttentionWeekCache();
      await Promise.all([loadWeek(fecha||selectedHomeDate||toISO(new Date()),fecha||selectedHomeDate),refreshPendingBadges()]);
    },'Borrando…');
  }catch(e){alert(e.message)}
}
function table(rows,opt={}){
  if(!rows?.length)return '<div class="panel muted empty-state">No hay pacientes registrados en este día.</div>';
  const home=!!opt.home;
  if(home)return homeTable(rows);
  const head='<tr><th>Fecha</th><th>Cédula</th><th>Paciente</th><th>Estado</th><th>Atención</th><th>Valor</th></tr>';
  const body=rows.map(r=>`<tr><td>${fmtDate(r.fecha)}</td><td>${esc(r.patient?.cedula||'')}</td><td>${patientNameCell(r,false)}</td><td><span class="badge">${esc(statusLabel(r.tipo))}</span></td><td>${serviceBadge(r)}</td><td><span class="money-pill">${money(r.valor)}</span></td></tr>`).join('');
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

let st;
let activePatientFilter='';
function clearPatientFilterButtons(){
  document.querySelectorAll('[data-patient-filter]').forEach(b=>b.classList.toggle('active',b.dataset.patientFilter===activePatientFilter));
}
function patientsEmptyHtml(message='Escribe al menos 2 caracteres o usa uno de los filtros de arriba.'){
  return `<div class="patients-empty-state"><span>⌕</span><b>Encuentra un paciente</b><p>${esc(message)}</p></div>`;
}
function resetPatientsView(){
  activePatientFilter='';clearPatientFilterButtons();
  const input=$('#search');if(input)input.value='';
  const box=$('#patientResults');if(box){box.className='results patient-results-list';box.innerHTML=patientsEmptyHtml()}
}
function patientCompactResult(p={}){
  if(isHistoricalPatient(p)){
    const date=p.historical_last_visit_date?fmtDate(p.historical_last_visit_date):`Histórico ${historicalYears(p)}`;
    return `<article class="patient-compact-row historical-result"><button class="patient-compact-main" onclick="activateHistoricalPatient(${Number(p.historical_id)},'open')"><span class="patient-compact-name">${esc(p.nombre)}</span><span class="patient-compact-meta"><b>Histórico ${esc(historicalYears(p))}</b>${p.cedula?` · ${esc(p.cedula)}`:''}${p.celular?` · ${esc(formatPhoneValue(p.celular))}`:''}</span><span class="patient-compact-last">Última fecha conocida: ${esc(date)}</span></button><button class="patient-compact-action" onclick="activateHistoricalPatient(${Number(p.historical_id)},'attention')">Usar ficha</button></article>`;
  }
  const missing=missingPatientFields(p);
  const reason=p.review_reason?`<span class="patient-review-reason">⚠ ${esc(p.review_reason)}</span>`:'';
  const imported=p.confirmafy_origin?`<span class="patient-origin-badge">CONFIRMAFY</span>`:'';
  const reviewActions=p.review_reason||p.confirmafy_origin?`<div class="patient-review-actions"><button type="button" onclick="event.stopPropagation();openPatientReview(${Number(p.id)})">Revisar / vincular</button>${p.safe_confirmafy_delete?`<button type="button" class="danger-soft" onclick="event.stopPropagation();deleteConfirmafyImportedPatient(${Number(p.id)})">Eliminar importado</button>`:''}</div>`:'';
  return `<article class="patient-compact-row ${reason?'needs-review':''}" onclick="openPatient(${Number(p.id)},'patients')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPatient(${Number(p.id)},'patients')}"><div class="patient-compact-main"><span class="patient-compact-name">${esc(p.nombre)} ${imported}</span><span class="patient-compact-meta">${p.cedula?`Cédula ${esc(p.cedula)}`:'Sin cédula'} · ${p.celular?esc(formatPhoneValue(p.celular)):'Sin celular'}${p.correo?` · ${esc(p.correo)}`:''}</span><span class="patient-compact-last">${p.ultima_atencion?`Última atención: ${fmtDate(p.ultima_atencion)}`:'Sin atención registrada desde 2026'}</span>${reason}</div>${reviewActions|| (missing.length?`<span class="patient-compact-warning" title="Faltan ${esc(missing.join(', '))}">⚠</span>`:'<span class="patient-compact-chevron">›</span>')}</article>`;
}
function renderPatientResults(rows=[],title=''){
  const box=$('#patientResults');if(!box)return;
  box.className='results patient-results-list';
  if(!rows.length){box.innerHTML=`${title?`<div class="patient-results-heading">${esc(title)}</div>`:''}<div class="patients-empty-state small"><span>✓</span><b>Sin resultados</b><p>No hay pacientes para mostrar con este criterio.</p></div>`;return}
  box.innerHTML=`${title?`<div class="patient-results-heading">${esc(title)} <span>${rows.length}</span></div>`:''}<div class="patient-compact-list">${rows.map(patientCompactResult).join('')}</div>`;
}

function patientReviewIdentity(p={}){
  const parts=[];
  if(p.cedula)parts.push(`Cédula ${esc(p.cedula)}`);
  if(p.celular)parts.push(esc(formatPhoneValue(p.celular)));
  if(p.correo)parts.push(esc(p.correo));
  return parts.join(' · ')||'Sin cédula ni celular';
}
function patientReviewCandidateRow(source={},target={}){
  const score=Math.round(Number(target.similarity||0)*100);
  const sourceName=String(source.nombre||'ESTA FICHA').toUpperCase();
  const targetName=String(target.nombre||'OTRA FICHA').toUpperCase();
  if(isHistoricalPatient(target)){
    const last=target.historical_last_visit_date?`Última fecha histórica ${fmtDate(target.historical_last_visit_date)}`:`Histórico ${historicalYears(target)}`;
    return `<article class="patient-review-match-card historical-link-card"><div class="patient-review-match-info"><div class="historical-review-title"><b>${esc(targetName)}</b><span class="historical-link-badge">HISTÓRICO ${esc(historicalYears(target))}</span></div><span>${patientReviewIdentity(target)}</span><small>${esc(last)}${score?` · Coincidencia ${score}%`:''}</small></div><div class="patient-review-merge-actions"><button type="button" class="primary-soft" onclick="linkHistoricalToPatient(${Number(source.id)},${Number(target.historical_id)})">Vincular histórico a esta ficha</button></div></article>`;
  }
  const last=target.ultima_atencion?`Última atención ${fmtDate(target.ultima_atencion)}`:'Sin atención registrada desde 2026';
  return `<article class="patient-review-match-card"><div class="patient-review-match-info"><b>${esc(targetName)}</b><span>${patientReviewIdentity(target)}</span><small>${esc(last)}${score?` · Coincidencia ${score}%`:''}${target.visit_count!=null?` · ${Number(target.visit_count)} atención${Number(target.visit_count)===1?'':'es'}`:''}</small></div><div class="patient-review-merge-actions"><button type="button" class="primary-soft" onclick="mergeReviewedPatients(${Number(source.id)},${Number(target.id)},'target')">Conservar esta ficha</button><button type="button" onclick="mergeReviewedPatients(${Number(target.id)},${Number(source.id)},'source')">Conservar ${esc(sourceName.split(' ')[0]||'actual')}</button></div></article>`;
}
async function openPatientReview(id){
  try{
    const d=await api('/api/patients/'+Number(id)+'/review-detail');
    const p=d.patient||{}, matches=d.matches||[];
    const imported=p.confirmafy_origin?`<span class="patient-origin-badge strong">CREADO POR CONFIRMAFY</span>`:'';
    const safeDelete=p.safe_confirmafy_delete?`<div class="confirmafy-safe-delete"><div><b>Ficha importada antigua sin historia clínica</b><small>El sistema pudo comprobar que esta ficha fue creada por una importación antigua de agenda y no tiene atenciones. Puedes eliminarla manualmente si no corresponde a nadie.</small></div><button class="danger" onclick="deleteConfirmafyImportedPatient(${Number(p.id)})">Eliminar ficha importada</button></div>`:'';
    const candidateHtml=matches.length?matches.map(x=>patientReviewCandidateRow(p,x)).join(''):'<div class="identity-no-match">No encontramos una segunda ficha suficientemente parecida. Puedes buscarla manualmente abajo.</div>';
    openModal(`<div class="patient-review-modal"><div class="modal-form-heading"><h2>Revisar paciente</h2><p>Decide tú qué ficha debe quedar. El programa no fusionará nada sin tu confirmación.</p></div><div class="patient-review-source-card"><div><b>${esc(p.nombre||'')}</b>${imported}</div><span>${patientReviewIdentity(p)}</span><small>${p.ultima_atencion?`Última atención ${fmtDate(p.ultima_atencion)}`:'Sin atención registrada desde 2026'} · ${Number(p.visit_count||0)} atención${Number(p.visit_count||0)===1?'':'es'}</small></div>${safeDelete}<div class="patient-review-section"><div class="patient-review-section-head"><b>Posibles coincidencias actuales e históricas</b><span>Las fichas actuales se fusionan; un histórico se vincula sin crear otro paciente.</span></div><div id="patientReviewMatches">${candidateHtml}</div></div><div class="patient-review-section"><div class="patient-review-section-head"><b>Buscar otra ficha</b><span>Úsalo si la correcta no aparece arriba.</span></div><input id="patientReviewSearch" class="search uppercase-search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="APELLIDOS Y NOMBRES, CÉDULA O CELULAR" oninput="upperSearchInput(this);searchPatientReviewTarget(${Number(p.id)})"><div id="patientReviewSearchResults" class="patient-review-search-results"></div></div><div class="actions"><button onclick="closeModal()">Cerrar</button><button onclick="editPatient(${Number(p.id)},'patients')">Editar esta ficha</button></div></div>`);
  }catch(e){alert(e.message)}
}
let patientReviewSearchTimer=null;
async function searchPatientReviewTarget(sourceId){
  const input=$('#patientReviewSearch'),box=$('#patientReviewSearchResults');if(!input||!box)return;
  clearTimeout(patientReviewSearchTimer);
  const q=String(input.value||'').trim().toUpperCase();
  if(q.length<2){box.innerHTML='';return}
  box.innerHTML='<div class="patients-loading">Buscando en la copia local…</div>';
  patientReviewSearchTimer=setTimeout(async()=>{
    try{
      const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=20');
      const options=(rows||[]).filter(x=>isHistoricalPatient(x)||Number(x.id)!==Number(sourceId));
      box.innerHTML=options.length?options.map(x=>isHistoricalPatient(x)?`<article class="patient-review-search-row historical-result"><div><b>${esc(x.nombre||'')}</b><small>HISTÓRICO ${esc(historicalYears(x))} · ${patientReviewIdentity(x)}${x.historical_last_visit_date?` · Última fecha ${fmtDate(x.historical_last_visit_date)}`:''}</small></div><button type="button" onclick="linkHistoricalToPatient(${Number(sourceId)},${Number(x.historical_id)})">Vincular histórico</button></article>`:`<article class="patient-review-search-row"><div><b>${esc(x.nombre||'')}</b><small>${patientReviewIdentity(x)}${x.ultima_atencion?` · Última atención ${fmtDate(x.ultima_atencion)}`:''}</small></div><button type="button" onclick="mergeReviewedPatients(${Number(sourceId)},${Number(x.id)},'target')">Fusionar y conservar esta</button></article>`).join(''):'<div class="attention-search-hint">No se encontraron otras fichas.</div>';
    }catch(e){box.innerHTML=`<div class="attention-search-hint err">${esc(e.message)}</div>`}
  },180);
}
async function linkHistoricalToPatient(patientId,historicalId){
  try{
    const current=await api('/api/patients/'+Number(patientId));
    const msg=`¿Vincular esta ficha histórica con ${current.nombre}?\n\nEsto NO creará otro paciente. El histórico 2020–2025 quedará asociado a esta ficha y dejará de aparecer como un resultado separado. Solo se completarán datos vacíos seguros.`;
    if(!confirm(msg))return;
    const d=await api(`/api/patients/${Number(patientId)}/link-historical/${Number(historicalId)}`,{method:'POST'});
    alert(`Histórico vinculado correctamente.${d.last_visit_date?`\nÚltima fecha histórica conocida: ${fmtDate(d.last_visit_date)}`:''}${d.data_completed?'\nTambién se completaron campos que estaban vacíos.':''}`);
    closeModal();
    if(activePatientFilter)await loadPatientFilter(activePatientFilter);else await searchPatients();
  }catch(e){alert(e.message)}
}
async function mergeReviewedPatients(sourceId,targetId,direction='target'){
  try{
    const [source,target]=await Promise.all([api('/api/patients/'+Number(sourceId)),api('/api/patients/'+Number(targetId))]);
    const msg=`¿Fusionar estas dos fichas?\n\nSE ELIMINARÁ COMO FICHA:\n${source.nombre}\n\nSE CONSERVARÁ:\n${target.nombre}\n\nTodas las atenciones y citas de la primera se trasladarán a la ficha conservada. Los datos ya existentes en la ficha conservada no se reemplazarán.`;
    if(!confirm(msg))return;
    const d=await api(`/api/patients/${Number(sourceId)}/merge/${Number(targetId)}`,{method:'POST'});
    alert(`Fusión terminada.\n\n${d.visits_moved||0} atención(es) trasladadas\n${d.appointments_moved||0} cita(s) trasladadas${d.appointments_removed?`\n${d.appointments_removed} cita(s) duplicadas de agenda eliminadas`:''}`);
    closeModal();
    if(activePatientFilter)await loadPatientFilter(activePatientFilter);else await searchPatients();
    await Promise.all([refreshPendingBadges(),loadWeek(selectedHomeDate||toISO(new Date()))]);
  }catch(e){alert(e.message)}
}
async function deleteConfirmafyImportedPatient(id){
  try{
    const d=await api('/api/patients/'+Number(id)+'/review-detail');
    const p=d.patient||{};
    if(!p.safe_confirmafy_delete){alert('Esta ficha ya no cumple las condiciones de seguridad para borrarla como importación antigua. No se hizo ningún cambio.');return}
    if(!confirmDeletion(`¿Eliminar la ficha importada “${p.nombre}”?\n\nSolo se permitirá si no tiene atenciones clínicas y el programa puede demostrar que fue creada por una importación antigua. También se borrarán únicamente sus citas importadas asociadas.`))return;
    const r=await api('/api/patients/'+Number(id)+'/confirmafy-imported',{method:'DELETE'});
    alert(`Ficha importada eliminada.\n${r.appointments_deleted||0} cita(s) importada(s) asociada(s) eliminada(s).`);
    closeModal();
    if(activePatientFilter)await loadPatientFilter(activePatientFilter);else await searchPatients();
    invalidateAttentionWeekCache();await refreshPendingBadges();
  }catch(e){alert(e.message)}
}
async function loadPatientFilter(mode,button=null){
  clearTimeout(st);activePatientFilter=String(mode||'');clearPatientFilterButtons();
  const input=$('#search');if(input)input.value='';
  const box=$('#patientResults');if(!box)return;
  box.innerHTML='<div class="patients-loading">Cargando desde la copia local…</div>';
  const labels={recent:'Pacientes atendidos recientemente',incomplete:'Pacientes con datos incompletos',historical:'Pacientes históricos 2020–2025',review:'Pacientes por revisar · incluye coincidencias con histórico',confirmafy:'Fichas creadas por importaciones antiguas de agenda'};
  const lim=activePatientFilter==='review'?80:30;
  try{const rows=await api('/api/patients?mode='+encodeURIComponent(activePatientFilter)+'&limit='+lim);renderPatientResults(rows,labels[activePatientFilter]||'Pacientes')}catch(e){box.innerHTML=`<div class="attention-search-hint err">${esc(e.message)}</div>`}
}
async function searchPatients(){
  clearTimeout(st);st=setTimeout(async()=>{
    const input=$('#search'),box=$('#patientResults');if(!input||!box)return;
    const q=String(input.value||'').trim().toUpperCase();
    if(!q){
      if(activePatientFilter){await loadPatientFilter(activePatientFilter);return}
      box.innerHTML=patientsEmptyHtml();return;
    }
    activePatientFilter='';clearPatientFilterButtons();
    if(q.length<2){box.innerHTML=patientsEmptyHtml('Escribe al menos 2 caracteres para buscar.');return}
    box.innerHTML='<div class="patients-loading">Buscando en la copia local…</div>';
    try{const d=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=30');renderPatientResults(d,`Resultados para “${q}”`)}catch(e){box.innerHTML=`<div class="attention-search-hint err">${esc(e.message)}</div>`}
  },180);
}

function openModal(html){$('#modalBody').innerHTML=html;const box=$('#modal .modalbox');if(box){box.classList.toggle('modalbox-wide',String(html||'').includes('new-attention-start-modal'));box.classList.toggle('v4413-profile-shell',String(html||'').includes('v4413-patient-profile'))}$('#modal').classList.remove('hidden')}
function closeModal(){$('#modal').classList.add('hidden');const box=$('#modal .modalbox');box?.classList.remove('modalbox-wide');box?.classList.remove('v4413-profile-shell');attentionContext=null}
function patientNameWords(value=''){return String(value||'').trim().toUpperCase().replace(/[^A-ZÁÉÍÓÚÜÑ0-9 ]+/g,' ').split(/\s+/).filter(x=>x.length>=2)}
function patientNameQuality(value=''){const n=patientNameWords(value).length;return n>=4?'completo':n===3?'aceptable':'incompleto'}
let patientSimilarTimer=null;
let lastPatientSimilarity={name:'',matches:[]};
function patientSimilaritySummary(item={}){
  const historical=!!item.historical;
  const id=historical?`Histórico ${historicalYears(item)}`:(item.ultima_atencion?`Última atención ${fmtDate(item.ultima_atencion)}`:'Paciente actual');
  const identity=[item.cedula||'',formatPhoneValue(item.celular||'')].filter(Boolean).join(' · ');
  return `<div><b>${esc(item.nombre||'')}</b><small>${esc(id)}${identity?` · ${esc(identity)}`:''}</small></div>`;
}
function renderPatientSimilarity(data={},excludeId=0){
  lastPatientSimilarity={name:String($('#fNombre')?.value||''),matches:data.matches||[]};
  const warning=$('#patientSimilarWarning');
  const actionBox=$('#identitySimilarActions');
  const quality=data.name_quality||patientNameQuality($('#fNombre')?.value||'');
  const words=Number(data.word_count||patientNameWords($('#fNombre')?.value||'').length);
  const matches=data.matches||[];
  if(warning){
    const qualityText=quality==='completo'?'Nombre completo':quality==='aceptable'?'Nombre utilizable; confirma si existe segundo nombre':'Completa apellidos y nombres antes de atender';
    warning.className=`patient-name-quality ${quality}`;
    const mini=matches.length?`<div class="patient-similar-mini">${matches.slice(0,3).map(x=>`<span>⚠ ${esc(x.nombre||'')}</span>`).join('')}</div>`:'';
    warning.innerHTML=`<span>${quality==='completo'?'✓':'!'}</span><div><b>${esc(qualityText)}</b><small>${words} palabra${words===1?'':'s'} en el nombre${matches.length?` · ${matches.length} posible${matches.length===1?'':'s'} coincidencia${matches.length===1?'':'s'}`:''}</small>${mini}</div>`;
  }
  if(actionBox){
    if(!matches.length){actionBox.innerHTML='<div class="identity-no-match">✓ No encontramos otra ficha parecida.</div>';return}
    actionBox.innerHTML=`<div class="identity-match-warning"><div><b>⚠ Encontramos una ficha parecida</b><small>Revísala antes de crear o modificar otra ficha. Así evitamos duplicados.</small></div>${matches.slice(0,5).map(item=>`<article class="identity-match-row">${patientSimilaritySummary(item)}<div>${item.historical?`<button type="button" onclick="linkIdentityHistorical(${Number(excludeId)},${Number(item.historical_id)})">Vincular histórico</button>`:`<button type="button" onclick="linkIdentityCurrent(${Number(excludeId)},${Number(item.id)})">Vincular y usar</button>`}</div></article>`).join('')}<label class="identity-different-confirm"><input id="identityDifferentPerson" type="checkbox"> Confirmo que es otra persona</label></div>`;
  }
}
function schedulePatientSimilarity(excludeId=0){
  clearTimeout(patientSimilarTimer);
  patientSimilarTimer=setTimeout(async()=>{
    const name=String($('#fNombre')?.value||'').trim().toUpperCase();
    const warning=$('#patientSimilarWarning'),actions=$('#identitySimilarActions');
    if(!name){if(warning)warning.innerHTML='';if(actions)actions.innerHTML='';return}
    const words=patientNameWords(name);
    if(words.length<2){renderPatientSimilarity({name_quality:patientNameQuality(name),word_count:words.length,matches:[]},excludeId);return}
    try{const data=await api('/api/patients/similar?name='+encodeURIComponent(name)+'&exclude_id='+Number(excludeId||0)+'&limit=6');renderPatientSimilarity(data,excludeId)}catch{if(actions)actions.innerHTML=''}
  },320);
}
function patientForm(p={}){
  const foreign=isForeignIdentificationValue(p.cedula||'');
  return `<div class="patient-form-shell"><div class="patient-form-grid">
    <div class="form-field identification-field"><div class="field-label-row"><label for="fCedula">Cédula o identificación</label><label class="foreign-toggle" title="Usar para pasaporte u otra identificación"><input id="fForeign" type="checkbox" ${foreign?'checked':''} onchange="toggleForeignIdentification()"><span>Extranjero</span></label></div><input id="fCedula" type="text" inputmode="${foreign?'text':'numeric'}" autocomplete="off" maxlength="${foreign?30:10}" placeholder="${foreign?'Pasaporte o identificación':'Ingrese 10 dígitos'}" value="${esc(p.cedula||'')}" oninput="identificationInput(this)"><small id="fCedulaHelp" class="field-help">${foreign?'Se permite otro formato de identificación.':'Cédula ecuatoriana: exactamente 10 dígitos.'}</small><small id="fCedulaError" class="field-error hidden"></small></div>
    <div class="form-field patient-name-field"><label for="fNombre">Apellidos y nombres</label><input id="fNombre" class="uppercase-name" autocapitalize="characters" autocomplete="off" placeholder="2 APELLIDOS Y NOMBRES" value="${esc(String(p.nombre||'').toUpperCase())}" oninput="upperNameInput(this);clearPatientFieldError('fNombre');schedulePatientSimilarity(${Number(p.id||0)})"><small class="field-help">Ideal: dos apellidos y dos nombres. Con 1–2 palabras se pedirá confirmar la identidad antes de atender.</small><small id="fNombreError" class="field-error hidden"></small></div>
    <div class="form-field"><label for="fNac">Fecha de nacimiento</label><input type="date" id="fNac" value="${esc(p.fecha_nacimiento||'')}"></div>
    <div class="form-field"><label for="fCel">Celular</label><input id="fCel" type="text" inputmode="numeric" pattern="[0-9 ]*" maxlength="12" autocomplete="tel" placeholder="09x xxx xxxx" value="${esc(formatPhoneValue(p.celular||''))}" oninput="formatPhoneInput(this)"></div>
    <div class="form-field email-field"><label for="fMail">Correo</label><input id="fMail" type="email" autocapitalize="none" autocomplete="email" spellcheck="false" placeholder="nombre@correo.com" value="${esc(String(p.correo||'').toLowerCase())}" oninput="lowerEmailInput(this);clearPatientFieldError('fMail')"><div class="email-domain-chips"><button type="button" onclick="completeEmailDomain('@gmail.com')">@gmail.com</button><button type="button" onclick="completeEmailDomain('@hotmail.com')">@hotmail.com</button><button type="button" onclick="completeEmailDomain('@outlook.com')">@outlook.com</button><button type="button" onclick="completeEmailDomain('@yahoo.com')">@yahoo.com</button></div><small id="fMailError" class="field-error hidden"></small></div>
    <div class="form-field"><label for="fLugar">Lugar</label><input id="fLugar" placeholder="Ciudad o sector" value="${esc(p.lugar||'')}"></div>
  </div><div id="patientSimilarWarning" class="patient-name-quality"></div><div class="form-field notes-field"><label for="fNotas">Notas</label><textarea id="fNotas" placeholder="Observaciones adicionales del paciente">${esc(p.notas||'')}</textarea></div></div>`
}
function getPatientForm(){
  ['fCedula','fNombre','fMail'].forEach(clearPatientFieldError);
  const extranjero=!!$('#fForeign')?.checked;
  const rawId=String($('#fCedula')?.value||'').trim();
  const cedula=extranjero?rawId.toUpperCase().replace(/\s+/g,''):rawId.replace(/\D/g,'');
  const nombre=String($('#fNombre')?.value||'').trim().toUpperCase();
  const correo=String($('#fMail')?.value||'').trim().toLowerCase();
  if(!nombre){setPatientFieldError('fNombre','Escribe los apellidos y nombres del paciente.');throw Error('Los apellidos y nombres son obligatorios.');}
  if(cedula&&!extranjero){if(cedula.length!==10){setPatientFieldError('fCedula','La cédula debe tener exactamente 10 dígitos.');throw Error('La cédula debe tener exactamente 10 dígitos.');}if(!validEcuadorianCedula(cedula)){setPatientFieldError('fCedula','La cédula no es válida. Revisa si se digitó correctamente.');throw Error('La cédula ecuatoriana no es válida.');}}
  if(cedula&&extranjero&&cedula.length>30){setPatientFieldError('fCedula','La identificación no puede superar 30 caracteres.');throw Error('La identificación extranjera es demasiado larga.');}
  if(correo&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo)){setPatientFieldError('fMail','Revisa el formato del correo.');throw Error('El correo no tiene un formato válido.');}
  return {cedula:cedula||null,nombre,fecha_nacimiento:$('#fNac').value||null,celular:($('#fCel').value||'').replace(/\D/g,'')||null,correo:correo||null,lugar:$('#fLugar').value||null,notas:$('#fNotas').value||null,extranjero};
}
let pendingNewPatientAgendaSlot=null;
function newPatient(continueToAttention=false,agendaSlot=null){
  pendingNewPatientAgendaSlot=agendaSlot||null;
  const actions=continueToAttention
    ?`<button class="cancel-btn" onclick="newAttention()">Cancelar</button><button class="primary" onclick="saveNewPatient(true)">Guardar y continuar a atención</button>`
    :`<button class="cancel-btn" onclick="closeModal()">Cancelar</button><button onclick="saveNewPatient(false)">Guardar paciente</button><button class="primary" onclick="saveNewPatient('agenda')">Guardar y agendar paciente</button>`;
  openModal(`<div class="patient-form-modal"><div class="modal-form-heading"><h2>Nuevo paciente</h2><p>${continueToAttention?'Registra al paciente y al guardar pasarás directamente a su nueva atención.':'Guarda la ficha o guarda y pasa directamente a agendar una cita.'}</p></div>${patientForm()}<div class="actions form-actions">${actions}</div></div>`);
  setTimeout(()=>$('#fCedula')?.focus(),0);
}
async function saveNewPatient(action=false){
  try{
    const data=getPatientForm();
    const sameName=String(lastPatientSimilarity.name||'').trim().toUpperCase()===String(data.nombre||'').trim().toUpperCase();
    if(sameName&&(lastPatientSimilarity.matches||[]).length){const names=lastPatientSimilarity.matches.slice(0,3).map(x=>x.nombre).join('\n• ');if(!confirm(`Encontramos una ficha parecida:\n\n• ${names}\n\n¿Confirmas que este sí es un paciente distinto y deseas crearlo?`))return}
    await singleFlightMutation('patient:create',async()=>{
      const p=await api('/api/patients',{method:'POST',body:JSON.stringify(data)});
      if(action===true){await attentionFor(p.id)}
      else if(action==='agenda'){
        const slot=pendingNewPatientAgendaSlot;pendingNewPatientAgendaSlot=null;
        await openAgendaPatient(p.id,null,slot?.date||null,slot?.time||null);
      }else{await openPatient(p.id,'patients')}
      await searchPatients();
    },action===true?'Guardando…':action==='agenda'?'Guardando y abriendo Agenda…':'Guardando paciente…');
  }catch(e){alert(e.message)}
}

async function openHistoricalPatientProfile(hid){
  try{
    const p=await api(`/api/historical/${Number(hid)}/activate`,{method:'POST'});
    return openPatient(Number(p.id),'attention-search');
  }catch(e){alert(e.message||'No se pudo abrir el paciente histórico.')}
}
function setPatientProfileTab(tab){
  const wanted=String(tab||'resumen');
  document.querySelectorAll('#v4413ProfileTabs [data-profile-tab]').forEach(b=>b.classList.toggle('active',b.dataset.profileTab===wanted));
  document.querySelectorAll('#v4413ProfilePanels [data-profile-panel]').forEach(p=>p.classList.toggle('hidden',p.dataset.profilePanel!==wanted));
}
function patientProfileWarningHtml(p){
  const missing=missingPatientFields(p);
  if(!missing.length)return `<div class="v4413-profile-complete"><span>✓</span><div><b>Datos principales completos</b><small>Cédula, celular y correo registrados.</small></div></div>`;
  const labels=missing.join(', ');
  return `<div class="v4413-profile-warning"><span class="v4413-warning-icon">⚠</span><div><b>Datos incompletos</b><small>Falta completar: ${esc(labels)}.</small></div><button type="button" onclick="editPatient(${Number(p.id)},currentPatientSource)">Completar datos</button></div>`;
}
function patientProfileAgendaHtml(rows=[]){
  if(!rows.length)return '<div class="v4413-profile-empty">No hay citas de Agenda registradas para esta ficha.</div>';
  return `<div class="v4413-profile-timeline">${rows.map(a=>{const st=agendaStatusInfo(a.estado);return `<article class="v4413-timeline-row"><div class="v4413-timeline-date"><b>${fmtDate(a.fecha)}</b><span>${esc(fmtTime(a.hora))}</span></div><div class="v4413-timeline-main"><strong>${esc(st.label)}</strong><small>${a.origen?esc(String(a.origen).replaceAll('_',' ')):'Agenda'}${a.nota?` · ${esc(a.nota)}`:''}</small></div><span class="native-detail-status ${esc(st.cls)}">${esc(st.label)}</span></article>`}).join('')}</div>`;
}
function patientProfileBillingHtml(p){
  const emissions=Array.isArray(p.emissions)?p.emissions:[];
  const lines=Array.isArray(p.billing)?p.billing:[];
  const invoices=emissions.length?`<div class="v4413-profile-subhead"><b>Comprobantes AZUR / SRI</b><span>${emissions.length}</span></div><div class="v4413-profile-timeline">${emissions.map(x=>{const st=String(x.estado||'EN PROCESO').toUpperCase();const cls=st==='AUTORIZADA'?'ok':(['RECHAZADA','DEVUELTA'].includes(st)?'bad':'wait');return `<article class="v4413-timeline-row"><div class="v4413-timeline-date"><b>${fmtDate(x.fecha)}</b><span>${x.numero_factura?`Factura ${esc(x.numero_factura)}`:'Sin número todavía'}</span></div><div class="v4413-timeline-main"><strong>${esc(st.replaceAll('_',' '))}</strong><small>${x.has_clave_acceso?'Enviada a AZUR':'Registro de facturación'}</small></div><span class="v4413-invoice-state ${cls}">${esc(st.replaceAll('_',' '))}</span></article>`}).join('')}</div>`:'';
  const billing=lines.length?`<div class="v4413-profile-subhead"><b>Atenciones en facturación</b><span>${lines.length}</span></div><div class="v4413-profile-timeline">${lines.map(x=>{const service=String(x.procedimiento||'').trim()||'CONSULTA';return `<article class="v4413-timeline-row"><div class="v4413-timeline-date"><b>${fmtDate(x.fecha)}</b><span>${esc(serviceLabel(service))}</span></div><div class="v4413-timeline-main"><strong>${esc(String(x.estado||'PENDIENTE').replaceAll('_',' '))}</strong><small>${x.numero_factura?`Factura ${esc(x.numero_factura)}`:'Sin número de factura'}</small></div><b class="v4413-profile-money">${money(x.valor)}</b></article>`}).join('')}</div>`:'';
  return invoices+billing||'<div class="v4413-profile-empty">No hay registros de facturación para esta ficha.</div>';
}
async function openPatient(id,source='general'){
  currentPatientSource=source;
  const p=await api('/api/patients/'+Number(id)+'/profile');
  const visits=Array.isArray(p.visits)?p.visits:[];
  const appointments=Array.isArray(p.appointments)?p.appointments:[];
  const emissions=Array.isArray(p.emissions)?p.emissions:[];
  const canDelete=source==='patients';
  const history=visits.length?`<div class="patient-history-wrap"><table class="patient-history-table"><thead><tr><th>Fecha</th><th>Estado</th><th>Atención</th><th>Valor</th>${canDelete?'<th class="delete-col">Acción</th>':''}</tr></thead><tbody>${visits.map(v=>`<tr><td>${fmtDate(v.fecha)}</td><td>${esc(statusLabel(v.tipo))}</td><td>${serviceBadge(v)}</td><td><span class="money-pill">${money(v.valor)}</span></td>${canDelete?`<td><button class="danger ghost small-delete" onclick="deleteVisit(${Number(v.id)},${Number(id)})">Borrar</button></td>`:''}</tr>`).join('')}</tbody></table></div>`:'<div class="v4413-profile-empty">Todavía no tiene atenciones registradas desde 2026.</div>';
  const historical=p.historical?`<div class="patient-historical-summary"><div><span>PACIENTE ANTERIOR</span><b>${esc(historicalLastLabel(p))}</b></div><small>Figura en el archivo histórico ${esc(historicalYears(p))}. El histórico anterior a 2026 se conserva como referencia.</small></div>`:'';
  const missing=missingPatientFields(p);
  const last=p.ultima_atencion?fmtDate(p.ultima_atencion):(historicalLastDate(p)?fmtDate(historicalLastDate(p)):'Sin fecha registrada');
  const deleteButton=canDelete?`<button class="danger ghost patient-delete-compact" onclick="deletePatient(${Number(id)},${visits.length})">🗑 Borrar paciente</button>`:'';
  const birth=p.fecha_nacimiento?fmtDate(p.fecha_nacimiento):'Sin registrar';
  const notes=String(p.notas||'').trim();
  openModal(`<div class="patient-profile-modal v4413-patient-profile"><div class="v4413-profile-head"><div class="v4413-profile-name"><span>FICHA DEL PACIENTE</span><h2>${esc(p.nombre)}</h2><div class="v4413-profile-identity"><b>${esc(p.cedula||'Sin cédula')}</b><span>${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</span>${p.correo?`<span>${esc(p.correo)}</span>`:''}</div></div><div class="v4413-profile-actions"><button class="primary" onclick="attentionFor(${Number(id)})">＋ Nueva atención</button><button onclick="openAgendaPatient(${Number(id)})">＋ Agendar cita</button><button class="patient-edit-btn" onclick="editPatient(${Number(id)},'${esc(source)}')">Editar datos</button>${deleteButton}</div></div>${patientProfileWarningHtml(p)}<div class="v4413-profile-kpis"><div><span>Última atención</span><b>${esc(last)}</b></div><div><span>Atenciones</span><b>${visits.length}</b></div><div><span>Citas en Agenda</span><b>${appointments.length}</b></div><div><span>Facturas / envíos</span><b>${emissions.length}</b></div></div><div id="v4413ProfileTabs" class="v4413-profile-tabs"><button class="active" data-profile-tab="resumen" onclick="setPatientProfileTab('resumen')">Datos</button><button data-profile-tab="atenciones" onclick="setPatientProfileTab('atenciones')">Atenciones <span>${visits.length}</span></button><button data-profile-tab="agenda" onclick="setPatientProfileTab('agenda')">Agenda <span>${appointments.length}</span></button><button data-profile-tab="facturacion" onclick="setPatientProfileTab('facturacion')">Facturación <span>${emissions.length||p.billing?.length||0}</span></button></div><div id="v4413ProfilePanels" class="v4413-profile-panels"><section data-profile-panel="resumen"><div class="v4413-data-grid"><div><span>Cédula / identificación</span><b>${esc(p.cedula||'Sin registrar')}</b></div><div><span>Celular</span><b>${esc(formatPhoneValue(p.celular||'')||'Sin registrar')}</b></div><div><span>Correo</span><b>${esc(p.correo||'Sin registrar')}</b></div><div><span>Fecha de nacimiento</span><b>${esc(birth)}</b></div><div><span>Lugar</span><b>${esc(p.lugar||'Sin registrar')}</b></div><div><span>Estado de ficha</span><b>${missing.length?'Datos por completar':'Completa'}</b></div></div>${notes?`<div class="v4413-profile-notes"><span>Notas</span><p>${esc(notes)}</p></div>`:''}${historical}</section><section class="hidden" data-profile-panel="atenciones"><div class="v4413-profile-section-title"><h3>Historial de atenciones</h3><span>Más reciente primero</span></div>${history}</section><section class="hidden" data-profile-panel="agenda"><div class="v4413-profile-section-title"><h3>Historial de Agenda</h3><span>Citas registradas en esta ficha</span></div>${patientProfileAgendaHtml(appointments)}</section><section class="hidden" data-profile-panel="facturacion"><div class="v4413-profile-section-title"><h3>Historial de Facturación</h3><span>Registros vinculados a este paciente</span></div>${patientProfileBillingHtml(p)}</section></div></div>`);
}
async function editPatient(id,source=currentPatientSource){const p=await api('/api/patients/'+id);currentPatientSource=source;openModal(`<div class="patient-form-modal"><div class="modal-form-heading"><h2>Editar paciente</h2><p>Actualiza la información y guarda los cambios.</p></div>${patientForm(p)}<div class="actions form-actions"><button class="cancel-btn" onclick="openPatient(${id},'${source}')">Cancelar</button><button class="primary" onclick="savePatient(${id},'${source}')">Guardar cambios</button></div></div>`);setTimeout(()=>schedulePatientSimilarity(Number(id)),0) }
async function savePatient(id,source=currentPatientSource){try{const data=getPatientForm();await singleFlightMutation(`patient:update:${id}`,async()=>{await api('/api/patients/'+id,{method:'PUT',body:JSON.stringify(data)});await openPatient(id,source);await searchPatients()},'Guardando…')}catch(e){alert(e.message)}}
async function deletePatient(id,visitCount){
  const extra=visitCount?` También se eliminarán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'}.`:'';
  if(!confirmDeletion(`¿Borrar este paciente?${extra} Esta acción no se puede deshacer.`))return;
  try{await singleFlightMutation(`patient:delete:${id}`,async()=>{await api('/api/patients/'+id,{method:'DELETE'});closeModal();show('pacientes');await searchPatients();await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()])},'Borrando…')}catch(e){alert(e.message)}
}
async function deleteVisit(visitId,patientId){
  if(!confirmDeletion('¿Borrar esta atención? Se eliminará del historial y de los reportes.'))return;
  try{await singleFlightMutation(`visit:delete:${visitId}`,async()=>{await api('/api/visits/'+visitId,{method:'DELETE'});invalidateAttentionWeekCache();await openPatient(patientId,'patients');await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()])},'Borrando…')}catch(e){alert(e.message)}
}

let attentionWeekCache=new Map();
const ATTENTION_WEEK_CACHE_MS=60000;
let attentionWeekAnchor=toISO(new Date());
let attentionSearchTimer=null;
let attentionSearchSeq=0;

/* v4.4.10 — restaura únicamente la lógica del buscador existente de Nueva atención. */
function setAttentionSearchView(active){
  const agenda=$('#attentionWeekBlock'),box=$('#aResults');
  const shell=document.querySelector('#modal .new-attention-start-modal');
  if(agenda)agenda.classList.toggle('hidden',!!active);
  if(shell)shell.classList.toggle('attention-searching',!!active);
  if(box){
    box.classList.toggle('attention-results-expanded',!!active);
    if(active){
      box.style.maxHeight='56vh';
      box.style.overflowY='auto';
      box.style.marginTop='8px';
    }else{
      box.style.removeProperty('max-height');
      box.style.removeProperty('overflow-y');
      box.style.removeProperty('margin-top');
    }
  }
}
function attentionSearch(immediate=false){
  clearTimeout(attentionSearchTimer);
  const run=async()=>{
    const input=$('#aSearch'),box=$('#aResults');
    if(!input||!box)return;
    const q=String(input.value||'').trim().toUpperCase();
    const active=q.length>=2;
    setAttentionSearchView(active);
    if(!active){
      attentionSearchSeq++;
      box.innerHTML='';
      box.classList.add('hidden');
      return;
    }

    const seq=++attentionSearchSeq;
    box.classList.remove('hidden');
    box.innerHTML='<div class="panel muted">Buscando paciente…</div>';
    try{
      const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=18');
      if(seq!==attentionSearchSeq)return;
      const usable=(rows||[]).slice(0,14);
      box.innerHTML=usable.length?usable.map(p=>{
        const missing=typeof missingPatientFields==='function'?missingPatientFields(p):[];
        const warning=missing.length?`<span class="v4413-result-warning">⚠ Datos incompletos</span>`:'';
        if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)){
          const years=typeof historicalYears==='function'?historicalYears(p):'2020–2025';
          const last=p.historical_last_visit_date||p.ultima_atencion;
          const lastText=last?`Última atención histórica: ${fmtDate(last)}`:`Paciente histórico ${years}`;
          return `<article class="v4413-attention-result historical-result" data-v4413-profile-card="1" role="button" tabindex="0" onclick="openHistoricalPatientProfile(${Number(p.historical_id)})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openHistoricalPatientProfile(${Number(p.historical_id)})}"><div class="v4413-result-main"><div class="v4413-result-name-row"><b>${esc(p.nombre||'')}</b><span class="historical-badge">HISTÓRICO ${esc(years)}</span>${warning}</div><span class="v4413-result-meta">${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}${p.correo?` · ${esc(p.correo)}`:''}</span><strong class="v4413-result-last historical">${esc(lastText)}</strong></div><span class="v4413-result-chevron">›</span></article>`;
        }
        const lastText=p.ultima_atencion?`Última atención: ${fmtDate(p.ultima_atencion)}`:'Sin atención registrada desde 2026';
        return `<article class="v4413-attention-result" data-v4413-profile-card="1" role="button" tabindex="0" onclick="openPatient(${Number(p.id)},'attention-search')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPatient(${Number(p.id)},'attention-search')}"><div class="v4413-result-main"><div class="v4413-result-name-row"><b>${esc(p.nombre||'')}</b>${warning}</div><span class="v4413-result-meta">${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}${p.correo?` · ${esc(p.correo)}`:''}</span><strong class="v4413-result-last ${p.ultima_atencion?'has-date':'empty'}">${esc(lastText)}</strong></div><span class="v4413-result-chevron">›</span></article>`;
      }).join(''):'<div class="panel muted">No encontramos coincidencias. Revisa nombre, cédula, celular o correo.</div>';
    }catch(e){
      if(seq!==attentionSearchSeq)return;
      box.innerHTML=`<div class="panel err">${esc(e.message||'No se pudo buscar el paciente.')}</div>`;
    }
  };
  if(immediate)return run();
  attentionSearchTimer=setTimeout(run,160);
}

function attentionWeekKey(anchorValue){
  const d=parseISO(anchorValue||toISO(new Date()));
  const day=d.getDay()===0?6:d.getDay()-1;d.setDate(d.getDate()-day);return toISO(d);
}
function invalidateAttentionWeekCache(){attentionWeekCache.clear()}
function moveAttentionWeek(delta){
  const d=parseISO(attentionWeekAnchor||toISO(new Date()));d.setDate(d.getDate()+(Number(delta)||0)*7);
  attentionWeekAnchor=toISO(d);loadAttentionWeek(false,attentionWeekAnchor);
}
function currentAttentionWeek(){attentionWeekAnchor=toISO(new Date());loadAttentionWeek(false,attentionWeekAnchor)}
function attentionWeekStatus(row={}){
  const a=row.appointment||{};
  const imported=String(a.origen||'').toUpperCase()==='CONFIRMAFY_IMPORTADO';
  const state=String(a.estado||'PENDIENTE').toUpperCase();
  if(imported||state==='CARGADO')return {label:'Sin vincular',cls:'loaded'};
  if(state==='EXPORTADO')return {label:'Pendiente',cls:'pending'};
  return {label:'Pendiente',cls:'pending'};
}
function attentionWeekRow(row={}){
  const a=row.appointment||{},p=row.patient||{},staged=row.staged||null;
  const source=String(row.source_type||'');
  const isStaged=source==='CONFIRMAFY_STAGED'||!!staged;
  const isLegacyConfirmafy=source==='CONFIRMAFY_LEGACY';
  const needsIdentity=isStaged||isLegacyConfirmafy;
  if(!needsIdentity&&p.id!=null)agendaPatientById.set(Number(p.id),p);
  if(!needsIdentity&&a.id!=null)agendaAppointmentById.set(Number(a.id),row);
  if(isStaged&&staged?.id!=null)confirmafyStagedById.set(Number(staged.id),row);
  const phone=formatPhoneValue((staged?.celular??p.celular)||'');
  const fecha=esc((staged?.fecha??a.fecha)||'');
  const shownName=staged?.nombre??p.nombre??'Paciente';
  const title=needsIdentity?`Atender y confirmar identidad de ${shownName}`:`Atender a ${shownName}`;
  const click=isStaged
    ?`attendConfirmafyStaged(${Number(staged?.id||0)},'${fecha}')`
    :(isLegacyConfirmafy
      ?`attendLegacyConfirmafy(${Number(a.id||0)},'${fecha}')`
      :`attendFromAgenda(${Number(p.id||0)},'${fecha}')`);
  return `<div class="attention-week-row ${row.conflict?'has-conflict':''} ${needsIdentity?'confirmafy-unlinked':''}" role="button" tabindex="0" title="${esc(title)}" onclick="${click}" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();${click}}">
    <div class="attention-week-time">${esc(fmtTimeCompact(staged?.hora??a.hora))}</div>
    <div class="attention-week-person"><b>${esc(shownName)}</b><small>${esc(phone||'IDENTIDAD PENDIENTE')}</small></div>
    ${row.conflict?`<div class="attention-week-conflict">⚠ Horario duplicado${!needsIdentity?` <button onclick="event.stopPropagation();openAgendaPatient(${Number(p.id||0)},${Number(a.id||0)})">Corregir</button>`:''}</div>`:''}
  </div>`;
}

function renderAttentionWeek(d={}){
  const box=$('#attentionWeekCalendar');if(!box)return;
  const days=d.days||[];
  const today=toISO(new Date());
  if(days.length){
    const label=$('#attentionWeekLabel');
    if(label)label.textContent=`${fmtDate(days[0].date)} — ${fmtDate(days[days.length-1].date)}`;
  }
  const conflict=$('#attentionWeekConflict');
  if(conflict){
    const n=Number(d.conflicts||0);
    conflict.textContent=n?`⚠ ${n} cita${n===1?'':'s'} con horario duplicado`:'';
    conflict.classList.toggle('hidden',n<=0);
  }
  box.innerHTML=days.map(day=>`<article class="attention-week-day ${String(day.date).slice(0,10)===today?'today':''}">
    <header><div><b>${esc(day.label)}</b><span>${fmtDate(day.date)}</span></div><strong>${(day.appointments||[]).length}</strong></header>
    <div class="attention-week-list">${(day.appointments||[]).map(attentionWeekRow).join('')||'<div class="attention-week-empty">Sin citas</div>'}</div>
  </article>`).join('')||'<div class="attention-week-empty wide">No hay agenda disponible para esta semana.</div>';
}
async function loadAttentionWeek(force=false,anchorValue=null){
  const box=$('#attentionWeekCalendar');if(!box)return;
  const anchor=anchorValue||attentionWeekAnchor||toISO(new Date());
  attentionWeekAnchor=anchor;
  const key=attentionWeekKey(anchor);
  const cached=attentionWeekCache.get(key);
  const valid=!force&&cached&&(Date.now()-cached.ts)<ATTENTION_WEEK_CACHE_MS;
  if(valid){renderAttentionWeek(cached.data);return}
  box.innerHTML='<div class="attention-week-loading">Cargando agenda…</div>';
  try{
    const d=await api('/api/agenda/week?anchor='+encodeURIComponent(anchor));
    attentionWeekCache.set(key,{ts:Date.now(),data:d});
    if(attentionWeekCache.size>8){const first=attentionWeekCache.keys().next().value;attentionWeekCache.delete(first)}
    renderAttentionWeek(d);
  }catch(e){
    if(box)box.innerHTML=`<div class="attention-week-empty wide err">${esc(e.message)}</div>`;
  }
}
async function newAttention(){
  currentPatientSource='general';
  attentionWeekAnchor=toISO(new Date());
  openModal(`<div class="new-attention-start-modal attention-agenda-only"><div class="modal-form-heading"><h2>Nueva atención</h2><p>Selecciona una cita para registrar la atención.</p></div><div id="attentionWeekBlock" class="attention-week-block"><div class="attention-week-head"><div><b>Agenda</b><span>Jueves, viernes y sábado</span></div><div class="attention-week-nav"><button type="button" title="Semana anterior" onclick="moveAttentionWeek(-1)">‹</button><button type="button" class="week-today" onclick="currentAttentionWeek()">Esta semana</button><button type="button" title="Semana siguiente" onclick="moveAttentionWeek(1)">›</button></div><div class="attention-week-range"><strong id="attentionWeekLabel"></strong><span id="attentionWeekConflict" class="attention-week-conflict-note hidden"></span></div></div><div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda…</div></div></div></div>`);
  loadAttentionWeek(false,attentionWeekAnchor);
}
function procedureByName(name){
  const key=serviceKey(name);
  return procedures.find(p=>serviceKey(p.nombre)===key)||null;
}
function procedureNamesForAttention(){
  const fromDb=procedures.map(p=>serviceKey(p.nombre)).filter(Boolean);
  return [...new Set([...QUICK_PROCEDURES,...fromDb])];
}
function selectedServiceOrder(){
  return ['CONSULTA',...procedureNamesForAttention()].filter(name=>selectedServices.has(name));
}
function serviceCardsHtml(){
  const consultaSelected=selectedServices.has('CONSULTA');
  const consulta=`<button type="button" class="service-card consultation-card ${consultaSelected?'selected':''}" data-service="CONSULTA" aria-pressed="${consultaSelected}" onclick="toggleService('CONSULTA')"><span class="service-icon">✚</span><strong>CONSULTA</strong><span class="service-price">$40.00</span><span class="service-check">✓</span></button>`;
  const procs=procedureNamesForAttention().map(name=>{
    const p=procedureByName(name), val=p?.valor_default, selected=selectedServices.has(name), encoded=encodeURIComponent(name);
    return `<button type="button" class="service-card procedure-card ${serviceTone(name)} ${selected?'selected':''}" data-service="${esc(name)}" aria-pressed="${selected}" onclick="toggleService(decodeURIComponent('${encoded}'))"><span class="service-icon">▣</span><strong>${esc(serviceLabel(name))}</strong><span class="service-price">${val==null?'Valor editable':money(val)}</span><span class="service-check">✓</span></button>`;
  }).join('');
  return `<div class="service-section consultation-service-section"><div class="service-group-heading"><div><b>Consulta</b><span>Atención médica</span></div></div><div class="service-grid consultation-grid">${consulta}</div></div><div class="service-section procedures-service-section"><div class="service-group-heading"><div><b>Procedimientos y servicios</b><span>Selecciona uno o varios si corresponde</span></div></div><div class="service-grid">${procs}</div></div>`;
}
function captureProcedureValues(){
  document.querySelectorAll('.procedure-value-input').forEach(input=>{
    const key=serviceKey(input.dataset.service);
    attentionServiceValues[key]=input.value;
  });
}
function renderSelectedServiceValues(){
  captureProcedureValues();
  const box=$('#procedureValuesBox');if(!box)return;
  const names=selectedServiceOrder().filter(name=>name!=='CONSULTA');
  const hint=$('#serviceSelectionHint');if(hint)hint.textContent=`Puedes elegir varias · ${selectedServices.size} seleccionada${selectedServices.size===1?'':'s'}`;
  document.querySelectorAll('.service-card').forEach(card=>{
    const key=serviceKey(card.dataset.service);
    const active=selectedServices.has(key);
    card.classList.toggle('selected',active);card.setAttribute('aria-pressed',String(active));
  });
  if(!names.length){box.classList.add('hidden');box.innerHTML='';return}
  box.innerHTML=names.map(name=>{
    const p=procedureByName(name);
    if(attentionServiceValues[name]===undefined||attentionServiceValues[name]===null)attentionServiceValues[name]=p?.valor_default??'';
    const value=attentionServiceValues[name];
    return `<div class="procedure-value-row"><label><span>Valor de <b>${esc(serviceLabel(name))}</b></span><div class="money-input"><span>$</span><input class="procedure-value-input" data-service="${esc(name)}" type="number" min="0" step="0.01" value="${esc(value)}" placeholder="Ingresa el valor"></div></label></div>`;
  }).join('')+`<small>Los valores se pueden cambiar para esta atención.</small>`;
  box.classList.remove('hidden');
}
function toggleService(name){
  const key=serviceKey(name);if(!key)return;
  captureProcedureValues();
  if(selectedServices.has(key)){
    selectedServices.delete(key);
  }else{
    selectedServices.add(key);
    const p=procedureByName(key);
    if(key!=='CONSULTA'&&(attentionServiceValues[key]===undefined||attentionServiceValues[key]===null))attentionServiceValues[key]=p?.valor_default??'';
  }
  renderSelectedServiceValues();
}
function captureAttentionDraft(){
  if(!attentionContext)return null;
  captureProcedureValues();
  return {
    patientId:attentionContext.patient?.id,
    manualSubsequent:!!attentionContext.manualSubsequent,
    selectedServices:[...selectedServices],
    procedureValues:{...attentionServiceValues},
    fecha:$('#aFecha')?.value||toISO(new Date()),
    observacion:$('#aObs')?.value??'',
    stagedId:Number(attentionContext?.stagedId||0)
  };
}
function attentionMissingActions(p,id){
  const missing=missingPatientFields(p);if(!missing.length)return '';
  const text=`Faltan datos: ${missing.join(', ')}`;
  return `<div class="attention-missing-actions"><div class="data-warning"><span class="warning-icon">⚠</span><span>${esc(text)}</span></div><button type="button" class="complete-data-btn" onclick="editPatientFromAttention(${id})">Completar datos</button></div>`;
}
let identityReviewDraft=null;
let identityReviewSourceId=0;
function openIdentityReview(p,draft=null){
  identityReviewDraft={...(draft||{}),identityReviewed:true};identityReviewSourceId=Number(p.id||0);
  openModal(`<div class="identity-review-modal"><div class="modal-form-heading"><h2>Confirmar identidad antes de atender</h2><p>Esta ficha tiene un nombre demasiado corto. Completa los apellidos y nombres o vincúlala con una ficha existente.</p></div><div class="identity-review-tip"><b>Objetivo</b><span>Registrar, cuando sea posible, 2 apellidos y 2 nombres. Tres palabras se aceptan cuando ese sea el nombre disponible; una o dos deben revisarse.</span></div>${patientForm(p)}<div id="identitySimilarActions" class="identity-similar-actions"></div><div class="actions form-actions"><button class="cancel-btn" onclick="newAttention()">Volver</button><button class="primary" onclick="saveIdentityAndContinue(${Number(p.id)})">Guardar y continuar</button></div></div>`);
  setTimeout(()=>{const el=$('#fNombre');if(el){el.focus();el.setSelectionRange(el.value.length,el.value.length)}schedulePatientSimilarity(Number(p.id));},0);
}
async function saveIdentityAndContinue(id){
  try{
    const data=getPatientForm();
    const words=patientNameWords(data.nombre).length;
    if(words<3){setPatientFieldError('fNombre','Completa al menos dos apellidos y un nombre, o vincula la ficha correcta.');throw Error('El nombre sigue demasiado corto para confirmar la atención.');}
    const sameName=String(lastPatientSimilarity.name||'').trim().toUpperCase()===String(data.nombre||'').trim().toUpperCase();
    if(sameName&&(lastPatientSimilarity.matches||[]).length&&!$('#identityDifferentPerson')?.checked){throw Error('Encontramos una ficha parecida. Vincúlala o marca “Confirmo que es otra persona” antes de continuar.');}
    await api('/api/patients/'+id,{method:'PUT',body:JSON.stringify(data)});
    const draft={...(identityReviewDraft||{}),identityReviewed:true};identityReviewDraft=null;identityReviewSourceId=0;
    await attentionFor(id,draft);
  }catch(e){alert(e.message)}
}
async function linkIdentityCurrent(sourceId,targetId){
  if(!sourceId||!targetId||sourceId===targetId){return attentionFor(targetId,{...(identityReviewDraft||{}),identityReviewed:true})}
  if(!confirm('¿Vincular esta cita con la ficha seleccionada?\n\nLa ficha duplicada solo se eliminará si no tiene atenciones clínicas.'))return;
  try{
    const result=await api(`/api/patients/${Number(sourceId)}/link/${Number(targetId)}`,{method:'POST'});
    invalidateAttentionWeekCache();
    const target=Number(result?.patient?.id||targetId);const draft={...(identityReviewDraft||{}),identityReviewed:true};identityReviewDraft=null;identityReviewSourceId=0;
    await attentionFor(target,draft);
  }catch(e){alert(e.message)}
}
async function linkIdentityHistorical(sourceId,hid){
  if(!confirm('¿Usar esta ficha histórica como el paciente correcto?\n\nSe conservarán sus datos históricos y la cita actual se moverá a esa ficha.'))return;
  try{
    const activated=await api(`/api/historical/${Number(hid)}/activate`,{method:'POST'});
    if(Number(activated.id)!==Number(sourceId)){
      await api(`/api/patients/${Number(sourceId)}/link/${Number(activated.id)}`,{method:'POST'});
    }
    invalidateAttentionWeekCache();
    const draft={...(identityReviewDraft||{}),identityReviewed:true};identityReviewDraft=null;identityReviewSourceId=0;
    await attentionFor(Number(activated.id),draft);
  }catch(e){alert(e.message)}
}

async function editPatientFromAttention(id){
  attentionDraft=captureAttentionDraft();
  const p=await api('/api/patients/'+id);
  openModal(`<h2>Completar datos del paciente</h2><p class="muted">Completa la información faltante. Al guardar volverás directamente a esta atención.</p>${patientForm(p)}<div class="actions"><button onclick="returnToAttention(${id})">Cancelar</button><button class="primary" onclick="savePatientAndReturnToAttention(${id})">Guardar y volver a atención</button></div>`);
  setTimeout(()=>{
    const missing=missingPatientFields(p);
    if(missing.includes('cédula'))$('#fCedula')?.focus();
    else if(missing.includes('celular'))$('#fCel')?.focus();
    else if(missing.includes('correo'))$('#fMail')?.focus();
    schedulePatientSimilarity(Number(id));
  },0);
}
async function savePatientAndReturnToAttention(id){
  try{
    await api('/api/patients/'+id,{method:'PUT',body:JSON.stringify(getPatientForm())});
    await searchPatients();
    await returnToAttention(id);
  }catch(e){alert(e.message)}
}
async function returnToAttention(id){
  const draft=attentionDraft;
  attentionDraft=null;
  await attentionFor(id,draft);
}
async function attentionFor(id,draft=null){
  const p=await api('/api/patients/'+id);
  if(!draft?.identityReviewed&&patientNameWords(p.nombre||'').length<3){openIdentityReview(p,draft);return}
  if(!procedures.length)procedures=await api('/api/procedures');
  const draftServices=Array.isArray(draft?.selectedServices)?draft.selectedServices:(draft?.selectedService?[draft.selectedService]:[]);
  selectedServices=new Set(draftServices.map(serviceKey).filter(Boolean));
  attentionServiceValues={...(draft?.procedureValues||{})};
  if(draft?.selectedService&&draft?.valorProc!==undefined&&draft?.selectedService!=='CONSULTA')attentionServiceValues[serviceKey(draft.selectedService)]=draft.valorProc;
  attentionContext={patient:p,manualSubsequent:!!draft?.manualSubsequent,stagedId:Number(draft?.stagedId||0)};
  attentionSaveInFlight=false;
  const fecha=draft?.fecha||toISO(new Date());
  const cancelAction=Number(draft?.stagedId||0)?`attendConfirmafyStaged(${Number(draft.stagedId)},'${esc(fecha)}')`:`openPatient(${id},currentPatientSource)`;
  openModal(`<div class="attention-form-modal"><div class="modal-form-heading attention-heading"><h2>Nueva atención</h2><p>Confirma el paciente y selecciona exactamente la atención realizada.</p></div><div class="attention-patient-card"><div class="attention-patient-main"><span>Paciente</span><b>${esc(p.nombre)}</b><small>${esc(p.cedula||'Sin cédula o identificación registrada')}</small></div>${attentionMissingActions(p,id)}</div><div id="attentionStatus"></div><div class="attention-date-card"><label for="aFecha">Fecha de atención</label><input id="aFecha" type="date" value="${fecha}"></div><div class="service-title enhanced"><div><b>Selecciona la atención</b><small>No hay ninguna opción marcada por defecto.</small></div><span id="serviceSelectionHint">0 seleccionadas</span></div><div class="service-groups">${serviceCardsHtml()}</div><div id="procedureValuesBox" class="procedure-values-box hidden"></div><div class="form-field attention-observation"><label for="aObs">Observación</label><textarea id="aObs" placeholder="Observación opcional">${esc(draft?.observacion||'')}</textarea></div><div class="actions form-actions"><button class="cancel-btn" onclick="${cancelAction}">Cancelar</button><button id="saveAttentionBtn" class="primary" onclick="saveAttention(${id})">Guardar atención</button></div></div>`);
  renderAttentionStatus();
  renderSelectedServiceValues();
}
function currentDetectedStatus(){
  if(!attentionContext)return 'N';
  if(attentionContext.patient.suggested_type==='S')return 'S';
  return attentionContext.manualSubsequent?'S':'N';
}
function renderAttentionStatus(){
  const box=$('#attentionStatus');if(!box||!attentionContext)return;
  const original=attentionContext.patient.suggested_type;
  const current=currentDetectedStatus();
  const last=attentionContext.patient.ultima_atencion;
  if(current==='S'){
    const corrected=original==='N'&&attentionContext.manualSubsequent;
    const hist=attentionContext.patient.historical;
    box.innerHTML=`<div class="detected-status subsequent"><div><span>Tipo de paciente detectado</span><strong>SUBSECUENTE</strong>${last?`<small>Última atención registrada: ${fmtDate(last)}</small>`:hist?`<small>${esc(historicalLastLabel(attentionContext.patient))}</small>`:corrected?'<small>Marcado manualmente por historial anterior no disponible.</small>':''}</div>${corrected?'<button type="button" onclick="toggleLegacySubsequent()">Deshacer corrección</button>':''}</div>`;
  }else{
    box.innerHTML=`<div class="legacy-subsequent-inline"><div><b>¿Paciente de años anteriores?</b><small>Si ya se atendía antes y ese historial no está en la base, puedes corregirlo.</small></div><button type="button" class="legacy-button" onclick="toggleLegacySubsequent()">Marcar como subsecuente</button></div>`;
  }
}
function toggleLegacySubsequent(){if(!attentionContext||attentionContext.patient.suggested_type==='S')return;attentionContext.manualSubsequent=!attentionContext.manualSubsequent;renderAttentionStatus()}
async function saveAttention(id){
  if(attentionSaveInFlight)return;
  const saveBtn=$('#saveAttentionBtn');
  attentionSaveInFlight=true;
  if(saveBtn){saveBtn.disabled=true;saveBtn.dataset.originalText=saveBtn.textContent;saveBtn.textContent='Guardando…'}
  let completed=false;
  try{
    const fecha=$('#aFecha').value;
    const patient={...(attentionContext?.patient||{})};
    captureProcedureValues();
    const serviceNames=selectedServiceOrder();
    if(!serviceNames.length)throw Error('Selecciona al menos una atención.');
    const services=serviceNames.map(name=>{
      if(name==='CONSULTA')return {procedimiento:null,valor:40};
      const raw=attentionServiceValues[name];
      if(raw===undefined||raw===null||String(raw).trim()==='')throw Error(`Ingresa el valor de ${serviceLabel(name)}.`);
      const valor=Number(raw);if(Number.isNaN(valor)||valor<0)throw Error(`El valor de ${serviceLabel(name)} no es válido.`);
      return {procedimiento:name,valor};
    });
    const tipo=(attentionContext?.patient?.suggested_type==='N'&&attentionContext?.manualSubsequent)?'S':null;
    const saved=await api('/api/visits/batch',{method:'POST',body:JSON.stringify({patient_id:id,fecha,tipo,services,observacion:$('#aObs').value||null})});
    completed=true;
    const stagedId=Number(attentionContext?.stagedId||0);
    if(stagedId){
      try{await api(`/api/agenda/confirmafy-staged/${stagedId}/attended`,{method:'POST',body:JSON.stringify({patient_id:id})});confirmafyStagedById.delete(stagedId);invalidateAttentionWeekCache()}catch(e){console.warn('No se pudo marcar la cita externa como atendida:',e)}
    }
    closeModal();
    if(saved?.pending){
      setBillingPendingSummary(saved.pending);
      setAgendaPendingBadge(saved.pending.agenda||0);
    }
    await loadWeek(fecha,fecha);
    show('inicio');
    if(serviceNames.includes('CONSULTA')){
      const receipt=receiptDataFromHome(id,fecha);
      if(receipt)showAttentionSlip(receipt.visit,receipt.patient,receipt.dayNumber,true);
      else{
        const consultationSaved=(saved?.items||[]).find(x=>!String(x?.procedimiento||'').trim())||saved?.items?.[0]||saved;
        showAttentionSlip(consultationSaved,patient,patientDayNumber(fecha,id),true);
      }
    }
  }catch(e){alert(e.message)}
  finally{
    if(!completed){
      attentionSaveInFlight=false;
      const btn=$('#saveAttentionBtn');
      if(btn){btn.disabled=false;btn.textContent=btn.dataset.originalText||'Guardar atención'}
    }
  }
}

function receiptNameLines(name){
  const parts=String(name||'').trim().toUpperCase().split(/\s+/).filter(Boolean);
  if(!parts.length)return ['SIN NOMBRE',''];
  if(parts.length===1)return [parts[0],''];
  // En la base del consultorio el nombre se registra como APELLIDO APELLIDO NOMBRE(S).
  return [parts.slice(0,2).join(' '),parts.slice(2).join(' ')];
}
function attentionSlipHtml(visit,patient,dayNumber=null){
  const isNew=visit?.tipo==='N';
  const phone=formatPhoneValue(patient?.celular||'')||'Sin registrar';
  const birth=patient?.fecha_nacimiento?fmtDate(patient.fecha_nacimiento):'Sin registrar';
  const number=dayNumber||'';
  const [surnameLine,givenLine]=receiptNameLines(patient?.nombre||'');
  return `<div id="attentionSlip" class="attention-slip receipt-card ${isNew?'new':'subsequent'}">
    <div class="receipt-brand-row">
      <img class="receipt-brand-icon" src="/static/doctor_isotype.png" alt="">
      <div class="receipt-title">RECIBO DE CONSULTA MÉDICA</div>
    </div>
    <div class="receipt-date-row"><span>Fecha:</span><strong>${fmtDate(visit?.fecha||toISO(new Date()))}</strong></div>
    <div class="receipt-name-block"><span>Nombre</span><strong><em>${esc(surnameLine)}</em>${givenLine?`<em>${esc(givenLine)}</em>`:''}</strong></div>
    ${isNew?`<div class="receipt-line-row birth-row"><span>Fecha de nacimiento:</span><strong>${esc(birth)}</strong></div>`:''}
    ${appPreferences.show_blood_pressure!==false?`<div class="receipt-pressure-row"><span>Presión Arterial:</span><span class="receipt-pressure-box" aria-hidden="true"></span></div>`:''}
    <div class="receipt-line-row"><span>Teléfono:</span><strong>${esc(phone)}</strong></div>
    ${number?`<div class="receipt-turn-row"><span>Turno:</span><strong>${number}</strong></div>`:''}
    <div class="receipt-status-row">
      <div class="receipt-check-item"><span class="receipt-check-box">${isNew?'✓':''}</span><b>PRIMERO</b></div>
      <div class="receipt-check-item"><span class="receipt-check-box">${isNew?'':'✓'}</span><b>SUBSECUENTE</b></div>
    </div>
  </div>`;
}
function showAttentionSlip(visit,patient,dayNumber=null,justSaved=false){
  lastAttentionSlipData={visit,patient,dayNumber};
  const html=attentionSlipHtml(visit,patient,dayNumber);
  const title=justSaved?'Atención guardada ✓':'Recibo de consulta médica';
  const note=justSaved?'Ficha lista para pasar al papelito o imprimir en térmica de 80 mm.':'Este es el mismo recibo de esa atención; puedes reimprimirlo cuando lo necesites.';
  openModal(`<div class="attention-slip-modal"><h2>${title}</h2><p class="muted">${note}</p>${html}<div class="actions attention-slip-actions"><button onclick="closeModal()">Cerrar</button><button class="primary" onclick="printAttentionSlip()">🖨 Imprimir 80 mm</button></div></div>`);
}
function printAttentionSlipData(visit,patient,dayNumber=null){
  const card=attentionSlipHtml(visit,patient,dayNumber);
  document.querySelector('#receiptPrintFrame')?.remove();
  const frame=document.createElement('iframe');
  frame.id='receiptPrintFrame';
  frame.title='Impresión de recibo';
  frame.setAttribute('aria-hidden','true');
  Object.assign(frame.style,{position:'fixed',right:'-10000px',bottom:'0',width:'80mm',height:'160mm',border:'0',opacity:'0',pointerEvents:'none'});
  document.body.appendChild(frame);
  const doc=frame.contentDocument||frame.contentWindow?.document;
  if(!doc){frame.remove();alert('No se pudo preparar la impresión. Intenta nuevamente.');return}
  let printing=false,cleaned=false;
  const cleanup=()=>{if(cleaned)return;cleaned=true;setTimeout(()=>frame.remove(),120)};
  const doPrint=()=>{
    if(printing||cleaned)return;
    printing=true;
    try{
      const win=frame.contentWindow;
      if(!win)throw Error('Ventana de impresión no disponible');
      try{win.addEventListener('afterprint',cleanup,{once:true})}catch{}
      win.focus();
      win.print();
      setTimeout(cleanup,120000);
    }catch{
      frame.remove();
      alert('No se pudo abrir la impresión. Intenta nuevamente.');
    }
  };
  const printWhenReady=()=>{
    const img=doc.querySelector('.receipt-brand-icon');
    if(img&&!img.complete){
      let fired=false;
      const ready=()=>{if(fired)return;fired=true;setTimeout(doPrint,80)};
      img.addEventListener('load',ready,{once:true});
      img.addEventListener('error',ready,{once:true});
      setTimeout(ready,700);
    }else setTimeout(doPrint,80);
  };
  frame.onload=printWhenReady;
  doc.open();
  doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Recibo de consulta médica</title><style>
    *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Helvetica,sans-serif}
    body{width:74mm;padding:2.5mm 2mm;margin:0 auto}.attention-slip{width:100%;border:1.2px solid #111;padding:3.5mm;background:#fff}
    .receipt-brand-row{display:grid;grid-template-columns:12mm 1fr;gap:2mm;align-items:center;padding-bottom:2.6mm;border-bottom:1px solid #222}.receipt-brand-icon{width:11mm;height:11mm;object-fit:contain;filter:grayscale(1) contrast(1.35)}
    .receipt-title{text-align:center;font-size:12.5pt;font-weight:900;line-height:1.12;letter-spacing:.2px}.receipt-date-row,.receipt-line-row,.receipt-turn-row,.receipt-pressure-row{display:flex;align-items:center;gap:2mm;padding:2.1mm 0;border-bottom:1px dotted #777}.receipt-date-row span,.receipt-line-row span,.receipt-turn-row span,.receipt-pressure-row span:first-child{font-size:9.2pt;font-weight:800;white-space:nowrap}.receipt-date-row strong,.receipt-line-row strong,.receipt-turn-row strong{font-size:10.5pt;font-weight:800;overflow-wrap:anywhere}.receipt-turn-row strong{font-size:13pt}.receipt-name-block{padding:2.8mm 0;border-bottom:1px solid #222;text-align:center}.receipt-name-block span{display:block;font-size:8.5pt;font-weight:800;margin-bottom:1.2mm}.receipt-name-block strong{display:block;font-size:11.5pt;line-height:1.2;font-weight:900;overflow-wrap:anywhere}.receipt-name-block strong em{display:block;font-style:normal}.receipt-name-block strong em+em{margin-top:.7mm}.receipt-pressure-box{display:inline-block;width:22mm;height:8mm;border:1.2px solid #111;margin-left:1mm;background:#fff}.receipt-status-row{display:grid;grid-template-columns:1fr 1fr;gap:3mm;padding-top:4mm}.receipt-check-item{display:flex;align-items:center;justify-content:center;gap:1.5mm;font-size:9pt}.receipt-check-box{display:inline-flex;width:5.5mm;height:5.5mm;border:1.5px solid #111;align-items:center;justify-content:center;font-size:12pt;font-weight:900;line-height:1}
    @media print{body{width:74mm;padding:0} @page{size:80mm auto;margin:3mm}}
  </style></head><body>${card}</body></html>`);
  doc.close();
  setTimeout(printWhenReady,350);
}
function receiptPrintPayload(visit,patient,dayNumber=null){
  return {
    fecha:fmtDate(visit?.fecha||toISO(new Date())),
    nombre:String(patient?.nombre||'').toUpperCase(),
    fecha_nacimiento:patient?.fecha_nacimiento?fmtDate(patient.fecha_nacimiento):null,
    celular:formatPhoneValue(patient?.celular||'')||null,
    turno:dayNumber?Number(dayNumber):null,
    is_new:visit?.tipo==='N'
  };
}
async function directPrintAttentionSlip(visit,patient,dayNumber=null){
  return await api('/api/printing/receipt',{method:'POST',body:JSON.stringify(receiptPrintPayload(visit,patient,dayNumber))});
}
async function printAttentionSlipByPreference(visit,patient,dayNumber=null){
  if(String(appPreferences.print_mode||'PREVIEW').toUpperCase()!=='DIRECT'){
    printAttentionSlipData(visit,patient,dayNumber);return;
  }
  try{
    await directPrintAttentionSlip(visit,patient,dayNumber);
  }catch(e){
    alert(`${e.message||'No se pudo imprimir directamente.'}\n\nAbriré la vista previa para que no pierdas el recibo.`);
    printAttentionSlipData(visit,patient,dayNumber);
  }
}
async function printAttentionSlip(){
  if(!lastAttentionSlipData)return;
  await printAttentionSlipByPreference(lastAttentionSlipData.visit,lastAttentionSlipData.patient,lastAttentionSlipData.dayNumber);
}
function receiptDataFromHome(patientId,fecha){
  const rows=weeklyData[String(fecha||'').slice(0,10)]?.visits||[];
  const groups=groupHomeVisits(rows);
  const index=groups.findIndex(g=>Number(g.patient?.id)===Number(patientId));
  if(index<0)return null;
  const g=groups[index];
  const consultations=g.visits.filter(v=>!String(v.procedimiento||'').trim());
  const primary=consultations[0];
  if(!primary)return null;
  const receiptVisit={...primary,tipo:g.isNew?'N':'S'};
  return {visit:receiptVisit,patient:g.patient,dayNumber:groups.length-index};
}
function viewReceiptFromHome(patientId,fecha){
  const data=receiptDataFromHome(patientId,fecha);if(!data){alert('No se encontró el recibo de este paciente.');return}
  showAttentionSlip(data.visit,data.patient,data.dayNumber,false);
}
async function reprintReceiptFromHome(patientId,fecha){
  const data=receiptDataFromHome(patientId,fecha);if(!data){alert('No se encontró el recibo de este paciente.');return}
  lastAttentionSlipData=data;await printAttentionSlipByPreference(data.visit,data.patient,data.dayNumber);
}


let confirmafyImportFileCache=null;
let confirmafyPatientLinks={};
let confirmafyUnmatchedByLine=new Map();
function chooseConfirmafyImport(){
  confirmafyPatientLinks={};confirmafyUnmatchedByLine=new Map();
  const el=$('#confirmafyImportFile');if(!el)return;el.value='';el.click();
}
async function postConfirmafyCsv(url,file){
  const fd=new FormData();fd.append('file',file,file.name||'confirmafy.csv');fd.append('links',JSON.stringify(confirmafyPatientLinks||{}));
  const r=await fetch(url,{method:'POST',body:fd});
  if(r.status===401){showLogin();throw Error('No autenticado')}
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw Error(d.detail||'No se pudo leer el archivo de Confirmafy.');
  return d;
}
async function previewConfirmafyImport(input){
  const incoming=input?.files?.[0]||null;
  const file=incoming||confirmafyImportFileCache;if(!file)return;
  if(incoming){confirmafyImportFileCache=file;confirmafyPatientLinks={};}
  try{
    const d=await postConfirmafyCsv('/api/agenda/import-confirmafy/preview',file);
    const conflicts=(d.conflict_examples||[]).map(x=>`<li><b>${esc(x.name)}</b> · ${fmtDate(x.date)} ${esc(fmtTime(x.time))}${x.occupied_by?.length?`<small>Ocupado por: ${esc(x.occupied_by.join(', '))}</small>`:''}</li>`).join('');
    const invalid=(d.invalid_examples||[]).map(x=>`<li>Línea ${x.line}: ${esc(x.reason)}</li>`).join('');
    confirmafyUnmatchedByLine=new Map();
    openModal(`<div class="confirmafy-import-modal"><h2>Importar agenda desde Confirmafy</h2>
      <p class="muted">Archivo: <b>${esc(file.name)}</b></p>
      <div class="confirmafy-import-summary">
        <div><b>${d.importable}</b><span>Citas nuevas</span></div>
        <div><b>${d.duplicates}</b><span>Ya existen</span></div>
        <div><b>${d.conflicts}</b><span>Horarios ocupados</span></div>
        <div><b>${d.invalid}</b><span>No válidas</span></div>
      </div>
      <div class="confirmafy-deferred-identity"><b>✓ Solo se importará la cita</b><span>No se creará, activará, vinculará ni modificará ningún paciente ahora. Cuando la persona llegue y pulses su cita en <b>Nueva atención</b>, podrás buscar/vincular su ficha o crearla con el paciente presente.</span></div>
      ${conflicts?`<details class="import-details"><summary>Ver horarios que no se importarán</summary><ul>${conflicts}</ul></details>`:''}
      ${invalid?`<details class="import-details"><summary>Ver filas no válidas</summary><ul>${invalid}</ul></details>`:''}
      <div class="import-safe-note">✓ 0 pacientes creados. ✓ 0 fichas modificadas. ✓ Los nombres y teléfonos del CSV viven solo en la agenda hasta el momento de atender. ✓ Un horario ocupado no se reemplaza.</div>
      <div class="actions"><button onclick="closeModal()">Cancelar</button><button class="primary" ${d.importable<=0?'disabled':''} onclick="confirmConfirmafyImport()">Importar ${d.importable} cita${d.importable===1?'':'s'} a la agenda</button></div></div>`);
  }catch(e){alert(e.message)}
}

async function openConfirmafyPatientLinker(line){
  const item=confirmafyUnmatchedByLine.get(Number(line));if(!item)return;
  openModal(`<div class="confirmafy-link-modal"><div class="modal-form-heading"><h2>Vincular paciente</h2><p>Confirmafy: <b>${esc(item.name)}</b>${item.phone?` · ${esc(item.phone)}`:''}</p></div><label>Buscar paciente existente</label><input id="confirmafyLinkSearch" class="master-search-input" value="${esc(item.name)}" placeholder="APELLIDOS Y NOMBRES" oninput="upperSearchInput(this);searchConfirmafyLinkPatients(${Number(line)})"><div id="confirmafyLinkResults" class="confirmafy-link-results"></div><div class="actions"><button onclick="previewConfirmafyImport(null)">Volver</button><button class="primary-soft" onclick="newPatientFromConfirmafy(${Number(line)})">Crear paciente manualmente</button></div></div>`);
  setTimeout(()=>{const el=$('#confirmafyLinkSearch');if(el){el.focus();el.setSelectionRange(el.value.length,el.value.length)}searchConfirmafyLinkPatients(Number(line));},0);
}
let confirmafyLinkSearchTimer=null;
function searchConfirmafyLinkPatients(line){
  clearTimeout(confirmafyLinkSearchTimer);confirmafyLinkSearchTimer=setTimeout(async()=>{
    const q=String($('#confirmafyLinkSearch')?.value||'').trim().toUpperCase();const box=$('#confirmafyLinkResults');if(!box)return;
    if(q.length<2){box.innerHTML='<div class="muted">Escribe al menos 2 caracteres.</div>';return}
    try{
      const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=20');
      box.innerHTML=(rows||[]).map(p=>isHistoricalPatient(p)?`<article class="confirmafy-link-row historical-result"><div><b>${esc(p.nombre)}</b><small>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')} · HISTÓRICO ${esc(historicalYears(p))}</small></div><button onclick="activateHistoricalForConfirmafy(${Number(line)},${Number(p.historical_id)})">Activar y vincular</button></article>`:`<article class="confirmafy-link-row"><div><b>${esc(p.nombre)}</b><small>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</small></div><button class="primary" onclick="selectConfirmafyPatientLink(${Number(line)},${Number(p.id)})">Vincular</button></article>`).join('')||'<div class="muted">No se encontraron pacientes.</div>';
    }catch(e){box.innerHTML=`<div class="field-error">${esc(e.message)}</div>`}
  },180);
}
async function selectConfirmafyPatientLink(line,pid){confirmafyPatientLinks[String(Number(line))]=Number(pid);await previewConfirmafyImport(null)}
async function activateHistoricalForConfirmafy(line,hid){
  try{const p=await api(`/api/historical/${Number(hid)}/activate`,{method:'POST'});confirmafyPatientLinks[String(Number(line))]=Number(p.id);await previewConfirmafyImport(null)}catch(e){alert(e.message)}
}
function newPatientFromConfirmafy(line){
  const item=confirmafyUnmatchedByLine.get(Number(line));if(!item)return;
  const seed={nombre:item.name||'',celular:item.phone||''};
  openModal(`<div class="patient-form-modal"><div class="modal-form-heading"><h2>Crear paciente</h2><p>Creación manual para vincular la cita de Confirmafy. Completa el nombre y revisa cualquier coincidencia antes de guardar.</p></div>${patientForm(seed)}<div class="confirmafy-create-warning">Si aparece una ficha parecida, vuelve a <b>Buscar y vincular</b> en lugar de crear otra.</div><div class="actions form-actions"><button class="cancel-btn" onclick="openConfirmafyPatientLinker(${Number(line)})">Buscar y vincular</button><button class="primary" onclick="saveNewPatientFromConfirmafy(${Number(line)})">Guardar y vincular</button></div></div>`);
  setTimeout(()=>schedulePatientSimilarity(0),0);
}
async function saveNewPatientFromConfirmafy(line){
  try{const data=getPatientForm();if(patientNameWords(data.nombre).length<3)throw Error('Completa al menos dos apellidos y un nombre antes de crear la ficha.');if((lastPatientSimilarity.matches||[]).length)throw Error('Hay una ficha parecida. Pulsa “Buscar y vincular” y revisa esa coincidencia antes de crear un paciente nuevo.');const p=await api('/api/patients',{method:'POST',body:JSON.stringify(data)});confirmafyPatientLinks[String(Number(line))]=Number(p.id);await previewConfirmafyImport(null)}catch(e){alert(e.message)}
}

async function confirmConfirmafyImport(){
  const file=confirmafyImportFileCache;if(!file)return;
  const btn=document.querySelector('#modal .actions .primary');if(btn){btn.disabled=true;btn.textContent='Importando…'}
  try{
    const d=await postConfirmafyCsv('/api/agenda/import-confirmafy',file);invalidateAttentionWeekCache();invalidateAgendaSlotCache();
    closeModal();
    alert(`Importación terminada.\n\n${d.importable} cita(s) agregadas a la agenda\n${d.duplicates} ya existían\n${d.conflicts} horario(s) ocupado(s) omitidos\n${d.invalid} fila(s) no válidas\n\nPacientes creados o modificados: 0\nLa identidad se resolverá únicamente cuando pulses la cita para atender.${d.offline?'\n\nLa agenda quedó en la copia de emergencia y se sincronizará al volver la nube.':''}`);
  }catch(e){alert(e.message);if(btn){btn.disabled=false;btn.textContent='Importar'}}
}

let agendaPatientCache=null;
let agendaSelectedTime='';
let agendaNativeAnchor=toISO(new Date());
let agendaNativeWeek=null;
let agendaNativeSearchTimer=null;
const agendaPatientById=new Map();
const confirmafyStagedById=new Map();
const agendaAppointmentById=new Map();
const agendaSlotsCache=new Map();
const AGENDA_SLOT_TIMES=(()=>{const out=[];for(let m=8*60;m<=17*60;m+=20){const end=m+20;if(m<14*60&&end>12*60+30)continue;out.push(`${pad(Math.floor(m/60))}:${pad(m%60)}`)}return out})();
function invalidateAgendaSlotCache(){agendaSlotsCache.clear()}
function cacheAgendaPatients(rows=[]){for(const p of rows){if(p?.id!=null)agendaPatientById.set(Number(p.id),p)}}
function agendaPhoneOk(p={}){return !!String(p.celular||'').replace(/[^0-9]/g,'')}
function mondayIso(value){const d=parseISO(value||toISO(new Date()));const day=d.getDay()===0?6:d.getDay()-1;d.setDate(d.getDate()-day);return toISO(d)}
function firstClinicAnchorOfMonth(year,monthZero){
  const d=new Date(Number(year),Number(monthZero),1);
  for(let i=0;i<7;i++){const x=new Date(d.getFullYear(),d.getMonth(),d.getDate()+i);if(x.getDay()===4)return toISO(x)}
  return toISO(d);
}
function agendaTodayIso(){return toISO(new Date())}
function agendaCurrentMonthValue(){const d=new Date();return `${d.getFullYear()}-${pad(d.getMonth()+1)}`}
function syncNativeAgendaMonthControl(value=null){
  const input=$('#agendaNativeMonth');if(!input)return;
  const d=parseISO(value||agendaNativeAnchor||agendaTodayIso());
  input.min=agendaCurrentMonthValue();
  input.value=`${d.getFullYear()}-${pad(d.getMonth()+1)}`;
}
function syncNativeAgendaWeekControl(value=null){
  const input=$('#agendaNativeWeekDate');if(!input)return;
  input.min=agendaTodayIso();
  input.value=String(value||agendaNativeAnchor||agendaTodayIso()).slice(0,10);
}
function nativeAgendaToday(){agendaNativeAnchor=agendaTodayIso();syncNativeAgendaMonthControl();syncNativeAgendaWeekControl();loadAgenda()}
function moveNativeAgendaWeek(delta){
  const d=parseISO(agendaNativeAnchor||agendaTodayIso());d.setDate(d.getDate()+Number(delta||0)*7);
  const target=toISO(d);agendaNativeAnchor=target<agendaTodayIso()?agendaTodayIso():target;
  syncNativeAgendaMonthControl();syncNativeAgendaWeekControl();loadAgenda();
}
function jumpNativeAgendaWeek(value){
  let iso=String(value||'').slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(iso))return;
  if(iso<agendaTodayIso())iso=agendaTodayIso();
  agendaNativeAnchor=iso;syncNativeAgendaMonthControl(iso);syncNativeAgendaWeekControl(iso);loadAgenda();
}
function moveNativeAgendaMonth(delta){
  const d=parseISO(agendaNativeAnchor||agendaTodayIso());
  const target=new Date(d.getFullYear(),d.getMonth()+Math.max(0,Number(delta||0)),1);
  const targetMonth=`${target.getFullYear()}-${pad(target.getMonth()+1)}`;
  if(targetMonth<agendaCurrentMonthValue()){nativeAgendaToday();return}
  agendaNativeAnchor=firstClinicAnchorOfMonth(target.getFullYear(),target.getMonth());
  syncNativeAgendaMonthControl();syncNativeAgendaWeekControl();loadAgenda();
}
function jumpNativeAgendaMonth(value){
  const m=/^(\d{4})-(\d{2})$/.exec(String(value||''));if(!m)return;
  const chosen=`${m[1]}-${m[2]}`;if(chosen<agendaCurrentMonthValue()){nativeAgendaToday();return}
  agendaNativeAnchor=firstClinicAnchorOfMonth(Number(m[1]),Number(m[2])-1);
  syncNativeAgendaMonthControl();syncNativeAgendaWeekControl();loadAgenda();
}
function agendaStatusInfo(state){const s=String(state||'PENDIENTE').toUpperCase();if(['CONFIRMADA','CONFIRMADO'].includes(s))return {label:'Confirmada',cls:'confirmed'};if(['NO_ASISTIRA','CANCELADA','CANCELADO'].includes(s))return {label:'No asistirá',cls:'cancelled'};if(s==='REAGENDADA')return {label:'Reagendada',cls:'rescheduled'};return {label:'Pendiente',cls:'pending'}}
function agendaWeekLabel(week={}){const days=week.days||[];if(!days.length)return '—';return `${fmtDate(days[0].date)} – ${fmtDate(days[days.length-1].date)}`}
async function loadAgenda(){
  const box=$('#agendaNativeGrid');if(box)box.innerHTML='<div class="panel muted">Cargando agenda…</div>';
  try{
    const d=await api('/api/agenda/week?anchor='+encodeURIComponent(agendaNativeAnchor));agendaNativeWeek=d;
    $('#agendaNativeWeekLabel').textContent=agendaWeekLabel(d);
    const visibleAnchor=(d.days||[])[0]?.date||agendaNativeAnchor;
    syncNativeAgendaMonthControl(visibleAnchor);
    syncNativeAgendaWeekControl(visibleAnchor);
    renderNativeAgenda(d);
    const pending=(d.days||[]).flatMap(x=>x.appointments||[]).filter(x=>agendaStatusInfo(x.appointment?.estado).cls==='pending').length;setAgendaPendingBadge(pending);
  }catch(e){if(box)box.innerHTML=`<div class="panel err">${esc(e.message)}</div>`}
}
function nativeAgendaRowCell(row,date,time){
  if(!row)return `<button class="native-slot free" onclick="openAgendaSlotPicker('${date}','${time}')"><b class="native-free-time">${esc(fmtTime(time))}</b><span>Disponible</span></button>`;
  const a=row.appointment||{},p=row.patient||{},staged=row.staged||{},source=String(row.source_type||''),unlinked=source==='MOBILE_UNLINKED'||source==='LEGACY_UNLINKED'||source==='CONFIRMAFY_STAGED'||source==='CONFIRMAFY_LEGACY';
  const name=staged.nombre||p.nombre||'PACIENTE';const status=agendaStatusInfo(a.estado);const sourceBadge=unlinked?'<small class="native-unlinked">SIN VINCULAR</small>':'';
  const action=unlinked
    ?`openUnlinkedAgendaDetail(${Number(staged.id||0)},'${date}')`
    :`openLinkedAgendaDetail(${Number(a.id||0)},${Number(p.id||0)},'${date}')`;
  return `<button class="native-slot occupied ${status.cls}" onclick="${action}"><b>${esc(name)}</b><span>${esc(status.label)}</span>${sourceBadge}</button>`;
}
function renderNativeAgenda(week={}){
  const box=$('#agendaNativeGrid');if(!box)return;const days=week.days||[];const maps=days.map(day=>{const m=new Map();for(const row of day.appointments||[]){const t=String(row.appointment?.hora||row.staged?.hora||'');if(t&&!m.has(t))m.set(t,row)}return m});
  let html='<div class="native-schedule"><div class="native-corner">HORA</div>'+days.map(d=>`<div class="native-day-head"><b>${esc(String(d.label||'').toUpperCase())}</b><span>${fmtDate(d.date)}</span></div>`).join('');
  let lunch=false;
  for(const time of AGENDA_SLOT_TIMES){if(!lunch&&time==='14:00'){html+=`<div class="native-time lunch">12:30 PM</div><div class="native-lunch" style="grid-column:span ${days.length}">ALMUERZO · 12:30 PM – 2:00 PM</div>`;lunch=true}html+=`<div class="native-time">${esc(fmtTime(time))}</div>`;days.forEach((d,i)=>{html+=`<div class="native-cell">${nativeAgendaRowCell(maps[i].get(time),d.date,time)}</div>`})}
  html+='</div>';box.innerHTML=html;
}
const agendaRecentPickerCache=new Map();
function agendaPickerPatientCard(p,date,time,compact=false){
  const last=p.ultima_atencion?`<small class="agenda-last-visit">Última atención: <b>${fmtDate(String(p.ultima_atencion).slice(0,10))}</b></small>`:'';
  const phoneOk=agendaPhoneOk(p);
  const action=phoneOk
    ?`<button class="primary" onclick="openAgendaPatient(${Number(p.id)},null,'${date||''}','${time||''}')">Agendar</button>`
    :`<div class="agenda-phone-required"><span>Falta celular</span><button type="button" onclick="editPatient(${Number(p.id)},'patients')">Completar celular</button></div>`;
  return `<article class="agenda-patient-card ${compact?'quick':''} ${phoneOk?'':'phone-missing'}"><div class="agenda-patient-main"><b>${esc(p.nombre)}</b>${patientIdentityHtml(p,true)}${last}${phoneOk?'':'<small class="agenda-phone-warning">Debes registrar un celular antes de agendar a este paciente.</small>'}</div>${action}</article>`;
}
async function loadAgendaRecentPicker(date,time){
  const box=$('#nativeAgendaRecentPatients'),label=$('#nativeAgendaRecentLabel');if(!box)return;
  const today=toISO(new Date()),anchor=(date&&date<=today)?date:today;
  if(label)label.textContent=anchor===today?'Atendidos hoy':`Atendidos el ${fmtDate(anchor)}`;
  try{
    const key=anchor;let rows;const cached=agendaRecentPickerCache.get(key);
    if(cached&&Date.now()-cached.ts<60000)rows=cached.rows;
    else{rows=await api(`/api/agenda/recent-patients?limit=8&days=1&anchor=${encodeURIComponent(anchor)}`);agendaRecentPickerCache.set(key,{ts:Date.now(),rows})}
    cacheAgendaPatients(rows||[]);
    box.innerHTML=(rows||[]).map(p=>agendaPickerPatientCard(p,date,time,true)).join('')||'<div class="agenda-recent-empty">No hay pacientes atendidos recientemente en este día.</div>';
  }catch(e){box.innerHTML=`<div class="agenda-recent-empty">${esc(e.message)}</div>`}
}
function openAgendaNewPicker(){openAgendaSlotPicker(null,null)}
function openAgendaSlotPicker(date,time){
  const slot=date&&time?`<div class="slot-highlight"><span>${fmtDate(date)}</span><strong>${esc(fmtTime(time))}</strong></div>`:'';
  openModal(`<div class="agenda-picker"><div class="modal-form-heading"><h2>Nueva cita</h2><p>Selecciona primero uno de los pacientes atendidos recientemente o busca cualquier ficha.</p></div>${slot}<div class="agenda-recent-quick"><div class="agenda-picker-section-head"><div><span>ACCESO RÁPIDO</span><b id="nativeAgendaRecentLabel">Atendidos hoy</b></div><small>Los más recientes aparecen primero.</small></div><div id="nativeAgendaRecentPatients" class="agenda-recent-quick-grid"><div class="agenda-recent-empty">Cargando pacientes recientes…</div></div></div><div class="agenda-picker-divider"><span>O BUSCA OTRO PACIENTE</span></div><input id="nativeAgendaPatientSearch" class="search uppercase-search" placeholder="CÉDULA, APELLIDOS Y NOMBRES O CELULAR" oninput="upperSearchInput(this);searchNativeAgendaPatients('${date||''}','${time||''}')"><div id="nativeAgendaPatientResults" class="agenda-results"><div class="muted">Escribe al menos 2 caracteres.</div></div><div class="actions"><button onclick="closeModal()">Cancelar</button><button class="primary-soft" onclick="newPatient(false,${date&&time?`{date:'${date}',time:'${time}'}`:'null'})">＋ Nuevo paciente</button></div></div>`);
  loadAgendaRecentPicker(date,time);
  setTimeout(()=>$('#nativeAgendaPatientSearch')?.focus(),80);
}
function searchNativeAgendaPatients(date,time){clearTimeout(agendaNativeSearchTimer);agendaNativeSearchTimer=setTimeout(async()=>{const q=String($('#nativeAgendaPatientSearch')?.value||'').trim();const box=$('#nativeAgendaPatientResults');if(!box)return;if(q.length<2){box.innerHTML='<div class="muted">Escribe al menos 2 caracteres.</div>';return}try{const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=18');cacheAgendaPatients(rows);const current=rows.filter(x=>!isHistoricalPatient(x));box.innerHTML=current.map(p=>agendaPickerPatientCard(p,date,time,false)).join('')||'<div class="muted">No se encontraron pacientes actuales.</div>'}catch(e){box.innerHTML=`<div class="err">${esc(e.message)}</div>`}},180)}
async function openLinkedAgendaDetail(appointmentId,patientId,fecha){
  try{let row=agendaAppointmentById.get(Number(appointmentId));if(!row){const d=await api(`/api/agenda/appointments/${appointmentId}`);row=d}const a=row.appointment||{},p=row.patient||await api('/api/patients/'+patientId),st=agendaStatusInfo(a.estado);agendaAppointmentById.set(Number(appointmentId),row);agendaPatientById.set(Number(p.id),p);
    openModal(`<div class="native-appointment-detail"><div class="modal-form-heading"><h2>${esc(p.nombre)}</h2><p>${fmtDate(a.fecha)} · ${esc(fmtTime(a.hora))}</p></div><div class="native-detail-status ${st.cls}">${esc(st.label)}</div>${a.nota?`<div class="native-detail-note">${esc(a.nota)}</div>`:''}<div class="actions wrap-actions"><button onclick="openPatient(${Number(p.id)},'patients')">Ver paciente</button><button onclick="attendFromAgenda(${Number(p.id)},'${String(fecha).slice(0,10)}')">✓ Atender</button><button onclick="openAgendaPatient(${Number(p.id)},${Number(a.id)})">✎ Editar cita</button><button class="danger ghost" onclick="deleteAgendaAppointment(${Number(a.id)})">Eliminar cita</button></div></div>`);
  }catch(e){alert(e.message)}
}
async function openUnlinkedAgendaDetail(itemId,fecha){
  try{const staged=await getConfirmafyStagedRow(itemId);currentStagedResolve=staged;openModal(`<div class="native-appointment-detail"><div class="modal-form-heading"><h2>${esc(staged.nombre||'Paciente')}</h2><p>${fmtDate(staged.fecha)} · ${esc(fmtTime(staged.hora))}</p></div><div class="native-detail-status pending">Pendiente · sin ficha vinculada</div><p class="muted">La identidad se resolverá cuando el paciente sea atendido.</p><div class="actions wrap-actions"><button class="primary" onclick="attendConfirmafyStaged(${Number(itemId)},'${String(fecha).slice(0,10)}')">✓ Atender</button><button class="danger ghost" onclick="deleteUnlinkedAppointment(${Number(itemId)})">Eliminar cita</button></div></div>`)}catch(e){alert(e.message)}
}
async function deleteUnlinkedAppointment(itemId){if(!confirmDeletion('¿Eliminar esta cita y liberar el horario?'))return;try{await api(`/api/agenda/unlinked/${Number(itemId)}`,{method:'DELETE'});closeModal();invalidateAgendaSlotCache();invalidateAttentionWeekCache();await loadAgenda()}catch(e){alert(e.message)}}
async function getConfirmafyStagedRow(itemId){const cached=confirmafyStagedById.get(Number(itemId));if(cached?.staged)return cached.staged;const d=await api(`/api/agenda/confirmafy-staged/${Number(itemId)}`);return d.staged}
let stagedResolveSearchTimer=null;let currentStagedResolve=null;
async function attendLegacyConfirmafy(appointmentId,fecha){try{const d=await api(`/api/agenda/confirmafy-legacy/${Number(appointmentId)}/stage`,{method:'POST'});const staged=d?.staged;if(!staged?.id)throw Error('No se pudo preparar esta cita.');confirmafyStagedById.set(Number(staged.id),{staged});invalidateAttentionWeekCache();await attendConfirmafyStaged(Number(staged.id),String(fecha||staged.fecha).slice(0,10))}catch(e){alert(e.message)}}
async function attendConfirmafyStaged(itemId,fecha){
  try{const staged=await getConfirmafyStagedRow(itemId);currentStagedResolve=staged;const target=String(fecha||staged.fecha||toISO(new Date())).slice(0,10);openModal(`<div class="staged-attend-modal"><div class="modal-form-heading"><h2>¿Nuevo paciente o subsecuente?</h2><p>Esta cita todavía no está vinculada a una ficha. Elige con el paciente presente.</p></div><div class="staged-appointment-card"><div><span>Cita</span><b>${esc(staged.nombre||'Paciente')}</b><small>${fmtDate(target)} · ${esc(fmtTime(staged.hora))}</small></div><span class="staged-safe-badge">Sin vincular</span></div><div class="identity-choice-grid"><button class="identity-choice new" onclick="newPatientFromStaged(${Number(itemId)},'${target}')"><b>＋ Nuevo paciente</b><span>Crear una ficha nueva y continuar.</span></button><button class="identity-choice existing" onclick="openSubsequentStagedSearch(${Number(itemId)},'${target}')"><b>↻ Subsecuente</b><span>Recién aquí buscar en pacientes existentes.</span></button></div><div class="actions"><button onclick="closeModal()">Cancelar</button></div></div>`)}catch(e){alert(e.message)}
}
function openSubsequentStagedSearch(itemId,fecha){const staged=currentStagedResolve;openModal(`<div class="staged-attend-modal"><div class="modal-form-heading"><h2>Buscar paciente subsecuente</h2><p>Busca por nombre, cédula o celular y selecciona la ficha correcta.</p></div><input id="stagedPatientSearch" class="master-search-input uppercase-search" value="${esc(staged?.nombre||'')}" placeholder="APELLIDOS Y NOMBRES, CÉDULA O CELULAR" oninput="upperSearchInput(this);searchStagedPatient(${Number(itemId)},'${fecha}')"><div id="stagedPatientResults" class="confirmafy-link-results"><div class="muted">Buscando…</div></div><div class="actions"><button onclick="attendConfirmafyStaged(${Number(itemId)},'${fecha}')">Volver</button></div></div>`);setTimeout(()=>searchStagedPatient(Number(itemId),fecha,true),0)}
async function searchStagedPatient(itemId,fecha,immediate=false){clearTimeout(stagedResolveSearchTimer);const run=async()=>{const q=String($('#stagedPatientSearch')?.value||'').trim().toUpperCase(),box=$('#stagedPatientResults');if(!box)return;if(q.length<2){box.innerHTML='<div class="muted">Escribe al menos 2 caracteres.</div>';return}try{const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=22');box.innerHTML=(rows||[]).slice(0,18).map(p=>isHistoricalPatient(p)?`<article class="confirmafy-link-row historical-result"><div><b>${esc(p.nombre)}</b><small>HISTÓRICO ${esc(historicalYears(p))}</small></div><button onclick="useHistoricalForStaged(${Number(itemId)},${Number(p.historical_id)},'${fecha}')">Usar esta ficha</button></article>`:`<article class="confirmafy-link-row"><div><b>${esc(p.nombre)}</b><small>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</small></div><button onclick="usePatientForStaged(${Number(itemId)},${Number(p.id)},'${fecha}')">Usar esta ficha</button></article>`).join('')||'<div class="muted">No encontramos coincidencias. Vuelve y elige Nuevo paciente si corresponde.</div>'}catch(e){box.innerHTML=`<div class="err">${esc(e.message)}</div>`}};if(immediate)return run();stagedResolveSearchTimer=setTimeout(run,180)}
async function usePatientForStaged(itemId,patientId,fecha){const target=String(fecha||toISO(new Date())).slice(0,10);if(target!==toISO(new Date())&&!confirm(`Esta cita corresponde al ${fmtDate(target)}. ¿Registrar la atención con esa fecha?`))return;await attentionFor(Number(patientId),{fecha:target,stagedId:Number(itemId)})}
async function useHistoricalForStaged(itemId,hid,fecha){try{const p=await api(`/api/historical/${Number(hid)}/activate`,{method:'POST'});invalidateAttentionWeekCache();await usePatientForStaged(Number(itemId),Number(p.id),fecha)}catch(e){alert(e.message)}}
async function newPatientFromStaged(itemId,fecha){try{const staged=currentStagedResolve?.id===Number(itemId)?currentStagedResolve:await getConfirmafyStagedRow(itemId);const seed={nombre:staged.nombre||'',celular:staged.celular||''};lastPatientSimilarity={name:'',matches:[]};openModal(`<div class="patient-form-modal"><div class="modal-form-heading"><h2>Crear paciente nuevo</h2><p>Completa la ficha con el paciente presente.</p></div>${patientForm(seed)}<label class="identity-different-confirm staged-different-confirm"><input id="stagedDifferentPerson" type="checkbox"> Si aparece una coincidencia parecida, confirmo que esta persona es distinta</label><div class="actions form-actions"><button class="cancel-btn" onclick="attendConfirmafyStaged(${Number(itemId)},'${fecha}')">Volver</button><button class="primary" onclick="saveNewPatientFromStaged(${Number(itemId)},'${fecha}')">Guardar y continuar</button></div></div>`);setTimeout(()=>schedulePatientSimilarity(0),0)}catch(e){alert(e.message)}}
async function saveNewPatientFromStaged(itemId,fecha){try{const data=getPatientForm();const sameName=String(lastPatientSimilarity.name||'').trim().toUpperCase()===String(data.nombre||'').trim().toUpperCase();if(sameName&&(lastPatientSimilarity.matches||[]).length&&!$('#stagedDifferentPerson')?.checked)throw Error('Encontramos una ficha parecida. Si realmente es otra persona, marca la confirmación antes de crearla.');const p=await api('/api/patients',{method:'POST',body:JSON.stringify(data)});await attentionFor(Number(p.id),{fecha:String(fecha||toISO(new Date())).slice(0,10),stagedId:Number(itemId),identityReviewed:true})}catch(e){alert(e.message)}}
async function attendFromAgenda(patientId,fecha){const today=toISO(new Date()),target=String(fecha||today).slice(0,10);if(target!==today&&!confirm(`Esta cita corresponde al ${fmtDate(target)}. ¿Registrar la atención con esa fecha?`))return;await attentionFor(patientId,{fecha:target})}
async function openAgendaPatient(id,appointmentId=null,preferredDate=null,preferredTime=null){
  try{let p=agendaPatientById.get(Number(id));if(!p){p=await api('/api/patients/'+id);agendaPatientById.set(Number(id),p)}if(!agendaPhoneOk(p)){alert('Este paciente no tiene celular registrado. Completa el campo Celular antes de agendar.');await editPatient(Number(id),'patients');return}agendaPatientCache=p;let dateValue=preferredDate||nextClinicDate(),timeValue=preferredTime||'',note='';if(appointmentId){let row=agendaAppointmentById.get(Number(appointmentId));if(!row){try{row=await api(`/api/agenda/appointments/${appointmentId}`)}catch{}}if(row){dateValue=String(row.appointment.fecha).slice(0,10);timeValue=row.appointment.hora||'';note=row.appointment.nota||''}}agendaSelectedTime=timeValue;openModal(`<div class="agenda-modal"><h2>${appointmentId?'Editar cita':'Nueva cita'}</h2><div class="agenda-person"><b>${esc(p.nombre)}</b><span>${esc(p.cedula||'Sin cédula registrada')}</span></div><label class="agenda-date-label">Fecha<input id="agendaDate" type="date" value="${esc(dateValue)}" onchange="agendaDateChanged(${appointmentId||'null'})"></label><div class="agenda-time-section"><div class="agenda-time-head"><div><b>Hora</b><span>Bloques de 20 minutos.</span></div><strong id="agendaSelectedTimeLabel">${timeValue?esc(fmtTime(timeValue)):'Sin seleccionar'}</strong></div><input id="agendaTime" type="hidden" value="${esc(timeValue)}"><div id="agendaTimeSlots" class="agenda-time-slots"><div class="agenda-time-loading">Cargando horarios…</div></div></div><div class="agenda-fixed-row"><div class="agenda-fixed-duration"><small>Duración</small><b>20 minutos</b></div><label>Nota (opcional)<input id="agendaNote" maxlength="80" value="${esc(note)}" placeholder="Ej. Control"></label></div><div class="agenda-native-note"><b>Agenda propia</b><span>La cita queda guardada directamente en Recepción.</span></div><div class="actions"><button onclick="closeModal()">Cancelar</button><button class="primary" onclick="saveAgendaAppointment(${appointmentId||'null'})">Guardar cita</button></div></div>`);await loadAgendaTimeSlots(appointmentId,timeValue)}catch(e){alert(e.message)}}
async function agendaDateChanged(appointmentId=null){agendaSelectedTime='';const hidden=$('#agendaTime');if(hidden)hidden.value='';const label=$('#agendaSelectedTimeLabel');if(label)label.textContent='Sin seleccionar';await loadAgendaTimeSlots(appointmentId,'')}
async function loadAgendaTimeSlots(appointmentId=null,preferred=''){const fecha=$('#agendaDate')?.value,box=$('#agendaTimeSlots');if(!fecha||!box)return;box.innerHTML='<div class="agenda-time-loading">Cargando horarios…</div>';try{const qs=new URLSearchParams({fecha});if(appointmentId)qs.set('exclude_id',appointmentId);const key=qs.toString();const cached=agendaSlotsCache.get(key);let d;if(cached&&Date.now()-cached.ts<10000)d=cached.data;else{d=await api('/api/agenda/slots?'+key);agendaSlotsCache.set(key,{ts:Date.now(),data:d})}const slots=d.slots||[];box.innerHTML=slots.map(x=>{const selected=(preferred||agendaSelectedTime)===x.time&&x.available;return `<button type="button" class="agenda-time-slot ${selected?'selected':''} ${x.available?'':'busy'}" ${x.available?'':'disabled'} onclick="selectAgendaTime('${x.time}',this)">${esc(fmtTime(x.time))}${x.available?'':' · ocupado'}</button>`}).join('')||'<div class="agenda-time-loading">No hay horarios configurados.</div>';if(preferred){const found=slots.find(x=>x.time===preferred&&x.available);if(found){selectAgendaTime(preferred,[...box.querySelectorAll('.agenda-time-slot')].find(x=>x.textContent.startsWith(fmtTime(preferred))))}else{agendaSelectedTime='';if($('#agendaTime'))$('#agendaTime').value='';if($('#agendaSelectedTimeLabel'))$('#agendaSelectedTimeLabel').textContent='Selecciona otra hora'}}}catch(e){box.innerHTML=`<div class="panel err">${esc(e.message)}</div>`}}
function selectAgendaTime(time,btn){agendaSelectedTime=time;if($('#agendaTime'))$('#agendaTime').value=time;if($('#agendaSelectedTimeLabel'))$('#agendaSelectedTimeLabel').textContent=fmtTime(time);document.querySelectorAll('.agenda-time-slot.selected').forEach(x=>x.classList.remove('selected'));btn?.classList.add('selected')}
async function saveAgendaAppointment(appointmentId=null){try{const p=agendaPatientCache;if(!p)throw Error('No se encontró el paciente.');const fecha=$('#agendaDate')?.value,hora=$('#agendaTime')?.value,nota=($('#agendaNote')?.value||'').trim();if(!fecha||!hora)throw Error('Selecciona fecha y hora.');const body=appointmentId?{fecha,hora,nota}:{patient_id:p.id,fecha,hora,nota};await singleFlightMutation(`appointment:${appointmentId||'new'}:${p.id}`,async()=>{await api(appointmentId?`/api/agenda/appointments/${appointmentId}`:'/api/agenda/appointments',{method:appointmentId?'PUT':'POST',body:JSON.stringify(body)});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda()},'Guardando cita…')}catch(e){alert(e.message)}}
async function deleteAgendaAppointment(id){if(!confirmDeletion('¿Eliminar esta cita y liberar el horario? La ficha del paciente no se borrará.'))return;try{await singleFlightMutation(`appointment:delete:${id}`,async()=>{await api(`/api/agenda/appointments/${id}`,{method:'DELETE'});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();await loadAgenda()},'Eliminando…')}catch(e){alert(e.message)}}
let billingGroupsCache=[];
let billingPreferencesCache={};
function billingPreferenceForPatient(patientId){return billingPreferencesCache[String(Number(patientId))]||null}
function billingRecipientDraft(patientId,fecha){const p=billingPreferenceForPatient(patientId);return p?.enabled?{alternate:true,identificacion:p.identificacion||'',nombre:p.nombre||'',direccion:p.direccion||'',telefono:p.telefono||'',correo:p.correo||''}:null}
function billingRecipientFromPatient(p={}){return {alternate:false,identificacion:String(p.cedula||'').trim(),nombre:String(p.nombre||'').trim(),direccion:String(p.lugar||'').trim(),telefono:String(p.celular||'').replace(/[^0-9]/g,''),correo:String(p.correo||'').trim().toLowerCase()}}
function billingRecipientForGroup(g){return billingRecipientDraft(g.patient.id,g.fecha)||billingRecipientFromPatient(g.patient)}
function billingRecipientPayload(patientId,fecha){const d=billingRecipientDraft(patientId,fecha);if(!d||!d.alternate)return {factura_otro:false};return {factura_otro:true,factura_identificacion:d.identificacion||'',factura_nombre:d.nombre||'',factura_direccion:d.direccion||'',factura_telefono:d.telefono||'',factura_correo:d.correo||''}}
function billingRecipientKind(id){const d=String(id||'').replace(/\D/g,'');return d.length===13?'RUC':d.length===10?'CÉDULA':'IDENTIFICACIÓN'}
function billingRecipientSummary(g){const d=billingRecipientDraft(g.patient.id,g.fecha);if(!d?.alternate)return '';return `<div class="billing-recipient-note"><span>Factura siempre a</span><b>${esc(d.nombre||'OTROS DATOS')}</b><small>${esc(billingRecipientKind(d.identificacion))}: ${esc(d.identificacion||'—')} · preferencia guardada</small></div>`}
function billingRecipientIdInput(el){el.value=String(el.value||'').replace(/\D/g,'').slice(0,13)}
function completeBillingEmailDomain(domain){const input=$('#brEmail');if(!input)return;const current=String(input.value||'').trim().toLowerCase();const local=(current.includes('@')?current.split('@')[0]:current).trim();if(!local){input.focus();return}input.value=local+String(domain||'').toLowerCase();input.focus()}
function billingRecipientMode(mode){const alt=mode==='alternate',box=$('#billingRecipientAlt'),patient=$('#billingRecipientPatient');box?.classList.toggle('hidden',!alt);patient?.classList.toggle('selected',!alt);$('#billingRecipientOther')?.classList.toggle('selected',alt);if($('#brAlternate'))$('#brAlternate').value=alt?'1':'0';if(alt)setTimeout(()=>$('#brId')?.focus(),0)}
function findBillingGroupCached(patientId,fecha){return billingGroupsCache.find(x=>Number(x.patient.id)===Number(patientId)&&x.fecha===String(fecha).slice(0,10))||null}
async function openBillingRecipientEditor(patientId,fecha=null){
  let p=null;if(fecha){const g=findBillingGroupCached(patientId,fecha);p=g?.patient||null}if(!p)p=await api('/api/patients/'+patientId);
  let pref=billingPreferenceForPatient(patientId);if(pref===undefined||pref===null){try{const d=await api(`/api/patients/${Number(patientId)}/billing-preference`);pref=d.preference;if(pref)billingPreferencesCache[String(Number(patientId))]=pref}catch{}}
  const alt=!!pref?.enabled,d=alt?{identificacion:pref.identificacion,nombre:pref.nombre,direccion:pref.direccion,telefono:pref.telefono,correo:pref.correo}:{identificacion:'',nombre:'',direccion:'',telefono:'',correo:''};
  openModal(`<div class="billing-recipient-editor"><div class="modal-form-heading"><h2>Preferencia de facturación</h2><p>La ficha clínica seguirá a nombre de ${esc(p.nombre||'paciente')}. Si eliges otra persona o empresa, esta preferencia se guardará para las próximas facturas.</p></div><input id="brAlternate" type="hidden" value="${alt?'1':'0'}"><div class="billing-recipient-modes"><button id="billingRecipientPatient" class="${alt?'':'selected'}" type="button" onclick="billingRecipientMode('patient')"><b>Facturar al paciente</b><span>Usar su ficha normal</span></button><button id="billingRecipientOther" class="${alt?'selected':''}" type="button" onclick="billingRecipientMode('alternate')"><b>Otra persona o empresa</b><span>Guardar como preferencia</span></button></div><div id="billingRecipientAlt" class="billing-recipient-alt ${alt?'':'hidden'}"><div class="form-grid"><div class="form-field"><label>Cédula o RUC</label><input id="brId" inputmode="numeric" maxlength="13" value="${esc(d.identificacion||'')}" oninput="billingRecipientIdInput(this)"></div><div class="form-field"><label>Nombre o razón social</label><input id="brName" class="uppercase-search" value="${esc(d.nombre||'')}" oninput="upperSearchInput(this)"></div><div class="form-field"><label>Dirección</label><input id="brAddress" value="${esc(d.direccion||'')}"></div><div class="form-field"><label>Teléfono</label><input id="brPhone" inputmode="numeric" value="${esc(d.telefono||'')}" oninput="formatPhoneInput(this)"></div><div class="form-field email-field billing-email-field"><label>Correo</label><input id="brEmail" type="email" value="${esc(d.correo||'')}" oninput="lowerEmailInput(this)"><div class="email-domain-chips"><button type="button" onclick="completeBillingEmailDomain('@gmail.com')">@gmail.com</button><button type="button" onclick="completeBillingEmailDomain('@hotmail.com')">@hotmail.com</button><button type="button" onclick="completeBillingEmailDomain('@outlook.com')">@outlook.com</button></div></div></div><div class="billing-recipient-help">Esta preferencia se guardará en la base y la respetarán tanto la emisión individual como “Emitir todas”.</div></div><div class="actions"><button onclick="closeModal()">Cancelar</button><button class="primary" onclick="saveBillingRecipientEditor(${Number(patientId)},${fecha?`'${String(fecha).slice(0,10)}'`:'null'})">Guardar preferencia</button></div></div>`)
}
async function saveBillingRecipientEditor(patientId,fecha=null){
  const alt=$('#brAlternate')?.value==='1';
  try{
    if(!alt){await api(`/api/patients/${Number(patientId)}/billing-preference`,{method:'DELETE'});delete billingPreferencesCache[String(Number(patientId))];closeModal();if($('#billingList'))await loadBilling();return}
    const ident=String($('#brId')?.value||'').replace(/\D/g,''),name=String($('#brName')?.value||'').trim().toUpperCase(),email=String($('#brEmail')?.value||'').trim().toLowerCase();
    if(![10,13].includes(ident.length))throw Error('La cédula debe tener 10 dígitos o el RUC 13 dígitos.');if(name.length<3)throw Error('Ingresa el nombre o razón social.');if(!email.includes('@'))throw Error('Ingresa un correo válido.');
    const d=await api(`/api/patients/${Number(patientId)}/billing-preference`,{method:'PUT',body:JSON.stringify({enabled:true,identificacion:ident,nombre:name,direccion:String($('#brAddress')?.value||'').trim().toUpperCase(),telefono:String($('#brPhone')?.value||'').replace(/[^0-9]/g,''),correo:email})});if(d.preference)billingPreferencesCache[String(Number(patientId))]=d.preference;closeModal();if($('#billingList'))await loadBilling();
  }catch(e){alert(e.message)}
}
async function openPatientBillingPreference(patientId){await openBillingRecipientEditor(patientId,null)}

async function loadAzurStatus(){
  const pill=$('#azurStatusPill'),base=$('#azurBaseUrl'),hint=$('#azurKeyHint'),result=$('#azurConnectionResult');
  try{
    const d=await api('/api/azur/status');
    if(base && !base.matches(':focus'))base.value=d.base_url||'';
    if(hint)hint.textContent=d.api_key_saved?`API key guardada: ${d.api_key_masked||'••••••••'}`:'No hay API key guardada.';
    if(pill){pill.textContent=d.configured?'Configurado':'Sin configurar';pill.classList.toggle('ready',!!d.configured)}
    if(result && !result.dataset.busy)result.textContent=d.configured?`AZUR configurado en ${d.domain||'tu cuenta'}. Puedes probar la conexión sin emitir comprobantes.`:'Configura la dirección y la API key para comenzar.';
    return d;
  }catch(e){if(result)result.textContent=e.message||'No se pudo leer la configuración de AZUR.';return null}
}
function openAzurConfig(){
  show('config','facturacion');
  setTimeout(()=>document.querySelector('#azurConfigPanel')?.scrollIntoView({behavior:'smooth',block:'start'}),80);
}
async function saveAzurConfig(){
  const base=String($('#azurBaseUrl')?.value||'').trim(),key=String($('#azurApiKey')?.value||'').trim(),result=$('#azurConnectionResult');
  if(!base){alert('Pega primero la dirección web de tu cuenta AZUR.');$('#azurBaseUrl')?.focus();return}
  try{
    if(result){result.dataset.busy='1';result.textContent='Guardando configuración de AZUR…'}
    await api('/api/azur/config',{method:'POST',body:JSON.stringify({base_url:base,api_key:key||null})});
    if($('#azurApiKey'))$('#azurApiKey').value='';
    if(result){result.dataset.busy='';result.textContent='Configuración guardada. La API key quedó únicamente en el .env de esta PC.'}
    await loadAzurStatus();
  }catch(e){if(result){result.dataset.busy='';result.textContent=e.message||'No se pudo guardar AZUR.'};alert(e.message||'No se pudo guardar la configuración de AZUR.')}
}
async function testAzurConnection(){
  const result=$('#azurConnectionResult'),btns=[...document.querySelectorAll('#azurConfigPanel .actions button')];
  try{
    btns.forEach(b=>b.disabled=true);
    if(result){result.dataset.busy='1';result.textContent='Probando conexión segura con AZUR… No se emitirá ninguna factura.'}
    const d=await api('/api/azur/test',{method:'POST'});
    const icon=d.ok?'✅':'⚠️';
    if(result){result.dataset.busy='';result.textContent=`${icon} ${d.message||'AZUR respondió.'}`}
    if(d.ok)alert('✅ Conexión con AZUR confirmada.\n\nLa prueba fue de solo lectura/validación y no emitió ningún comprobante.');
    else alert(d.message||'AZUR respondió, pero la API key no fue aceptada.');
  }catch(e){if(result){result.dataset.busy='';result.textContent='❌ '+(e.message||'No se pudo conectar con AZUR.')};alert(e.message||'No se pudo conectar con AZUR.')}
  finally{btns.forEach(b=>b.disabled=false)}
}
function azurInvoicePreviewHtml(d={},patientId,fecha){
  const p=d.payload||{},buyer=p.comprador||{},items=p.items||[],payments=p.pagos||[],az=d.azur||{};
  const total=payments.reduce((sum,x)=>sum+Number(x.total||0),0);
  const sent=d.already_sent?`<div class="billing-warning">⚠ Esta factura ya fue enviada a AZUR. Estado guardado: <b>${esc(az.estado||'EN PROCESO')}</b>. No se reenviará.</div>`:'';
  const lines=items.map(x=>`<div class="billing-line"><span>${esc(x.descripcion||'SERVICIO')}</span><b>${money(x.precio_unitario)}</b></div>`).join('');
  const config=d.configured?`<span class="billing-status aprobada">AZUR LISTO</span>`:`<span class="billing-status pendiente">AZUR SIN CONFIGURAR</span>`;
  const action=d.already_sent?`<button class="primary" onclick="checkAzurInvoiceStatus(${Number(patientId)},'${String(fecha).slice(0,10)}')">↻ Consultar estado AZUR/SRI</button>`:(!d.configured?`<button onclick="closeModal();openAzurConfig()">Configurar AZUR</button>`:(d.live_enabled?`<button class="primary" onclick="emitAzurInvoice(${Number(patientId)},'${String(fecha).slice(0,10)}')">⚡ Emitir factura ahora</button>`:`<span class="muted">Emisión real desactivada.</span>`));
  return `<div class="billing-queue-modal"><div class="modal-form-heading"><h2>Factura electrónica · AZUR</h2><p>Revisa antes de enviar. Si tu API key pertenece a Producción, el siguiente paso emitirá un comprobante real. Recibir una clave de acceso no significa todavía que el SRI la autorizó.</p></div>${sent}<div class="billing-recipient-note"><span>Factura a</span><b>${esc(buyer.razon_social||'')}</b><small>${esc(billingRecipientKind(buyer.identificacion))}: ${esc(buyer.identificacion||'—')} · ${esc(buyer.correo||'')}</small></div><div class="billing-lines">${lines}</div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${money(total)}</strong></div>${config}</div><div class="actions"><button onclick="closeModal()">Cancelar</button>${action}</div></div>`;
}
async function previewAzurInvoice(patientId,fecha){
  try{
    const d=await api('/api/billing/azur/preview',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha,...billingRecipientPayload(patientId,fecha)})});
    openModal(azurInvoicePreviewHtml(d,patientId,fecha));
  }catch(e){alert(e.message||'No se pudo preparar la factura para AZUR.')}
}
async function emitAzurInvoice(patientId,fecha){
  if(!confirm('¿EMITIR ESTA FACTURA REAL EN AZUR?\n\nSe enviará a tu ambiente de PRODUCCIÓN y puede generar un comprobante ante el SRI. Revisa nombre, identificación, correo, servicios y total antes de continuar.'))return;
  try{
    await singleFlightMutation(`azur:emit:${patientId}:${fecha}`,async()=>{
      const d=await api('/api/billing/azur/emit',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha,...billingRecipientPayload(patientId,fecha)})});
      closeModal();
      await loadBilling();refreshPendingBadges();
      alert('✅ AZUR recibió el comprobante.\n\nRecepción guardó la clave de acceso y BLOQUEÓ cualquier reenvío. Todavía falta confirmar la autorización del SRI.\n\nAbre nuevamente “Emitir en AZUR” y pulsa “Consultar estado AZUR/SRI”.');
    },'Enviando a AZUR…');
  }catch(e){alert(e.message||'No se pudo emitir en AZUR.')}
}

async function checkAzurInvoiceStatus(patientId,fecha){
  try{
    const d=await singleFlightMutation(`azur:status:${patientId}:${fecha}`,()=>api('/api/billing/azur/check-status',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha,...billingRecipientPayload(patientId,fecha)})}),'Consultando AZUR/SRI…');
    closeModal();await loadBilling();refreshPendingBadges();
    const extra=d.numero_factura?`\nFactura: ${d.numero_factura}`:'';
    const unlock=d.mass_emission_unlocked?'\n\n✅ La emisión masiva quedó habilitada porque ya validamos una factura real autorizada.':'';
    if(d.estado==='AUTORIZADA'&&(d.pdf_url||d.xml_url)){
      const links=`<div class="azur-document-actions">${d.pdf_url?`<button class="primary" onclick='window.open(${safeInlineJsString(d.pdf_url)},"_blank","noopener")'>📄 Abrir PDF / RIDE</button>`:''}${d.xml_url?`<button onclick='window.open(${safeInlineJsString(d.xml_url)},"_blank","noopener")'>⌘ Abrir XML</button>`:''}</div>`;
      openModal(`<div class="billing-queue-modal"><div class="modal-form-heading"><h2>✅ Factura autorizada</h2><p>AZUR/SRI confirmó el comprobante.</p></div><div class="billing-invoice-success"><span>Número de factura</span><strong>${esc(d.numero_factura||'Autorizada')}</strong></div>${links}<div class="actions"><button onclick="closeModal()">Cerrar</button></div></div>`);
    }else{
      alert((d.estado==='AUTORIZADA'?'✅ ':d.estado==='RECHAZADA'?'⚠ ':'⏳ ')+(d.message||`Estado: ${d.estado}`)+extra+unlock);
    }
  }catch(e){alert(e.message||'No se pudo consultar el estado en AZUR.')}
}

function billingGroupRows(items=[]){
  const map=new Map();
  for(const item of items){
    const key=`${item.patient.id}|${String(item.visit.fecha).slice(0,10)}`;
    if(!map.has(key))map.set(key,{patient:item.patient,fecha:String(item.visit.fecha).slice(0,10),items:[]});
    map.get(key).items.push(item);
  }
  return [...map.values()];
}
function billingGroupStatus(g){
  const states=[...new Set(g.items.map(x=>x.billing.estado))];
  return states.length===1?states[0]:'MIXTA';
}
function billingStatusBadge(state){
  const label={PENDIENTE:'PENDIENTE',APROBADA:'APROBADA',EMITIDA:'EMITIDA',MIXTA:'REVISAR'}[state]||state;
  return `<span class="billing-status ${String(state).toLowerCase()}">${label}</span>`;
}
function billingMissingFields(p={}){
  const out=[];if(!String(p.cedula||'').trim())out.push('cédula');if(!String(p.correo||'').trim())out.push('correo');return out;
}
function billingServicesHtml(g){
  return g.items.map(x=>`<div class="billing-line"><span>${serviceBadge(x.visit)}</span><b>${money(x.visit.valor)}</b></div>`).join('');
}
function billingTotal(g){return g.items.reduce((sum,x)=>sum+Number(x.visit.valor||0),0)}
function billingInvoiceNumber(g){return g.items.map(x=>x.billing.numero_factura).find(Boolean)||''}
function billingCardHtml(g){
  const state=billingGroupStatus(g), missing=billingMissingFields(g.patient), total=billingTotal(g), invoice=billingInvoiceNumber(g), alt=billingRecipientDraft(g.patient.id,g.fecha);
  let actions='';
  const recipientButton=`<button onclick="openBillingRecipientEditor(${g.patient.id},'${g.fecha}')">👤 ${alt?.alternate?'Editar datos de factura':'Facturar con otros datos'}</button>`;
  if(state==='PENDIENTE'){
    const approve=`<button class="primary billing-approve" onclick="approveBilling(${g.patient.id},'${g.fecha}')">✓ Aprobar para facturar</button>`;
    actions=alt?.alternate?`${recipientButton}${approve}`:(missing.length?`<button class="complete-patient-list-btn" onclick="editPatientFromBilling(${g.patient.id})">✎ Completar datos</button>${recipientButton}`:`${recipientButton}${approve}`);
  }else if(state==='APROBADA'){
    actions=`${recipientButton}<button class="primary" onclick="previewAzurInvoice(${g.patient.id},'${g.fecha}')">⚡ Emitir en AZUR</button><button onclick="reopenBilling(${g.patient.id},'${g.fecha}')">Volver a pendiente</button><button onclick="markBillingEmitted(${g.patient.id},'${g.fecha}')">Marcar emitida manualmente</button>`;
  }else if(state==='EMITIDA'){
    actions=`${recipientButton}<button onclick="copyBillingData(${g.patient.id},'${g.fecha}')">📋 Ver datos de factura</button>`;
  }
  const warn=missing.length&&!alt?.alternate?`<div class="billing-warning">⚠ Falta ${esc(missing.join(' y '))} para aprobar con los datos del paciente. También puedes facturar con otros datos.</div>`:'';
  const emitted=invoice?`<div class="billing-invoice-number"><span>Factura</span><b>${esc(invoice)}</b></div>`:'';
  return `<article class="billing-card ${String(state).toLowerCase()}"><div class="billing-card-head"><div><div class="billing-patient-name">${esc(g.patient.nombre)}</div><div class="billing-meta"><span><b>Cédula:</b> ${esc(g.patient.cedula||'Sin cédula')}</span><span><b>Correo:</b> ${esc(g.patient.correo||'Sin correo')}</span><span><b>Fecha:</b> ${fmtDate(g.fecha)}</span></div></div>${billingStatusBadge(state)}</div>${billingRecipientSummary(g)}${warn}<div class="billing-lines">${billingServicesHtml(g)}</div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${money(total)}</strong></div>${emitted}<div class="billing-actions">${actions}</div></div></article>`;
}
async function loadBilling(){
  try{
    const params=new URLSearchParams();
    const estado=$('#bEstado')?.value||'PENDIENTE';
    params.set('estado',estado);
    const d=await api('/api/billing?'+params.toString());
    billingPreferencesCache={...billingPreferencesCache,...(d.billing_preferences||{})};
    const groups=billingGroupRows(d.items||[]);
    billingGroupsCache=groups;
    $('#billingSummary').innerHTML=`<button onclick="setBillingStatus('PENDIENTE')"><b>${d.counts?.PENDIENTE||0}</b><span>Pendientes</span></button><button onclick="setBillingStatus('APROBADA')"><b>${d.counts?.APROBADA||0}</b><span>Aprobadas</span></button><button onclick="setBillingStatus('EMITIDA')"><b>${d.counts?.EMITIDA||0}</b><span>Emitidas</span></button>`;
    setBillingPendingSummary({billing:Number(d.counts?.PENDIENTE||0)+Number(d.counts?.APROBADA||0),billing_pending:Number(d.counts?.PENDIENTE||0),billing_approved:Number(d.counts?.APROBADA||0)});
    $('#billingList').innerHTML=groups.map(billingCardHtml).join('')||'<div class="panel muted">No hay facturaciones en este estado.</div>';
  }catch(e){$('#billingList').innerHTML=`<div class="panel err">${esc(e.message)}</div>`}
}
async function setBillingStatus(state){
  if($('#bEstado'))$('#bEstado').value=state;await loadBilling();
}
async function reviewNextBilling(){
  try{
    show('facturacion');
    const d=await api('/api/billing/next');
    if(d.billing_preference)billingPreferencesCache[String(Number(d.patient?.id||0))]=d.billing_preference;
    const groups=billingGroupRows(d.items||[]).sort((a,b)=>String(a.fecha).localeCompare(String(b.fecha)));
    if(!groups.length){alert('No hay facturas pendientes.');return}
    const g=groups[0],p=g.patient||{},missing=missingPatientFields(p).filter(x=>['cédula','correo'].includes(x)),alt=billingRecipientDraft(p.id,g.fecha);
    const services=billingServicesHtml(g);const total=money(billingTotal(g));
    const warning=missing.length&&!alt?.alternate?`<div class="data-warning"><span class="warning-icon">⚠</span><span>Falta ${esc(missing.join(' y '))} para facturar con los datos del paciente.</span></div>`:'';
    const recipient=alt?.alternate?`<div class="billing-recipient-note"><span>Factura a</span><b>${esc(alt.nombre||'OTROS DATOS')}</b><small>${esc(billingRecipientKind(alt.identificacion))}: ${esc(alt.identificacion||'—')}</small></div>`:'';
    const config=`<button onclick="openBillingRecipientEditor(${p.id},'${g.fecha}')">👤 ${alt?.alternate?'Editar datos de factura':'Facturar con otros datos'}</button>`;
    const action=alt?.alternate?`${config}<button class="primary" onclick="approveBillingAndNext(${p.id},'${g.fecha}')">✓ Aprobar y seguir</button>`:(missing.length?`<button onclick="editPatientFromBilling(${p.id})">Completar datos</button>${config}`:`${config}<button class="primary" onclick="approveBillingAndNext(${p.id},'${g.fecha}')">✓ Aprobar y seguir</button>`);
    openModal(`<div class="billing-queue-modal"><h2>Siguiente factura pendiente</h2><div class="billing-queue-patient"><b>${esc(p.nombre||'')}</b><span>${fmtDate(g.fecha)}</span></div>${recipient}${warning}<div class="billing-lines">${services}</div><div class="billing-queue-total"><span>Total</span><b>${total}</b></div><div class="actions"><button onclick="closeModal()">Cerrar</button>${action}</div></div>`);
  }catch(e){alert(e.message)}
}
async function approveBillingAndNext(patientId,fecha){
  try{
    await singleFlightMutation(`billing:approve:${patientId}:${fecha}`,async()=>{
      await api('/api/billing/approve',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha,...billingRecipientPayload(patientId,fecha)})});
      closeModal();await loadBilling();
      setTimeout(()=>reviewNextBilling(),120);
    },'Aprobando…');
  }catch(e){alert(e.message)}
}

async function emitAllPendingInvoices(){
  try{
    const pre=await api('/api/billing/azur/batch-preview');
    const c=pre.counts||{},ready=Number(c.ready||0),skipped=Number(c.skipped||0);
    if(!pre.unlocked){alert('🔒 Emisión masiva bloqueada por seguridad.\n\nPrimero emitiremos UNA factura individual real y confirmaremos que AZUR/SRI la marque AUTORIZADA. Después este botón se habilitará automáticamente.');return}
    if(!ready){alert(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`);return}
    const examples=(pre.skipped||[]).slice(0,5).map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
    const text=`¿Emitir ${ready} factura${ready===1?'':'s'} real${ready===1?'':'es'} en AZUR?\n\nSe omitirán ${skipped} por datos incompletos/estado. Cada comprobante enviado quedará bloqueado contra reenvíos y después deberá confirmarse su autorización.`+(examples?`\n\nEjemplos omitidos:\n${examples}`:'');
    if(!confirm(text))return;
    const result=await singleFlightMutation('billing:azur:emit-all',()=>api('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}'}),'Enviando facturas…');
    const r=result.counts||{};let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
    const omit=(result.skipped||[]).slice(0,8);if(omit.length)detail+='\n\nOmitidas:\n'+omit.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
    const failed=(result.failed||[]).slice(0,5);if(failed.length)detail+='\n\nFallidas:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
    alert('Lote enviado. Las enviadas quedan EN PROCESO hasta confirmar autorización SRI.\n\n'+detail);await loadBilling();await refreshPendingBadges();
  }catch(e){alert(e.message||'No se pudo completar la emisión masiva.')}
}

async function editPatientFromBilling(id){
  const p=await api('/api/patients/'+id);
  openModal(`<h2>Completar datos para facturación</h2><p class="muted">Al guardar volverás a Facturación.</p>${patientForm(p)}<div class="actions"><button onclick="closeModal()">Cancelar</button><button class="primary" onclick="savePatientFromBilling(${id})">Guardar cambios</button></div>`);
}
async function savePatientFromBilling(id){
  try{const data=getPatientForm();await singleFlightMutation(`patient:update:${id}`,async()=>{await api('/api/patients/'+id,{method:'PUT',body:JSON.stringify(data)});closeModal();await loadBilling()},'Guardando…')}catch(e){alert(e.message)}
}
async function approveBilling(patientId,fecha){
  const draft=billingRecipientDraft(patientId,fecha);
  const who=draft?.alternate?`\n\nLa factura se emitirá a: ${draft.nombre} (${billingRecipientKind(draft.identificacion)} ${draft.identificacion})`:'';
  if(!confirm('¿Aprobar esta pre-factura para emitirla en AZUR?'+who))return;
  try{await singleFlightMutation(`billing:approve:${patientId}:${fecha}`,async()=>{await api('/api/billing/approve',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha,...billingRecipientPayload(patientId,fecha)})});await loadBilling()},'Aprobando…')}catch(e){alert(e.message)}
}
async function reopenBilling(patientId,fecha){
  if(!confirm('¿Volver esta pre-factura a pendiente?'))return;
  try{await singleFlightMutation(`billing:pending:${patientId}:${fecha}`,async()=>{await api('/api/billing/pending',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha})});await loadBilling()},'Guardando…')}catch(e){alert(e.message)}
}
function findBillingGroup(patientId,fecha){
  const cards=[...document.querySelectorAll('.billing-card')];return null;
}
function identificationType(cedula){
  const d=String(cedula||'').replace(/[^0-9]/g,'');
  if(d.length===10)return 'CÉDULA';
  if(d.length===13)return 'RUC';
  return d?'REVISAR':'SIN IDENTIFICACIÓN';
}
async function copyTextValue(value,label='Dato'){
  const text=String(value??'');
  try{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
    else throw Error('clipboard');
  }catch{
    const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();
  }
  const toast=document.createElement('div');toast.className='copy-toast';toast.textContent=`${label} copiado`;
  document.body.appendChild(toast);setTimeout(()=>toast.remove(),1300);
}
function safeInlineJsString(value){return JSON.stringify(String(value??'')).replace(/'/g,'\u0027').replace(/</g,'\u003c')}
function billingFieldRow(label,value,copyLabel=label){
  const shown=String(value||'').trim()||'—';
  return `<div class="billing-copy-row"><div><small>${esc(label)}</small><b>${esc(shown)}</b></div><button ${shown==='—'?'disabled':''} onclick='copyTextValue(${safeInlineJsString(value)},${safeInlineJsString(copyLabel)})'>📋 Copiar</button></div>`;
}
async function copyBillingData(patientId,fecha){
  try{
    let g=billingGroupsCache.find(x=>Number(x.patient.id)===Number(patientId)&&x.fecha===fecha);
    if(!g){
      const d=await api(`/api/billing?estado=TODAS&desde=${fecha}&hasta=${fecha}`);
      g=billingGroupRows(d.items||[]).find(x=>Number(x.patient.id)===Number(patientId)&&x.fecha===fecha);
    }
    if(!g)throw Error('No se encontró la pre-factura');
    const p=g.patient||{},r=billingRecipientForGroup(g);
    const cedula=String(r.identificacion||'').trim();
    const telefono=String(r.telefono||'').replace(/[^0-9]/g,'');
    const correo=String(r.correo||'').toLowerCase();
    const direccion=String(r.direccion||'').trim();
    const recipientName=String(r.nombre||p.nombre||'').trim();
    const services=g.items.map(x=>`${serviceLabel(x.visit.procedimiento||'CONSULTA')} - ${money(x.visit.valor)}`).join(' | ');
    const total=money(billingTotal(g));
    const all=`Identificación: ${cedula}\nRazón social o nombre: ${recipientName}\nDirección: ${direccion}\nTeléfono: ${telefono}\nE-Mail: ${correo}\nServicios: ${services}\nTotal: ${total}`;
    const eligible=billingGroupsCache.filter(x=>['APROBADA','EMITIDA'].includes(billingGroupStatus(x)));
    const currentIndex=eligible.findIndex(x=>Number(x.patient.id)===Number(patientId)&&x.fecha===fecha);
    const next=currentIndex>=0?eligible[currentIndex+1]:null;
    const nextButton=next?`<button class="billing-next-patient" onclick="copyBillingData(${next.patient.id},'${next.fecha}')">Siguiente paciente →</button>`:`<button class="billing-next-patient" disabled>Último paciente</button>`;
    openModal(`<div class="billing-copy-sheet"><div class="billing-copy-head"><div><h2>Datos de facturación</h2><p class="muted">Estos son los datos que se usarán para la factura electrónica.</p><div class="billing-copy-recipient"><span>${r.alternate?'FACTURA CON OTROS DATOS':'DATOS DEL PACIENTE'}</span><b>${esc(recipientName)}</b><button onclick="openBillingRecipientEditor(${Number(patientId)},'${String(fecha).slice(0,10)}')">Editar</button></div></div><button class="external-billing-link" onclick="openExternalApp(\'facturero\')">Abrir Facturero Móvil ↗</button></div>
      <div class="billing-copy-grid">
        ${billingFieldRow('Identificación',cedula)}
        ${billingFieldRow('Razón social o nombre',recipientName)}
        ${billingFieldRow('Dirección / lugar',direccion)}
        ${billingFieldRow('Teléfono',telefono)}
        ${billingFieldRow('E-Mail',correo)}
      </div>
      <div class="billing-copy-services"><small>Atención / servicios</small><b>${esc(services)}</b><span>Total ${esc(total)}</span></div>
      <div class="actions billing-copy-actions"><button onclick='copyTextValue(${safeInlineJsString(all)},"Todos los datos")'>📋 Copiar todo</button>${nextButton}<button class="primary" onclick="closeModal()">Listo</button></div></div>`);
  }catch(e){alert(e.message)}
}

async function markBillingEmitted(patientId,fecha){
  openModal(`<h2>Marcar factura como emitida</h2><p class="muted">Usa esta opción solo si la factura fue emitida fuera de la integración automática de AZUR.</p><label>Número de factura<input id="invoiceNumber" placeholder="Ej. 001-001-000001234" autocomplete="off"></label><div class="actions"><button onclick="closeModal()">Cancelar</button><button class="primary" onclick="confirmBillingEmitted(${patientId},'${fecha}')">Guardar como emitida</button></div>`);
  setTimeout(()=>$('#invoiceNumber')?.focus(),0);
}
async function confirmBillingEmitted(patientId,fecha){
  try{
    const numero=($('#invoiceNumber')?.value||'').trim();if(!numero)throw Error('Ingresa el número de factura.');
    await singleFlightMutation(`billing:emit:${patientId}:${fecha}`,async()=>{
      await api('/api/billing/emit',{method:'POST',body:JSON.stringify({patient_id:patientId,fecha,numero_factura:numero})});closeModal();await loadBilling();
    },'Guardando factura…');
  }catch(e){alert(e.message)}
}

function reportServiceLabel(service){return serviceLabel(service||'CONSULTA')}
function reportThisMonth(){const now=new Date(),y=now.getFullYear(),m=now.getMonth();$('#rDesde').value=`${y}-${pad(m+1)}-01`;$('#rHasta').value=toISO(now);loadReport()}
function reportPreviousMonth(){const now=new Date(),first=new Date(now.getFullYear(),now.getMonth()-1,1),last=new Date(now.getFullYear(),now.getMonth(),0);$('#rDesde').value=toISO(first);$('#rHasta').value=toISO(last);loadReport()}
function reportChangeText(current,previous,moneyValue=false){
  const c=Number(current||0),p=Number(previous||0);
  if(!p){return c?'<span class="report-delta new">Nuevo</span>':'<span class="report-delta same">0%</span>'}
  const pct=((c-p)/p)*100;
  const cls=pct>0?'up':pct<0?'down':'same';
  const sign=pct>0?'+':'';
  return `<span class="report-delta ${cls}">${sign}${pct.toFixed(1)}%</span>`;
}
function renderReportComparison(d){
  const box=$('#reportComparison');if(!box)return;
  const c=d?.comparison;
  if(!c?.available){box.classList.add('hidden');box.innerHTML='';return}
  const prev=c.previous||{};
  const current={patients:d.patients,consultations:d.consultations,P:d.P,total:d.total};
  const cards=[
    ['Pacientes',current.patients,prev.patients,false],
    ['Consultas',current.consultations,prev.consultations,false],
    ['Procedimientos',current.P,prev.P,false],
    ['Total',current.total,prev.total,true],
  ];
  box.innerHTML=`<div class="report-comparison-head"><div><h3>Comparativo mensual</h3><span>${fmtDate(c.current_from)} — ${fmtDate(c.current_to)} vs ${fmtDate(c.previous_from)} — ${fmtDate(c.previous_to)}</span></div><small>Mismo tramo del mes anterior</small></div><div class="report-comparison-grid">${cards.map(([label,cur,old,isMoney])=>`<div class="report-comparison-card"><span>${label}</span><div><b>${isMoney?money(cur):cur}</b>${reportChangeText(cur,old,isMoney)}</div><small>Anterior: ${isMoney?money(old):old}</small></div>`).join('')}</div>`;
  box.classList.remove('hidden');
}
async function loadReport(){
  const desde=$('#rDesde').value,hasta=$('#rHasta').value;if(!desde||!hasta)return;
  try{
    const d=await api(`/api/report?desde=${desde}&hasta=${hasta}`);
    renderReportComparison(d);
    $('#reportSummary').innerHTML=`
      <div class="report-kpi"><span>Pacientes atendidos</span><b>${d.patients}</b></div>
      <div class="report-kpi"><span>Nuevos</span><b>${d.N}</b></div>
      <div class="report-kpi"><span>Subsecuentes</span><b>${d.S}</b></div>
      <div class="report-kpi"><span>Consultas</span><b>${d.consultations}</b></div>
      <div class="report-kpi"><span>Procedimientos</span><b>${d.P}</b></div>
      <div class="report-kpi money"><span>Total del período</span><b>${money(d.total)}</b></div>`;
    $('#reportServices').innerHTML=(d.services||[]).length?`<div class="report-simple-table"><div class="head"><span>Atención</span><span>Cantidad</span><span>Total</span></div>${d.services.map(x=>`<div><strong>${esc(reportServiceLabel(x.service))}</strong><span>${x.count}</span><b>${money(x.total)}</b></div>`).join('')}</div>`:`<div class="empty-state">No hay atenciones en este período.</div>`;
    $('#reportDaily').innerHTML=(d.days||[]).length?`<div class="report-daily-list">${d.days.map(x=>`<div class="report-day-row"><div><b>${fmtDate(x.fecha)}</b><small>${x.patients} paciente${x.patients===1?'':'s'}</small></div><div><span>${x.N} nuevos</span><span>${x.S} subsecuentes</span></div><div><span>${x.consultations} consultas</span><span>${x.procedures} procedimientos</span></div><strong>${money(x.total)}</strong></div>`).join('')}</div>`:`<div class="empty-state">No hay días con atenciones en este período.</div>`;
    $('#reportTable').innerHTML=(d.details||[]).length?`<div class="report-detail-wrap"><table class="report-detail-table"><thead><tr><th>Fecha</th><th>Turno</th><th>Paciente</th><th>Estado</th><th>Atención</th><th>Valor</th></tr></thead><tbody>${d.details.map(x=>`<tr><td>${fmtDate(x.fecha)}</td><td>${x.turno}</td><td><b>${esc(x.patient?.nombre||'')}</b></td><td><span class="report-status ${x.classification==='NUEVO'?'new':'sub'}">${x.classification==='NUEVO'?'Nuevo':'Subsecuente'}</span></td><td>${esc(reportServiceLabel(x.service))}</td><td><b>${money(x.value)}</b></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty-state">No hay detalle para mostrar.</div>`;
  }catch(e){alert(e.message)}
}
async function exportExcel(){
  const d=$('#rDesde').value,h=$('#rHasta').value;
  if(!d||!h)return;
  const btn=document.querySelector('.excel-export-btn');
  const original=btn?.textContent||'⬇ Exportar Excel';
  try{
    if(btn){btn.disabled=true;btn.textContent='Guardando…'}
    const result=await api(`/api/export.xlsx/save?desde=${encodeURIComponent(d)}&hasta=${encodeURIComponent(h)}`,{method:'POST'});
    alert(`Excel guardado correctamente\n\n${result.filename}\nCarpeta: ${result.folder}`);
  }catch(e){
    alert(`No se pudo exportar el Excel.\n\n${e.message||e}`);
  }finally{
    if(btn){btn.disabled=false;btn.textContent=original}
  }
}
async function exportCsv(){
  const d=$('#rDesde').value,h=$('#rHasta').value;if(!d||!h)return;
  try{
    const result=await api(`/api/export.csv/save?desde=${encodeURIComponent(d)}&hasta=${encodeURIComponent(h)}`,{method:'POST'});
    alert(`CSV guardado correctamente\n\n${result.filename}\nCarpeta: ${result.folder}`);
  }catch(e){alert(`No se pudo exportar el CSV.\n\n${e.message||e}`)}
}
async function loadProcedures(){
  try{
    procedures=await api('/api/procedures');
    $('#procList').innerHTML=procedures.map(p=>`<div class="procedure-config-row ${serviceTone(p.nombre)}"><div class="procedure-config-name"><span class="procedure-color-dot"></span><b>${esc(serviceLabel(p.nombre).toUpperCase())}</b></div><div class="procedure-config-actions"><div class="money-input compact-money"><span>$</span><input id="procVal${p.id}" type="number" min="0" step="0.01" value="${p.valor_default??''}" placeholder="Sin valor"></div><button onclick="saveProcedureValue(${p.id})">Guardar</button><button class="danger-lite" onclick="deleteProcedure(${p.id},${JSON.stringify(p.nombre)})">Eliminar</button></div></div>`).join('');
  }catch{}
}
async function saveProcedureValue(id){
  try{const raw=$(`#procVal${id}`).value;await api('/api/procedures/'+id,{method:'PUT',body:JSON.stringify({valor_default:raw===''?null:Number(raw)})});procedures=[];await loadProcedures()}
  catch(e){alert(e.message)}
}
async function deleteProcedure(id,name){
  if(!confirmDeletion(`¿Eliminar “${name}”?\n\nSi ya fue usado en atenciones anteriores, se archivará y conservará el historial.`))return;
  try{const d=await api('/api/procedures/'+Number(id),{method:'DELETE'});alert(d.message||'Procedimiento actualizado.');procedures=[];await loadProcedures()}catch(e){alert(e.message)}
}
async function addProcedure(){
  try{await api('/api/procedures',{method:'POST',body:JSON.stringify({nombre:$('#procName').value,valor_default:$('#procValue').value?Number($('#procValue').value):null})});$('#procName').value='';$('#procValue').value='';procedures=[];await loadProcedures()}
  catch(e){alert(e.message)}
}
async function loadReceptionConfig(){
  await loadPreferences(true);
  try{const d=await api('/api/printing/status');populatePrinterSelect(d||{},appPreferences)}catch{}
}
async function loadConfigTabData(tab){
  if(tab==='general')return loadReceptionConfig();
  if(tab==='agenda')return Promise.all([loadMobileConfigLinks(),loadWhatsappStatus(),loadWhatsappCloudStatus(false)]);
  if(tab==='procedimientos')return loadProcedures();
  if(tab==='facturacion')return loadAzurStatus();
  if(tab==='sistema')return refreshProtectionStatus(false);
  if(tab==='actualizaciones')return Promise.all([loadUpdateInfo(),loadWindowModeInfo()]);
}
function showConfigTab(tab='general',button=null){
  document.querySelectorAll('[data-config-section]').forEach(x=>x.classList.toggle('hidden',x.dataset.configSection!==tab));
  document.querySelectorAll('[data-config-tab]').forEach(x=>x.classList.toggle('active',x.dataset.configTab===tab));
  if(button)button.classList.add('active');
  loadConfigTabData(tab).catch(()=>{});
}

let mobileConfigCache=null;
function mobileLinkRow(label,url,copyLabel){if(!url)return'';return `<div class="mobile-link-row"><div><span>${esc(label)}</span><code>${esc(url)}</code></div><button onclick='copyTextValue(${safeInlineJsString(url)},${safeInlineJsString(copyLabel)})'>Copiar</button></div>`}
function openCloudAgenda(url){if(!url)return;window.open(url,'_blank','noopener')}
function prepareAgendaEditor(url){if(!url)return;if(!confirm('Esto guardará el modo agendador únicamente en el navegador que abras ahora.\n\nEl enlace que compartes con el doctor seguirá siendo de solo consulta.'))return;try{const u=new URL(url);u.searchParams.set('setup_editor','1');window.open(u.toString(),'_blank','noopener')}catch{window.open(url,'_blank','noopener')}}
function agendaEditorSetupUrl(url){try{const u=new URL(url);u.searchParams.set('setup_editor','1');return u.toString()}catch{return url}}
async function copyAgendaEditorSetup(url){const u=agendaEditorSetupUrl(url);await copyTextValue(u,'Activación privada del modo agendador')}
function renderCloudAgenda(cloud={}){
  const box=$('#cloudAgendaLinks'),pill=$('#cloudAgendaPill');if(!box)return;
  const registered=!!cloud.registered,doctor=cloud.doctor_url||'',editor=cloud.reception_url||'';
  if(pill){pill.textContent=registered?'ACTIVA 24/7':'POR VERIFICAR';pill.classList.toggle('ready',registered)}
  const state=registered
    ?`<div class="mobile-network-state ready"><b>Agenda Web activa 24/7</b><span>${esc(cloud.architecture||'GitHub Pages + Neon')}</span></div>`
    :`<div class="mobile-network-state"><b>Acceso preparado</b><span>${esc(cloud.last_error||'Pulsa “Verificar con Neon”.')}</span></div>`;
  box.innerHTML=`${state}${mobileLinkRow('Enlace único · modo consulta',doctor,'Agenda Web del doctor')}<div class="cloud-single-actions"><button class="primary-soft" onclick='openCloudAgenda(${safeInlineJsString(doctor)})'>Abrir Agenda</button><button class="editor-setup-btn" onclick='prepareAgendaEditor(${safeInlineJsString(editor)})'>Preparar este dispositivo</button><button class="editor-setup-btn" onclick='copyAgendaEditorSetup(${safeInlineJsString(editor)})'>Copiar activación para mi teléfono</button></div><small>Comparte únicamente el enlace de consulta. El acceso de agendador no se muestra ni se copia.</small>`;
}
async function loadMobileConfigLinks(force=false){
  const cloud=$('#cloudAgendaLinks');if(!cloud)return;
  try{
    if(!mobileConfigCache||force)mobileConfigCache=await api('/api/mobile/config'+(force?'?force_cloud=true':''));
    renderCloudAgenda(mobileConfigCache.cloud||{});
  }catch(e){cloud.innerHTML=`<div class="err">${esc(e.message)}</div>`}
}
async function rotateMobileLinks(){if(!confirm('¿Generar accesos 24/7 nuevos?\n\nEl enlace anterior y los modos agendador guardados dejarán de funcionar.'))return;try{const d=await api('/api/mobile/links/rotate',{method:'POST'});alert(d.message||'Accesos renovados.');mobileConfigCache=null;await loadMobileConfigLinks(true)}catch(e){alert(e.message)}}
let whatsappCloudCache=null,whatsappCloudCacheAt=0;
function waStatusLabel(s){s=String(s||'').toUpperCase();return ({READ:'Leído',DELIVERED:'Entregado',SENT:'Enviado',SENDING:'Enviando',FAILED:'Falló',ERROR:'Error'})[s]||s||'—'}
function waStatusTone(s){s=String(s||'').toUpperCase();if(s==='READ'||s==='DELIVERED')return'ok';if(s==='FAILED'||s==='ERROR')return'bad';return'mid'}
function renderWhatsappCloudStatus(d={}){
  const summary=$('#whatsappDeliverySummary'),list=$('#whatsappDeliveryList');if(!summary||!list)return;
  if(!d.available){summary.innerHTML=`<span>${esc(d.message||'Estado Cloud no disponible.')}</span>`;list.innerHTML='';return}
  const x=d.summary||{},bad=Number(x.FAILED||0)+Number(x.ERROR||0);
  summary.innerHTML=`<span class="wa-stat"><b>${Number(x.TOTAL||0)}</b>Total</span><span class="wa-stat ok"><b>${Number(x.DELIVERED||0)}</b>Entregados</span><span class="wa-stat ok"><b>${Number(x.READ||0)}</b>Leídos</span><span class="wa-stat ${bad?'bad':''}"><b>${bad}</b>Errores</span><small>${esc(d.message||'')}</small>`;
  const rows=(d.items||[]).slice(0,18);
  list.innerHTML=rows.length?rows.map(r=>`<div class="wa-delivery-row"><div><b>${esc(r.patient||'Sin nombre')}</b><span>${esc(r.template||'')} · ${esc(r.date||'')} ${esc(r.time||'')}</span></div><span class="wa-status ${waStatusTone(r.status)}">${esc(waStatusLabel(r.status))}</span>${r.error?`<small>${esc(r.error)}</small>`:''}</div>`).join(''):'<div class="desktop-runtime-status">Todavía no hay mensajes Cloud en los últimos 7 días.</div>';
}
async function loadWhatsappCloudStatus(force=false){
  const btn=$('#waDeliveryRefreshBtn');if(!$('#whatsappDeliverySummary'))return;
  if(!force&&whatsappCloudCache&&Date.now()-whatsappCloudCacheAt<45000){renderWhatsappCloudStatus(whatsappCloudCache);return}
  const old=btn?.textContent||'↻ Actualizar mensajes';try{if(btn){btn.disabled=true;btn.classList.add('spinning-label');btn.textContent='↻ Consultando…'}const d=await api('/api/whatsapp/cloud-status');whatsappCloudCache=d;whatsappCloudCacheAt=Date.now();renderWhatsappCloudStatus(d)}catch(e){renderWhatsappCloudStatus({available:false,message:e.message})}finally{if(btn){btn.disabled=false;btn.classList.remove('spinning-label');btn.textContent=old}}}
async function loadWhatsappStatus(){
  const pill=$('#whatsappStatusPill'),text=$('#whatsappStatusText'),testPill=$('#whatsappTestPill');if(!pill&&!text&&!testPill)return;
  try{
    const d=await api('/api/whatsapp/status');
    if(pill){pill.textContent=d.cloud_mode?'Cloud 24/7':(d.enabled?'Activo':'Pendiente');pill.classList.toggle('ready',!!(d.cloud_mode||d.enabled))}
    if(text){const rc=d.templates?.recordatorio_cita||{},ca=d.templates?.cita_agendada||{},rh=d.templates?.recordatorio_hoy||{};text.textContent=`${d.message||''} · ${rc.name||'recordatorio_cita'}: ${rc.language||'es_ES'} · ${ca.name||'cita_agendada'}: ${ca.language||'es_EC'} · ${rh.name||'recordatorio_hoy'}: ${rh.language||'es_EC'}.`}
    if(testPill){const ready=!!d.manual_test?.ready;testPill.textContent=ready?'LISTA PARA PROBAR':'FALTA CONFIGURAR';testPill.classList.toggle('ready',ready)}
    const dateInput=$('#waTestDate');if(dateInput&&!dateInput.value){const x=new Date();x.setDate(x.getDate()+1);dateInput.value=toISO(x)}
    const phone=$('#waTestPhone');if(phone&&!phone.value){phone.value=localStorage.getItem('revelo_wa_test_phone')||d.manual_test?.default_phone||''}if(phone&&!phone.dataset.persist){phone.dataset.persist='1';phone.addEventListener('input',()=>localStorage.setItem('revelo_wa_test_phone',phone.value.trim()))}
  }catch(e){if(text)text.textContent=e.message}
}
async function sendWhatsappTest(){
  const template=$('#waTestTemplate')?.value||'recordatorio_cita',phone=($('#waTestPhone')?.value||'').trim(),name=($('#waTestName')?.value||'Prueba').trim(),date=$('#waTestDate')?.value||'',time=$('#waTestTime')?.value||'',result=$('#whatsappTestResult'),btn=$('#waTestSendBtn');
  if(!phone){alert('Ingresa el número que recibirá la prueba.');$('#waTestPhone')?.focus();return}if(!date||!time){alert('Selecciona fecha y hora para mostrar en el mensaje.');return}
  localStorage.setItem('revelo_wa_test_phone',phone);
  if(!confirm(`¿Enviar UNA prueba de ${template} a ${phone}?\n\nEsto no modifica los envíos automáticos.`))return;
  const original=btn?.textContent||'📨 Enviar mensaje de prueba';
  try{if(btn){btn.disabled=true;btn.textContent='Enviando a Meta…'}if(result)result.textContent=`Enviando ${template}…`;const d=await api('/api/whatsapp/test-message',{method:'POST',body:JSON.stringify({template,phone,name,date,time})});if(result)result.textContent=`✅ ${d.template} enviada a ${d.to} · idioma ${d.language}.${d.message_id?' ID: '+d.message_id:''}`;alert('✅ Meta aceptó el mensaje de prueba.\n\nRevisa WhatsApp en tu teléfono.')}catch(e){if(result)result.textContent='❌ '+(e.message||e);alert('No se pudo enviar la prueba.\n\n'+(e.message||e))}finally{if(btn){btn.disabled=false;btn.textContent=original}}
}
async function loadPreferences(updateUi=true){
  try{
    const d=await api('/api/preferences');appPreferences={...appPreferences,...d};
    if(updateUi){
      const mode=$('#printModeSelect');if(mode)mode.value=appPreferences.print_mode||'PREVIEW';
      const pressure=$('#showBloodPressureToggle');if(pressure)pressure.checked=appPreferences.show_blood_pressure!==false;
      const toggle=$('#confirmDeleteToggle');if(toggle)toggle.checked=appPreferences.confirm_delete!==false;
      const auto=$('#autoLoginToggle');if(auto)auto.checked=appPreferences.auto_login!==false;
    }
    const logoutBtn=$('#logoutBtn');if(logoutBtn)logoutBtn.classList.toggle('hidden',appPreferences.auto_login!==false);
    return appPreferences;
  }catch{return appPreferences}
}
function populatePrinterSelect(info={},prefs=appPreferences){
  const select=$('#printerSelect'),status=$('#printerStatusText');if(!select)return;
  const printers=Array.isArray(info.printers)?info.printers:[];
  const selected=String(prefs.printer||'');
  const def=String(info.default_printer||'');
  select.innerHTML=`<option value="">Predeterminada de Windows${def?` · ${esc(def)}`:''}</option>`+printers.map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');
  if(selected && printers.includes(selected))select.value=selected;else select.value='';
  if(status){
    if(info.supported===false)status.textContent='Impresión directa no disponible: '+(info.error||'Windows no informó impresoras.');
    else status.textContent=selected?`Seleccionada: ${selected}`:(def?`Predeterminada: ${def}`:'No hay impresora predeterminada.');
  }
}
function renderConnectionSummary(cloud={}){
  const grid=$('#systemStatusGrid');if(!grid)return;
  const cloudText=cloud.configured?(cloud.idle?'En espera · ahorro activo':(cloud.online?'En línea':'Sin Internet · usando copia local')):'Nube no configurada';
  const sync=cloud.last_sync?fmtDateTime(cloud.last_sync):'Aún no disponible';
  const success=cloud.last_success?fmtDateTime(cloud.last_success):(cloud.online?'Ahora':'Aún no registrada');
  const pending=Number(cloud.pending||0);
  const pendingText=pending?`${pending} pendiente${pending===1?'':'s'} de subir`:'Todo sincronizado';
  grid.innerHTML=`<div><span>Conexión con Neon</span><b>${esc(cloudText)}</b><small>${cloud.online?'La nube está disponible.':'La copia local permite seguir trabajando.'}</small></div><div><span>Última conexión correcta</span><b>${esc(success)}</b></div><div><span>Última copia recibida</span><b>${esc(sync)}</b><small>Datos guardados localmente en esta PC.</small></div><div><span>Cambios por enviar</span><b>${esc(pendingText)}</b><small>${pending?'Se enviarán al volver Internet.':'No hay cambios esperando sincronización.'}</small></div>`;
}
async function loadSystemStatus(){
  const grid=$('#systemStatusGrid');
  try{
    const d=await api('/api/system-status');
    appPreferences={...appPreferences,...(d.preferences||{})};
    const mode=$('#printModeSelect');if(mode)mode.value=appPreferences.print_mode||'PREVIEW';
    const pressure=$('#showBloodPressureToggle');if(pressure)pressure.checked=appPreferences.show_blood_pressure!==false;
    const toggle=$('#confirmDeleteToggle');if(toggle)toggle.checked=appPreferences.confirm_delete!==false;
    const auto=$('#autoLoginToggle');if(auto)auto.checked=appPreferences.auto_login!==false;
    populatePrinterSelect(d.printing||{},appPreferences);
    renderConnectionSummary(d.cloud||{});
    return d;
  }catch(e){if(grid)grid.innerHTML=`<div class="system-status-error">No se pudo leer el estado: ${esc(e.message||'')}</div>`;return null}
}
async function saveReceiptSettings(){
  const mode=$('#printModeSelect')?.value||'PREVIEW',printer=$('#printerSelect')?.value||'';
  const show_blood_pressure=$('#showBloodPressureToggle')?.checked!==false;
  try{
    const d=await api('/api/preferences',{method:'POST',body:JSON.stringify({print_mode:mode,printer,show_blood_pressure})});
    appPreferences={...appPreferences,...d};
    await loadReceptionConfig();
    alert(mode==='DIRECT'?'Impresión directa guardada. Reimprimir enviará el recibo a la impresora seleccionada sin abrir la vista previa.':'Vista previa guardada. Reimprimir volverá a mostrar el diálogo de impresión.');
  }catch(e){alert(e.message||'No se pudo guardar la impresión.')}
}
async function saveBehaviorSettings(){
  const confirm_delete=$('#confirmDeleteToggle')?.checked!==false;
  const auto_login=$('#autoLoginToggle')?.checked!==false;
  try{
    const d=await api('/api/preferences',{method:'POST',body:JSON.stringify({confirm_delete,auto_login})});
    appPreferences={...appPreferences,...d};
    const logoutBtn=$('#logoutBtn');if(logoutBtn)logoutBtn.classList.toggle('hidden',appPreferences.auto_login!==false);
    await loadReceptionConfig();
    alert(auto_login?'Preferencias guardadas. Recepción abrirá directamente sin pedir contraseña.':'Preferencias guardadas. En el próximo inicio se pedirá contraseña.');
  }catch(e){alert(e.message||'No se pudieron guardar las preferencias.')}
}

async function changePassword(){
  try{await api('/api/change-password',{method:'POST',body:JSON.stringify({current_password:$('#oldPass').value,new_password:$('#newPass').value})});alert('Contraseña cambiada');$('#oldPass').value='';$('#newPass').value=''}
  catch(e){alert(e.message)}
}

async function loadWindowModeInfo(retry=0){
  const status=$('#desktopRuntimeStatus'),select=$('#windowModeSelect');
  if(!status||!select)return;
  try{
    const d=await api('/api/window-mode');
    select.value=d.mode||'AUTO';
    let text='',cls='';
    if(d.webview2===true && d.pywebview===true){
      text='✅ WebView2 está listo. En modo Automático, Recepción abrirá en su ventana ligera propia.';cls='ready';
    }else if(d.edge===true){
      text='🟡 '+(d.message||'WebView2 todavía no está listo; Edge queda disponible como respaldo automático.');cls='fallback';
    }else{
      text='ℹ '+(d.message||'La preparación de WebView2 se comprobará automáticamente al abrir Recepción.');
    }
    if(d.error)text+=` Detalle: ${d.error}`;
    status.className='desktop-runtime-status '+cls;status.textContent=text;
    if((d.webview2==null||d.pywebview==null) && retry<2)setTimeout(()=>loadWindowModeInfo(retry+1),4500);
  }catch(e){status.className='desktop-runtime-status';status.textContent='No se pudo leer el estado de la ventana. Edge seguirá disponible como respaldo.'}
}
async function saveWindowMode(){
  const select=$('#windowModeSelect');if(!select)return;
  try{
    const d=await api('/api/window-mode',{method:'POST',body:JSON.stringify({mode:select.value})});
    await loadWindowModeInfo();
    const label=d.mode==='EDGE'?'Edge modo aplicación':d.mode==='WEBVIEW2'?'WebView2':'Automático';
    alert(`Modo guardado: ${label}.\n\nSe aplicará la próxima vez que abras Recepción desde el acceso directo.`);
  }catch(e){alert(e.message||'No se pudo guardar el modo de ventana.')}
}

function renderProtectionStatus(d={}){
  lastProtectionData=d;
  const lastSync=d.last_sync||null,lastBackup=d.last_backup||null,count=Number(d.backup_count||0);
  const box=$('#protectionStatus');
  if(box){
    const lastOk=d.last_success?new Date(d.last_success).getTime():0;
    const recentOk=!d.online&&lastOk&&(Date.now()-lastOk<90000);
    const cloud=d.configured?(d.idle?'🔵 En espera · ahorro de nube':(d.online?'🟢 En línea':(recentOk?'🟡 Conexión inestable':'🟠 Sin Internet'))):'⚪ Nube no configurada';
    box.innerHTML=`<div><span>Estado de nube</span><b>${cloud}</b></div><div><span>Copia de emergencia</span><b>${lastSync?fmtDateTime(lastSync):'Aún no disponible'}</b></div><div><span>Último respaldo local</span><b>${lastBackup?fmtDateTime(lastBackup):'Aún no creado'}</b></div><div><span>Respaldos conservados</span><b>${count}</b></div>`;
  }
  if(Number(d.pending||0)>0)loadSyncQueue();else clearSyncQueue();
}

function clearSyncQueue(){
  const panel=$('#syncQueuePanel');if(!panel)return;
  panel.classList.add('hidden');panel.innerHTML='';
}
function syncStatusLabel(status){
  if(status==='REVIEW')return ['⚠ Necesita revisión','review'];
  if(status==='WAITING')return ['⏳ Esperando cambio anterior','waiting'];
  return ['● Listo para sincronizar','pending'];
}
function openSyncQueueSection(section){
  const map={home:'inicio',patients:'pacientes',agenda:'agenda',facturacion:'facturacion',config:'config'};
  show(map[section]||'config');
}
async function loadSyncQueue(){
  const panel=$('#syncQueuePanel');if(!panel)return;
  panel.classList.remove('hidden');
  panel.innerHTML='<div class="sync-queue-loading">Revisando cambios pendientes…</div>';
  try{
    const d=await api('/api/offline/queue');
    const items=d.items||[];
    if(!items.length){clearSyncQueue();return}
    panel.innerHTML=`<div class="sync-queue-head"><div><h4>Cambios pendientes de sincronizar <span>${items.length}</span></h4><p>Estos cambios siguen guardados en esta PC. Puedes reintentarlos o descartarlos si sabes que fueron pruebas y no deben llegar a Neon.</p></div><div class="sync-queue-head-actions"><button onclick="retrySyncQueue()">↻ Reintentar todos</button><button class="danger-soft" onclick="discardAllSyncQueue()">🗑 Descartar todos</button></div></div>
      <div class="sync-queue-list">${items.map(it=>{const [label,cls]=syncStatusLabel(it.status);return `<div class="sync-queue-item ${cls}">
        <div class="sync-queue-item-main"><div class="sync-queue-title-row"><b>${esc(it.title)}</b><span class="sync-queue-state ${cls}">${label}</span></div>${it.detail?`<div class="sync-queue-detail">${esc(it.detail)}</div>`:''}${it.error?`<div class="sync-queue-error">${esc(it.error)}</div>`:''}<small>${it.created_at?fmtDateTime(it.created_at):''}</small></div>
        <div class="sync-queue-actions"><button onclick="openSyncQueueSection('${it.section||'config'}')">Ver en ${it.section==='agenda'?'Agenda':it.section==='facturacion'?'Facturación':it.section==='patients'?'Pacientes':it.section==='home'?'Inicio':'Configuración'}</button><button class="danger-soft" onclick='discardSyncQueueItem(${Number(it.id)},${safeInlineJsString(it.title)},${safeInlineJsString(it.detail||'')})'>🗑 Descartar</button></div>
      </div>`}).join('')}</div>`;
  }catch(e){
    panel.innerHTML=`<div class="sync-queue-error-box">No se pudo cargar el detalle de los cambios pendientes. ${esc(e.message||'')}</div>`;
  }
}
async function discardSyncQueueItem(id,title,detail){
  const what=[title,detail].filter(Boolean).join(' — ');
  if(!confirm(`¿Descartar este cambio?\n\n${what}\n\nEste cambio dejará de enviarse a Neon. Hazlo solo si fue una prueba o ya no debe conservarse.`))return;
  try{
    const d=await api(`/api/offline/queue/${id}`,{method:'DELETE'});
    await refreshProtectionStatus(true);
    if(Number(d.pending||0)===0){clearSyncQueue();refreshPendingBadges();location.reload();}
    else await loadSyncQueue();
  }catch(e){alert(e.message||'No se pudo descartar el cambio.')}
}
async function discardAllSyncQueue(){
  if(!confirm('¿Descartar TODOS los cambios pendientes?\n\nNo se enviará ninguno a Neon. Usa esta opción solo si sabes que todos fueron pruebas o cambios que no deseas conservar.'))return;
  if(!confirm('Última confirmación: ¿seguro que quieres descartar toda la cola pendiente?'))return;
  try{
    const d=await api('/api/offline/queue',{method:'DELETE'});
    clearSyncQueue();
    await refreshProtectionStatus(true);
    refreshPendingBadges();
    alert(`${d.discarded||0} cambio(s) descartado(s). La copia local se volvió a alinear con Neon cuando fue posible.`);
    location.reload();
  }catch(e){alert(e.message||'No se pudieron descartar los cambios.')}
}

async function retrySyncQueue(){
  try{
    const d=await api('/api/offline/queue/retry',{method:'POST'});
    await refreshProtectionStatus(true);
    if(Number(d.pending||0)===0){alert(`Listo. ${d.processed||0} cambio(s) quedaron sincronizados.`);clearSyncQueue();refreshPendingBadges();}
    else{const err=(d.errors||[])[0]||'Todavía hay un cambio que necesita revisión.';alert(`Quedan ${d.pending||0} cambio(s) pendientes.\n\n${err}`);await loadSyncQueue();}
  }catch(e){alert(e.message||'No se pudo reintentar la sincronización.')}
}
async function refreshProtectionStatus(force=false){
  try{
    const r=await fetch('/api/connectivity'+(force?'?force=true':''),{cache:'no-store'});
    if(!r.ok)return;const d=await r.json();renderProtectionStatus(d);renderConnectionSummary(d);
  }catch{}
}

async function recoverCloudNow(){
  const buttons=[...document.querySelectorAll('.protection-panel .actions button')];
  try{
    buttons.forEach(b=>b.disabled=true);
    setConnectionBadge('syncing','Reconectando','Comprobando Neon y sincronizando cambios…');
    const d=await api('/api/connectivity/recover',{method:'POST'});
    renderProtectionStatus(d);renderConnectionSummary(d);
    if(d.online && Number(d.pending||0)===0){
      setConnectionBadge('online','En línea','Todos los cambios están protegidos en la nube');
      alert('Conexión con Neon restablecida. Todos los cambios pendientes quedaron sincronizados.');
      refreshPendingBadges();
    }else if(d.online){
      setConnectionBadge('warning','Sincronización pendiente',`${d.pending||0} cambio(s) por sincronizar`);
      const err=(d.errors||[])[0]||d.last_error||'Hay un cambio que necesita revisión.';
      alert(`Neon está en línea, pero todavía quedan ${d.pending||0} cambio(s) pendientes.\n\n${err}`);
      await loadSyncQueue();
    }else{
      setConnectionBadge('offline','Sin Internet',d.last_error||'No se pudo conectar con Neon');
      alert(d.last_error||'No se pudo conectar con Neon. La copia de emergencia sigue activa.');
    }
  }catch(e){
    alert(e.message||'No se pudo completar la reconexión.');
  }finally{buttons.forEach(b=>b.disabled=false);await updateConnectivity(true)}
}

async function createBackupNow(){
  const btn=$('#backupNowBtn');
  try{
    if(btn){btn.disabled=true;btn.textContent='Creando respaldo…'}
    let d=null,lastErr=null;
    for(const endpoint of ['/api/backup/now','/api/data-protection/backup']){
      try{d=await api(endpoint,{method:'POST'});break}catch(e){lastErr=e}
    }
    if(!d)throw lastErr||Error('No se pudo crear el respaldo.');
    await refreshProtectionStatus(true);
    alert(`Respaldo creado correctamente.\n${fmtDateTime(d.last_backup)}`);
  }catch(e){
    const msg=String(e?.message||e||'');
    if(/not found/i.test(msg))alert('El servidor que quedó abierto es de una versión anterior. Pulsa “Reiniciar Recepción” en Programa y vuelve a intentar el respaldo.');
    else alert(msg);
  }finally{if(btn){btn.disabled=false;btn.textContent='🛡 Crear respaldo local'}}
}
async function restartReception(){
  if(!confirm('¿Reiniciar Recepción ahora?\n\nLa ventana se recargará sola cuando el nuevo proceso esté listo.'))return;
  const status=$('#updateStatus'),buttons=[...document.querySelectorAll('.update-drop-row button')];
  let oldPid=0;try{const v=await api('/api/version');oldPid=Number(v.pid||0)}catch{}
  try{buttons.forEach(b=>b.disabled=true);if(status){status.dataset.busy='1';status.textContent='Reiniciando Recepción…'}await api('/api/app/restart',{method:'POST'})}catch(e){if(!/failed to fetch|network|load failed/i.test(String(e?.message||''))){if(status)status.textContent='Esperando el nuevo proceso…'}}
  const started=Date.now();let sawDown=false;
  const poll=setInterval(async()=>{
    try{const r=await fetch('/api/version?ts='+Date.now(),{cache:'no-store'});if(!r.ok){sawDown=true;return}const d=await r.json(),pid=Number(d.pid||0);if((oldPid&&pid&&pid!==oldPid)||(sawDown&&r.ok)){clearInterval(poll);if(status)status.textContent='Recepción reiniciada correctamente.';setTimeout(()=>location.reload(),180);return}}catch{sawDown=true}
    if(Date.now()-started>45000){clearInterval(poll);buttons.forEach(b=>b.disabled=false);if(status){status.dataset.busy='';status.textContent='El reinicio no terminó. Puedes pulsar “Reiniciar Recepción” otra vez.'}}
  },850);
}
async function loadUpdateInfo(){
  try{const d=await api('/api/update/info');if($('#currentVersionBadge'))$('#currentVersionBadge').textContent='v'+d.version;if($('#updateStatus')&&!$('#updateStatus').dataset.busy)$('#updateStatus').textContent=d.message||'Selecciona un paquete ZIP de actualización.'}catch{}
}
async function applyUpdatePackage(){
  const input=$('#updatePackage'),status=$('#updateStatus'),file=input?.files?.[0];
  if(!file){alert('Selecciona primero el ZIP de actualización.');return}
  if(!confirm(`¿Aplicar ${file.name}?\n\nEl programa hará un respaldo automático antes de actualizar.`))return;
  const form=new FormData();form.append('package',file,file.name);
  try{
    if(status){status.dataset.busy='1';status.textContent='Validando paquete y creando respaldo…'}
    const r=await fetch('/api/update/apply',{method:'POST',body:form});let d={};try{d=await r.json()}catch{}
    if(!r.ok)throw Error(d.detail||'No se pudo aplicar la actualización.');
    if(status){status.textContent=`Actualización ${d.from_version} → ${d.to_version} aplicada. Reiniciando Recepción…`;status.classList.add('update-success')}
    const target=String(d.to_version||'');
    const started=Date.now();
    const poll=setInterval(async()=>{
      try{const rr=await fetch('/api/version?ts='+Date.now(),{cache:'no-store'});if(rr.ok){const vv=await rr.json();if(String(vv.version)===target){clearInterval(poll);location.reload();return}}}catch{}
      if(Date.now()-started>25000){clearInterval(poll);if(status)status.textContent='La actualización se aplicó. Si no recarga sola, abre el acceso directo del Escritorio.'}
    },700);
  }catch(e){if(status){status.textContent=e.message;status.classList.remove('update-success')}alert(e.message)}finally{if(status)delete status.dataset.busy}
}

(async()=>{try{await api('/api/me');$('#login').classList.add('hidden');$('#app').classList.remove('hidden');await init()}catch{}})();

/* v4.4.9 — integra directamente el hotfix v4.4.4 sobre la base real v4.4.3.
   El frontend queda contenido en un único archivo JavaScript. */
;(() => {
  'use strict';

  function normalizeGlobalPatientSearch() {
    const current = document.querySelector('#globalSearch');
    if (!current || current.dataset.v449SearchNormalized === '1') return;

    const input = current.cloneNode(true);
    const value = String(current.value || '');
    input.removeAttribute('oninput');
    input.removeAttribute('onfocus');
    input.removeAttribute('pattern');
    input.removeAttribute('maxlength');
    input.removeAttribute('inputmode');
    input.type = 'search';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = 'Buscar paciente por nombre, cédula, celular o correo…';
    input.value = value;
    input.dataset.v449SearchNormalized = '1';
    current.replaceWith(input);

    const wrap = input.closest('.global-search-wrap') || input.parentElement;
    if (wrap) {
      wrap.querySelectorAll('label, small, span, [data-search-label]').forEach(el => {
        const t = String(el.textContent || '').trim().toUpperCase();
        if (t === 'CÉDULA' || t === 'CEDULA') el.textContent = 'PACIENTE';
      });
    }

    const runSearch = (force = false) => {
      try {
        if (typeof upperSearchInput === 'function') upperSearchInput(input);
        else {
          const start = input.selectionStart, end = input.selectionEnd;
          input.value = String(input.value || '').toUpperCase();
          try { if (start != null) input.setSelectionRange(start, end); } catch {}
        }
        if (typeof globalSearchPatients === 'function') globalSearchPatients(force);
      } catch (err) {
        console.error('Búsqueda paciente v4.4.9:', err);
      }
    };

    input.addEventListener('input', () => runSearch(false));
    input.addEventListener('focus', () => runSearch(true));
  }

  function bootSearch444() {
    normalizeGlobalPatientSearch();
    document.addEventListener('click', () => {
      const input = document.querySelector('#globalSearch');
      if (input) input.placeholder = 'Buscar paciente por nombre, cédula, celular o correo…';
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootSearch444, { once: true });
  } else {
    bootSearch444();
  }
})();



/* v4.4.11 — el estado vacío de cédula no ocupa espacio; la validación útil se conserva. */
(()=>{
  const EMPTY_HINT='Ingresa la cédula para validarla localmente.';
  function cleanCedulaHint(){
    const modal=document.querySelector('#modal');
    const status=modal?.querySelector('.v481-id-status');
    if(!status)return;
    const text=String(status.textContent||'').trim();
    if(!text||text===EMPTY_HINT){
      if(text===EMPTY_HINT)status.textContent='';
      status.classList.add('hidden');
    }else{
      status.classList.remove('hidden');
    }
  }
  function install(){
    const modal=document.querySelector('#modal');
    if(!modal||modal.dataset.v4411CedulaCleanup==='1')return;
    modal.dataset.v4411CedulaCleanup='1';
    new MutationObserver(cleanCedulaHint).observe(modal,{childList:true,subtree:true,characterData:true});
    modal.addEventListener('input',()=>setTimeout(cleanCedulaHint,0),true);
    modal.addEventListener('change',()=>setTimeout(cleanCedulaHint,0),true);
    cleanCedulaHint();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
