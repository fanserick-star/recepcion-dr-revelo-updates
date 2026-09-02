from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"
TEMPLATE = ROOT / "build" / "v4433_ui_fix" / "validate_candidate.py"


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    subprocess.run([sys.executable, str(ROOT / "build" / "v4444_weekly_appointment_guard" / "build_v4444.py")], cwd=ROOT, check=True)


def contract():
    app = (OUT / "app.py").read_text(encoding="utf-8")
    compile(app, "app.py", "exec")
    for marker in [
        'APP_VERSION = "4.4.44"',
        '/api/agenda/appointments/guarded',
        '/api/agenda/week-conflict',
        'AgendaGuardedAppointmentIn',
        '_v4444_same_week_conflict',
        'Agendar de todas formas',
        'core.agenda_create(stable_data, db, user)',
        'core.appointment_conflicts(db, values["fecha"], values["hora"], 20)',
        'window.__v4444WeeklyAppointmentGuard=true',
        'method = _payment_from_visit(visit) or "EFECTIVO"',
        'core._azur_payload_for_group = _azur_payload_for_group_v4431',
        '_wa_timeline_defs_v4443',
        'window.__v4443DailyEmitted=true',
    ]:
        require(marker in app, f"Falta contrato: {marker}")

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == "4.4.44" and candidate.get("version") == "4.4.44", "Versión incorrecta")
    require(manifest.get("required_python_packages") == [{"import": "pg8000", "pip": "pg8000==1.31.2"}], "Se perdió guardia pg8000")
    require(sha(OUT / "app_base_4428.py") == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba", "Se modificó la base estable")
    require(sha(OUT / "static" / "app.js") == "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90", "Se modificó JS base")
    require(sha(OUT / "static" / "index.html") == "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728", "Se modificó HTML base")
    launcher = b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))
    require(hashlib.sha256(launcher).hexdigest() == "39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e", "Launcher cambió")
    compile(launcher.decode("utf-8-sig"), "ABRIR_RECEPCION.py", "exec")
    print("V4444_CONTRACT_OK")


def extract_js():
    tree = ast.parse((OUT / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id == "V4444_WEEK_GUARD_JS" for t in node.targets):
                return node.value.value
    raise AssertionError("No se encontró V4444_WEEK_GUARD_JS")


def browser_guard():
    js = extract_js()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 900, "height": 700})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.set_content('''
          <input id="agendaDate" value="2026-09-04"><input id="agendaTime" value="09:20"><input id="agendaNote" value="CONTROL">
          <script>
          let agendaPatientCache={id:7,nombre:'PACIENTE PRUEBA'},agendaNativeAnchor='';
          let calls=[],closed=0,loaded=0;
          const $=s=>document.querySelector(s);
          const esc=s=>String(s??'').replace(/[&<>"']/g,'');
          const fmtDate=s=>String(s||''); const fmtTime=s=>String(s||'');
          function invalidateAgendaSlotCache(){} function invalidateAttentionWeekCache(){}
          function closeModal(){closed++} async function loadAgenda(){loaded++}
          async function singleFlightMutation(k,fn){return fn()}
          async function api(url,opt){calls.push({url,body:opt?.body?JSON.parse(opt.body):null}); if(calls.length===1)return {created:false,same_week_conflict:{date:'2026-09-03',time:'09:00',name:'PACIENTE PRUEBA'}}; return {created:true,appointment:{id:99}}}
          </script>
        ''')
        page.add_script_tag(content=js)
        page.evaluate("window.__guardPromise=saveAgendaAppointment()")
        page.wait_for_selector('.v4444-week-guard-backdrop')
        require(page.locator('[data-action="cancel"]').inner_text() == 'Cancelar', "Falta botón Cancelar")
        require(page.locator('[data-action="proceed"]').inner_text() == 'Agendar de todas formas', "Falta override explícito")
        page.click('[data-action="cancel"]')
        page.evaluate("window.__guardPromise")
        require(page.evaluate("calls.length") == 1, "Cancelar creó/reintentó una cita")
        require(page.evaluate("calls[0].body.allow_same_week") is False, "Primer intento no usa guardia")

        page.evaluate("calls=[];closed=0;loaded=0;window.__guardPromise2=saveAgendaAppointment()")
        page.wait_for_selector('.v4444-week-guard-backdrop')
        page.click('[data-action="proceed"]')
        page.evaluate("window.__guardPromise2")
        require(page.evaluate("calls.length") == 2, "Override no hizo segundo intento")
        require(page.evaluate("calls[1].body.allow_same_week") is True, "Override no quedó explícito")
        require(page.evaluate("closed===1 && loaded===1"), "Guardado no refrescó Agenda")
        require(not errors, f"Errores JS: {errors}")
        browser.close()
    print("V4444_BROWSER_GUARD_OK")


def inherited_functional_smoke():
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace('OUT = ROOT / "updates" / "v4_4_33_ui_fix"', 'OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"', 1)
    text = text.replace('LEGACY_APP = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"', 'LEGACY_APP = ROOT / "updates" / "v4_4_35_payment_per_card" / "app.py"', 1)
    text = text.replace("4.4.33", "4.4.44").replace("v4433", "v4444").replace("4433", "4444")
    ns = {"__file__": str(pathlib.Path(__file__).resolve()), "__name__": "v4444_inherited"}
    exec(compile(text, "validate_candidate_v4444_inherited.py", "exec"), ns, ns)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        install = tmp / "full-install"
        ns["prepare_install"](install, OUT / "app.py")
        ns["browser_smoke"](pathlib.Path(sys.executable), install)
        launcher = ns["reconstruct_launcher"](tmp)
        ns["updater_smoke"](launcher)
    print("V4444_FUNCTIONAL_BROWSER_UPDATER_OK")


def main():
    build()
    contract()
    browser_guard()
    inherited_functional_smoke()
    print("VALIDATE_V4444_OK")


if __name__ == "__main__":
    main()
