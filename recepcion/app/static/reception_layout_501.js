/* Recepción 5.0.1 — layout integration only. All actions remain with original controllers. */
;(()=>{
 'use strict';
 if(window.__reception501)return;
 window.__reception501=true;
 const $=s=>document.querySelector(s), by=id=>document.getElementById(id);
 let previousAttention=false, previousDossier=false, updating=false;
 function update(){
   if(updating)return;
   updating=true;
   try{
     const modal=by('modal'),patients=by('pacientes');
     if(!modal)return;
     const visible=!modal.classList.contains('hidden');
     const attention=visible&&!!modal.querySelector('.new-attention-start-modal,.attention-form-modal');
     const dossier=visible&&!!modal.querySelector('.v4100-dossier')&&!!patients&&!patients.classList.contains('hidden');
     modal.classList.toggle('v501-workspace-open',attention);
     modal.classList.toggle('v501-docked-profile',dossier);
     const stage=by('v501AttentionStage');
     if(attention){
       if(stage){
         // The original form stays in #modal for every selector and save callback.
         if(!previousAttention){
           for(const section of document.querySelectorAll('#app>main>section'))section.classList.add('hidden');
           stage.classList.remove('hidden');
         }
       }
       document.querySelectorAll('.side-nav>.nav-btn[data-section]').forEach(b=>b.classList.remove('active'));
       $('.side-nav>.v50-nav-attention')?.classList.add('active');
     }else if(previousAttention){
       if(stage)stage.classList.add('hidden');
       if(![...document.querySelectorAll('#app>main>section')].some(x=>!x.classList.contains('hidden'))){
         // Do not re-fetch data merely because the user closed a form.
         by('inicio')?.classList.remove('hidden');
         $('.side-nav>[data-section="inicio"]')?.classList.add('active');
       }
       $('.side-nav>.v50-nav-attention')?.classList.remove('active');
     }
     previousAttention=attention;
     previousDossier=dossier;
   }finally{updating=false}
 }
 function addAttentionStage(){
   const main=$('#app>main');if(!main||by('v501AttentionStage'))return;
   const stage=document.createElement('section');stage.id='v501AttentionStage';
   stage.className='hidden v501-attention-stage';
   main.append(stage);
 }
 function enhancePatientRows(){
   const list=by('patientResults');if(!list)return;
   // Only decorate the records already rendered from the local database.
   for(const item of list.querySelectorAll('.patient-compact-row:not([data-v501-row])')){
     item.dataset.v501Row='1';
     const name=item.querySelector('.patient-compact-name');
     const main=item.querySelector('.patient-compact-main');
     if(!name||!main)continue;
     const avatar=document.createElement('span');avatar.className='v501-avatar';
     const words=String(name.textContent||'').trim().split(/\s+/).filter(Boolean);
     avatar.textContent=(words[0]?.[0]||'P')+(words[1]?.[0]||'');
     avatar.setAttribute('aria-hidden','true');
     main.insertBefore(avatar,main.firstChild);
   }
 }
 function enhanceHomeTable(){
   const table=by('todayTable');if(!table)return;
   for(const row of table.querySelectorAll('table.home-patient-table>tbody>tr.patient-main-row:not([data-v501-row])')){
     row.dataset.v501Row='1';
     const cell=row.querySelector('.row-number');
     if(cell)cell.classList.add('v501-turn-number');
   }
 }
 function moveAlerts(){
   const home=by('inicio');
   if(!home||by('v501AlertsLine'))return;
   const alertLine=document.createElement('div');alertLine.id='v501AlertsLine';
   const billing=by('homePendingStrip'),wa=by('homeWhatsappReviewStrip');
   for(const node of [billing,wa])if(node)alertLine.append(node);
   home.insertBefore(alertLine,by('r486Metrics')||home.firstChild);
 }
 function fixSearchHint(){
   const input=by('globalSearch');const chip=by('v50SearchHelp');
   if(!chip||!input)return;
   chip.textContent='Ctrl + K';
   chip.title='Presiona Ctrl + K para buscar';
 }
 function observe(){
   const modal=by('modal');
   if(modal)new MutationObserver(update).observe(modal,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
   const patients=by('pacientes');
   if(patients)new MutationObserver(update).observe(patients,{attributes:true,attributeFilter:['class']});
   const results=by('patientResults');
   if(results){let scheduled=false;new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;enhancePatientRows()})}).observe(results,{childList:true,subtree:true});}
   const table=by('todayTable');
   if(table)new MutationObserver(enhanceHomeTable).observe(table,{childList:true,subtree:false});
 }
 function boot(){
   addAttentionStage();moveAlerts();fixSearchHint();
   observe();enhancePatientRows();enhanceHomeTable();update();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
