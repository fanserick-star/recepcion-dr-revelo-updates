"""Chromium screenshot regression for the *real* Recepción Nueva atención page,
1600×900 at 100% zoom, with 100% synthetic patient and schedule data.

Tests patient search -> click -> native form (no dossier modal) -> service selection.
No production API or Neon connectivity.
"""
from __future__ import annotations
import json
import ast
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"recepcion"/"app"
OUT=ROOT/"reports"/"reception-507-new-attention-1600x900.png"
OUT.parent.mkdir(parents=True,exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(APP),**kwargs)
    def log_message(self,*args):
        return

srv=ThreadingHTTPServer(("127.0.0.1",0),Handler)
threading.Thread(target=srv.serve_forever,daemon=True).start()

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1600,"height":900},device_scale_factor=1)
    errors=[]
    page.on("pageerror",lambda exc:errors.append(str(exc)))
    page.goto(f"http://127.0.0.1:{srv.server_port}/static/index.html",wait_until="domcontentloaded",timeout=30000)
    page.wait_for_function("typeof newAttention==='function' && typeof attentionFor==='function' && typeof window.r507AttentionSelected==='function'")

    # Execute actual payment/Bendo overlays, which production backend appends
    # to HTML. Static screenshot alone does not exercise fiscal integration.
    def overlay(source,begin,end):
        start=source.index(begin)+len(begin)
        stop=source.index(end,start)
        return ast.literal_eval(source[start:stop].strip())
    payment=(APP/"reception_payment_terminal.py").read_text(encoding="utf-8")
    bendo=(APP/"reception_payment_terminal_panel.py").read_text(encoding="utf-8")
    page.add_script_tag(content=overlay(payment,"    V4504_JS = ","\n    core.V460_OVERLAY_CSS"))
    page.add_script_tag(content=overlay(bendo,"V4525_JS = ","\ncore.V460_OVERLAY_CSS"))
    page.evaluate(r"""() => {
      const day=toISO(new Date());
      const patient={id:1,nombre:'MARÍA FERNANDA CRUZ LÓPEZ',
        cedula:'1718945623',celular:'0993475621',correo:'prueba@example.invalid',
        fecha_nacimiento:'1990-05-12',ultima_atencion:'2026-11-10',
        suggested_type:'S'};
      const visits=[
        {id:101,fecha:'2026-11-10',tipo:'S',procedimiento:null,valor:40,observacion:'Control registrado'},
        {id:100,fecha:'2026-10-21',tipo:'S',procedimiento:null,valor:40,observacion:'Seguimiento registrado'},
      ];
      const appointment={date:day,appointments:[
        {appointment:{id:1,patient_id:1,hora:'09:00',estado:'CONFIRMADA'},patient},
        {appointment:{id:2,patient_id:2,hora:'10:20',estado:'PENDIENTE'},
           patient:{id:2,nombre:'PACIENTE FICTICIO DOS'}}
      ]};
      window.api=async (url,opt={})=>{
        if((opt.method||'GET')!=='GET')throw new Error('No writes permitted in visual test');
        if(url.startsWith('/api/patients?q='))return [patient];
        if(url==='/api/patients/1')return patient;
        if(url==='/api/procedures')return [{nombre:'CISTOSCOPIA',valor_default:180},{nombre:'ECOGRAFIA',valor_default:80}];
        if(url==='/api/patients/1/profile')return {...patient,visits,appointments:[],emissions:[]};
        if(url.startsWith('/api/historia-identity/status/'))return {ok:true,reachable:true,linked:true,clinical_patient:{verified:true},history_date_count:2};
        if(url.startsWith('/api/agenda/week?'))return {days:[appointment]};
        if(url.startsWith('/api/ops/today'))return {ok:true};
        return {};
      };
      document.getElementById('app')?.classList.remove('hidden');
      document.getElementById('login')?.classList.add('hidden');
      newAttention();
    }""")
    assert page.locator("#atencion:not(.hidden)").count()==1
    page.locator("#aSearch").fill("MARÍA FERNANDA")
    page.wait_for_selector("#aResults .v4413-attention-result",timeout=10000)
    page.locator("#aResults .v4413-attention-result").first.click()
    page.wait_for_selector("#r507VisitSlot:not(.hidden) #saveAttentionBtn",timeout=10000)
    page.wait_for_function("document.querySelector('#r507ClinicalPanel')?.textContent.includes('Ficha de Historia vinculada')",timeout=10000)
    page.locator(".r507-services > summary").click()
    page.locator("#atencion .service-card[data-service='CONSULTA']").click()
    page.wait_for_function("document.querySelector('#r507BillingSummary')?.textContent.includes('40.00')",timeout=10000)
    page.wait_for_selector("#v4504Payment .v4504-pay-option",timeout=10000)
    assert page.locator("#v4504Payment .v4504-pay-option").count()==4,"Real fiscal payment choices missing"
    page.locator("#v4504Payment [data-mode='EFECTIVO']").click()
    page.wait_for_function("document.querySelector('#v4504Payment .v4504-pay-state')?.textContent.includes('Efectivo')",timeout=10000)
    page.locator(".r507-services > summary").click()
    page.wait_for_function("document.querySelector('#r507AgendaList')?.textContent.includes('MARÍA FERNANDA')",timeout=10000)
    page.wait_for_function("document.querySelector('#r507HistoryList')?.textContent.includes('Control registrado')",timeout=10000)
    # Production regression: the official v4613 overlay can prepend its
    # warning to the native form. It must not become an extra grid item.
    page.evaluate(r"""() => {
      const grid=document.querySelector('#atencion .r507-page-grid.attention-form-modal');
      const warning=document.createElement('div');
      warning.className='v4613-history-card warn';
      warning.textContent='⚠ Sin vincular con Historia Clínica';
      grid.prepend(warning);
    }""")
    # The same clinical link action must remain visible in the right rail.
    page.evaluate(r"""() => {
      attentionContext.clinicalLink=false;
      window.r507ClinicalStatusChanged();
      window.__r508LinkParams=null;
      window.openRegistrationHistoryLink=(pid,name,afterLink)=>{
        window.__r508LinkParams={pid,name,hasCallback:typeof afterLink==='function'};
        return Promise.resolve();
      };
    }""")
    page.wait_for_selector("#r507ClinicalPanel .r507-link-chart",timeout=3000)
    page.locator("#r507ClinicalPanel .r507-link-chart").click()
    link=page.evaluate("window.__r508LinkParams")
    assert link["pid"]==1 and link["hasCallback"],link
    layout=page.evaluate(r"""() => {
      const rect=s=>{
        const e=document.querySelector(s),r=e?.getBoundingClientRect();
        return r?{x:r.x,y:r.y,w:r.width,h:r.height}:null;
      };
      const dom={viewport:[innerWidth,innerHeight],
        page:rect('#atencion'),
        identity:rect('#atencion .r507-identity'),
        details:rect('#atencion .r507-details'),
        rail:rect('#atencion .r507-rail'),
        billing:rect('#atencion .r507-billing'),
        history:rect('#atencion .r507-history'),
        clinical:rect('#atencion .r507-clinical'),
        agenda:rect('#atencion .r507-agenda'),
        patient:document.querySelector('#r507PickedPatient')?.textContent,
        bill:document.querySelector('#r507BillingSummary')?.textContent,
        modalHidden:document.querySelector('#modal')?.classList.contains('hidden'),
        hasSave:!!document.querySelector('#atencion #saveAttentionBtn'),
        hasReview:!!document.querySelector('#atencion .exam-review-turn-btn'),
        realPaymentOptions:document.querySelectorAll('#v4504Payment .v4504-pay-option').length,
        selectedPayment:document.querySelector('#v4504Payment .v4504-pay-state')?.textContent,
        misplacedWarningDisplay:getComputedStyle(document.querySelector('#atencion .r507-page-grid > .v4613-history-card')).display,
        gridAreas:getComputedStyle(document.querySelector('#atencion .r507-page-grid')).gridTemplateAreas,
        clinicalAction:!!document.querySelector('#r507ClinicalPanel .r507-link-chart'),
        date:document.querySelector('#aFecha')?.value
      };
      return dom;
    }""")
    print("RECEPTION_507_VISUAL",json.dumps(layout,ensure_ascii=False))
    assert layout["viewport"]==[1600,900]
    assert layout["modalHidden"] is True,"Patient selection opened detached dossier modal"
    assert layout["misplacedWarningDisplay"]=="none","Legacy clinical warning must not take the first grid cell"
    assert layout["clinicalAction"],"Manual verified Historia linkage action must remain accessible"
    assert 'r507-main' in layout["gridAreas"] and 'r507-rail' in layout["gridAreas"]
    assert layout["details"] is not None and layout["hasSave"] and layout["hasReview"]
    assert layout["realPaymentOptions"]==4 and "Efectivo" in layout["selectedPayment"],layout
    assert layout["identity"]["x"]<layout["rail"]["x"],layout
    assert layout["details"]["x"]<layout["rail"]["x"],layout
    assert layout["billing"]["h"]<325 and layout["history"]["h"]<300,layout
    assert layout["clinical"]["h"]<200 and layout["agenda"]["h"]<300,layout
    assert layout["agenda"]["y"]+layout["agenda"]["h"]<=900, "Agenda should fit the 1600x900 viewport with the selected patient: "+str(layout)
    assert "MARÍA FERNANDA" in layout["patient"]
    assert "40.00" in layout["bill"]
    page.screenshot(path=str(OUT),full_page=True)
    if errors:
       print("BROWSER_ERRORS",json.dumps(errors[:8],ensure_ascii=False))
    browser.close()

srv.shutdown()
print("RECEPTION_507_NATIVE_NEW_ATTENTION_1600X900_VISUAL_OK",OUT)
