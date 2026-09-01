from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/"updates"/"v4_4_43_daily_emitted_whatsapp_schedule"
TEMPLATE=ROOT/"build"/"v4433_ui_fix"/"validate_candidate.py"


def require(cond,msg):
    if not cond: raise AssertionError(msg)


def build():
    subprocess.run([sys.executable,str(ROOT/"build"/"v4443_daily_emitted_whatsapp_schedule"/"build_v4443.py")],cwd=ROOT,check=True)


def contract():
    app=(OUT/"app.py").read_text(encoding="utf-8")
    compile(app,"app.py","exec")
    required=[
      'APP_VERSION = "4.4.43"',"const VERSION='4.4.43';","_wa_timeline_defs_v4443","Se enviará:",
      "window.__v4443DailyEmitted=true","Últimos 7 días","No hay facturas emitidas hoy.",
      'method = _payment_from_visit(visit) or "EFECTIVO"','"EFECTIVO": "01"','"TRANSFERENCIA": "20"',
      "core._azur_payload_for_group = _azur_payload_for_group_v4431","_rp_diag" if False else "window.__v4435BillingPayment=true",
    ]
    for marker in required: require(marker in app,f"Falta contrato: {marker}")
    manifest=json.loads((OUT/"update_manifest.json").read_text(encoding="utf-8"))
    candidate=json.loads((OUT/"candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version")=="4.4.43" and manifest.get("app_version")=="4.4.43","Manifest incorrecto")
    require(manifest.get("required_python_packages")==[{"import":"pg8000","pip":"pg8000==1.31.2"}],"Se perdió guardia pg8000")
    paths=[x.get("path") for x in candidate.get("files",[])]
    require(paths==["ABRIR_RECEPCION.py","app_base_4428.py","app.py","static/app.js","static/index.html","update_manifest.json"],"Release dejó de ser acumulativo")
    launcher=b"".join((OUT/f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1,5)).decode("utf-8-sig")
    compile(launcher,"ABRIR_RECEPCION.py","exec")
    for marker in ("_rp_ensure_python_runtime","_rp_diag_upload_via_venv","_rp_v4437_required_files","_choose_app_port"):
        require(marker in launcher,f"Launcher perdió {marker}")
    print("V4443_CONTRACT_OK")


def planned_time_unit():
    tree=ast.parse((OUT/"app.py").read_text(encoding="utf-8"))
    fn=next((n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="_v4443_planned_label"),None)
    require(fn is not None,"No se encontró formatter planned")
    module=ast.Module(body=[fn],type_ignores=[]);ast.fix_missing_locations(module)
    ns={"core":SimpleNamespace(datetime=datetime)}
    exec(compile(module,"planned_unit.py","exec"),ns,ns)
    f=ns["_v4443_planned_label"]
    require(f("2026-09-03T08:00:00")=="Se enviará: jue 3 sep · 8:00 a. m.",f("2026-09-03T08:00:00"))
    require(f("2026-09-04T13:05:00")=="Se enviará: vie 4 sep · 1:05 p. m.",f("2026-09-04T13:05:00"))
    print("V4443_WHATSAPP_PLANNED_TIME_OK")


def extract_js():
    tree=ast.parse((OUT/"app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
            if any(isinstance(t,ast.Name) and t.id=="V4443_UI_JS" for t in node.targets):
                return node.value.value
    raise AssertionError("No se encontró V4443_UI_JS")


def billing_ui_browser():
    js=extract_js()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1000,"height":700})
        errors=[];page.on("pageerror",lambda exc:errors.append(str(exc)))
        page.set_content('''<select id="bEstado"><option value="PENDIENTE">Pendiente</option><option value="EMITIDA" selected>Emitida</option></select><section id="facturacion"><div id="billingList"></div></section><script>var billingGroupsCache=[];function billingCardHtml(g){return `<article class="billing-card" data-fecha="${g.fecha}">${g.patient.nombre} | ${g.fecha}</article>`}window.loadBilling=async()=>true;window.setBillingStatus=async function(s){document.querySelector('#bEstado').value=String(s||'').toUpperCase();return true}</script>''')
        page.add_script_tag(content=js)
        page.evaluate('''() => {const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;const d0=new Date();d0.setHours(12,0,0,0);const d1=new Date(d0);d1.setDate(d1.getDate()-1);const d6=new Date(d0);d6.setDate(d6.getDate()-6);const d8=new Date(d0);d8.setDate(d8.getDate()-8);billingGroupsCache=[{fecha:iso(d0),patient:{nombre:'HOY'}},{fecha:iso(d1),patient:{nombre:'AYER'}},{fecha:iso(d6),patient:{nombre:'DIA6'}},{fecha:iso(d8),patient:{nombre:'DIA8'}}];window.__v4443EmittedRangeTest.renderEmittedRange()}''')
        today=page.locator('#billingList .billing-card').all_text_contents()
        require(len(today)==1 and today[0].startswith('HOY'),f"Hoy incorrecto: {today}")
        bar=page.locator('#v4443EmittedRange').inner_text()
        require("Hoy · 1" in bar and "Últimos 7 días · 3" in bar,f"Conteos incorrectos: {bar}")
        page.evaluate("window.__v4443EmittedRangeTest.setRange('week')")
        week=page.locator('#billingList .billing-card').all_text_contents()
        require(len(week)==3 and not any('DIA8' in x for x in week),f"Semana incorrecta: {week}")
        page.evaluate("window.setBillingStatus('EMITIDA')")
        page.wait_for_timeout(30)
        require(window_range:=page.evaluate("window.__v4443EmittedRangeTest.getRange()")=='today',f"EMITIDA no vuelve a Hoy: {window_range}")
        require(not errors,f"Errores JS: {errors}")
        browser.close()
    print("V4443_BILLING_TODAY_WEEK_BROWSER_OK")


def load_base_validator():
    text=TEMPLATE.read_text(encoding="utf-8")
    text=text.replace('OUT = ROOT / "updates" / "v4_4_33_ui_fix"','OUT = ROOT / "updates" / "v4_4_43_daily_emitted_whatsapp_schedule"',1)
    text=text.replace('LEGACY_APP = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"','LEGACY_APP = ROOT / "updates" / "v4_4_35_payment_per_card" / "app.py"',1)
    text=text.replace("4.4.33","4.4.43").replace("v4433","v4443").replace("4433","4443")
    ns={"__file__":str(pathlib.Path(__file__).resolve()),"__name__":"v4443_inherited"}
    exec(compile(text,"validate_candidate_v4443_inherited.py","exec"),ns,ns)
    return ns


def functional_smoke():
    v=load_base_validator()
    with tempfile.TemporaryDirectory() as td:
        tmp=pathlib.Path(td)
        install=tmp/"full-install"
        v["prepare_install"](install,OUT/"app.py")
        v["browser_smoke"](pathlib.Path(sys.executable),install)
        launcher=v["reconstruct_launcher"](tmp)
        v["updater_smoke"](launcher)
    print("V4443_FUNCTIONAL_BROWSER_UPDATER_OK")


def main():
    build();contract();planned_time_unit();billing_ui_browser();functional_smoke();print("VALIDATE_V4443_OK")

if __name__=="__main__":main()
