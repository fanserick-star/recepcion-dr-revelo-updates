from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "build" / "v4433_ui_fix" / "validate_candidate.py"
OUT = ROOT / "updates" / "v4_4_34_payment_tick"


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def load_base_validator() -> dict:
    text = TEMPLATE.read_text(encoding="utf-8")
    old_out = 'OUT = ROOT / "updates" / "v4_4_33_ui_fix"'
    new_out = 'OUT = ROOT / "updates" / "v4_4_34_payment_tick"'
    old_legacy = 'LEGACY_APP = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"'
    new_legacy = 'LEGACY_APP = ROOT / "updates" / "v4_4_33_ui_fix" / "app.py"'
    require(text.count(old_out) == 1, "Plantilla de validación cambió: OUT")
    require(text.count(old_legacy) == 1, "Plantilla de validación cambió: LEGACY_APP")
    text = text.replace(old_out, new_out, 1)
    text = text.replace(old_legacy, new_legacy, 1)
    text = text.replace("4.4.33", "4.4.34")
    text = text.replace("v4433", "v4434")
    text = text.replace("4433", "4434")
    ns = {
        "__file__": str(pathlib.Path(__file__).resolve()),
        "__name__": "v4434_inherited_validator",
    }
    exec(compile(text, "validate_candidate_v4434_inherited.py", "exec"), ns, ns)
    return ns


def payment_tick_contract() -> None:
    app = (OUT / "app.py").read_text(encoding="utf-8")
    require('APP_VERSION = "4.4.34"' in app, "APP_VERSION no quedó 4.4.34")
    require("const VERSION='4.4.34';" in app, "Frontend no quedó 4.4.34")
    require(
        "document.querySelectorAll('.billing-card').forEach(card=>renderPicker(card));" in app,
        "La forma de pago no se monta sobre fichas POR EMITIR",
    )
    require(
        "const card=btn.closest('.billing-card');" in app,
        "El bloqueo previo a emisión no reconoce la ficha POR EMITIR",
    )
    require(".billing-card.aprobada" not in app, "Quedó selector antiguo .aprobada")
    require(app.count('<span class=\"v4431-check\">✓</span>') >= 2, "Faltan vistos de Efectivo/Transferencia")
    require("paymentMap.set(key(patient_id,fecha)" in app, "La elección no queda persistida en el mapa local")
    require("/api/billing/payment-method" in app, "Se perdió guardado de forma de pago")
    require('"EFECTIVO": "01"' in app and '"TRANSFERENCIA": "20"' in app, "Se perdieron códigos SRI 01/20")
    require("Antes de emitir, marca Efectivo o Transferencia en la ficha." in app, "Se perdió bloqueo de seguridad")
    require("font-weight:950" in app and "box-shadow:0 0 0 2px rgba(47,141,89,.12)" in app, "El visto seleccionado no quedó reforzado")
    print("PAYMENT_TICK_CONTRACT_OK")


def main() -> None:
    v = load_base_validator()
    payment_tick_contract()
    v["static_contract"]()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        launcher = v["reconstruct_launcher"](tmp)
        install = tmp / "full-install"
        v["prepare_install"](install, OUT / "app.py")
        v["browser_smoke"](pathlib.Path(v["os"].sys.executable), install)
        v["updater_smoke"](launcher)
    print("V4434_ALL_VALIDATIONS_OK")


if __name__ == "__main__":
    main()
