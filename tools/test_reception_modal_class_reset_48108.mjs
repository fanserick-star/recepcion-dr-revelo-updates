// Regression for a patient profile opened after new/edit patient forms.
// Uses the actual openModal()/closeModal() source; does not load real patients.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app=fs.readFileSync('recepcion/app/static/app.js','utf8');
const start=app.indexOf('function openModal(html){');
const end=app.indexOf('function patientNameWords(',start);
assert(start>=0&&end>start,'modal functions not found');
const actual=app.slice(start,end);

function fakeClasses(...initial){
  const value=new Set(initial);
  return {
    contains:x=>value.has(x),
    add:(...xs)=>xs.forEach(x=>value.add(x)),
    remove:(...xs)=>xs.forEach(x=>value.delete(x)),
    toggle:(name,on)=>{if(on)value.add(name);else value.delete(name);return !!on}
  };
}
const box={
  classList:fakeClasses('modalbox','v481-patient-modal','v477-attention-modalbox','modalbox-wide'),
  dataset:{v481Patient:'1'},scrollTop:484
};
const body={innerHTML:'<div class="patient-form-modal"></div>',scrollTop:275};
const modal={classList:fakeClasses('modal','hidden')};
const elements={'#modalBody':body,'#modal .modalbox':box,'#modal':modal};
const ctx=vm.createContext({
  $:selector=>elements[selector]||null,
  attentionContext:{something:'old'}
});
vm.runInContext(actual,ctx);
assert.equal(typeof ctx.openModal,'function');
assert.equal(typeof ctx.closeModal,'function');

ctx.openModal('<div class="v4413-patient-profile v4100-dossier">Expediente</div>');
assert(box.classList.contains('v4413-profile-shell'),'dossier class must be active');
assert(!box.classList.contains('v481-patient-modal'),'old narrow form class must be removed');
assert(!box.classList.contains('v477-attention-modalbox'),'old attention class must be removed');
assert(!box.classList.contains('modalbox-wide'),'attention width must be released');
assert.equal(box.dataset.v481Patient,undefined,'patient form flag must be reset');
assert.equal(box.scrollTop,0,'scroll should begin at top');
assert.equal(body.scrollTop,0,'inner scroll should begin at top');
assert(!modal.classList.contains('hidden'));
ctx.closeModal();
assert(!box.classList.contains('v4413-profile-shell'));
assert(!box.classList.contains('v481-patient-modal'));
assert(modal.classList.contains('hidden'));

ctx.openModal('<div class="new-attention-start-modal">Buscar paciente</div>');
assert(box.classList.contains('modalbox-wide'));
assert(!box.classList.contains('v4413-profile-shell'));
ctx.closeModal();

ctx.openModal('<div class="patient-form-modal">Crear paciente</div>');
assert(!box.classList.contains('v481-patient-modal'),'form class is added only by its own remaster');
assert(!box.classList.contains('v4413-profile-shell'));
box.classList.add('v481-patient-modal');
box.dataset.v481Patient='1';
box.scrollTop=200;
ctx.openModal('<div class="v4413-patient-profile">Expediente otra vez</div>');
assert(box.classList.contains('v4413-profile-shell'));
assert(!box.classList.contains('v481-patient-modal'));
assert.equal(box.scrollTop,0);
console.log('RECEPTION_MODAL_CLASS_RESET_48108_OK');
