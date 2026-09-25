from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "updates" / "v4_6_0_stabilization"
SOURCE_MAP = CANDIDATE / "runtime_sources.json"
RUNTIME_ZIP = CANDIDATE / "recepcion_legacy_runtime.zip"
RUNTIME_MANIFEST = CANDIDATE / "runtime_manifest.json"

OUTSIDE_RUNTIME = {"historia_bridge.py", "historia_lan_transport.py"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(f"blob {len(data)}\0".encode("ascii"))
    h.update(data)
    return h.hexdigest()


def verify_source(path: Path, expected_blob: str) -> bytes:
    data = path.read_bytes()
    got = git_blob_sha(data)
    if got != expected_blob:
        raise RuntimeError(
            f"Fuente alterada: {path.relative_to(ROOT)}; blob {got}, esperado {expected_blob}"
        )
    return data


def compile_python(name: str, data: bytes) -> None:
    compile(data.decode("utf-8"), name, "exec")


def patch_base_dir(data: bytes) -> bytes:
    text = data.decode("utf-8")
    old = 'BASE_DIR = os.path.dirname(os.path.abspath(__file__))'
    new = (
        'BASE_DIR = (os.getenv("RP_APP_ROOT") or '
        'os.path.dirname(os.path.abspath(__file__))).strip()'
    )
    if text.count(old) != 1:
        raise RuntimeError("No se encontró una única asignación BASE_DIR en app_base_4428.py")
    return text.replace(old, new, 1).encode("utf-8")


def patch_azur_client(data: bytes) -> bytes:
    """Agrega la consulta de autorización usada por Recepción 4.3.54+.

    Conserva intactos normalize/test/emit del cliente RC3; únicamente completa
    query_comprobante, cuya ruta está documentada por AZUR como
    /plataforma/api/v2/consulta/comprobante.
    """
    text = data.decode("utf-8")
    if "def query_comprobante(" in text:
        return data

    extension = r'''

def _query_walk_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _query_walk_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _query_walk_values(item)


def _query_first(data, keys):
    wanted = {re.sub(r"[^a-z0-9]", "", str(k).lower()) for k in keys}
    for key, value in _query_walk_values(data):
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized in wanted and value not in (None, "", [], {}):
            return value
    return None


def _query_state(data, fallback_text=""):
    raw = _query_first(
        data,
        (
            "estado", "estado_sri", "estado_autorizacion",
            "estadoautorizacion", "estado_comprobante",
            "status", "autorizacion_estado",
        ),
    )
    origin = str(raw or "").strip()
    flat = (" ".join([
        _flatten_text(data, fallback_text),
        origin,
    ])).upper()

    # Evaluar rechazo antes de autorización porque "NO AUTORIZADO"
    # contiene la palabra AUTORIZADO.
    rejected_tokens = (
        "NO AUTORIZADO", "NO AUTORIZADA", "RECHAZADO", "RECHAZADA",
        "DEVUELTO", "DEVUELTA", "ANULADO", "ANULADA",
    )
    if any(token in flat for token in rejected_tokens):
        return "RECHAZADA", origin or None

    authorized_tokens = ("AUTORIZADO", "AUTORIZADA")
    if any(token in flat for token in authorized_tokens):
        return "AUTORIZADA", origin or None

    processing_tokens = (
        "RECIBIDA", "RECIBIDO", "PROCESANDO", "EN PROCESO",
        "PENDIENTE", "GENERADO", "GENERADA", "FIRMADO", "FIRMADA",
    )
    if any(token in flat for token in processing_tokens):
        return "EN_PROCESO", origin or None

    return "CONSULTADA", origin or None


def query_comprobante(base_url: str, api_key: str, clave_acceso: str, timeout: int = 15) -> dict[str, Any]:
    base = normalize_base_url(base_url)
    key = (api_key or "").strip()
    access_key = re.sub(r"\D", "", str(clave_acceso or ""))
    if not key:
        raise AzurError("La API key de AZUR no está configurada")
    if len(access_key) != 49:
        raise AzurError("La clave de acceso de AZUR debe tener 49 dígitos")

    payload = {
        "api_key": key,
        "claveacceso": access_key,
        "clave_acceso": access_key,
    }
    attempts = []
    for url in _endpoint_candidates(base, "consulta/comprobante"):
        try:
            response = _post_json(url, payload, timeout=timeout, api_key=key)
        except AzurError as exc:
            attempts.append(f"{url}: {exc}")
            continue

        if _looks_like_route_missing(response):
            attempts.append(f"{url}: ruta no disponible ({response.status})")
            continue

        flat = _flatten_text(response.data, response.text)
        if response.status in {401, 403} or _auth_rejected(flat):
            raise AzurError("AZUR rechazó la API key")
        if response.status >= 500:
            attempts.append(f"{url}: HTTP {response.status}")
            continue
        if response.status >= 400:
            raise AzurError(
                f"AZUR no pudo consultar el comprobante (HTTP {response.status}): "
                f"{flat[:350]}"
            )

        data = response.data
        if data is None:
            raise AzurError("AZUR respondió sin JSON al consultar el comprobante")

        state, origin = _query_state(data, response.text)
        number = _query_first(
            data,
            ("numero_factura", "numero_comprobante", "numero", "secuencial"),
        )
        authorization = _query_first(
            data,
            ("numero_autorizacion", "numeroautorizacion", "autorizacion"),
        )
        pdf_url = _query_first(
            data,
            ("pdf_url", "url_pdf", "pdf", "ride_url", "url_ride"),
        )
        xml_url = _query_first(
            data,
            ("xml_url", "url_xml", "xml"),
        )
        return {
            "ok": True,
            "estado": state,
            "estado_origen": origin,
            "clave_acceso": access_key,
            "numero_factura": str(number).strip() if number not in (None, "") else None,
            "numero_autorizacion": str(authorization).strip() if authorization not in (None, "") else None,
            "pdf_url": str(pdf_url).strip() if pdf_url not in (None, "") else None,
            "xml_url": str(xml_url).strip() if xml_url not in (None, "") else None,
            "endpoint": response.url,
            "data": data,
        }

    detail = "; ".join(attempts[-3:]) if attempts else "sin respuesta"
    raise AzurError(f"No se pudo consultar el comprobante en AZUR: {detail}")
'''
    return (text.rstrip() + "\n" + extension.strip() + "\n").encode("utf-8")


def build() -> dict:
    cfg = json.loads(SOURCE_MAP.read_text(encoding="utf-8"))
    if cfg.get("candidate_version") != "4.6.0":
        raise RuntimeError("runtime_sources.json no corresponde a 4.6.0")

    runtime: dict[str, bytes] = {}
    outside: dict[str, bytes] = {}

    for name, meta in cfg["modules"].items():
        path = ROOT / meta["path"]
        data = verify_source(path, meta["blob_sha"])
        if name == "app_base_4428.py":
            data = patch_base_dir(data)
        compile_python(name, data)
        if name in OUTSIDE_RUNTIME:
            outside[name] = data
        else:
            runtime[name] = data

    for name, meta in cfg.get("extracted_modules", {}).items():
        if meta.get("archive_b64"):
            archive_bytes = base64.b64decode(
                (ROOT / meta["archive_b64"]).read_text(encoding="ascii")
            )
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                data = zf.read(meta["member"])
        else:
            archive = ROOT / meta["archive"]
            with zipfile.ZipFile(archive) as zf:
                data = zf.read(meta["member"])
        if name == "azur_client.py":
            data = patch_azur_client(data)
        compile_python(name, data)
        runtime[name] = data

    for name, rel in cfg.get("generated_modules", {}).items():
        data = (ROOT / rel).read_bytes()
        compile_python(name, data)
        runtime[name] = data

    # Dos módulos necesitan una ruta física real porque mantienen outboxes/LAN.
    for name, data in outside.items():
        (CANDIDATE / name).write_bytes(data)

    # ZIP determinista: orden fijo y timestamp fijo para que el SHA sea reproducible.
    with zipfile.ZipFile(RUNTIME_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(runtime):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, runtime[name])

    members = {
        name: {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        for name, data in sorted(runtime.items())
    }
    runtime_manifest = {
        "schema": 1,
        "version": "4.6.0",
        "base": "4.5.44",
        "member_count": len(members),
        "members": members,
        "runtime_zip_sha256": sha256(RUNTIME_ZIP),
        "runtime_zip_size": RUNTIME_ZIP.stat().st_size,
    }
    RUNTIME_MANIFEST.write_text(
        json.dumps(runtime_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Recursos físicos de la instalación limpia: CSS, logos, iconos y móvil.
    resource_meta = cfg.get("resource_archive") or {}
    if resource_meta.get("archive_b64"):
        resource_bytes = base64.b64decode(
            (ROOT / resource_meta["archive_b64"]).read_text(encoding="ascii")
        )
        with zipfile.ZipFile(io.BytesIO(resource_bytes)) as zf:
            for member in resource_meta.get("include", []):
                dest = CANDIDATE / member
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))

    # Frontend estable más nuevo: sobrescribe app.js/index.html de la base limpia.
    for target, source in cfg.get("static_files", {}).items():
        dest = CANDIDATE / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, dest)

    required = [
        "app.py",
        "recepcion_legacy_runtime.zip",
        "historia_bridge.py",
        "historia_lan_transport.py",
        "static/app.js",
        "static/index.html",
        "static/style.css",
        "static/doctor_full_logo.png",
        "static/doctor_isotype.png",
        "static/doctor_icon.ico",
        "static/azur_mark.svg",
        "static/whatsapp_mark.svg",
        "mobile/index.html",
        "mobile/app.js",
        "mobile/sw.js",
        "recepcion-version.json",
        "update_manifest.json",
        "requirements.txt",
        "runtime_manifest.json",
    ]
    manifest = {
        "product": "recepcion-pacientes",
        "version": "4.6.0",
        "app_version": "4.6.0",
        "runtime_version": "4.6.0",
        "mandatory": True,
        "version_source": "recepcion-version.json",
        "launcher_minimum": "1.0.13",
        "updater_version": "launcher-v1-atomic-runtime",
        "required_dependencies": required,
        "required_python_packages": [
            {"import": "fastapi", "pip": "fastapi==0.115.6"},
            {"import": "pydantic", "pip": "pydantic==1.10.24"},
            {"import": "uvicorn", "pip": "uvicorn==0.34.0"},
            {"import": "sqlalchemy", "pip": "SQLAlchemy==2.0.36"},
            {"import": "pg8000", "pip": "pg8000==1.31.2"},
            {"import": "dotenv", "pip": "python-dotenv==1.0.1"},
            {"import": "multipart", "pip": "python-multipart==0.0.20"},
        ],
        "copy": required,
        "notes": {
            "candidate_only": True,
            "base_stable_version": "4.5.44",
            "protected_data": True,
            "protected_env": True,
            "preserves_data_env_excel": True,
            "automatic_updates_only": True,
            "transactional_updater": True,
            "sha256_required": True,
            "isolated_preflight": True,
            "rollback": True,
            "atomic_legacy_runtime_zip": True,
            "scattered_patch_files_required": False,
            "duplicate_routes_canonicalized": True,
            "legacy_health_handlers_consolidated": True,
            "legacy_cloudflare_tunnel_removed": True,
            "legacy_zip_updater_retired": True,
            "experimental_dataphone_api_default_off": True,
            "bendo_manual_flow_preserved": True,
            "whatsapp_cloud_mode_preserved": True,
            "patient_duplicate_guard_normalized": True,
            "read_only_data_audit": True,
            "database_schema_changes": False,
            "patient_data_destructive_changes": False,
            "historia_changes": False,
            "facturacion_logic_rewritten": False,
            "print_logic_rewritten": False,
            "purpose": (
                "Estabilización estructural: runtime histórico atómico, rutas únicas, "
                "superficies obsoletas retiradas y diagnóstico/auditoría unificados."
            ),
        },
        "channel": "launcher-v1-candidate",
    }
    (CANDIDATE / "update_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validación de sintaxis del entrypoint, sin importarlo todavía.
    compile_python("app.py", (CANDIDATE / "app.py").read_bytes())

    return {
        "runtime_zip": str(RUNTIME_ZIP.relative_to(ROOT)),
        "runtime_sha256": runtime_manifest["runtime_zip_sha256"],
        "runtime_members": len(members),
        "required_files": required,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(build(), indent=2, ensure_ascii=False))
