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
    # 5.0.12: native service popup must keep the actual attention form
    # unchanged, let prices be edited, and safely rollback on Cancel.
    service_layout=lambda: page.evaluate(r"""() => {
      const rect=s=>document.querySelector(s)?.getBoundingClientRect();
      const details=rect('#atencion .r507-details');
      const workspace=rect('#atencion .r509-attention-workspace');
      const save=rect('#saveAttentionBtn');
      const bill=rect('#atencion .r507-billing');
      return {detailsHeight:details?.height,workspaceHeight:workspace?.height,
        saveY:save?.y,billY:bill?.y,documentHeight:document.documentElement.scrollHeight};
    }""")
    collapsed=service_layout()
    page.locator("#r512ServiceButton").click()
    page.wait_for_selector("#r512ServiceOverlay [role='dialog']")
    opened=service_layout()
    for key in ("detailsHeight","workspaceHeight","saveY","billY","documentHeight"):
        assert abs(opened[key]-collapsed[key])<=2,"Opening the popup reflows "+key+": "+str((collapsed,opened))
    assert page.locator("#r512ServiceOverlay .consultation-service-section").count()==1
    assert page.locator("#r512ServiceOverlay .procedures-service-section").count()==1
    assert page.locator("#r512ServiceOverlay .consultation-card .service-price").inner_text()=="$40.00"
    # Clicking consultation and procedures only changes the local draft.
    page.locator("#r512ServiceOverlay .service-card[data-service='CONSULTA']").click()
    page.locator("#r512ServiceOverlay .service-card[data-service='CISTOSCOPIA']").click()
    page.locator("#r512ServiceOverlay .r512-price-input[data-service='CISTOSCOPIA']").fill("215.50")
    assert page.locator("#r512PickerTotal").inner_text()=="$ 255.50"
    expanded=service_layout()
    # Choosing two services can naturally add a billing line, but must never
    # push the form, its Save button or the document below 900 px.
    for key in ("detailsHeight","saveY","billY","documentHeight"):
        assert abs(expanded[key]-collapsed[key])<=2,"Service selection moves native controls "+key+": "+str((collapsed,expanded))
    assert page.locator("#r512ServiceOverlay").bounding_box()["height"]==900
    # Cancel restores selection and prices, and never saves or charges.
    page.locator("#r512ServiceOverlay .r512-cancel").click()
    assert page.locator("#r512ServiceOverlay").count()==0
    assert "Todavía no hay" in page.locator("#r512SelectionPreview").inner_text()
    assert "Selecciona una consulta" in page.locator("#r507BillingSummary").inner_text()
    # The selector is intentionally exempted from the generic 700 ms double-click
    # guard; the Save button is NOT exempted.
    assert page.locator('#r512ServiceButton').get_attribute('data-allow-rapid-clicks')=='true'
    assert page.locator('#saveAttentionBtn').get_attribute('data-allow-rapid-clicks') is None
    page.locator("#r512ServiceButton").click()
    assert page.locator('#r512ServiceOverlay [role="dialog"]').count()==1,"Reopen did not show modal"
    page.locator("#r512ServiceOverlay .service-card[data-service='CONSULTA']").click()
    page.locator("#r512ServiceOverlay .service-card[data-service='CISTOSCOPIA']").click()
    page.locator("#r512ServiceOverlay .r512-price-input[data-service='CISTOSCOPIA']").fill("215.50")
    OUT_MODAL=ROOT/"reports"/"reception-512-service-modal-1600x900.png"
    page.screenshot(path=str(OUT_MODAL),full_page=False)
    page.locator("#r512Apply").click()
    assert page.locator("#r512ServiceOverlay").count()==0
    assert "CISTOSCOPIA" in page.locator("#r512SelectionPreview").inner_text()
    assert "$255.50" in page.locator("#r507BillingSummary").inner_text()
    assert page.locator("#procedureValuesBox .procedure-value-input[data-service='CISTOSCOPIA']").input_value()=="215.50"
    page.wait_for_selector("#v4504Payment .v4504-pay-option",timeout=10000)
    assert page.locator("#v4504Payment .v4504-pay-option").count()==4,"Real fiscal payment choices missing"
    page.locator("#v4504Payment [data-mode='EFECTIVO']").click()
    page.wait_for_function("document.querySelector('#v4504Payment .v4504-pay-state')?.textContent.includes('Efectivo')",timeout=10000)
    # Escape closes a reopened popup and preserves committed values.
    page.locator("#r512ServiceButton").click()
    page.keyboard.press("Escape")
    assert page.locator("#r512ServiceOverlay").count()==0
    assert "$255.50" in page.locator("#r507BillingSummary").inner_text()
    page.wait_for_function("document.querySelector('#r507HistoryList')?.textContent.includes('10/11/2026')",timeout=10000)
    # Production regression: the official v4613 overlay can prepend its
    # warning to the native form. It must not become an extra grid item.
    page.evaluate(r"""() => {
      const grid=document.querySelector('#atencion .r507-page-grid.attention-form-modal');
      const warning=document.createElement('div');
      warning.className='v4613-history-card warn';
      warning.textContent='⚠ Sin vincular con Historia Clínica';
      grid.prepend(warning);
    }""")
    # The clinical link action remains visible in the compact identity strip.
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
        workspace:rect('#atencion .r509-attention-workspace'),
        billing:rect('#atencion .r507-billing'),
        last:rect('#atencion .r509-last'),
        clinical:rect('#atencion .r509-link'),
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
        date:document.querySelector('#aFecha')?.value,
        dateHidden:getComputedStyle(document.querySelector('#atencion .r507-core-fields')).display,
        observationHidden:getComputedStyle(document.querySelector('#atencion .r507-observation')).display,
        latestText:document.querySelector('#r507HistoryList')?.textContent,
        agendaRemoved:!document.querySelector('#atencion #r507AgendaList')
      };
      return dom;
    }""")
    print("RECEPTION_507_VISUAL",json.dumps(layout,ensure_ascii=False))
    assert layout["viewport"]==[1600,900]
    assert layout["modalHidden"] is True,"Patient selection opened detached dossier modal"
    assert layout["misplacedWarningDisplay"]=="none","Legacy clinical warning must not take the first grid cell"
    assert layout["clinicalAction"],"Manual verified Historia linkage action must remain accessible"
    assert 'r507-main' in layout["gridAreas"] and 'r507-rail' not in layout["gridAreas"]
    assert layout["details"] is not None and layout["hasSave"] and layout["hasReview"]
    assert layout["realPaymentOptions"]==4 and "Efectivo" in layout["selectedPayment"],layout
    assert layout["details"]["x"]<layout["billing"]["x"],layout
    assert layout["last"]["y"]<layout["details"]["y"],layout
    assert layout["clinical"]["h"]<130,layout
    assert layout["agendaRemoved"] and layout["dateHidden"]=="none" and layout["observationHidden"]=="none",layout
    assert "10/11/2026" in layout["latestText"],layout
    assert layout["workspace"]["y"]+layout["workspace"]["h"]<=900, "Attention + billing should fit the 1600x900 viewport: "+str(layout)
    assert "MARÍA FERNANDA" in layout["patient"]
    assert "40.00" in layout["bill"]
    page.screenshot(path=str(OUT),full_page=True)
    if errors:
       print("BROWSER_ERRORS",json.dumps(errors[:8],ensure_ascii=False))
    browser.close()

srv.shutdown()
print("RECEPTION_507_NATIVE_NEW_ATTENTION_1600X900_VISUAL_OK",OUT)
