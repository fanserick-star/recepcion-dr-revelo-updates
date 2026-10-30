/** Real dialog behavior: identity and consent individually required before any send.
 * No browser automation/network, no patient data, no WhatsApp calls.
 */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source=fs.readFileSync('recepcion/app/static/clinical_delivery.js','utf8');
const start=source.indexOf('let deliveryConfirmationOpen=false;');
const end=source.indexOf('async function sendDoc(doc){',start);
assert(start>=0&&end>start,'Clinical confirmation function is missing');
const fnSource=source.slice(start,end);
assert(!fnSource.includes('window.confirm('),'No native browser confirmation dialogs');
const nodes=[];
function create(tag){
  const node={tag,children:[],className:'',textContent:'',disabled:false,checked:false,
    isConnected:true,handlers:{},attrs:{},
    append(...children){this.children.push(...children);this.lastChild=this.children.at(-1)},
    addEventListener(name,fn){(this.handlers[name]??=[]).push(fn)},
    setAttribute(name,value){this.attrs[name]=value},
    remove(){this.removed=true;this.isConnected=false},
    focus(){document.activeElement=this},
    click(){for(const handler of this.handlers.click||[])handler({target:this})},
    change(){for(const handler of this.handlers.change||[])handler({target:this})},
  };
  nodes.push(node);
  return node;
}
const document={
  activeElement:null,handlers:{},body:create('body'),createElement:create,
  addEventListener(name,fn){(this.handlers[name]??=[]).push(fn)},
  removeEventListener(name,fn){this.handlers[name]=(this.handlers[name]||[]).filter(x=>x!==fn)},
  key(key){const fn=(this.handlers.keydown||[]).at(-1);if(fn)fn({key,preventDefault(){}})}
};
const state={pid:25,phone:'0981234567',name:'PACIENTE PRUEBA'};
const notices=[];
const confirmDelivery=vm.runInNewContext('(()=>{'+fnSource+';return confirmDelivery})()',{
  state,document,notice:(msg,type)=>notices.push({msg,type}),
  cell:(tag,label,cls='')=>{const el=create(tag);el.textContent=label;el.className=cls;return el;}
});
function dialog(){
  const modal=nodes.filter(x=>x.className.includes('rp-clinical-delivery-confirm-dialog')).at(-1);
  assert(modal,'Dialog not present');
  const inputs=nodes.filter(x=>x.tag==='input'&&x.type==='checkbox');
  const buttons=nodes.filter(x=>x.tag==='button');
  const accept=buttons.find(x=>x.textContent==='Enviar por WhatsApp'&&!x.__checked);
  const cancel=buttons.filter(x=>x.textContent==='Cancelar').at(-1);
  const submit=buttons.filter(x=>x.textContent==='Enviar por WhatsApp').at(-1);
  return {modal,inputs:inputs.slice(-2),cancel,accept:submit};
}
{
  const result=confirmDelivery('Receta médica');
  const {modal,inputs,accept}=dialog();
  assert.equal(modal.attrs.role,'dialog');assert.equal(modal.attrs['aria-modal'],'true');
  assert.equal(accept.disabled,true);
  assert.equal(inputs.length,2);assert.equal(inputs[0].checked,false);assert.equal(inputs[1].checked,false);
  inputs[0].checked=true;inputs[0].change();
  assert.equal(accept.disabled,true,'Identity alone is insufficient');
  inputs[1].checked=true;inputs[1].change();
  assert.equal(accept.disabled,false,'Both checks enable the send');
  inputs[0].checked=false;inputs[0].change();
  assert.equal(accept.disabled,true,'Unchecking either one revokes authorization');
  inputs[0].checked=true;inputs[0].change();
  accept.click();
  const approval=await result;
  assert.equal(approval.confirmed_phone,'593981234567');
  assert.equal(approval.identity_confirmed,true);
  assert.equal(approval.consent_confirmed,true);
}
{
  const result=confirmDelivery('Certificado');
  const {cancel}=dialog();cancel.click();
  assert.equal(await result,null,'Cancel must not produce delivery authorization');
}
{
  const result=confirmDelivery('Informe');
  document.key('Escape');
  assert.equal(await result,null,'Escape cancels');
}
{
  const result=confirmDelivery('Receta');
  const {inputs,accept}=dialog();
  inputs.forEach(x=>{x.checked=true;x.change()});
  state.pid=26;
  accept.click();
  assert.equal(await result,null,'No cross-patient confirmation');
  state.pid=25;
}
{
  state.phone='0000000000';
  assert.equal(await confirmDelivery('Receta'),null,'Invalid telephone must fail closed');
  assert(notices.some(x=>x.type==='error'));
}
console.log('RECEPTION_48116_CLINICAL_WHATSAPP_MODAL_TWO_CHECKS_CANCEL_FOCUS_NO_NATIVE_POPUPS_OK');
