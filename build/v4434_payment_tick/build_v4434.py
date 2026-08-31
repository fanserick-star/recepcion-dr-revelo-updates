from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_33_ui_fix" / "app.py"
OUT = ROOT / "updates" / "v4_4_34_payment_tick"
VERSION = "4.4.34"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def main() -> None:
    src = SOURCE.read_text(encoding="utf-8")
    if 'APP_VERSION = "4.4.33"' not in src:
        raise SystemExit("La fuente ya no es v4.4.33")

    text = replace_once(src, 'APP_VERSION = "4.4.33"', f'APP_VERSION = "{VERSION}"', "APP_VERSION")

    # El literal de versión aparece dos veces: dentro del módulo de pago y en la
    # sustitución del overlay estable. Ambos deben avanzar juntos.
    version_marker = "const VERSION='4.4.33';"
    if text.count(version_marker) != 2:
        raise SystemExit(f"VERSION frontend: esperaba 2 coincidencias y encontró {text.count(version_marker)}")
    text = text.replace(version_marker, f"const VERSION='{VERSION}';")

    # v4.4.33 buscaba únicamente '.billing-card.aprobada'. La tarjeta que ve el
    # usuario se presenta como POR EMITIR y no siempre conserva esa clase visual,
    # aunque sí tiene el botón real previewAzurInvoice. renderPicker ya valida ese
    # botón, por lo que recorrer todas las billing-card es seguro y más robusto.
    text = replace_once(
        text,
        "document.querySelectorAll('.billing-card.aprobada').forEach(card=>renderPicker(card));",
        "document.querySelectorAll('.billing-card').forEach(card=>renderPicker(card));",
        "selector de tarjetas para forma de pago",
    )
    text = replace_once(
        text,
        "const card=btn.closest('.billing-card.aprobada');",
        "const card=btn.closest('.billing-card');",
        "protección visual al emitir",
    )

    # El visto ya formaba parte del control seleccionado. Lo reforzamos para que
    # la elección sea inequívoca: círculo verde + ✓ blanco + texto en negrita.
    old_css = """.v4431-pay-choice.selected .v4431-check{\n  border-color:#3d9b67;background:#3d9b67;color:#fff\n}"""
    new_css = """.v4431-pay-choice.selected .v4431-check{\n  border-color:#2f8d59;background:#2f8d59;color:#fff;font-weight:950;\n  box-shadow:0 0 0 2px rgba(47,141,89,.12)\n}\n.v4431-pay-choice.selected span:last-child{font-weight:950}"""
    text = replace_once(text, old_css, new_css, "visto visual de forma de pago")

    required = [
        "import app_base_4428 as core",
        "PAYMENT_SENTINELS",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "Antes de emitir, marca Efectivo o Transferencia en la ficha.",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
        "window.__v4431BillingPayment",
        "document.querySelectorAll('.billing-card').forEach(card=>renderPicker(card));",
        "const card=btn.closest('.billing-card');",
        '<span class=\"v4431-check\">✓</span><span>💵 Efectivo</span>',
        '<span class=\"v4431-check\">✓</span><span>🏦 Transferencia</span>',
        "core.V459_SETTINGS_JS = _v459_base",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"Se perdió funcionalidad requerida: {marker}")
    if ".billing-card.aprobada" in text:
        raise SystemExit("Quedó selector visual antiguo que ocultaba la forma de pago")

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
        "notes": "Parche mínimo sobre v4.4.33: muestra la forma de pago también en fichas POR EMITIR y deja un visto verde persistente en Efectivo o Transferencia. No toca launcher, static, .env ni datos.",
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
        "message": "v4.4.34: muestra Efectivo/Transferencia directamente en cada ficha POR EMITIR y deja un visto verde en la opción guardada. Conserva el bloqueo antes de AZUR, el código SRI 01/20 y el launcher dinámico. No toca datos, .env ni static.",
        "files": [
            {
                "path": "app.py",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_34_payment_tick/app.py",
                "sha256": sha256(app_path),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_34_payment_tick/update_manifest.json",
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
    print("V4434_BUILT", sha256(app_path))


if __name__ == "__main__":
    main()
