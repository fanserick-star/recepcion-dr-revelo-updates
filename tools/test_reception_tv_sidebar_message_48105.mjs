// Prueba funcional del mensaje entre panel TV y barra lateral sin datos clínicos.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync('recepcion/app/static/sidebar_status_hub_4897.js','utf8');
const originalTv=fs.readFileSync('recepcion/app/tv_control.html','utf8');
assert.match(originalTv,/function sendTvStatusToReception\(s\)/);
assert.match(originalTv,/type:'reception-tv-heartbeat-v1'/);
assert.match(originalTv,/sendTvStatusToReception\(s\);updateDisplay\(s\.display_mode\)/);

function createHarness(routes={}){
  const labels={};
  const rows={};
  for(const id of ['r497SystemRow','r497HistoryRow','r497TvRow','r497VersionRow']){
    labels[id]={textContent:'Comprobando…'};
    rows[id]={dataset:{state:'unknown'},title:'',querySelector:()=>labels[id]};
  }
  const frameWindow={};
  const frame={contentWindow:frameWindow,getAttribute:()=> 'http://127.0.0.1:8899/control'};
  const app={classList:{contains:()=>false}};
  const elements={...rows,r486TvFrame:frame,app};
  const listeners={};
  const calls=[];
  const document={
    hidden:false,readyState:'complete',baseURI:'http://127.0.0.1:8000/',
    getElementById:id=>elements[id]||null,
    querySelector:selector=>selector==='.r497-status-sources'?{}:null,
    addEventListener:(event,fn)=>{listeners['document:'+event]=fn}
  };
  const window={addEventListener:(event,fn)=>{listeners[event]=fn}};
  const fetch=async(url)=>{
    calls.push(url);
    const result=routes[url]||{ok:false,status:503};
    return {ok:result.ok,status:result.status||200,json:async()=>result.data};
  };
  vm.runInNewContext(source,{window,document,MutationObserver:class{observe(){}},
    fetch,setInterval:()=>1,Date,URL,Error,String,Number,Boolean,Math});
  return {labels,rows,frameWindow,listeners,calls};
}
const drain=()=>new Promise(resolve=>setTimeout(resolve,0));
const event=(h,source,origin,online)=>h.listeners.message({
  source,origin,data:{type:'reception-tv-heartbeat-v1',ok:true,tv_online:online}
});
{
  const h=createHarness();
  await drain();
  assert.equal(h.labels.r497TvRow.textContent,'Sin comprobar');
  assert(h.calls.includes('/api/reception/tv/status'));
  assert(h.calls.includes('/api/tv-turnos/health'));
  event(h,{},'http://127.0.0.1:8899',true);
  assert.equal(h.labels.r497TvRow.textContent,'Sin comprobar','mensaje de origen iframe ajeno');
  event(h,h.frameWindow,'http://example.org',true);
  assert.equal(h.labels.r497TvRow.textContent,'Sin comprobar','mensaje de origen externo');
  event(h,h.frameWindow,'http://127.0.0.1:8899',true);
  assert.equal(h.labels.r497TvRow.textContent,'Conectada');
  assert.equal(h.rows.r497TvRow.dataset.state,'online');
  h.listeners.focus();
  await drain();
  assert.equal(h.labels.r497TvRow.textContent,'Conectada','error HTTP no tapa señal TV reciente');
  event(h,h.frameWindow,'http://127.0.0.1:8899',false);
  assert.equal(h.labels.r497TvRow.textContent,'Sin conexión');
}
{
  const h=createHarness({
    '/api/reception/tv/status':{ok:false,status:503},
    '/api/tv-turnos/health':{ok:true,data:{ok:true,tv_online:true}}
  });
  await drain();
  assert.equal(h.labels.r497TvRow.textContent,'Conectada','fallback autenticado');
}
{
  const h=createHarness({
    '/api/reception/tv/status':{ok:true,data:{ok:true,tv_online:true}}
  });
  await drain();
  assert.equal(h.labels.r497TvRow.textContent,'Conectada','ruta principal');
  assert(!h.calls.includes('/api/tv-turnos/health'),'sin consultas duplicadas si primario funciona');
}
console.log('RECEPTION_TV_SIDEBAR_MESSAGE_48105_OK');
