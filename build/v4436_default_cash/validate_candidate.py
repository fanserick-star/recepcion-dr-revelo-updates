from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "build" / "v4433_ui_fix" / "validate_candidate.py"
OUT = ROOT / "updates" / "v4_4_36_default_cash"


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def load_base_validator() -> dict:
    text = TEMPLATE.read_text(encoding="utf-8")
    old_out = 'OUT = ROOT / "updates" / "v4_4_33_ui_fix"'
    new_out = 'OUT = ROOT / "updates" / "v4_4_36_default_cash"'
    old_legacy = 'LEGACY_APP = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"'
    new_legacy = 'LEGACY_APP = ROOT / "updates" / "v4_4_35_payment_per_card" / "app.py"'
    require(text.count(old_out) == 1, "Plantilla cambió: OUT")
    require(text.count(old_legacy) == 1, "Plantilla cambió: LEGACY_APP")
    text = text.replace(old_out, new_out, 1)
    text = text.replace(old_legacy, new_legacy, 1)
    text = text.replace("4.4.33", "4.4.36")
    text = text.replace("v4433", "v4436")
    text = text.replace("4433", "4436")
    ns = {
        "__file__": str(pathlib.Path(__file__).resolve()),
        "__name__": "v4436_inherited_validator",
    }
    exec(compile(text, "validate_candidate_v4436_inherited.py", "exec"), ns, ns)
    return ns


def contract() -> None:
    app = (OUT / "app.py").read_text(encoding="utf-8")
    required = [
        'APP_VERSION = "4.4.36"',
        "const VERSION='4.4.36';",
        "window.__v4435BillingPayment=true",
        '.where(core.BillingRecord.estado != "EMITIDA")',
        'method = _payment_from_visit(visit) or "EFECTIVO"',
        "const selected=paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO';",
        "return !(paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO');",
        "const locked=false;",
        '<span class=\"v4431-check\">✓</span><span>💵 Efectivo</span>',
        '<span class=\"v4431-check\">✓</span><span>🏦 Transferencia</span>',
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "📦 Emitir por lotes",
        "batchPreflight",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
    ]
    for marker in required:
        require(marker in app, f"Falta contrato 4.4.36: {marker}")
    forbidden = [
        "Primero aprueba la ficha y luego selecciona la forma de pago.",
        '.where(core.BillingRecord.estado == "APROBADA")',
        "document.querySelectorAll('.billing-card.aprobada')",
        "new MutationObserver(()=>",
    ]
    for marker in forbidden:
        require(marker not in app, f"Regresión 4.4.36: {marker}")
    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == "4.4.36", "Manifest incorrecto")
    require(manifest.get("copy") == ["app.py", "update_manifest.json"], "Manifest toca archivos extra")
    require([x.get("path") for x in candidate.get("files", [])] == ["app.py", "update_manifest.json"], "Canal toca archivos extra")
    print("DEFAULT_CASH_CONTRACT_OK")


def server_pending_state_smoke(runtime_python: pathlib.Path, root: pathlib.Path) -> None:
    script = root / "_v4436_pending_state_test.py"
    script.write_text(
        '''import importlib.util, os, pathlib, sys\n'''
        '''from datetime import date\n'''
        '''root=pathlib.Path(__file__).resolve().parent\n'''
        '''sys.path.insert(0,str(root))\n'''
        '''spec=importlib.util.spec_from_file_location("rp_candidate_4436",root/"app.py")\n'''
        '''m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n'''
        '''class Visit:\n'''
        '''    id=1; patient_id=777; source_row=None\n'''
        '''class Billing:\n'''
        '''    estado="PENDIENTE"\n'''
        '''visit=Visit(); billing=Billing()\n'''
        '''class Result:\n'''
        '''    def all(self): return [(visit,billing)]\n'''
        '''class DB:\n'''
        '''    def execute(self,q): return Result()\n'''
        '''    def commit(self): self.committed=True\n'''
        '''db=DB()\n'''
        '''m.core.is_offline_db=lambda _db: False\n'''
        '''m.core.audit=lambda *a,**k: None\n'''
        '''m.core.mirror_visit_to_local=lambda *a,**k: None\n'''
        '''route=next(r.endpoint for r in m.app.routes if getattr(r,"path","")=="/api/billing/payment-method" and "POST" in getattr(r,"methods",set()))\n'''
        '''data=m.BillingPaymentMethodIn.construct(patient_id=777,fecha=date(2026,8,31),payment_method="TRANSFERENCIA")\n'''
        '''out=route(data=data,db=db,user=object())\n'''
        '''assert out["payment_method"]=="TRANSFERENCIA",out\n'''
        '''assert out["sri_payment_code"]=="20",out\n'''
        '''assert visit.source_row==m.PAYMENT_SENTINELS["TRANSFERENCIA"],visit.source_row\n'''
        '''print("PENDING_STATE_SELECTION_OK")\n''',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(RP_FORCE_OFFLINE="1", RP_DATA_DIR=str(root / "data"), DISABLE_SQLALCHEMY_CEXT_RUNTIME="1")
    result = subprocess.run([str(runtime_python), str(script)], cwd=str(root), env=env, text=True, capture_output=True, timeout=45)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="")
        raise AssertionError(f"Selección en estado PENDIENTE falló: {result.returncode}")
    require("PENDING_STATE_SELECTION_OK" in result.stdout, "No confirmó selección en PENDIENTE")
    script.unlink(missing_ok=True)


def billing_fixture(v: dict, root: pathlib.Path) -> None:
    port = v["choose_free_port"](18836)
    env = os.environ.copy()
    env.update(
        RP_FORCE_OFFLINE="1",
        RP_DATA_DIR=str(root / "data"),
        RP_PORT=str(port),
        DISABLE_SQLALCHEMY_CEXT_RUNTIME="1",
    )
    diag = pathlib.Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "v4436-billing-fixture"
    diag.mkdir(parents=True, exist_ok=True)
    log = (diag / "backend.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([str(pathlib.Path(os.sys.executable)), str(root / "app.py")], cwd=str(root), env=env, stdout=log, stderr=log)
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"Backend fixture salió: {proc.returncode}")
            try:
                status, raw = v["get_bytes"](port, "/api/version", 1)
                if status == 200 and json.loads(raw).get("version") == "4.4.36":
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise AssertionError("Backend v4.4.36 no respondió")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 820})
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            response = page.goto(f"http://127.0.0.1:{port}/?fixture=v4436", wait_until="domcontentloaded", timeout=10000)
            require(response is not None and response.status == 200, "Fixture no abrió HTTP 200")
            page.wait_for_timeout(700)

            page.evaluate("""() => {
              const section=document.querySelector('#facturacion');
              if(section){section.classList.add('active');section.style.setProperty('display','block','important')}
              window.__fixturePayments = new Map();
              window.__batchCalled = false;
              window.__lastAlert = '';
              window.alert = msg => { window.__lastAlert = String(msg || ''); };
              const realApi = window.api;
              window.api = async (url, opts={}) => {
                if(url === '/api/billing/payment-methods'){
                  return {items:[...window.__fixturePayments.entries()].map(([k,method])=>{
                    const [patient_id,fecha]=k.split('|');
                    return {patient_id:Number(patient_id),fecha,payment_method:method,mixed:false};
                  })};
                }
                if(url === '/api/billing/payment-method'){
                  const body=JSON.parse(String(opts.body||'{}'));
                  const k=`${Number(body.patient_id)}|${String(body.fecha).slice(0,10)}`;
                  window.__fixturePayments.set(k,String(body.payment_method||''));
                  return {ok:true,patient_id:Number(body.patient_id),fecha:String(body.fecha).slice(0,10),payment_method:String(body.payment_method||'')};
                }
                return realApi(url,opts);
              };
              window.emitAllPendingInvoices = () => { window.__batchCalled = true; };
              const list=document.querySelector('#billingList');
              list.innerHTML=`
                <article class="billing-card pendiente">
                  <div class="billing-card-head"><div class="billing-patient-name">PACIENTE PRUEBA UNO</div></div>
                  <div class="billing-lines"><div class="billing-line"><span>CONSULTA</span><b>$40.00</b></div></div>
                  <div class="billing-card-foot">
                    <div class="billing-total"><span>TOTAL</span><strong>$40.00</strong></div>
                    <div class="billing-actions">
                      <button onclick="openBillingRecipientEditor(777,'2026-08-31')">👤 Facturar con otros datos</button>
                      <button class="primary">✓ Revisar y emitir</button>
                    </div>
                  </div>
                </article>`;
              window.__v4435BillingPaymentTest?.decorate();
            }""")
            page.wait_for_timeout(180)

            initial = page.evaluate("""() => {
              const card=document.querySelector('#billingList .billing-card');
              const cash=card.querySelector('.v4431-pay-choice[data-pay="EFECTIVO"]');
              const transfer=card.querySelector('.v4431-pay-choice[data-pay="TRANSFERENCIA"]');
              const emit=[...card.querySelectorAll('button')].find(b=>String(b.textContent||'').includes('Revisar y emitir'));
              const wrap=card.querySelector('.v4431-pay-wrap');
              return {
                cashSelected:cash?.classList.contains('selected'),
                transferSelected:transfer?.classList.contains('selected'),
                emitDisabled:!!emit?.disabled,
                beforeActions:!!(wrap&&wrap.nextElementSibling?.classList?.contains('billing-actions')),
                alert:window.__lastAlert,
                saved:[...window.__fixturePayments.entries()]
              };
            }""")
            print("DEFAULT_CASH_INITIAL", json.dumps(initial, ensure_ascii=True))
            require(initial["cashSelected"] is True, "Efectivo no aparece marcado por defecto")
            require(initial["transferSelected"] is False, "Transferencia aparece marcada por defecto")
            require(initial["emitDisabled"] is False, "Revisar y emitir quedó bloqueado con Efectivo por defecto")
            require(initial["beforeActions"], "Selector no quedó antes de las acciones")
            require(initial["alert"] == "", "Apareció alerta al cargar")
            require(initial["saved"] == [], "Efectivo por defecto hizo escritura innecesaria")

            page.locator('.v4431-pay-choice[data-pay="TRANSFERENCIA"]').click()
            page.wait_for_timeout(160)
            changed = page.evaluate("""() => {
              const card=document.querySelector('#billingList .billing-card');
              return {
                cash:card.querySelector('.v4431-pay-choice[data-pay="EFECTIVO"]').classList.contains('selected'),
                transfer:card.querySelector('.v4431-pay-choice[data-pay="TRANSFERENCIA"]').classList.contains('selected'),
                alert:window.__lastAlert,
                saved:[...window.__fixturePayments.entries()]
              };
            }""")
            print("TRANSFER_CHANGE", json.dumps(changed, ensure_ascii=True))
            require(changed["cash"] is False and changed["transfer"] is True, "No cambió manualmente a Transferencia")
            require(changed["alert"] == "", f"Apareció alerta al cambiar método: {changed['alert']}")
            require(changed["saved"] and changed["saved"][0][1] == "TRANSFERENCIA", "Transferencia no quedó guardada")

            page.evaluate("window.__v4435BillingPaymentTest?.decorate()")
            page.wait_for_timeout(80)
            require(page.locator('.v4431-pay-choice[data-pay="TRANSFERENCIA"]').get_attribute('class').find('selected') >= 0, "Se perdió Transferencia al redecorar")

            page.evaluate("""() => {
              document.querySelector('#billingList').insertAdjacentHTML('beforeend',`
                <article class="billing-card pendiente">
                  <div class="billing-card-head"><div class="billing-patient-name">PACIENTE PRUEBA DOS</div></div>
                  <div class="billing-lines"><div class="billing-line"><span>CONSULTA</span><b>$35.00</b></div></div>
                  <div class="billing-card-foot">
                    <div class="billing-total"><span>TOTAL</span><strong>$35.00</strong></div>
                    <div class="billing-actions">
                      <button onclick="openBillingRecipientEditor(778,'2026-08-31')">👤 Facturar con otros datos</button>
                      <button class="primary">✓ Revisar y emitir</button>
                    </div>
                  </div>
                </article>`);
              window.__v4435BillingPaymentTest?.decorate();
            }""")
            page.wait_for_timeout(120)
            second_default = page.evaluate("""() => {
              const c=document.querySelectorAll('#billingList .billing-card')[1];
              return {cash:c.querySelector('.v4431-pay-choice[data-pay="EFECTIVO"]').classList.contains('selected'),emit:[...c.querySelectorAll('button')].find(b=>String(b.textContent||'').includes('Revisar y emitir')).disabled};
            }""")
            require(second_default["cash"] is True and second_default["emit"] is False, "Segunda ficha no heredó Efectivo por defecto")
            page.evaluate("window.__batchCalled=false;window.__lastAlert=''")
            page.locator('#btnEmitAll, #v4435EmitAll').first.click()
            page.wait_for_timeout(180)
            batch = page.evaluate("() => ({called:window.__batchCalled,alert:window.__lastAlert})")
            print("DEFAULT_CASH_BATCH", json.dumps(batch, ensure_ascii=True))
            require(batch["called"] is True, "Lote no acepta Efectivo por defecto")
            require(batch["alert"] == "", "Lote mostró alerta con métodos efectivos válidos")
            require(not errors, f"Errores JS en fixture: {errors}")
            page.screenshot(path=str(diag / "billing_default_cash.png"), full_page=True)
            browser.close()
        print("REAL_DEFAULT_CASH_UI_OK")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        log.close()


def main() -> None:
    v = load_base_validator()
    contract()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        launcher = v["reconstruct_launcher"](tmp)
        install = tmp / "full-install"
        v["prepare_install"](install, OUT / "app.py")
        v["browser_smoke"](pathlib.Path(v["os"].sys.executable), install)
        server_pending_state_smoke(pathlib.Path(v["os"].sys.executable), install)
        billing_fixture(v, install)
        v["updater_smoke"](launcher)
    print("V4436_ALL_VALIDATIONS_OK")


if __name__ == "__main__":
    main()
