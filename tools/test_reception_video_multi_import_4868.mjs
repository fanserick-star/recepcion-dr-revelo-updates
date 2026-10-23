/** Offline dynamic UI regression: two and many patient MP4 files in one import.
 * No browser/network, no real clinical files, no Neon, no WhatsApp.
 */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source = fs.readFileSync('recepcion/app/static/clinical_delivery.js','utf8');
const section=(start,end)=> {
  const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  assert(a>=0&&b>a, 'Function boundary not found');
  return source.slice(a,b).trim();
};
const saveFn=section('async function saveVideo(file){','async function sendVideo(file){');
const sendFn=section('async function sendVideo(file){','window.loadClinicalDelivery=load;');

function env({approve=true,outcomes=[],pid=42,ready=true}={}){
  const calls=[],notices=[],confirmed=[],loads=[],items=[];
  const element=(tag='div')=>({
    tag,children:[],textContent:'',className:'',attributes:{},
    setAttribute(k,v){this.attributes[k]=v},
    append(...nodes){this.children.push(...nodes)},
    remove(){this.removed=true},
  });
  const host=element();
  const state={pid,name:'PACIENTE FICTICIO',phone:'',saving_video:false,
               sending:false,ready_video:ready};
  const sandbox={
    state,Array,Math,String,encodeURIComponent,
    document:{createElement:element},
    cell:(tag,text,cls='')=>{let x=element(tag);x.textContent=text;x.className=cls;items.push(x);return x;},
    container:()=>host,
    confirmVideoArchive:async files=>{confirmed.push(files.map(x=>x.name));return approve},
    notice:(message,kind)=>notices.push({message,kind}),
    api:async (url,options)=>{calls.push({url,body:options.body,headers:options.headers});const i=calls.length-1;
      if(outcomes[i] instanceof Error)throw outcomes[i];
      return outcomes[i]||{ok:true,duplicate:false,backup:false};
    },
    load:async(...args)=>loads.push(args),
  };
  return {fn:vm.runInNewContext('('+saveFn+')',sandbox),send:vm.runInNewContext('('+sendFn+')',sandbox),
          calls,notices,confirmed,loads,items,state,host};
}
const mp4=(name,size=1024)=>({name,size});
assert(source.includes("file.multiple=true"),'Native file input does not accept multiple MP4s');
assert(source.includes("selected.length>20"),'Batch limit missing');
assert(source.includes("total>10*1024*1024*1024"),'Aggregate capacity guard missing');
assert(source.includes("if(state.pid!==pid)"),'Cross-patient guard missing');

{
  const e=env();
  await e.fn({files:[mp4('first.mp4'),mp4('second.MP4')]});
  assert.equal(e.confirmed.length,1,'Must confirm the patient only once per batch');
  assert.deepEqual(e.confirmed[0],['first.mp4','second.MP4']);
  assert.equal(e.calls.length,2,'Both videos must be posted separately');
  assert(e.calls[0].url.includes('filename=first.mp4'));
  assert(e.calls[1].url.includes('filename=second.MP4'));
  assert.equal(e.calls[0].body.name,'first.mp4');
  assert.equal(e.calls[1].body.name,'second.MP4');
  assert.equal(e.loads.length,1,'Refresh exactly once after the batch');
  assert.equal(e.state.saving_video,false);
  assert(e.items.some(x=>x.textContent.includes('Resultado: 2 nuevo(s)')));
  assert.equal(e.notices[0].kind,'success');
}
{
  const e=env({outcomes:[{duplicate:true},new Error('Simulated filesystem outage'),{duplicate:false,backup:true}]});
  await e.fn({files:[mp4('duplicate.mp4'),mp4('problem.mp4'),mp4('third.mp4')]});
  assert.equal(e.calls.length,3,'A failure must not discard later videos');
  assert.equal(e.loads.length,1);
  assert.equal(e.notices.at(-1).kind,'error');
  assert(e.items.some(x=>x.textContent.includes('Resultado: 1 nuevo(s), 1 ya archivado(s) y 1 error(es)')));
  assert.equal(e.state.saving_video,false);
}
{
  const e=env({approve:false});
  await e.fn({files:[mp4('one.mp4'),mp4('two.mp4')]});
  assert.equal(e.calls.length,0,'No upload before explicit patient confirmation');
  assert.equal(e.loads.length,0);
}
{
  const e=env();
  await e.fn({files:[mp4('good.mp4'),mp4('bad.mov')]});
  assert.equal(e.confirmed.length,0,'Mixed unsupported files must be blocked before confirmation');
  assert.equal(e.calls.length,0,'No partial import on invalid selection');
}
{
  const e=env();
  await e.fn({files:Array.from({length:21},(_,i)=>mp4('video'+i+'.mp4'))});
  assert.equal(e.calls.length,0,'Too many files must be blocked');
}
{
  const e=env();
  await e.send({files:[mp4('one.mp4'),mp4('two.mp4')]});
  assert.equal(e.calls.length,0,'WhatsApp must not silently send the first file in a batch');
  assert(e.notices.some(x=>/un video por envío/.test(x.message)));
}
console.log('RECEPTION_4868_MULTIPLE_MP4_IMPORT_PATIENT_CONFIRM_SERIAL_DEDUP_SAFE_OK');
