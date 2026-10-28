// Regression: the new-attention search MUST NOT be reclassified as a patient
// registration form. No patient data, network, backend or mutations.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app=fs.readFileSync('recepcion/app/static/app.js','utf8');
const core=fs.readFileSync('recepcion/app/core_runtime.py','utf8');

const remasterStart=core.indexOf('function remaster(fromAttention){',core.indexOf('V481_PATIENT_JS = r"""'));
const remasterGuardEnd=core.indexOf("modal.dataset.v481Patient='1';",remasterStart);
assert(remasterStart>=0&&remasterGuardEnd>remasterStart);
const checkV481=core.slice(remasterStart,remasterGuardEnd);
const patientCheckStart=core.indexOf('function patientFieldsPresent(modal){',core.indexOf('V482_HOTFIX_JS = r"""'));
const patientCheckEnd=core.indexOf('function ensurePatientRemaster(){',patientCheckStart);
assert(patientCheckStart>=0&&patientCheckEnd>patientCheckStart);
const checkV482=core.slice(patientCheckStart,patientCheckEnd);
const marker=app.indexOf('function newAttention(){');
const end=app.indexOf('function procedureByName(',marker);
assert(marker>=0&&end>marker);
const newAttention=app.slice(marker,end);

const searchInput={id:'aSearch',placeholder:'Cédula, apellidos y nombres, celular o correo',value:''};
const saveButton={disabled:false,textContent:'＋ Crear paciente nuevo'};
const searchModal={
  dataset:{},classList:{add:()=>{throw Error('Search modal was altered')}},
  querySelector:q=>q==='#aSearch'?searchInput:q==='button'?saveButton:null,
  querySelectorAll:()=>[searchInput],
  textContent:'Nueva atención Buscar paciente Cédula, apellidos y nombres, celular o correo'
};
const patientId={id:'fCedula'},patientName={id:'fNombre'};
const realForm={
  querySelector:q=>q==='#fCedula'?patientId:q==='#fNombre'?patientName:null
};
const formModal={
  querySelector:q=>q==='.patient-form-modal'?realForm:realForm.querySelector(q),
  dataset:{},classList:{add:()=>{}}
};
const context={document:{querySelector:q=>q==='#modal .modalbox'?searchModal:null}};
vm.createContext(context);
vm.runInContext(checkV482+'globalThis.isForm=patientFieldsPresent;',context);
assert.equal(context.isForm(searchModal),false,'search must not be a patient form');
assert.equal(context.isForm(formModal),true,'real patient form must remain eligible');
assert.equal(context.isForm({querySelector:q=>q==='.patient-form-modal'?{}:q==='#fCedula'?patientId:null}),false,'missing separate name must not be enough');

const v481Context={document:{querySelector:q=>q==='#modal .modalbox'?searchModal:null}};
vm.createContext(v481Context);
vm.runInContext(checkV481+'}\nglobalThis.checkRemaster=remaster;',v481Context);
assert.doesNotThrow(()=>v481Context.checkRemaster(true));
assert.equal(saveButton.disabled,false,'remaster must never disable new patient button');
assert.equal(searchModal.dataset.v481Patient,undefined);

let rendered='',currentPatientSource='old',seq=0,cleared=false;
const context2={openModal:html=>{rendered=html;},setTimeout:()=>{},clearTimeout:()=>{cleared=true},
  document:{querySelector:()=>null},attentionSearchTimer:11,attentionSearchSeq:seq,currentPatientSource};
vm.createContext(context2);
vm.runInContext(newAttention,context2);
context2.newAttention();
assert.equal(context2.currentPatientSource,'general');
assert.equal(context2.attentionSearchSeq,1);
assert(cleared);
assert.match(rendered,/onclick="newPatient\(true\)"/);
assert.match(rendered,/＋ Crear paciente nuevo/);
assert.doesNotMatch(rendered,/disabled|v481-field-invalid|Revisa el correo|Correo no válido|v481-section/);
assert.match(rendered,/id="aSearch"/);
assert.doesNotMatch(rendered,/Agenda de hoy|attentionWeekBlock/);
assert.match(app,/function newPatient\(continueToAttention=false,agendaSlot=null\)/);
assert.match(app,/onclick="saveNewPatient\(true\)"/);

console.log('RECEPTION_NEW_PATIENT_REMASTER_SCOPE_48110_OK');
