from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "updates" / "v4_4_34_payment_tick" / "app.py"
OUT = ROOT / "updates" / "v4_4_35_payment_per_card"
VERSION = "4.4.35"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def main() -> None:
    src = SOURCE.read_text(encoding="utf-8")
    css = (HERE / "payment.css").read_text(encoding="utf-8").rstrip()
    js = (HERE / "payment.js").read_text(encoding="utf-8").rstrip()
    if 'APP_VERSION = "4.4.34"' not in src:
        raise SystemExit("La fuente ya no es v4.4.34")

    text = replace_once(src, 'APP_VERSION = "4.4.34"', f'APP_VERSION = "{VERSION}"', "APP_VERSION")

    css_start = text.index('    PAYMENT_CSS = r"""')
    js_start = text.index('    PAYMENT_JS = r"""')
    css_block = '    PAYMENT_CSS = r"""\n' + css + '\n"""\n\n'
    text = text[:css_start] + css_block + text[js_start:]

    js_start = text.index('    PAYMENT_JS = r"""')
    js_end = text.index('    _v459_base =', js_start)
    js_block = '    PAYMENT_JS = r"""\n' + js + '\n"""\n\n'
    text = text[:js_start] + js_block + text[js_end:]

    # Tras reemplazar PAYMENT_JS, queda una sola referencia vieja: la versión
    # que el wrapper coloca dentro del overlay estable v4.4.28.
    text = replace_once(text, "const VERSION='4.4.34';", f"const VERSION='{VERSION}';", "versión overlay")

    required = [
        "import app_base_4428 as core",
        "PAYMENT_SENTINELS",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "/api/billing/payment-method",
        "window.__v4431BillingPayment=true",
        "window.__v4435BillingPayment=true",
        "parseIdentityFromActions",
        "identityFromCache",
        "openBillingRecipientEditor",
        "foot.insertBefore(wrap,actions)",
        "v4435-pay-locked",
        "📦 Emitir por lotes",
        "batchPreflight",
        "listObserver.observe(list,{childList:true,subtree:false})",
        "Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
        "core.V459_SETTINGS_JS = _v459_base",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"Se perdió funcionalidad requerida: {marker}")
    if "document.querySelectorAll('.billing-card.aprobada')" in text:
        raise SystemExit("Quedó el selector frágil antiguo")
    if "new MutationObserver(()=>" in text:
        raise SystemExit("No se permite reintroducir el observer global regresivo")

    compile(text, "app.py", "exec")
    OUT.mkdir(parents=True, exist_ok=True)
    app_path = OUT / "app.py"
    app_path.write_text(text, encoding="utf-8", newline="\n")

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.100-standalone-7-dynamic-port",
        "updater_version": "integrado-en-launcher",
        "copy": ["app.py", "update_manifest.json"],
        "notes": "Forma de pago individual visible entre TOTAL y acciones de cada factura POR EMITIR; bloquea Revisar y emitir hasta escoger Efectivo/Transferencia y restaura Emitir por lotes con prevalidación individual. No toca launcher, static, .env ni datos.",
    }
    manifest_path = OUT / "update_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.35: Efectivo/Transferencia aparece dentro de cada ficha POR EMITIR, justo antes de Revisar y emitir. La elección es individual y obligatoria; también vuelve Emitir por lotes, que exige que cada factura tenga su forma de pago. No toca datos, .env ni static.",
        "files": [
            {
                "path": "app.py",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_35_payment_per_card/app.py",
                "sha256": sha256(app_path),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_35_payment_per_card/update_manifest.json",
                "sha256": sha256(manifest_path),
                "encoding": "utf-8",
            },
        ],
    }
    (OUT / "candidate_latest.json").write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("V4435_BUILT", sha256(app_path))


if __name__ == "__main__":
    main()
