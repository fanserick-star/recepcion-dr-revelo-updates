from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v479'
OUT=ROOT/'updates'/'v480'
VERSION='4.3.80'
LAUNCHER_VERSION='4.3.76-standalone-3'


def joined(prefix,n):
    ps=sorted(SRC.glob(prefix+'*'),key=lambda p:int(p.name.replace(prefix,'')))
    if len(ps)!=n: raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(ps)}')
    return ''.join(p.read_text(encoding='utf-8') for p in ps)

def sha(b): return hashlib.sha256(b).hexdigest()
def write_parts(text,prefix,n):
    OUT.mkdir(parents=True,exist_ok=True)
    for p in OUT.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/n); names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'; (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline=''); names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text: raise SystemExit(f'{prefix}: reconstrucción inválida')
    return names

CSS=r'''
/* v4.3.80 — Inicio más legible + resumen semanal separado + rechazadas condicional */
#inicio .week-cards{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:10px!important;margin-bottom:7px!important}
#inicio .week-card.v478-week-chip{min-height:67px!important;padding:11px 13px!important}
#inicio .v478-week-chip .week-day{font-size:14px!important;line-height:1.15!important}
#inicio .v478-week-chip .v478-week-count{font-size:23px!important}
#inicio .v478-week-chip .v478-week-meta{font-size:10px!important}
#inicio .v478-week-chip .v478-week-total{font-size:11.5px!important}
#inicio #weekSummary{display:flex!important;justify-content:flex-end!important;margin:0 0 10px!important;padding:0!important;background:transparent!important;border:0!important}
#inicio .v480-week-summary{min-width:285px;display:grid;grid-template-columns:1fr auto;grid-template-areas:'label money' 'patients money';align-items:center;gap:2px 18px;padding:9px 13px;border:1px solid #d8e3ef;border-radius:11px;background:#f4f7fb;box-shadow:none}
#inicio .v480-week-summary span{grid-area:label;font-size:9px;font-weight:900;letter-spacing:.1em;color:#6d7e94;text-transform:uppercase}
#inicio .v480-week-summary strong{grid-area:patients;font-size:11.5px;color:#344b68}
#inicio .v480-week-summary b{grid-area:money;font-size:17px;color:#214f84;white-space:nowrap}
#inicio .v478-week-total-card{display:none!important}
#inicio .v478-day-head h2{font-size:19px!important}
#inicio .v478-day-kicker{font-size:9px!important}
#inicio .v478-day-stats span,#inicio .v478-day-stats b{font-size:10px!important;padding:5px 9px!important}
#inicio .home-patient-table{font-size:13px!important}
#inicio .home-patient-table thead th{font-size:9.5px!important;padding:8px 9px!important}
#inicio .home-patient-table td{padding:7px 9px!important}
#inicio .row-number{font-size:12px!important}
.v478-home-table .patient-name-line>a{font-size:13.5px!important;line-height:1.18!important}
.v478-home-table .new-patient-badge{font-size:8px!important;padding:3px 6px!important}
.v478-home-table .service-badge{font-size:9.5px!important;padding:4px 8px!important}
.v478-home-table .money-pill{font-size:10px!important;min-width:62px!important;padding:5px 7px!important}
.v478-home-actions>button,.v478-more-summary{font-size:9px!important;padding:6px 8px!important;min-height:29px!important}
.v478-home-more-menu button{font-size:9px!important}
.v478-home-table .sub-visit-label{font-size:10px!important}

/* Rechazadas en cero: se elimina físicamente del layout, aunque cambie la etiqueta HTML. */
#facturacion #billingSummary [data-v480-zero-rejected="1"]{display:none!important}
#facturacion .billing-summary.v480-two-cards{grid-template-columns:repeat(2,minmax(0,1fr))!important}
#facturacion .billing-summary.v480-two-cards>*{min-width:0!important;width:100%!important}
#facturacion .billing-summary.v480-three-cards{grid-template-columns:repeat(3,minmax(0,1fr))!important}
@media(max-width:760px){#facturacion .billing-summary.v480-two-cards,#facturacion .billing-summary.v480-three-cards{grid-template-columns:1fr!important}#inicio .week-cards{grid-template-columns:1fr!important}#inicio .v480-week-summary{width:100%;min-width:0}}
'''

JS=r''';(()=>{
 if(window.__v480Polish)return;window.__v480Polish=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let billingGuard=false,observer=null;

 window.renderWeekCards=function(days){
   const data=days||[],totalPatients=data.reduce((s,d)=>s+Number(weeklyData[d.iso]?.count||0),0),totalMoney=data.reduce((s,d)=>s+Number(weeklyData[d.iso]?.total||0),0);
   const box=$('#weekCards');if(!box)return;
   box.innerHTML=data.map(d=>{const info=weeklyData[d.iso]||{count:0,total:0};return `<button class="week-card v478-week-chip ${selectedHomeDate===d.iso?'active':''}" data-date="${d.iso}" onclick="selectHomeDay('${d.iso}')"><span class="week-day">${esc(d.label)}</span><strong class="v478-week-count">${Number(info.count||0)}</strong><span class="v478-week-meta">${fmtDate(d.iso)} · ${Number(info.count||0)===1?'paciente':'pacientes'}</span><span class="v478-week-total">${money(info.total||0)}</span></button>`}).join('');
   const summary=$('#weekSummary');if(summary)summary.innerHTML=`<div class="v480-week-summary"><span>Resumen semanal</span><strong>${totalPatients} ${totalPatients===1?'paciente':'pacientes'}</strong><b>${money(totalMoney)}</b></div>`;
 };

 function extractCount(el){
   if(!el)return 0;
   const candidates=[...el.querySelectorAll('b,strong,[class*="count"],[class*="number"],[class*="value"]'),el];
   for(const node of candidates){const m=String(node?.textContent||'').trim().match(/(^|\s)(\d+)(\s|$)/);if(m)return Number(m[2]||0)}
   const m=String(el.textContent||'').match(/\d+/);return m?Number(m[0]):0;
 }
 function polishBillingSummary(){
   if(billingGuard)return;billingGuard=true;
   try{
     const box=document.querySelector('#billingSummary');if(!box)return;
     const children=[...box.children];let rejected=null;
     for(const el of children){if(norm(el.textContent).includes('rechaz')){rejected=el;break}}
     let count=0;
     if(rejected){count=extractCount(rejected);if(count<=0)rejected.setAttribute('data-v480-zero-rejected','1');else rejected.removeAttribute('data-v480-zero-rejected')}
     const visible=children.filter(el=>el!==rejected||count>0);
     box.classList.toggle('v480-two-cards',visible.length===2);
     box.classList.toggle('v480-three-cards',visible.length>=3);
     box.classList.toggle('v479-no-reject',!!rejected&&count<=0);
   }finally{billingGuard=false}
 }
 function observeBilling(){
   const box=document.querySelector('#billingSummary');if(!box||box.dataset.v480Observed==='1')return;
   box.dataset.v480Observed='1';observer=new MutationObserver(()=>queueMicrotask(polishBillingSummary));observer.observe(box,{childList:true,subtree:true,characterData:true});polishBillingSummary();
 }
 const oldLoad=window.loadBilling;if(typeof oldLoad==='function')window.loadBilling=async function(){const r=await oldLoad.apply(this,arguments);observeBilling();polishBillingSummary();return r};
 const oldSet=window.setBillingStatus;if(typeof oldSet==='function')window.setBillingStatus=async function(){const r=await oldSet.apply(this,arguments);observeBilling();polishBillingSummary();return r};
 function boot(){observeBilling();polishBillingSummary()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,40),{once:true});else setTimeout(boot,40);
 setTimeout(boot,300);setTimeout(boot,1000);
})();'''


def patch_app(s):
    if s.count('APP_VERSION = "4.3.79"')!=1: raise SystemExit('APP_VERSION 4.3.79 no encontrado')
    s=s.replace('APP_VERSION = "4.3.79"','APP_VERSION = "4.3.80"',1)
    visual="const VERSION=\\'4.3.79\\';"
    if visual not in s: raise SystemExit('versión visual 4.3.79 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.80\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inválido')
    injected=('V480_POLISH_CSS = r"""'+CSS+'"""\n'+'V480_POLISH_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V480_POLISH_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V480_POLISH_JS\n\n'+marker)
    return s.replace(marker,injected,1)


def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='V480_POLISH_JS' for t in node.targets): js=ast.literal_eval(node.value);break
    if not js: raise SystemExit('V480_POLISH_JS no encontrado')
    for token in ['data-v480-zero-rejected','MutationObserver','v480-two-cards','Resumen semanal','renderWeekCards','extractCount']:
        if token not in js: raise SystemExit('falta '+token)
    if ':scope > button' in js: raise SystemExit('no volver a depender de button directo')
    for token in ['V479_POLISH_JS','V478_REMIX_JS','MAÑANA','TARDE','V476_JS','b.estado = "EMITIDA"']:
        if token not in app: raise SystemExit('regresión: '+token)
    if 'APP_VERSION = "4.3.80"' not in app or "const VERSION=\\'4.3.80\\';" not in app: raise SystemExit('versiones incorrectas')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8');lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v480/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.80: oculta Rechazadas cuando está en cero, agranda la lectura de Inicio y separa el Resumen semanal de las tarjetas de días.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__':main()
