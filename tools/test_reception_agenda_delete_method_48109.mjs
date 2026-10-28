// Exercise the exact V474 capture listener from core_runtime.py with fake buttons.
// Never starts the server, accesses patients, or modifies an appointment.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const runtime=fs.readFileSync('recepcion/app/core_runtime.py','utf8');
const app=fs.readFileSync('recepcion/app/static/app.js','utf8');
const marker='V474_CAPTURE_FIX_JS = r"""';
const start=runtime.indexOf(marker);
assert(start>=0,'V474 overlay missing');
const end=runtime.indexOf('"""',start+marker.length);
assert(end>start,'V474 overlay not terminated');
const overlay=runtime.slice(start+marker.length,end);

// Both API routes must be DELETE, not a GET-only Confirmafy detail.
assert.match(runtime,/@app\.delete\("\/api\/agenda\/unlinked\/\{item_id\}"\)/);
assert.match(runtime,/@app\.delete\("\/api\/agenda\/appointments\/\{appointment_id\}"\)/);
assert.match(runtime,/@app\.get\("\/api\/agenda\/confirmafy-staged\/\{item_id\}"\)/);
assert.match(app,/deleteUnlinkedAppointment\(itemId\)/);
assert.match(app,/api\(`\/api\/agenda\/unlinked\/\$\{Number\(itemId\)\}`,\{method:'DELETE'\}\)/);
assert.match(runtime,/_whatsapp_cancel_pending\("staged", item_id\)/);

function harness(){
  let click;
  const calls=[],notices=[],confirmed=[],refreshes=[];
  let closed=0;
  const sandbox={
    window:{
      rpConfirm:async(message,title)=>{confirmed.push({message,title});return true},
      rpNotice:(message,title)=>notices.push({message,title}),
      closeModal:()=>{closed++},
      loadAgenda:async()=>{refreshes.push('agenda')}
    },
    document:{addEventListener:(name,listener,capture)=>{
      assert.equal(name,'click');assert.equal(capture,true);click=listener;
    }},
    fetch:async(url,opts={})=>{
      calls.push({url,method:opts.method,credentials:opts.credentials});
      return {ok:true,status:200,json:async()=>({ok:true,deleted:true})};
    },
    location:{reload:()=>{refreshes.push('reload')}},
    console
  };
  vm.runInNewContext(overlay,sandbox);
  assert.equal(typeof click,'function');
  const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
  async function press(action,label='Eliminar cita'){
    const button={
      textContent:label,disabled:false,
      getAttribute:key=>key==='onclick'?action:'',
    };
    let prevented=false,stopped=false,immediate=false;
    const event={
      target:{closest:selector=>selector==='button'?button:null},
      preventDefault:()=>{prevented=true},
      stopPropagation:()=>{stopped=true},
      stopImmediatePropagation:()=>{immediate=true},
    };
    click(event);
    await tick();await tick();
    return {button,prevented,stopped,immediate};
  }
  return {press,calls,notices,confirmed,refreshes,get closed(){return closed}};
}
{
  const h=harness();
  const result=await h.press('deleteUnlinkedAppointment(42)');
  assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,'/api/agenda/unlinked/42');
  assert.equal(h.calls[0].method,'DELETE');
  assert.equal(h.calls[0].credentials,'same-origin');
  assert.equal(h.confirmed.length,1);
  assert(result.prevented&&result.stopped&&result.immediate);
  assert.equal(result.button.disabled,false);
  assert.equal(h.closed,1);
  assert.deepEqual(h.refreshes,['agenda']);
  assert.equal(h.notices.length,0);
}
{
  const h=harness();
  await h.press('deleteAgendaAppointment(83)');
  assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,'/api/agenda/appointments/83');
  assert.equal(h.calls[0].method,'DELETE');
  assert.equal(h.closed,1);
}
{
  const h=harness();
  const untouched=await h.press('otherAction(42)');
  assert.equal(untouched.prevented,false);
  assert.equal(h.calls.length,0);
}
console.log('RECEPTION_AGENDA_DELETE_METHOD_48109_OK');
