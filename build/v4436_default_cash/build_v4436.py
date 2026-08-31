from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_35_payment_per_card" / "app.py"
OUT = ROOT / "updates" / "v4_4_36_default_cash"
VERSION = "4.4.36"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def main() -> None:
    src = SOURCE.read_text(encoding="utf-8")
    if 'APP_VERSION = "4.4.35"' not in src:
        raise SystemExit("La fuente ya no es v4.4.35")

    text = replace_once(src, 'APP_VERSION = "4.4.35"', f'APP_VERSION = "{VERSION}"', "APP_VERSION")
    version_marker = "const VERSION='4.4.35';"
    version_count = text.count(version_marker)
    if version_count != 2:
        raise SystemExit(f"versión overlay: esperaba 2 coincidencias y encontró {version_count}")
    text = text.replace(version_marker, f"const VERSION='{VERSION}';")

    # Las fichas POR EMITIR pueden guardar la forma de pago aunque el estado interno
    # de BillingRecord no sea literalmente APROBADA. Solo una factura ya EMITIDA
    # queda bloqueada para evitar modificar un comprobante autorizado.
    text = replace_once(
        text,
        '.where(core.BillingRecord.estado == "APROBADA")',
        '.where(core.BillingRecord.estado != "EMITIDA")',
        "consulta de formas de pago",
    )

    text = replace_once(
        text,
        '''        if states != {"APROBADA"}:
            raise core.HTTPException(
                409,
                "Primero aprueba la ficha y luego selecciona la forma de pago.",
            )

''',
        '''        # v4.4.36: la forma de pago se puede escoger directamente en cualquier
        # ficha POR EMITIR. No se exige el estado interno APROBADA; la única
        # restricción es no modificar una factura que ya fue EMITIDA.

''',
        "bloqueo incorrecto por APROBADA",
    )

    # Efectivo es el comportamiento por defecto real, también del lado servidor.
    # Así no se hace una escritura a Neon por cada ficha solo por abrir Facturación.
    text = replace_once(
        text,
        '''    def _azur_payload_for_group_v4431(data, patient, rows):
        methods = []
        missing = False
        for _billing, visit in rows:
            method = _payment_from_visit(visit)
            if method is None:
                missing = True
            else:
                methods.append(method)

        if missing:
            raise core.HTTPException(
                400,
                "Antes de emitir, marca Efectivo o Transferencia en la ficha.",
            )

        payload = _stable_azur_payload_for_group(data, patient, rows)
''',
        '''    def _azur_payload_for_group_v4431(data, patient, rows):
        # Si el usuario no cambia nada, la factura sale como EFECTIVO (SRI 01).
        # Transferencia solo se guarda cuando se cambia manualmente en la ficha.
        payload = _stable_azur_payload_for_group(data, patient, rows)
''',
        "efectivo por defecto en payload AZUR",
    )

    text = replace_once(
        text,
        '''            method = _payment_from_visit(visit)
            code = SRI_PAYMENT_CODES[method]
''',
        '''            method = _payment_from_visit(visit) or "EFECTIVO"
            code = SRI_PAYMENT_CODES[method]
''',
        "fallback SRI efectivo",
    )

    text = replace_once(
        text,
        "    const selected=paymentMap.get(key(id.patient_id,id.fecha))||'';",
        "    const selected=paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO';",
        "visto efectivo por defecto",
    )

    text = replace_once(
        text,
        "    return !paymentMap.get(key(id.patient_id,id.fecha));",
        "    return !(paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO');",
        "prevalidación de lote con efectivo por defecto",
    )

    # El botón Revisar y emitir ya debe estar disponible porque siempre existe una
    # forma efectiva: EFECTIVO por defecto o TRANSFERENCIA elegida por el usuario.
    text = replace_once(
        text,
        '''    const locked=!selected;
    emit.disabled=locked;
''',
        '''    const locked=false;
    emit.disabled=false;
''',
        "habilitación de Revisar y emitir",
    )

    required = [
        'APP_VERSION = "4.4.36"',
        "const VERSION='4.4.36';",
        "import app_base_4428 as core",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        '/api/billing/payment-method',
        '.where(core.BillingRecord.estado != "EMITIDA")',
        'method = _payment_from_visit(visit) or "EFECTIVO"',
        "const selected=paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO';",
        "return !(paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO');",
        "const locked=false;",
        "window.__v4435BillingPayment=true",
        "parseIdentityFromActions",
        "identityFromCache",
        "foot.insertBefore(wrap,actions)",
        "📦 Emitir por lotes",
        "batchPreflight",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
        "core.V459_SETTINGS_JS = _v459_base",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"Se perdió funcionalidad requerida: {marker}")

    forbidden = [
        "Primero aprueba la ficha y luego selecciona la forma de pago.",
        '.where(core.BillingRecord.estado == "APROBADA")',
        "document.querySelectorAll('.billing-card.aprobada')",
        "new MutationObserver(()=>",
    ]
    for marker in forbidden:
        if marker in text:
            raise SystemExit(f"Regresión detectada: {marker}")

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
        "notes": "Efectivo queda seleccionado por defecto en cada ficha POR EMITIR (SRI 01). Transferencia se cambia manualmente sin exigir estado APROBADA. No toca launcher, static, .env ni datos.",
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
        "message": "v4.4.36: Efectivo queda marcado por defecto en cada ficha POR EMITIR; Transferencia se cambia manualmente sin alertas de aprobación. La factura usa SRI 01 por defecto y SRI 20 si se cambia a transferencia. No toca launcher, datos, .env ni static.",
        "files": [
            {
                "path": "app.py",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_36_default_cash/app.py",
                "sha256": sha256(app_path),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_36_default_cash/update_manifest.json",
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
    print("V4436_BUILT", sha256(app_path))


if __name__ == "__main__":
    main()
