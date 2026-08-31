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
OUT = ROOT / "updates" / "v4_4_35_payment_per_card"


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def load_base_validator() -> dict:
    text = TEMPLATE.read_text(encoding="utf-8")
    old_out = 'OUT = ROOT / "updates" / "v4_4_33_ui_fix"'
    new_out = 'OUT = ROOT / "updates" / "v4_4_35_payment_per_card"'
    old_legacy = 'LEGACY_APP = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"'
    new_legacy = 'LEGACY_APP = ROOT / "updates" / "v4_4_34_payment_tick" / "app.py"'
    require(text.count(old_out) == 1, "Plantilla de validación cambió: OUT")
    require(text.count(old_legacy) == 1, "Plantilla de validación cambió: LEGACY_APP")
    text = text.replace(old_out, new_out, 1)
    text = text.replace(old_legacy, new_legacy, 1)
    text = text.replace("4.4.33", "4.4.35")
    text = text.replace("v4433", "v4435")
    text = text.replace("4433", "4435")
    ns = {
        "__file__": str(pathlib.Path(__file__).resolve()),
        "__name__": "v4435_inherited_validator",
    }
    exec(compile(text, "validate_candidate_v4435_inherited.py", "exec"), ns, ns)
    return ns


def payment_per_card_contract() -> None:
    app = (OUT / "app.py").read_text(encoding="utf-8")
    required = [
        'APP_VERSION = "4.4.35"',
        "const VERSION='4.4.35';",
        "window.__v4431BillingPayment=true",
        "window.__v4435BillingPayment=true",
        "parseIdentityFromActions",
        "identityFromCache",
        "findEmitButton",
        "foot.insertBefore(wrap,actions)",
        "setEmitLock(card,selected)",
        "v4435-pay-locked",
        "📦 Emitir por lotes",
        "batchPreflight",
        "listObserver.observe(list,{childList:true,subtree:false})",
        "Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.",
        "/api/billing/payment-method",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
    ]
    for marker in required:
        require(marker in app, f"Falta contrato v4.4.35: {marker}")
    require("document.querySelectorAll('.billing-card.aprobada')" not in app, "Volvió selector frágil .aprobada")
    require("new MutationObserver(()=>" not in app, "Volvió observer global regresivo")
    require(app.count('<span class=\"v4431-check\">✓</span>') >= 2, "Faltan vistos Efectivo/Transferencia")
    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == "4.4.35", "Manifest no quedó 4.4.35")
    require(manifest.get("copy") == ["app.py", "update_manifest.json"], "Manifest toca de más")
    require([x.get("path") for x in candidate.get("files", [])] == ["app.py", "update_manifest.json"], "Candidato toca de más")
    print("PAYMENT_PER_CARD_CONTRACT_OK")


def billing_card_fixture_smoke(v: dict, root: pathlib.Path) -> None:
    port = v["choose_free_port"](18816)
    env = os.environ.copy()
    env.update(
        RP_FORCE_OFFLINE="1",
        RP_DATA_DIR=str(root / "data"),
        RP_PORT=str(port),
        DISABLE_SQLALCHEMY_CEXT_RUNTIME="1",
    )
    diag = pathlib.Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "v4435-billing-fixture"
    diag.mkdir(parents=True, exist_ok=True)
    log = (diag / "backend.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([str(pathlib.Path(os.sys.executable)), str(root / "app.py")], cwd=str(root), env=env, stdout=log, stderr=log)
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"Backend fixture salió antes: {proc.returncode}")
            try:
                status, raw = v["get_bytes"](port, "/api/version", 1)
                if status == 200 and json.loads(raw).get("version") == "4.4.35":
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise AssertionError("Backend v4.4.35 no respondió para fixture")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 820})
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            response = page.goto(f"http://127.0.0.1:{port}/?fixture=v4435", wait_until="domcontentloaded", timeout=10000)
            require(response is not None and response.status == 200, "Fixture no abrió HTTP 200")
            page.wait_for_timeout(700)

            page.evaluate("""() => {
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
              if(!list)throw new Error('No existe #billingList');
              list.innerHTML=`
                <article class="billing-card aprobada">
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
              const wrap=card?.querySelector('.v4431-pay-wrap');
              const buttons=[...(wrap?.querySelectorAll('.v4431-pay-choice')||[])];
              const emit=[...card.querySelectorAll('button')].find(b=>String(b.textContent||'').includes('Revisar y emitir'));
              const batch=document.getElementById('btnEmitAll')||document.getElementById('v4435EmitAll');
              return {
                wrap:!!wrap,
                count:buttons.length,
                labels:buttons.map(b=>String(b.textContent||'').trim()),
                beforeActions:!!(wrap&&wrap.nextElementSibling?.classList?.contains('billing-actions')),
                emitDisabled:!!emit?.disabled,
                batch:!!batch,
                batchText:String(batch?.textContent||''),
                batchDisplay:batch?getComputedStyle(batch).display:'none'
              };
            }""")
            print("BILLING_FIXTURE_INITIAL", json.dumps(initial, ensure_ascii=True))
            require(initial["wrap"], "No apareció selector dentro de la ficha")
            require(initial["count"] == 2, "No aparecen exactamente Efectivo/Transferencia")
            require(any("Efectivo" in x for x in initial["labels"]), "Falta Efectivo")
            require(any("Transferencia" in x for x in initial["labels"]), "Falta Transferencia")
            require(initial["beforeActions"], "Selector no quedó entre TOTAL y acciones")
            require(initial["emitDisabled"], "Revisar y emitir no queda bloqueado antes de escoger")
            require(initial["batch"] and "lotes" in initial["batchText"].lower(), "No volvió Emitir por lotes")
            require(initial["batchDisplay"] != "none", "Botón por lotes sigue oculto")

            page.locator('#billingList .billing-card .v4431-pay-choice[data-pay="EFECTIVO"]').click()
            page.wait_for_timeout(120)
            after_cash = page.evaluate("""() => {
              const card=document.querySelector('#billingList .billing-card');
              const cash=card.querySelector('.v4431-pay-choice[data-pay="EFECTIVO"]');
              const transfer=card.querySelector('.v4431-pay-choice[data-pay="TRANSFERENCIA"]');
              const emit=[...card.querySelectorAll('button')].find(b=>String(b.textContent||'').includes('Revisar y emitir'));
              return {cashSelected:cash.classList.contains('selected'),transferSelected:transfer.classList.contains('selected'),emitDisabled:emit.disabled};
            }""")
            print("BILLING_FIXTURE_CASH", json.dumps(after_cash))
            require(after_cash["cashSelected"] and not after_cash["transferSelected"], "El visto no queda individual en Efectivo")
            require(not after_cash["emitDisabled"], "Revisar y emitir no se habilita después de escoger")

            page.evaluate("""() => {
              document.querySelector('#billingList').insertAdjacentHTML('beforeend',`
                <article class="billing-card aprobada">
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
            page.locator('#btnEmitAll, #v4435EmitAll').first.click()
            page.wait_for_timeout(100)
            blocked_batch = page.evaluate("""() => ({called:window.__batchCalled,lastAlert:window.__lastAlert,required:document.querySelectorAll('#billingList .v4431-pay-wrap.required').length})""")
            print("BILLING_FIXTURE_BATCH_BLOCK", json.dumps(blocked_batch, ensure_ascii=True))
            require(not blocked_batch["called"], "Lote se ejecutó con una factura sin forma de pago")
            require("individualmente" in blocked_batch["lastAlert"], "Lote no explica selección individual")
            require(blocked_batch["required"] >= 1, "Lote no resalta ficha faltante")

            page.locator('#billingList .billing-card').nth(1).locator('.v4431-pay-choice[data-pay="TRANSFERENCIA"]').click()
            page.wait_for_timeout(100)
            page.locator('#btnEmitAll, #v4435EmitAll').first.click()
            page.wait_for_timeout(100)
            allowed_batch = page.evaluate("""() => ({called:window.__batchCalled,secondSelected:document.querySelectorAll('#billingList .billing-card')[1].querySelector('.v4431-pay-choice[data-pay="TRANSFERENCIA"]').classList.contains('selected')})""")
            print("BILLING_FIXTURE_BATCH_OK", json.dumps(allowed_batch))
            require(allowed_batch["secondSelected"], "Transferencia no quedó seleccionada en segunda ficha")
            require(allowed_batch["called"], "Lote no continúa cuando todas tienen forma de pago")
            require(not errors, f"Errores JS en fixture: {errors}")
            page.screenshot(path=str(diag / "billing_fixture.png"), full_page=True)
            browser.close()
        print("REAL_BILLING_CARD_UI_OK")
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
    payment_per_card_contract()
    v["static_contract"]()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        launcher = v["reconstruct_launcher"](tmp)
        install = tmp / "full-install"
        v["prepare_install"](install, OUT / "app.py")
        v["browser_smoke"](pathlib.Path(v["os"].sys.executable), install)
        billing_card_fixture_smoke(v, install)
        v["updater_smoke"](launcher)
    print("V4435_ALL_VALIDATIONS_OK")


if __name__ == "__main__":
    main()
