from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v478'
OUT=ROOT/'updates'/'v479'
VERSION='4.3.79'
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
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text:
        raise SystemExit(f'{prefix}: reconstrucción inválida')
    return names

CSS=r'''
/* v4.3.79 — pulido Agenda + Facturación inteligente */
.v478-agenda-brand{position:relative!important;padding:11px 14px 11px 17px!important;background:#eef6ff!important;border-bottom:1px solid #d7e6f6!important}
.v478-agenda-brand:before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:#4e86c5}
.v478-agenda-title{gap:8px!important;align-items:center!important}
.v478-agenda-title span{display:none!important}
.v478-agenda-title strong{font-size:15px!important;line-height:1.15!important;color:#285f98!important;letter-spacing:.005em!important;font-weight:900!important}
.v478-agenda-date b{font-size:10px!important;color:#405774!important}.v478-agenda-date span{background:#fff!important;border-color:#cbdced!important;color:#426383!important}
.v478-shift-head{background:#fbfcfe!important}.v478-shift:first-child .v478-shift-head{box-shadow:inset 3px 0 0 #e4ad45}.v478-shift:last-child .v478-shift-head{box-shadow:inset 3px 0 0 #6c8fca}

#facturacion .billing-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}
#facturacion .billing-summary.v479-no-reject{grid-template-columns:repeat(2,minmax(0,1fr))!important}
#facturacion .billing-summary.v479-no-reject>button{width:100%!important;min-width:0!important}
#facturacion .billing-summary>button.v479-rejected{border-color:#efc7c4!important;background:#fff8f7!important;color:#874743!important}
#facturacion .billing-summary>button.v479-rejected b{color:#a24d47!important}
@media(max-width:760px){#facturacion .billing-summary,#facturacion .billing-summary.v479-no-reject{grid-template-columns:1fr!important}}
'''

JS=r''';(()=>{
 if(window.__v479Polish)return;window.__v479Polish=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function polishAgenda(){
   const title=document.querySelector('.v478-agenda-title strong');
   if(title)title.textContent='Agenda de hoy';
 }
 function billingSummary(){
   const box=document.querySelector('#billingSummary');if(!box)return;
   const buttons=[...box.querySelectorAll(':scope > button')];
   const rejected=buttons.find(b=>norm(b.textContent).includes('rechaz'));
   if(!rejected){box.classList.add('v479-no-reject');return}
   rejected.classList.add('v479-rejected');
   const numNode=rejected.querySelector('b,strong');
   const raw=(numNode?.textContent||rejected.textContent||'').match(/\d+/);
   const count=raw?Number(raw[0]):0;
   rejected.style.display=count>0?'':'none';
   box.classList.toggle('v479-no-reject',count<=0);
 }
 const oldRender=window.renderAttentionWeek;
 if(typeof oldRender==='function')window.renderAttentionWeek=function(d){const r=oldRender.apply(this,arguments);polishAgenda();return r};
 const oldLoad=window.loadBilling;
 if(typeof oldLoad==='function')window.loadBilling=async function(){const r=await oldLoad.apply(this,arguments);billingSummary();return r};
 const oldSet=window.setBillingStatus;
 if(typeof oldSet==='function')window.setBillingStatus=async function(){const r=await oldSet.apply(this,arguments);billingSummary();return r};
 function boot(){polishAgenda();billingSummary()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,40),{once:true});else setTimeout(boot,40);
 setTimeout(boot,400);
})();'''


def patch_app(s):
    if s.count('APP_VERSION = "4.3.78"')!=1: raise SystemExit('APP_VERSION 4.3.78 no encontrado')
    s=s.replace('APP_VERSION = "4.3.78"','APP_VERSION = "4.3.79"',1)
    visual="const VERSION=\\'4.3.78\\';"
    if visual not in s: raise SystemExit('versión visual 4.3.78 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.79\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inválido')
    injected=(
        'V479_POLISH_CSS = r"""'+CSS+'"""\n'
        'V479_POLISH_JS = r"""'+JS+'"""\n'
        'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V479_POLISH_CSS\n'
        'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V479_POLISH_JS\n\n'+marker
    )
    return s.replace(marker,injected,1)


def main():
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec'); compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app); js=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='V479_POLISH_JS' for t in node.targets):
            js=ast.literal_eval(node.value);break
    if not js: raise SystemExit('V479_POLISH_JS no encontrado')
    for token in ['Agenda de hoy','v479-no-reject','count<=0','loadBilling','renderAttentionWeek']:
        if token not in js: raise SystemExit('falta '+token)
    if 'V478_REMIX_JS' not in app or 'MAÑANA' not in app or 'TARDE' not in app: raise SystemExit('regresión v4.3.78')
    if 'V476_JS' not in app or 'b.estado = "EMITIDA"' not in app: raise SystemExit('regresión Facturación')
    if 'APP_VERSION = "4.3.79"' not in app or "const VERSION=\\'4.3.79\\';" not in app: raise SystemExit('versiones incorrectas')
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8'); lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8'); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v479/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.79: suaviza el encabezado de Agenda y oculta Rechazadas en Facturación cuando no existen errores.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
