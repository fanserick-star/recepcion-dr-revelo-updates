"""AZUR v2 consultation credentials: local, read-only connection and fiscal lookup.

No fiscal POST to AZUR; does not issue, regenerate, modify or print invoices.
Credentials stay in Recepcion's local .env, not in Neon or application source.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import date as _date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

import reception_payment_terminal_panel as _deps
from azur_client import normalize_base_url, AzurError

core = _deps.core
app = _deps.app

_READ_KEY = (os.getenv("AZUR_READ_API_KEY") or "").strip()
_KEY_PATTERN = re.compile(r"^(?:sk|azur)_(?:live|test)_[A-Za-z0-9._~-]{8,240}$")
_MAX_RESPONSE = 2 * 1024 * 1024


class _NeverRedirect(HTTPRedirectHandler):
    """Prevent AZUR API credentials from being forwarded to redirected hosts."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReadKeyIn(core.BaseModel):
    api_key: str


class InvoiceLookupIn(core.BaseModel):
    patient_id: int
    fecha: _date
    numero_factura: str


def _role_admin(user) -> None:
    if getattr(user, "role", None) != "admin":
        raise core.HTTPException(403, "Solo el administrador puede configurar la consulta AZUR")


def _env_name(token: str) -> str:
    return "PRODUCCIÓN" if token.startswith(("sk_live_", "azur_live_")) else "PRUEBAS"


def _config() -> dict:
    hostname = ""
    try:
        hostname = urlparse(normalize_base_url(core.AZUR_BASE_URL)).hostname or ""
    except Exception:
        pass
    return {
        "configured": bool(_READ_KEY),
        "read_only": True,
        "environment": _env_name(_READ_KEY) if _READ_KEY else None,
        "tenant": hostname,
        "emission_key_unchanged": True,
    }


def _remote_get(resource: str, query: str = "") -> dict:
    """Fixed read-only GET against the preconfigured AZUR host; never forwards secrets."""
    if not _READ_KEY:
        raise core.HTTPException(409, "Configura primero la credencial de consulta AZUR")
    try:
        base = normalize_base_url(core.AZUR_BASE_URL)
    except AzurError as exc:
        raise core.HTTPException(409, str(exc))
    if not base:
        raise core.HTTPException(409, "Configura la dirección de AZUR antes de consultar")
    # Caller supplies only a fixed resource. No user URLs or redirects accepted.
    if resource not in {"facturas"} and not re.fullmatch(r"factura/[1-9][0-9]{0,12}", resource):
        raise core.HTTPException(400, "Recurso de consulta no permitido")
    url = base + "/plataforma/api/v2/" + resource + (("?" + query) if query else "")
    code = 0
    body: bytes = b""
    # Curl.exe/Schannel works on the legacy Windows PC. Put the key on STDIN,
    # never in command-line flags, temporary files, URLs or exception messages.
    curl = (shutil.which("curl.exe") or shutil.which("curl")) if os.name == "nt" else None
    if curl:
        cmd = [
            curl, "--silent", "--show-error", "--proto", "=https",
            "--max-redirs", "0", "--connect-timeout", "6", "--max-time", "16",
            "--request", "GET", "--header", "Accept: application/json",
            "--config", "-", "--write-out", "\n__AZUR_STATUS__:%{http_code}", url,
        ]
        try:
            run = subprocess.run(
                cmd, input='header = "X-Api-Key: ' + _READ_KEY + '"\n',
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=21, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise core.HTTPException(504, "AZUR tardó demasiado en responder; intenta otra vez")
        raw = run.stdout or ""
        if "__AZUR_STATUS__:" not in raw:
            raise core.HTTPException(502, "No se pudo consultar AZUR desde Windows. Revisa Internet")
        text, tail = raw.rsplit("\n__AZUR_STATUS__:", 1)
        code = int(tail.strip() or "0")
        body = text.encode("utf-8")
    else:
        req = Request(url, headers={"X-Api-Key": _READ_KEY, "Accept": "application/json"},
                      method="GET")
        try:
            with build_opener(_NeverRedirect()).open(req, timeout=16) as result:
                code = int(result.status)
                body = result.read(_MAX_RESPONSE + 1)
        except HTTPError as exc:
            code = int(exc.code)
        except (URLError, TimeoutError, OSError):
            raise core.HTTPException(502, "No se pudo conectar con la consulta AZUR")
    if code in (401, 403):
        raise core.HTTPException(403, "AZUR rechazó la credencial o el permiso Consultar comprobantes")
    if code == 429:
        raise core.HTTPException(429, "AZUR alcanzó el límite de consultas. Intenta más tarde")
    if code == 404:
        raise core.HTTPException(404, "AZUR no encontró el comprobante solicitado")
    if not (200 <= code < 300):
        raise core.HTTPException(502, f"AZUR no pudo completar la consulta (HTTP {code})")
    if len(body) > _MAX_RESPONSE:
        raise core.HTTPException(502, "La respuesta de AZUR excedió el tamaño permitido")
    try:
        result = json.loads(body.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise core.HTTPException(502, "AZUR respondió sin el JSON esperado")
    if not isinstance(result, dict) or result.get("ok") is not True:
        # No echoing arbitrary remote response, which can contain PII.
        raise core.HTTPException(502, "AZUR respondió, pero no confirmó la consulta")
    return result


@app.get("/api/azur/readonly/status")
def azur_read_status(user=core.Depends(core.current_user)):
    return _config()


@app.post("/api/azur/readonly/config")
def azur_read_save(data: ReadKeyIn, user=core.Depends(core.current_user)):
    global _READ_KEY
    _role_admin(user)
    key = (data.api_key or "").strip()
    if not _KEY_PATTERN.fullmatch(key):
        raise core.HTTPException(400, "La credencial v2 no tiene un formato válido (sk_live_… o sk_test_…)")
    # Never overwrite the distinct emission key, connection string or billing records.
    core._upsert_local_env({"AZUR_READ_API_KEY": key})
    _READ_KEY = key
    return {"ok": True, **_config(), "message": "Credencial de solo consulta guardada en esta PC"}


@app.post("/api/azur/readonly/test")
def azur_read_test(user=core.Depends(core.current_user)):
    _role_admin(user)
    response = _remote_get("facturas", "limite=1")
    data = response.get("datos")
    if not isinstance(data, (dict, list)):
        raise core.HTTPException(502, "AZUR no devolvió la estructura de facturas esperada")
    return {
        "ok": True,
        "read_only": True,
        "environment": _env_name(_READ_KEY),
        "message": "Consulta v2 autenticada. No se emitió, anuló ni imprimió ninguna factura.",
    }


def _invoice_norm(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 15 else ""


def _remote_rows(data: Any) -> list:
    if isinstance(data, list):
        return data[:25]
    if not isinstance(data, dict):
        return []
    for name in ("facturas", "comprobantes", "items", "registros"):
        value = data.get(name)
        if isinstance(value, list):
            return value[:25]
    return []


def _field(obj: Any, *keys: str) -> str:
    if not isinstance(obj, dict):
        return ""
    for key in keys:
        val = obj.get(key)
        if isinstance(val, (str, int)) and str(val).strip():
            return str(val).strip()
    return ""


@app.post("/api/azur/readonly/verify-invoice")
def azur_read_verify_invoice(data: InvoiceLookupIn, db=core.Depends(core.get_db),
                             user=core.Depends(core.current_user)):
    """One invoice, no SRI writes and no printing. Require exact local + remote match."""
    _role_admin(user)
    numero = _invoice_norm(data.numero_factura)
    if not numero:
        raise core.HTTPException(400, "Número de factura no válido")
    if core.is_offline_db(db):
        raise core.HTTPException(503, "La consulta de impresión requiere la copia en línea")
    records = list(db.scalars(
        core.select(core.AzurEmission)
        .where(core.AzurEmission.patient_id == int(data.patient_id),
               core.AzurEmission.fecha == data.fecha,
               core.AzurEmission.estado == "AUTORIZADA")
    ))
    matched = [
        r for r in records if _invoice_norm(r.numero_factura) == numero
        and re.fullmatch(r"[0-9]{49}", str(r.clave_acceso or ""))
    ]
    if len(matched) != 1:
        raise core.HTTPException(409, "No se encontró una autorización AZUR inequívoca en Recepción")
    expected_key = str(matched[0].clave_acceso)
    remote = _remote_get("facturas", "buscar=" + quote(str(data.numero_factura), safe="") + "&limite=25")
    items = _remote_rows(remote.get("datos"))
    candidates = [v for v in items if _invoice_norm(_field(v, "numero", "numero_factura", "numero_comprobante")) == numero]
    if len(candidates) != 1:
        raise core.HTTPException(409, "AZUR no devolvió una coincidencia única para esta factura")
    v = candidates[0]
    remote_id = _field(v, "id")
    if not remote_id.isdigit() or int(remote_id) < 1:
        raise core.HTTPException(502, "La búsqueda de AZUR no devolvió un ID de factura válido")
    detail = _remote_get("factura/" + str(int(remote_id))).get("datos")
    if not isinstance(detail, dict):
        raise core.HTTPException(502, "El detalle de la factura en AZUR no está disponible")
    remote_key = _field(detail, "claveacceso", "clave_acceso", "claveAcceso")
    remote_num = _field(detail, "numero", "numero_factura", "numero_comprobante")
    if remote_key != expected_key or _invoice_norm(remote_num) != numero:
        raise core.HTTPException(409, "La factura remota no coincide con la autorización guardada; no se imprimirá")
    return {
        "ok": True,
        "verified": True,
        "numero_factura": str(data.numero_factura),
        "azur_id": int(remote_id),
        "environment": _env_name(_READ_KEY),
        "message": "Factura localizada en AZUR y clave de acceso comprobada. Pendiente validar el XML y la impresión térmica.",
        "printed": False,
    }


@app.get("/api/azur/readonly/health")
def azur_read_health(user=core.Depends(core.current_user)):
    return {"ok": True, "read_only": True, "no_fiscal_writes": True, "direct_print": False}
