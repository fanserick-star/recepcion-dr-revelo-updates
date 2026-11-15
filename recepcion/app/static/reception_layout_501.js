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
   if(by('v504HomeDashboard'))return;
   const home=by('inicio');
   if(!home||by('v501AlertsLine'))return;
   const alertLine=document.createElement('div');alertLine.id='v501AlertsLine';
   const billing=by('homePendingStrip'),wa=by('homeWhatsappReviewStrip');
   for(const node of [billing,wa])if(node)alertLine.append(node);
   home.insertBefore(alertLine,by('r486Metrics')||home.firstChild);
 }

 let homeAgendaCache=null,homeAgendaFetchedAt=0,homeAgendaRequest=null;
 async function showHomeAgenda(){
   const home=by('inicio'),root=by('v50AgendaHint'),app=by('app');
   if(!home||home.classList.contains('hidden')||!root||!app||app.classList.contains('hidden'))return;
   const date=typeof toISO==='function'?toISO(new Date()):'';
   if(!date||typeof api!=='function')return;
   const age=Date.now()-homeAgendaFetchedAt;
   if(homeAgendaCache?.date===date&&age<30*60*1000){renderHomeAgenda(homeAgendaCache.week,date);return;}
   if(homeAgendaRequest)return;
   homeAgendaFetchedAt=Date.now();
   // Reception's /api/agenda/week is local-first (SQLite); 30-minute cache and no polling.
   homeAgendaRequest=api('/api/agenda/week?anchor='+encodeURIComponent(date));
   try{
     const week=await homeAgendaRequest;
     homeAgendaCache={date,week};
     if(!home.classList.contains('hidden'))renderHomeAgenda(week,date);
   }catch(error){
     console.warn('No se pudo mostrar la agenda resumida',error);
     root.textContent='Consulta las citas y horarios reales desde Agenda.';
   }finally{homeAgendaRequest=null}
 }
 function renderHomeAgenda(week,date){
   const root=by('v50AgendaHint');if(!root)return;
   const day=(week?.days||[]).find(d=>d.date===date);
   root.replaceChildren();
   if(!day){
     root.textContent='La agenda del día no está disponible en la semana consultada.';
     return;
   }
   const appointments=(day.appointments||[]).slice().sort((a,b)=>
     String(a.appointment?.hora||a.staged?.hora||'').localeCompare(String(b.appointment?.hora||b.staged?.hora||'')));
   if(!appointments.length){root.textContent='Sin citas programadas para hoy.';return;}
   for(const row of appointments.slice(0,5)){
     const item=document.createElement('div');item.className='v50-rail-item';
     const time=String(row.appointment?.hora||row.staged?.hora||'').slice(0,5);
     const label=typeof agendaTime12==='function'?agendaTime12(time):time;
     const name=String(row.patient?.nombre||row.staged?.nombre||'Paciente sin vincular');
     const state=String(row.appointment?.estado||row.staged?.estado||'PENDIENTE');
     const when=document.createElement('span');when.textContent=label+' · '+state;
     const who=document.createElement('b');who.textContent=name;
     item.append(who,when);root.append(item);
   }
   if(appointments.length>5){
     const extra=document.createElement('span');extra.className='v50-rail-caption';
     extra.textContent='Y '+(appointments.length-5)+' cita(s) más · Ver agenda';
     root.append(extra);
   }
 }
 function watchHomeAgenda(){
   const home=by('inicio'),app=by('app');
   if(home)new MutationObserver(showHomeAgenda).observe(home,{attributes:true,attributeFilter:['class']});
   if(app)new MutationObserver(showHomeAgenda).observe(app,{attributes:true,attributeFilter:['class']});
   // UI loads before login; the first successful show('inicio') refreshes home.
   const oldShow=window.show;
   if(typeof oldShow==='function')window.show=function(id){
     const result=oldShow.apply(this,arguments);
     if(id==='agenda')homeAgendaFetchedAt=0;
     if(id==='inicio')void showHomeAgenda();
     return result;
   };
   void showHomeAgenda();
 }
 function fixSearchHint(){
   const input=by('globalSearch');const chip=by('v50SearchHelp');
   if(!chip||!input)return;
   chip.textContent='Ctrl + K';
   chip.title='Presiona Ctrl + K para buscar';
 }
 function guardNavigation(){
   for(const button of document.querySelectorAll('#app>aside .side-nav .nav-btn')){
     button.addEventListener('click',event=>{
       const modal=by('modal');
       if(!modal||modal.classList.contains('hidden')||!modal.classList.contains('v501-workspace-open'))return;
       if(!window.confirm('¿Salir de Nueva atención sin guardar los cambios?')){
         event.preventDefault();event.stopImmediatePropagation();
         return;
       }
       if(typeof window.closeModal==='function')window.closeModal();
     },true);
   }
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
   observe();enhancePatientRows();enhanceHomeTable();update();guardNavigation();
   // v5.0.2 — Visitas are the first-class content of Inicio.
   // Sidebar repeats the agenda and atenciones; turn it off without touching any data.
   const heading=$('#inicio .page-heading h1');
   if(heading&&!by('v504HomeDashboard'))heading.textContent='Atenciones del día';
   const redundantRail=by('v50HomeRail');
   if(redundantRail)redundantRail.hidden=true;
   // No agenda API read from Inicio when the duplicate rail is not displayed.
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
