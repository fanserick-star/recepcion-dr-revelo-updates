from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"
STATIC = APP / "static"
VERSION = "4.6.28"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


CONFIG_HTML = r'''    <section id="config" class="hidden config-consolidated">
      <div class="config-title-row"><div><h1>Configuración</h1><p class="muted">Lo que usas a diario primero; las opciones técnicas quedan en Avanzado.</p></div></div>
      <div class="config-tabs" role="tablist" aria-label="Secciones de configuración">
        <button class="active" data-config-tab="general" onclick="showConfigTab('general',this)">Recepción</button>
        <button data-config-tab="agenda" onclick="showConfigTab('agenda',this)">Agenda y WhatsApp</button>
        <button data-config-tab="procedimientos" onclick="showConfigTab('procedimientos',this)">Servicios y precios</button>
        <button data-config-tab="facturacion" onclick="showConfigTab('facturacion',this)">Facturación y cobros</button>
        <button data-config-tab="sistema" onclick="showConfigTab('sistema',this)">Sistema</button>
      </div>

      <div class="config-section" data-config-section="general">
        <div class="panel receipt-settings-panel compact-config-panel">
          <div class="config-panel-head"><div><h3>Recibos e impresora</h3><p class="muted">Elige cómo salen los recibos de consulta y qué impresora usar.</p></div><span class="receipt-format-pill">80 mm</span></div>
          <div class="receipt-settings-grid">
            <label><span>Cómo imprimir</span><select id="printModeSelect"><option value="PREVIEW">Mostrar vista previa</option><option value="DIRECT">Imprimir directamente</option></select><small>La vista previa permite revisar antes de imprimir.</small></label>
            <label><span>Impresora de recibos</span><select id="printerSelect"><option value="">Predeterminada de Windows</option></select><small id="printerStatusText">Buscando impresoras…</small></label>
            <label class="receipt-pressure-setting"><span>Dato opcional del recibo</span><div class="receipt-toggle-row"><b>Mostrar presión arterial</b><input id="showBloodPressureToggle" type="checkbox" checked></div></label>
          </div>
          <div class="actions"><button class="primary-soft" onclick="saveReceiptSettings()">Guardar recibos e impresora</button><button onclick="configPrintTest()">🖨 Imprimir prueba</button></div>
        </div>
        <div class="config-info-note config-safe-defaults"><b>Protecciones fijas</b><span>Recepción abre directamente en esta PC y siempre pide confirmación antes de borrar. Ya no hay interruptores que puedan desactivar esas protecciones por accidente.</span></div>
      </div>

      <div class="config-section hidden" data-config-section="agenda">
        <div class="panel compact-config-panel remote-agenda-panel">
          <div class="config-panel-head"><div><h3>Agenda Web 24/7</h3><p class="muted">Consulta y agenda desde tus dispositivos sin depender de que esta PC esté encendida.</p></div><span id="cloudAgendaPill" class="performance-pill">24/7</span></div>
          <div id="cloudAgendaLinks" class="mobile-link-box">Preparando Agenda Web…</div>
          <div class="actions remote-agenda-actions"><button onclick="loadMobileConfigLinks(true)">↻ Verificar con Neon</button><button class="primary-soft" onclick="configOpenAgenda()">Abrir Agenda</button></div>
          <details class="config-advanced"><summary>Accesos avanzados de Agenda</summary><div class="config-advanced-body"><p>Regenerar accesos invalida los enlaces y dispositivos preparados anteriormente.</p><button class="danger-lite" onclick="rotateMobileLinks()">🔑 Regenerar accesos</button></div></details>
        </div>

        <div class="panel compact-config-panel">
          <div class="config-panel-head"><div><h3>WhatsApp Cloud</h3><p class="muted">Automatización 24/7, plantillas aprobadas y entregas recientes.</p></div><span id="whatsappStatusPill" class="performance-pill">Cargando</span></div>
          <div id="whatsappStatusText" class="desktop-runtime-status">Consultando estado…</div>
          <div id="configWhatsappTemplates" class="config-template-grid"></div>
          <div class="wa-delivery-head"><b>Últimos 7 días</b><button id="waDeliveryRefreshBtn" onclick="loadWhatsappCloudStatus(true)">↻ Actualizar mensajes</button></div>
          <div id="whatsappDeliverySummary" class="wa-delivery-summary"><span>Sin consultar todavía.</span></div>
          <div id="whatsappDeliveryList" class="wa-delivery-list"></div>
        </div>

        <details class="panel compact-config-panel config-advanced whatsapp-test-panel">
          <summary>Prueba técnica de WhatsApp</summary>
          <div class="config-advanced-body">
            <p class="muted">La prueba usa el mismo Worker Cloud 24/7. No guarda tokens de Meta en esta PC y no crea pacientes ni citas reales.</p>
            <div class="whatsapp-test-grid">
              <label><span>Plantilla</span><select id="waTestTemplate"><option value="recordatorio_cita">Confirmación de cita</option><option value="cita_agendada">Cita agendada</option><option value="recordatorio_hoy">Recordatorio del día</option></select></label>
              <label><span>Número de prueba</span><input id="waTestPhone" inputmode="tel" autocomplete="off" placeholder="09xxxxxxxx"></label>
              <label><span>Nombre</span><input id="waTestName" autocomplete="off" value="Prueba" maxlength="80"></label>
              <label><span>Fecha mostrada</span><input id="waTestDate" type="date"></label>
              <label><span>Hora mostrada</span><input id="waTestTime" type="time" value="15:00" step="60"></label>
            </div>
            <div id="whatsappTestResult" class="desktop-runtime-status">No se ha enviado ninguna prueba.</div>
            <div class="actions"><button id="waTestSendBtn" class="primary-soft" onclick="sendWhatsappTest()">☁ Enviar prueba por Cloud</button><button id="configFinishWaTest" class="hidden" onclick="configFinishWhatsappTest()">Finalizar prueba</button></div>
          </div>
        </details>
      </div>

      <div class="config-section hidden" data-config-section="procedimientos">
        <div class="panel procedure-values-panel compact-config-panel">
          <div class="config-panel-head"><div><h3>Servicios y precios</h3><p class="muted">Administra los procedimientos disponibles y su valor predeterminado.</p></div></div>
          <div class="config-help-strip">Los precios se guardan con dos decimales y nunca pueden ser negativos. El historial anterior conserva sus valores originales.</div>
          <div id="procList"></div>
          <div class="compact-add-procedure"><input id="procName" class="uppercase-name" placeholder="Nuevo servicio o procedimiento" oninput="upperNameInput(this)"><input id="procValue" type="number" min="0" step="0.01" placeholder="Valor"><button class="primary-soft" onclick="addProcedure()">Agregar</button></div>
        </div>
      </div>

      <div class="config-section hidden" data-config-section="facturacion">
        <div class="config-integration-grid">
          <div class="panel compact-config-panel config-integration-card"><div><span>FACTURACIÓN ELECTRÓNICA</span><h3>AZUR</h3><p>Emisión de facturas y comunicación con SRI.</p></div><span id="azurStatusPill" class="performance-pill">Comprobando</span><div id="azurConnectionResult" class="desktop-runtime-status">Consultando conexión…</div><div class="actions"><button onclick="testAzurConnection()">🔌 Probar conexión</button></div></div>
          <div class="panel compact-config-panel config-integration-card"><div><span>COBRO CON TARJETA</span><h3>Bendo Smart</h3><p>Preparado para automatizar el cobro cuando estén disponibles el contrato y credenciales oficiales.</p></div><span id="configDataphonePill" class="performance-pill">Comprobando</span><div id="configDataphoneSummary" class="desktop-runtime-status">Consultando Bendo…</div><div class="actions"><button onclick="configValidateDataphone()">Revisar preparación</button><button onclick="configTestDataphone()">Probar API</button></div></div>
        </div>

        <details id="azurConfigPanel" class="panel compact-config-panel config-advanced">
          <summary>Configuración avanzada de AZUR</summary>
          <div class="config-advanced-body">
            <p class="muted">Normalmente no necesitas tocar estos datos después del instalador maestro.</p>
            <div class="azur-settings-grid"><label><span>Dirección de AZUR</span><input id="azurBaseUrl" type="url" placeholder="https://azur.com.ec" autocomplete="off"></label><label><span>API key</span><input id="azurApiKey" type="password" placeholder="Dejar vacío para conservar la guardada" autocomplete="new-password"><small id="azurKeyHint">No hay API key guardada.</small></label></div>
            <div class="actions"><button class="primary-soft" onclick="saveAzurConfig()">Guardar AZUR</button></div>
          </div>
        </details>

        <details class="panel compact-config-panel config-advanced">
          <summary>Configuración avanzada de Bendo</summary>
          <div id="configDataphoneBody" class="config-advanced-body"><div class="system-status-loading">Cargando configuración…</div></div>
        </details>
      </div>

      <div class="config-section hidden" data-config-section="sistema">
        <div class="config-two-col config-system-top">
          <div id="protectionPanel" class="panel protection-panel compact-config-panel">
            <div class="config-panel-head"><div><h3>Neon y copia local</h3><p class="muted">Puedes seguir trabajando sin Internet; los cambios pendientes se sincronizan al volver la conexión.</p></div><button onclick="refreshProtectionStatus(true)">Actualizar</button></div>
            <div id="protectionStatus" class="protection-status">Cargando…</div>
            <div id="syncQueuePanel" class="sync-queue-panel hidden"></div>
            <div class="actions"><button id="recoverCloudBtn" class="primary-soft" onclick="recoverCloudNow()">🔄 Reconectar ahora</button><button id="backupNowBtn" onclick="createBackupNow()">🛡 Crear respaldo</button></div>
          </div>
          <div class="panel compact-config-panel">
            <div class="config-panel-head"><div><h3>Programa</h3><p class="muted">Versión real y actualización mediante el launcher oficial.</p></div><span id="currentVersionBadge" class="version-badge">Comprobando</span></div>
            <div id="updateStatus" class="desktop-runtime-status">Sistema de actualización automática activo.</div>
            <div class="actions"><button class="primary-soft" onclick="configLaunchUpdater()">⬆ Comprobar actualización</button></div>
          </div>
        </div>

        <div class="panel compact-config-panel">
          <div class="config-panel-head"><div><h3>Estado del sistema</h3><p class="muted">Una sola revisión para copia local, Neon, impresora, respaldos y actualizador.</p></div><button onclick="loadConsolidatedSystem(true)">↻ Revisar sistema</button></div>
          <div id="systemStatusGrid" class="system-status-grid config-system-grid"><div class="system-status-loading">Cargando estado…</div></div>
          <div id="configMaintenanceNote" class="desktop-runtime-status">Sin revisar todavía.</div>
          <div class="actions"><button onclick="configPrintTest()">🖨 Imprimir prueba</button><button onclick="configCleanupTemps()">Limpiar temporales</button></div>
        </div>

        <details class="panel compact-config-panel config-advanced">
          <summary>Ventana y rendimiento · Avanzado</summary>
          <div class="config-advanced-body">
            <div class="performance-settings-grid"><label class="window-mode-setting"><span>Forma de abrir Recepción</span><select id="windowModeSelect"><option value="AUTO">Automático (recomendado)</option><option value="WEBVIEW2">Ventana ligera WebView2</option><option value="EDGE">Edge en modo aplicación</option></select><small>Déjalo en Automático salvo que estemos diagnosticando un problema.</small></label><div class="afk-setting-card"><span>Ahorro de Neon</span><b>Automático · después de 5 minutos</b><small>Reduce consultas cuando nadie usa el programa.</small></div></div>
            <div id="desktopRuntimeStatus" class="desktop-runtime-status">Comprobando el modo de ventana…</div>
            <div class="actions"><button onclick="saveWindowMode()">Guardar modo</button></div>
          </div>
        </details>
      </div>
    </section>'''

CONFIG_CSS = r'''/* Configuración canónica de Recepción 4.6.28 */
#config.config-consolidated{max-width:1180px}
#config.config-consolidated .config-tabs{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}
#config.config-consolidated .config-tabs button{padding:9px 13px;border-radius:10px;white-space:nowrap}
#config.config-consolidated .config-tabs button.active{background:#eaf3ff;border-color:#a9c9ec;color:#235989}
#config.config-consolidated .compact-config-panel{border-radius:14px}
#config.config-consolidated .config-panel-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}
#config.config-consolidated .config-safe-defaults{margin-top:12px}
#config.config-consolidated .config-integration-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px}
#config.config-consolidated .config-integration-card{display:grid;gap:10px;align-content:start}
#config.config-consolidated .config-integration-card>div:first-child>span{display:block;font-size:9px;font-weight:900;letter-spacing:.07em;color:#7b8ca0}
#config.config-consolidated .config-integration-card h3{margin:3px 0 4px;font-size:18px;color:#263f5b}
#config.config-consolidated .config-integration-card p{margin:0;color:#6f8093;font-size:11px;line-height:1.4}
#config.config-consolidated .config-advanced{margin-top:11px;border:1px solid #dfe7ef;border-radius:13px;background:#fbfcfe}
#config.config-consolidated .config-advanced>summary{cursor:pointer;list-style:none;padding:12px 14px;font-weight:850;color:#435b74}
#config.config-consolidated .config-advanced>summary::-webkit-details-marker{display:none}
#config.config-consolidated .config-advanced>summary::after{content:'▾';float:right;color:#8493a5}
#config.config-consolidated .config-advanced[open]>summary::after{content:'▴'}
#config.config-consolidated .config-advanced-body{padding:2px 14px 14px}
#config.config-consolidated .config-template-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0}
#config.config-consolidated .config-template-card{border:1px solid #e0e7ef;border-radius:11px;padding:10px;background:#fff}
#config.config-consolidated .config-template-card b,#config.config-consolidated .config-template-card small{display:block}
#config.config-consolidated .config-template-card small{margin-top:4px;color:#74869a;font-size:9px}
#config.config-consolidated .config-template-state{display:inline-flex;margin-top:7px;padding:3px 7px;border-radius:999px;background:#fff2d7;color:#845d13;font-size:8px;font-weight:900}
#config.config-consolidated .config-template-state.ready{background:#e8f7ed;color:#246d45}
#config.config-consolidated .config-system-top{margin-bottom:12px}
#config.config-consolidated .config-system-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
#config.config-consolidated .config-dp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
#config.config-consolidated .config-dp-grid label{min-width:0}
#config.config-consolidated .config-dp-grid label>span{display:block;margin-bottom:4px;font-size:9px;font-weight:850;color:#64788f}
#config.config-consolidated .config-dp-grid input,#config.config-consolidated .config-dp-grid select,#config.config-consolidated .config-dp-grid textarea{width:100%}
#config.config-consolidated .config-dp-grid .full{grid-column:1/-1}
#config.config-consolidated .config-dp-grid textarea{min-height:90px;font-family:Consolas,monospace;resize:vertical}
#currentVersionBadge{font-size:10px!important;line-height:1!important}
#currentVersionBadge::after{content:none!important}
#sidebarRealVersion{display:flex;align-items:center;justify-content:center;width:calc(100% - 28px);min-height:28px;margin:8px 14px 10px;padding:5px 10px;box-sizing:border-box;border:1px solid rgba(148,163,184,.28);border-radius:11px;background:rgba(15,23,42,.16);color:rgba(226,232,240,.78);font-size:10px;font-weight:800}
#sidebarRealVersion::before{content:'';width:6px;height:6px;margin-right:7px;border-radius:50%;background:#7dd3fc;box-shadow:0 0 0 3px rgba(125,211,252,.10)}
@media(max-width:850px){#config.config-consolidated .config-integration-grid,#config.config-consolidated .config-system-top,#config.config-consolidated .config-dp-grid{grid-template-columns:1fr}#config.config-consolidated .config-template-grid{grid-template-columns:1fr}#config.config-consolidated .config-system-grid{grid-template-columns:1fr}}
'''

CONFIG_JS = r'''(()=>{
'use strict';
if(window.__receptionConfigConsolidated)return;
window.__receptionConfigConsolidated=true;
const q=(s,r=document)=>r.querySelector(s);
const qa=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const call=async(url,opt={})=>{if(typeof window.api==='function')return window.api(url,opt);const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.message||'Error');return d};
let dpCache=null;
let waCloudTest=null;
let waPoll=null;

window.confirmDeletion=message=>window.confirm(message);

function cleanLegacyConfigArtifacts(){
  const config=q('#config');if(!config)return;
  for(const name of ['services','maintenance','dataphone','actualizaciones']){
    q(`[data-config-tab="${name}"]`,config)?.remove();
    q(`[data-config-section="${name}"]`,config)?.remove();
  }
}

async function loadRealVersion(){
  try{
    const d=await call('/api/version?t='+Date.now());
    const version=String(d.version||'').trim();
    if(!version)return;
    const chip=q('#currentVersionBadge');if(chip)chip.textContent='Recepción v'+version;
    const anchor=q('#historiaDoctorBadge')||q('#connectionBadge');
    if(anchor){let badge=q('#sidebarRealVersion');if(!badge){badge=document.createElement('div');badge.id='sidebarRealVersion';anchor.insertAdjacentElement('afterend',badge)}badge.textContent='Recepción v'+version}
  }catch{}
}

function renderWhatsappTemplates(d={}){
  const host=q('#configWhatsappTemplates');if(!host)return;
  const defs=[['recordatorio_cita','Confirmación de cita'],['cita_agendada','Cita agendada'],['recordatorio_hoy','Recordatorio del día']];
  host.innerHTML=defs.map(([key,label])=>{const x=d.templates?.[key]||{},ok=!!x.approved;return `<div class="config-template-card"><b>${esc(label)}</b><small>${esc(x.name||key)} · ${esc(x.language||'')}</small><span class="config-template-state ${ok?'ready':''}">${ok?'APROBADA':'EN ESPERA'}</span></div>`}).join('');
  const select=q('#waTestTemplate');if(select){let first='';for(const option of select.options){const x=d.templates?.[option.value]||{};option.disabled=!x.approved;if(x.approved&&!first)first=option.value}if(select.selectedOptions[0]?.disabled)select.value=first||'recordatorio_cita'}
}

async function loadWhatsappConsolidated(){
  try{const d=await call('/api/whatsapp/status');renderWhatsappTemplates(d)}catch{}
  if(typeof window.loadWhatsappStatus==='function')await window.loadWhatsappStatus();
  if(typeof window.loadWhatsappCloudStatus==='function')await window.loadWhatsappCloudStatus(false);
}

function waTestResult(text){const el=q('#whatsappTestResult');if(el)el.textContent=text}
async function pollWaCloudTest(){
  if(!waCloudTest)return;
  try{
    const d=await call(`/api/whatsapp/cloud-test/${waCloudTest.id}?token=${encodeURIComponent(waCloudTest.token)}`);
    const extra=d.timestamp?' · '+String(d.timestamp):'';
    waTestResult(`${d.status_label||d.status||'Procesando'}${extra}${d.error?' · '+d.error:''}`);
    if(d.terminal){clearInterval(waPoll);waPoll=null;q('#configFinishWaTest')?.classList.remove('hidden')}
  }catch(e){waTestResult('No se pudo consultar la prueba: '+(e.message||e))}
}
window.sendWhatsappTest=async function(){
  const phone=(q('#waTestPhone')?.value||'').trim(),name=(q('#waTestName')?.value||'Prueba').trim(),date=q('#waTestDate')?.value||'',time=q('#waTestTime')?.value||'',template=q('#waTestTemplate')?.value||'recordatorio_cita',btn=q('#waTestSendBtn');
  if(!phone){alert('Ingresa el número que recibirá la prueba.');return}if(!date||!time){alert('Selecciona fecha y hora.');return}
  if(!confirm(`¿Enviar UNA prueba Cloud a ${phone}?\n\nNo se tocará ningún paciente ni cita real.`))return;
  try{if(btn)btn.disabled=true;waTestResult('Registrando prueba técnica en Neon…');const d=await call('/api/whatsapp/cloud-test',{method:'POST',body:JSON.stringify({phone,name,date,time,template})});waCloudTest={id:d.test_id,token:d.token};q('#configFinishWaTest')?.classList.add('hidden');waTestResult('Solicitud registrada. Esperando al Worker Cloud…');clearInterval(waPoll);waPoll=setInterval(pollWaCloudTest,5000);pollWaCloudTest()}catch(e){waTestResult('❌ '+(e.message||e))}finally{if(btn)btn.disabled=false}
};
window.configFinishWhatsappTest=async function(){if(!waCloudTest)return;try{await call(`/api/whatsapp/cloud-test/${waCloudTest.id}?token=${encodeURIComponent(waCloudTest.token)}`,{method:'DELETE'});waCloudTest=null;clearInterval(waPoll);waPoll=null;q('#configFinishWaTest')?.classList.add('hidden');waTestResult('Prueba finalizada y retirada de la agenda técnica.')}catch(e){alert(e.message||e)}};

function dpField(id,label,value='',type='text',extra=''){return `<label class="${extra.includes('full')?'full':''}"><span>${esc(label)}</span><input id="${id}" type="${type}" value="${esc(value)}" ${extra.replace('full','')}></label>`}
function renderDataphone(d={}){
  dpCache=d;
  const ready=!!d.automatic_charge_ready,pill=q('#configDataphonePill'),summary=q('#configDataphoneSummary'),host=q('#configDataphoneBody');
  if(pill){pill.textContent=ready?'LISTO':'PENDIENTE';pill.classList.toggle('ready',ready)}
  if(summary)summary.textContent=ready?'Credenciales, terminal y contrato técnico completos.':'La estructura está preparada; faltan uno o más datos oficiales de Bendo.';
  if(!host)return;
  host.innerHTML=`<div class="config-dp-grid">${dpField('cfgDpProvider','Proveedor',d.provider||'BENDO')}${dpField('cfgDpModel','Modelo',d.model||'Bendo Smart')}${dpField('cfgDpBase','API base URL',d.api_base_url||'','url','full placeholder="https://..."')}${dpField('cfgDpKey','API key / token','','password',`placeholder="${d.api_key_saved?'Ya guardada · deja vacío para conservarla':'Pendiente'}"`)}${dpField('cfgDpMerchant','Merchant ID',d.merchant_id||'')}${dpField('cfgDpTerminal','Terminal ID',d.terminal_id||'')}</div><details class="config-advanced"><summary>Contrato técnico de Bendo</summary><div class="config-advanced-body"><div class="config-dp-grid">${dpField('cfgDpHealth','Ruta de prueba',d.health_path||'','text','full')}${dpField('cfgDpCreate','Ruta crear cobro',d.create_payment_path||'')}${dpField('cfgDpStatus','Ruta consultar estado',d.status_path_template||'')}${dpField('cfgDpAuthHeader','Header',d.auth_header||'Authorization')}${dpField('cfgDpAuthScheme','Esquema',d.auth_scheme||'Bearer')}${dpField('cfgDpRespId','Campo ID',d.response_id_field||'id')}${dpField('cfgDpRespStatus','Campo estado',d.response_status_field||'status')}${dpField('cfgDpWebhook','Webhook público',d.webhook_public_url||'','url','full')}${dpField('cfgDpWebhookSecret','Webhook secret','','password',`full placeholder="${d.webhook_secret_saved?'Ya guardado · deja vacío para conservarlo':'Opcional'}"`)}<label class="full"><span>Plantilla JSON de creación</span><textarea id="cfgDpTemplate">${esc(d.create_body_template||'')}</textarea></label></div></div></details><div id="configDataphoneDetail" class="desktop-runtime-status">${esc(d.api_key_saved?'Credencial API guardada.':'Aún no hay credencial API guardada.')}</div><div class="actions"><button class="primary-soft" onclick="configSaveDataphone()">Guardar Bendo</button></div>`;
}
window.loadConsolidatedDataphone=async function(){try{renderDataphone(await call('/api/v4506/dataphone/config'))}catch(e){const x=q('#configDataphoneSummary');if(x)x.textContent=e.message||e}};
window.configSaveDataphone=async function(){
  try{const d=dpCache||{};const body={provider:q('#cfgDpProvider')?.value||'BENDO',model:q('#cfgDpModel')?.value||'Bendo Smart',environment:d.environment||'PRODUCCION',api_base_url:q('#cfgDpBase')?.value||'',api_key:q('#cfgDpKey')?.value||null,merchant_id:q('#cfgDpMerchant')?.value||'',terminal_id:q('#cfgDpTerminal')?.value||'',auth_header:q('#cfgDpAuthHeader')?.value||d.auth_header||'Authorization',auth_scheme:q('#cfgDpAuthScheme')?.value||d.auth_scheme||'Bearer',health_path:q('#cfgDpHealth')?.value||'',create_payment_path:q('#cfgDpCreate')?.value||'',status_path_template:q('#cfgDpStatus')?.value||'',create_body_template:q('#cfgDpTemplate')?.value||d.create_body_template||'',response_id_field:q('#cfgDpRespId')?.value||d.response_id_field||'id',response_status_field:q('#cfgDpRespStatus')?.value||d.response_status_field||'status',approved_values:d.approved_values||'APPROVED,COMPLETED,SUCCESS',declined_values:d.declined_values||'DECLINED,FAILED,REJECTED,CANCELLED',webhook_public_url:q('#cfgDpWebhook')?.value||'',webhook_secret:q('#cfgDpWebhookSecret')?.value||null};const out=await call('/api/v4506/dataphone/config',{method:'POST',body:JSON.stringify(body)});renderDataphone(out);alert('Configuración de Bendo guardada en esta PC.')}catch(e){alert(e.message||e)}};
window.configValidateDataphone=async function(){try{const d=await call('/api/v4506/dataphone/validate',{method:'POST',body:'{}'});const target=q('#configDataphoneSummary');if(target)target.textContent=d.message||'';await window.loadConsolidatedDataphone()}catch(e){alert(e.message||e)}};
window.configTestDataphone=async function(){try{const d=await call('/api/v4506/dataphone/test',{method:'POST',body:'{}'});const target=q('#configDataphoneSummary');if(target)target.textContent=d.message||'Prueba terminada.'}catch(e){alert(e.message||e)}};

function fmtBytes(value){let n=Number(value||0);if(n<1024)return n+' B';if(n<1024*1024)return(n/1024).toFixed(1)+' KB';return(n/(1024*1024)).toFixed(1)+' MB'}
function renderSystem(d={}){
  const host=q('#systemStatusGrid');if(!host)return;
  const local=d.local||{},neon=d.neon||{},printer=d.printer||{},backup=d.backup||{},updater=d.updater||{};
  host.innerHTML=`<div><span>Copia local</span><b>${local.ok?'✓ Lista':'⚠ Revisar'}</b><small>${local.pending_sync??0} cambio(s) pendientes</small></div><div><span>Neon</span><b>${esc(neon.status||'SIN COMPROBAR')}</b><small>${esc(neon.detail||'')}</small></div><div><span>Impresora</span><b>${printer.ok?'✓ '+esc(printer.selected||printer.default||'Lista'):'⚠ Revisar'}</b><small>${printer.available_count??0} detectada(s)</small></div><div><span>Último respaldo</span><b>${backup.ok?'✓ Disponible':'Aún no creado'}</b><small>${backup.count??0} copia(s)</small></div><div><span>Actualizador</span><b>${updater.ok===false?'⚠ Revisar':'✓ Preparado'}</b><small>${esc(updater.latest?'Última: '+updater.latest:'Canal estable')}</small></div><div><span>Temporales</span><b>${Number(d.cleanup?.candidates||0)}</b><small>candidato(s) a limpieza</small></div>`;
}
window.loadConsolidatedSystem=async function(deep=false){try{const d=await call('/api/v4501/system-status?deep='+(deep?'true':'false'));renderSystem(d);const note=q('#configMaintenanceNote');if(note)note.textContent=deep?'Revisión completa terminada.':'Estado local actualizado.';await loadRealVersion()}catch(e){const note=q('#configMaintenanceNote');if(note)note.textContent=e.message||e}};
window.configPrintTest=async function(){try{const d=await call('/api/v4501/printing/test',{method:'POST',body:'{}'});alert('Prueba enviada a '+(d.printer||'la impresora')+'.')}catch(e){alert(e.message||e)}};
window.configCleanupTemps=async function(){if(!confirm('¿Limpiar temporales antiguos y conservar intactos pacientes, bases y respaldos recientes?'))return;try{const d=await call('/api/v4501/maintenance/cleanup',{method:'POST',body:'{}'});alert(`Limpieza terminada. ${d.removed_files||0} archivo(s), ${d.removed_dirs||0} carpeta(s), ${fmtBytes(d.freed_bytes||0)} liberados.`);await window.loadConsolidatedSystem(false)}catch(e){alert(e.message||e)}};
window.configLaunchUpdater=async function(){const status=q('#updateStatus');try{if(status)status.textContent='Abriendo launcher oficial…';let d;try{d=await call('/api/v4483/launch-updater',{method:'POST',body:'{}'})}catch(_e){d=await call('/api/app/restart',{method:'POST',body:'{}'})}if(status)status.textContent=d.message||'Launcher abierto. Si existe una actualización obligatoria, se instalará antes de continuar.'}catch(e){if(status)status.textContent=e.message||e;alert(e.message||e)}};
window.configOpenAgenda=function(){const btn=q('#cloudAgendaLinks .cloud-single-actions button');if(btn)btn.click()};

const originalShow=window.showConfigTab;
window.showConfigTab=function(tab='general',button=null){
  const out=typeof originalShow==='function'?originalShow(tab,button):undefined;
  cleanLegacyConfigArtifacts();
  if(tab==='agenda')loadWhatsappConsolidated();
  if(tab==='facturacion'){window.loadConsolidatedDataphone();if(typeof window.loadAzurStatus==='function')window.loadAzurStatus()}
  if(tab==='sistema'){window.loadConsolidatedSystem(false);if(typeof window.loadWindowModeInfo==='function')window.loadWindowModeInfo();if(typeof window.loadUpdateInfo==='function')window.loadUpdateInfo()}
  return out;
};

function boot(){
  cleanLegacyConfigArtifacts();
  loadRealVersion();
  const date=q('#waTestDate');if(date&&!date.value){const x=new Date();x.setDate(x.getDate()+1);date.value=x.toISOString().slice(0,10)}
  const phone=q('#waTestPhone');if(phone&&!phone.value){try{phone.value=localStorage.getItem('revelo_wa_test_phone')||''}catch{}}
  phone?.addEventListener('input',()=>{try{localStorage.setItem('revelo_wa_test_phone',phone.value.trim())}catch{}});
  if(!q('#config')?.classList.contains('hidden'))window.showConfigTab('general',q('[data-config-tab="general"]'));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
'''

# 1) Canonical configuration markup.
index_path = STATIC / "index.html"
index = read(index_path)
start = index.index('    <section id="config"')
end_marker = '    </section>\n  </main>'
end = index.index(end_marker, start) + len('    </section>')
index = index[:start] + CONFIG_HTML + index[end:]
write(index_path, index)
write(STATIC / "configuration.css", CONFIG_CSS)
write(STATIC / "configuration.js", CONFIG_JS)

# 2) Use only the consolidated configuration assets. Keep the main overlay for unrelated UI.
features_path = APP / "features_runtime.py"
features = read(features_path)
old_addon = '''        addon = (\n            '<link rel="stylesheet" href="/v458/settings.css?v=4.3.58">'\n            '<script defer src="/v458/settings.js?v=4.3.58"></script>'\n            '<link rel="stylesheet" href="/v459/settings.css?v=4.3.59">'\n            '<script defer src="/v459/settings.js?v=4.3.59"></script>'\n            f'<link rel="stylesheet" href="/v460/overlay.css?v={version}">'\n            f'<script defer src="/v460/overlay.js?v={version}"></script>'\n        )'''
new_addon = '''        addon = (\n            f'<link rel="stylesheet" href="/v460/overlay.css?v={version}">'\n            f'<link rel="stylesheet" href="/static/configuration.css?v={version}">'\n            f'<script defer src="/v460/overlay.js?v={version}"></script>'\n            f'<script defer src="/static/configuration.js?v={version}"></script>'\n        )'''
features = replace_once(features, old_addon, new_addon, "features addon")
strip_code = '''\n\ndef _strip_legacy_configuration_overlays() -> None:\n    """Retire only superseded Configuration UI blocks; backend endpoints stay available."""\n    css = getattr(core_runtime, "V460_OVERLAY_CSS", "") or ""\n    js = getattr(core_runtime, "V460_OVERLAY_JS", "") or ""\n    blocks = [\n        (reception_update_restart, ("V4482_CSS", "V4482_JS")),\n        (reception_update_launcher, ("V4483_CSS", "V4483_JS")),\n        (reception_system_status, ("V4501_JS",)),\n        (reception_payment_terminal_config, ("V4506_JS",)),\n        (reception_version_display, ("V4518_CSS", "V4518_JS")),\n        (reception_version_sidebar, ("V4519_CSS", "V4519_JS")),\n    ]\n    for module, attrs in blocks:\n        for attr in attrs:\n            block = getattr(module, attr, "") or ""\n            if not block:\n                continue\n            if attr.endswith("_CSS"):\n                css = css.replace(block, "")\n            else:\n                js = js.replace(block, "")\n    core_runtime.V460_OVERLAY_CSS = css\n    core_runtime.V460_OVERLAY_JS = js\n\n\n_strip_legacy_configuration_overlays()\n'''
anchor = '\n\n_install_versioned_overlay_home()\n'
if '_strip_legacy_configuration_overlays()' not in features:
    features = replace_once(features, anchor, strip_code + anchor, "configuration strip hook")
write(features_path, features)

# 3) Core safety / redundancy fixes.
core_path = APP / "core_runtime.py"
core = read(core_path)
core = core.replace('    "facturero": "https://app.factureromovil.com/documentos/facturas",\n', '')
core = core.replace('existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""', 'existing = env_path.read_text(encoding="utf-8-sig") if env_path.exists() else ""')
core = core.replace('@app.post("/api/data-protection/backup")\n', '')
core = re.sub(r'def _auto_login_enabled\(\) -> bool:\n(?:    .*\n)+?\n\ndef _default_local_user', 'def _auto_login_enabled() -> bool:\n    # Recepción es una aplicación local del consultorio: no exponemos un interruptor que pueda bloquear el arranque.\n    return True\n\n\ndef _default_local_user', core, count=1)
old_add = '''    if db.scalar(select(Procedure).where(Procedure.nombre == name)):\n        raise HTTPException(409, "Ese procedimiento ya existe")\n    p = Procedure(nombre=name, valor_default=data.valor_default)'''
new_add = '''    if db.scalar(select(Procedure).where(Procedure.nombre == name)):\n        raise HTTPException(409, "Ese procedimiento ya existe")\n    value = data.valor_default\n    if value is not None:\n        value = round(float(value), 2)\n        if value < 0:\n            raise HTTPException(400, "El valor del procedimiento no puede ser negativo")\n    p = Procedure(nombre=name, valor_default=value)'''
core = replace_once(core, old_add, new_add, "procedure create money guard")
old_update = '''    if not p:\n        raise HTTPException(404, "Procedimiento no encontrado")\n    p.valor_default = data.valor_default\n    if is_offline_db(db):\n        add_queue(\n            db, "procedure.update", "procedure",\n            {"procedure_id": procedure_id, "valor_default": data.valor_default},'''
new_update = '''    if not p:\n        raise HTTPException(404, "Procedimiento no encontrado")\n    value = data.valor_default\n    if value is not None:\n        value = round(float(value), 2)\n        if value < 0:\n            raise HTTPException(400, "El valor del procedimiento no puede ser negativo")\n    p.valor_default = value\n    if is_offline_db(db):\n        add_queue(\n            db, "procedure.update", "procedure",\n            {"procedure_id": procedure_id, "valor_default": value},'''
core = replace_once(core, old_update, new_update, "procedure update money guard")
write(core_path, core)

# 4) Frontend safety: confirmations cannot be disabled and backup uses one canonical endpoint.
appjs_path = STATIC / "app.js"
appjs = read(appjs_path)
appjs = replace_once(appjs, 'function confirmDeletion(message){return appPreferences.confirm_delete===false?true:confirm(message)}', 'function confirmDeletion(message){return confirm(message)}', 'always confirm deletion')
backup_pattern = re.compile(r'async function createBackupNow\(\)\{.*?\n\}\nasync function restartReception\(\)\{', re.S)
backup_repl = '''async function createBackupNow(){\n  const btn=$('#backupNowBtn');\n  try{\n    if(btn){btn.disabled=true;btn.textContent='Creando respaldo…'}\n    const d=await api('/api/backup/now',{method:'POST'});\n    await refreshProtectionStatus(true);\n    alert(`Respaldo creado correctamente.\\n${fmtDateTime(d.last_backup)}`);\n  }catch(e){alert(e.message||'No se pudo crear el respaldo.')}\n  finally{if(btn){btn.disabled=false;btn.textContent='🛡 Crear respaldo'}}\n}\nasync function restartReception(){'''
appjs, n = backup_pattern.subn(backup_repl, appjs, count=1)
if n != 1:
    raise RuntimeError(f"backup canonicalization: expected 1 replacement, found {n}")
write(appjs_path, appjs)

# 5) Version + manifest.
write(APP / "recepcion-version.json", json.dumps({"version": VERSION}, indent=2, ensure_ascii=False) + "\n")
manifest_path = APP / "update_manifest.json"
manifest = json.loads(read(manifest_path))
manifest["version"] = VERSION
manifest["app_version"] = VERSION
manifest["runtime_version"] = VERSION
for key in ("required_dependencies", "copy"):
    items = list(manifest.get(key) or [])
    for item in ("static/configuration.css", "static/configuration.js"):
        if item not in items:
            insert_at = items.index("static/app.js") + 1 if "static/app.js" in items else len(items)
            items.insert(insert_at, item)
    manifest[key] = items
notes = manifest.setdefault("notes", {})
notes.update({
    "purpose": "Consolida Configuración en cinco secciones canónicas, elimina UI redundante y blinda preferencias locales, respaldos, .env y precios.",
    "previous_version": "4.6.27",
    "candidate_only": True,
    "configuration_tabs": ["Recepción", "Agenda y WhatsApp", "Servicios y precios", "Facturación y cobros", "Sistema"],
    "configuration_v458_loaded": False,
    "configuration_v459_loaded": False,
    "local_login_toggle_removed": True,
    "delete_confirmation_toggle_removed": True,
    "destructive_actions_always_confirm": True,
    "backup_api_canonical": "/api/backup/now",
    "env_bom_safe_read_write": True,
    "facturero_mobile_destination_removed": True,
    "procedure_negative_price_blocked": True,
    "procedure_price_two_decimals": True,
    "azur_credentials_advanced_only": True,
    "dataphone_credentials_advanced_only": True,
    "database_schema_changes": False,
    "patient_data_changes": False,
})
write(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

print("CONFIG CLEANUP PATCH READY", VERSION)
