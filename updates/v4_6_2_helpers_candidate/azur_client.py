from __future__ import annotations

import json
import re
import socket
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class AzurError(RuntimeError):
    pass


@dataclass
class AzurResponse:
    status: int
    data: Any
    text: str
    url: str


def normalize_base_url(value: str) -> str:
    """Return only the HTTPS origin for an AZUR tenant URL.

    The local app deliberately refuses non-AZUR hosts so a configuration field
    cannot be abused as a generic server-side HTTP proxy.
    """
    raw = (value or "").strip()
    if not raw:
        raise AzurError("Ingresa la dirección web de tu cuenta AZUR")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise AzurError("La dirección de AZUR debe usar https://")
    host = (parsed.hostname or "").lower().strip(".")
    if not host or not (host == "azur.com.ec" or host.endswith(".azur.com.ec")):
        raise AzurError("La dirección debe pertenecer a azur.com.ec")
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"https://{host}{port}"


def mask_api_key(value: str) -> str:
    key = (value or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return key[:3] + "••••••••" + key[-3:]


def _safe_text(value: str, key: str) -> str:
    text = value or ""
    if key:
        text = text.replace(key, "[API_KEY_OCULTA]")
    return text[:4000]


def _post_json(url: str, payload: dict[str, Any], timeout: int = 12, api_key: str = "") -> AzurResponse:
    """POST JSON usando el transporte nativo de Windows cuando está disponible.

    En la PC antigua del consultorio, curl.exe/Schannel ya fue validado contra
    AZUR y evita diferencias de TLS/certificados del runtime Python. La consola
    se mantiene completamente oculta. En otros sistemas se conserva urllib.
    """
    if os.name == "nt":
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if curl:
            fd, temp_path = tempfile.mkstemp(prefix="azur_", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False)
                marker = "\n__HTTP__:%{http_code}"
                cmd = [
                    curl, "--silent", "--show-error", "--location",
                    "--connect-timeout", "8", "--max-time", str(max(10, timeout)),
                    "--request", "POST", "--header", "Content-Type: application/json",
                    "--header", "Accept: application/json",
                ]
                if api_key:
                    cmd += ["--header", f"api-key: {api_key}"]
                cmd += ["--data-binary", "@" + temp_path, "--write-out", marker, url]
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=max(14, timeout + 4), check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except subprocess.TimeoutExpired as exc:
                    raise AzurError("No se pudo conectar con AZUR: tiempo de espera agotado") from exc
                out = proc.stdout or ""; err = (proc.stderr or "").strip(); tag = "__HTTP__:"
                if tag not in out:
                    raise AzurError("No se pudo conectar con AZUR: " + (err or f"curl terminó con código {proc.returncode}")[:600])
                raw, code = out.rsplit(tag, 1)
                status = int(code.strip() or 0)
                safe = _safe_text(raw, api_key)
                try: data = json.loads(safe) if safe.strip() else {}
                except Exception: data = None
                return AzurResponse(status=status, data=data, text=safe, url=url)
            finally:
                try: os.unlink(temp_path)
                except Exception: pass

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", **({"api-key": api_key} if api_key else {})},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        status = int(exc.code or 500); raw = exc.read().decode("utf-8", errors="replace")
    except (URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc); raise AzurError(f"No se pudo conectar con AZUR: {reason}") from exc
    except Exception as exc:
        raise AzurError(f"No se pudo conectar con AZUR: {exc}") from exc
    safe = _safe_text(raw, api_key)
    try: data = json.loads(safe) if safe.strip() else {}
    except Exception: data = None
    return AzurResponse(status=status, data=data, text=safe, url=url)


def _flatten_text(data: Any, fallback: str = "") -> str:
    if isinstance(data, dict):
        chunks: list[str] = []
        for k, v in data.items():
            chunks.append(str(k))
            chunks.append(_flatten_text(v))
        return " ".join(chunks)
    if isinstance(data, (list, tuple)):
        return " ".join(_flatten_text(x) for x in data)
    if data is None:
        return fallback or ""
    return str(data)


def _auth_rejected(text: str) -> bool:
    s = re.sub(r"\s+", " ", (text or "").lower())
    mentions_auth = any(x in s for x in ("api_key", "api key", "apikey", "credencial", "token", "autentic"))
    rejected = any(x in s for x in ("inválid", "invalido", "inválido", "incorrect", "no válido", "no valido", "deneg", "unauthorized", "forbidden", "no autorizado", "no existe", "does not exist", "inexistente"))
    return mentions_auth and rejected


def _validation_after_auth(text: str) -> bool:
    s = re.sub(r"\s+", " ", (text or "").lower())
    # These errors mean the request advanced far enough to validate invoice fields.
    field_words = ("items", "comprador", "emisor", "obligatorio", "required", "campo")
    return any(x in s for x in field_words) and not _auth_rejected(s)


def _candidate_origins(base: str) -> list[str]:
    """Origins to try for AZUR API v2.

    AZUR currently publishes examples using both the tenant/main domain and its
    API documentation host. Some accounts are served directly from azur.com.ec
    while others use a tenant subdomain. We only try official AZUR HTTPS hosts.
    """
    parsed = urlparse(base)
    host = (parsed.hostname or "").lower()
    origins = [base.rstrip("/")]
    if host == "azur.com.ec":
        origins.append("https://api.azur.com.ec")
        origins.append("https://central.azur.com.ec")
    # Preserve order and remove duplicates.
    return list(dict.fromkeys(origins))


def _endpoint_candidates(base: str, resource: str) -> list[str]:
    urls: list[str] = []
    for origin in _candidate_origins(base):
        urls.append(origin + "/plataforma/api/v2/" + resource.lstrip("/"))
        urls.append(origin + "/api/v2/" + resource.lstrip("/"))
    return list(dict.fromkeys(urls))


def _looks_like_route_missing(response: AzurResponse) -> bool:
    if response.status not in {404, 405}:
        return False
    text = (response.text or "").lower()
    if isinstance(response.data, dict):
        flat = _flatten_text(response.data, response.text).lower()
        # A JSON API can legitimately use 404 for "comprobante no encontrado".
        if any(x in flat for x in ("comprobante", "clave", "api_key", "api key", "no encontrado")):
            return False
    return ("<html" in text or "<!doctype" in text or response.data is None or not text.strip())


def test_connection(base_url: str, api_key: str, timeout: int = 12) -> dict[str, Any]:
    """Safely locate the AZUR v2 API and verify that the configured key is not rejected.

    The test NEVER sends a valid invoice. It first tries the documented
    read-only comprobante query using an impossible access key. If that route is
    unavailable, it sends a deliberately incomplete/invalid invoice payload
    (no buyer and no items) to the emission route. That payload cannot produce
    an SRI document, but it lets AZUR validate routing/authentication.

    For compatibility with AZUR's current public pages, the key is sent both in
    the JSON body and the documented ``api-key`` header.
    """
    base = normalize_base_url(base_url)
    key = (api_key or "").strip()
    if not key:
        raise AzurError("La API key de AZUR no está configurada")

    attempts: list[dict[str, Any]] = []

    # 1) Read-only query: impossible 49-digit access key, so no real document is touched.
    fake_access_key = "0" * 49
    query_payload = {
        "api_key": key,
        "claveacceso": fake_access_key,
        "clave_acceso": fake_access_key,
    }
    for url in _endpoint_candidates(base, "consulta/comprobante"):
        try:
            response = _post_json(url, query_payload, timeout=timeout, api_key=key)
        except AzurError as exc:
            attempts.append({"url": url, "error": str(exc)})
            continue
        text = _flatten_text(response.data, response.text)
        attempts.append({"url": url, "status": response.status})
        if _looks_like_route_missing(response):
            continue
        if _auth_rejected(text) or response.status in {401, 403}:
            return {
                "ok": False,
                "reachable": True,
                "api_key_valid": False,
                "endpoint": url,
                "status": response.status,
                "message": "AZUR respondió, pero rechazó la API key.",
            }
        # Any structured API response to the impossible key means we reached the
        # correct endpoint. A not-found document is expected and is read-only.
        if isinstance(response.data, (dict, list)) or response.status < 500:
            return {
                "ok": True,
                "reachable": True,
                "api_key_valid": True,
                "endpoint": url,
                "status": response.status,
                "message": "Conexión con AZUR confirmada. La prueba consultó una clave inexistente y no emitió ningún comprobante.",
            }

    # 2) Safe fallback: deliberately invalid invoice. It has no buyer, no items,
    # and an invalid document code, therefore it cannot be emitted or authorized.
    validation_payload = {
        "api_key": key,
        "codigoDoc": "00",
        "emisor": {"manejo_interno_secuencia": "NO"},
        "comprador": {},
        "items": [],
    }
    for url in _endpoint_candidates(base, "factura/emision"):
        try:
            response = _post_json(url, validation_payload, timeout=timeout, api_key=key)
        except AzurError as exc:
            attempts.append({"url": url, "error": str(exc)})
            continue
        text = _flatten_text(response.data, response.text)
        attempts.append({"url": url, "status": response.status})
        if _looks_like_route_missing(response):
            continue
        if _auth_rejected(text) or response.status in {401, 403}:
            return {
                "ok": False,
                "reachable": True,
                "api_key_valid": False,
                "endpoint": url,
                "status": response.status,
                "message": "AZUR respondió, pero rechazó la API key.",
            }
        if isinstance(response.data, dict) and response.data.get("creado") is True:
            # Defensive guard. This should be impossible with codigoDoc=00 and no items.
            raise AzurError("AZUR respondió de una forma inesperada; se detuvo la prueba por seguridad")

        # A JSON validation/business error proves the route exists. If AZUR did
        # not reject authentication, report the connection as established.
        if isinstance(response.data, (dict, list)) or _validation_after_auth(text) or response.status in {400, 409, 422}:
            return {
                "ok": True,
                "reachable": True,
                "api_key_valid": True,
                "endpoint": url,
                "status": response.status,
                "message": "Conexión y API key aceptadas por AZUR. La prueba usó datos inválidos a propósito y no emitió ninguna factura.",
            }
        if response.status < 500:
            return {
                "ok": True,
                "reachable": True,
                "api_key_valid": None,
                "endpoint": url,
                "status": response.status,
                "message": "Se encontró la API de AZUR y respondió. No se emitió ningún comprobante.",
            }

    # Keep the diagnostic compact and never include the API key or response bodies.
    statuses = ", ".join(
        f"{a.get('status', 'sin respuesta')}" for a in attempts[-6:]
    )
    detail = f" (respuestas: {statuses})" if statuses else ""
    raise AzurError("No se pudo localizar la API v2 de AZUR en los endpoints oficiales" + detail)


def emit_invoice(base_url: str, api_key: str, invoice_payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    """Emit one invoice. This function is intentionally only called by the local
    backend after an explicit user confirmation in the UI.
    """
    base = normalize_base_url(base_url)
    key = (api_key or "").strip()
    if not key:
        raise AzurError("La API key de AZUR no está configurada")
    payload = dict(invoice_payload)
    payload["api_key"] = key

    last: AzurResponse | None = None
    for url in _endpoint_candidates(base, "factura/emision"):
        response = _post_json(url, payload, timeout=timeout, api_key=key)
        last = response
        if _looks_like_route_missing(response):
            continue
        data = response.data if isinstance(response.data, dict) else {}
        text = _flatten_text(data, response.text)
        if _auth_rejected(text) or response.status in {401, 403}:
            raise AzurError("AZUR rechazó la API key")
        if response.status >= 400 or data.get("creado") is False:
            errors = data.get("errors") or data.get("error") or data.get("message") or response.text
            if isinstance(errors, list):
                errors = "; ".join(str(x) for x in errors)
            raise AzurError(f"AZUR no pudo emitir la factura: {errors}")
        return {
            "ok": True,
            "endpoint": url,
            "status": response.status,
            "data": data,
        }
    if last:
        raise AzurError(f"AZUR respondió con HTTP {last.status}, pero no se pudo usar el endpoint de emisión")
    raise AzurError("No se pudo conectar con AZUR")


def _first_text_value(data: Any, keys: tuple[str, ...]) -> str:
    """Busca una clave textual en JSON anidado sin asumir una forma fija."""
    wanted = {k.lower() for k in keys}
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in wanted and value is not None:
                if isinstance(value, (str, int, float, bool)):
                    text = str(value).strip()
                    if text:
                        return text
            nested = _first_text_value(value, keys)
            if nested:
                return nested
    elif isinstance(data, (list, tuple)):
        for item in data:
            nested = _first_text_value(item, keys)
            if nested:
                return nested
    return ""


def invoice_number_from_access_key(access_key: str) -> str:
    """Return Ecuador's establecimiento-punto-secuencial encoded in a 49-digit SRI key."""
    digits = re.sub(r"\D", "", str(access_key or ""))
    if len(digits) != 49:
        return ""
    return f"{digits[24:27]}-{digits[27:30]}-{digits[30:39]}"


def query_comprobante(base_url: str, api_key: str, access_key: str, timeout: int = 15) -> dict[str, Any]:
    """Consulta el estado de un comprobante ya enviado a AZUR.

    La documentación pública de AZUR indica consultar ``/consulta/comprobante``
    después de recibir ``claveacceso``. La respuesta puede variar entre tenants,
    por eso devolvemos el JSON original y una clasificación conservadora. Nunca
    se considera AUTORIZADA por el simple hecho de tener una clave de acceso.
    """
    base = normalize_base_url(base_url)
    key = (api_key or "").strip()
    access = re.sub(r"\s+", "", access_key or "")
    if not key:
        raise AzurError("La API key de AZUR no está configurada")
    if not access:
        raise AzurError("No hay clave de acceso para consultar")

    payload = {
        "api_key": key,
        "claveacceso": access,
        # Compatibilidad defensiva con instalaciones que usan snake_case.
        "clave_acceso": access,
    }
    last: AzurResponse | None = None
    for url in _endpoint_candidates(base, "consulta/comprobante"):
        response = _post_json(url, payload, timeout=timeout, api_key=key)
        last = response
        if _looks_like_route_missing(response):
            continue
        data = response.data if isinstance(response.data, dict) else response.data
        text = _flatten_text(data, response.text)
        if _auth_rejected(text) or response.status in {401, 403}:
            raise AzurError("AZUR rechazó la API key")
        if response.status >= 500:
            raise AzurError(f"AZUR respondió con HTTP {response.status} al consultar el comprobante")
        if response.status >= 400 and not isinstance(data, (dict, list)):
            raise AzurError(f"AZUR no pudo consultar el comprobante (HTTP {response.status})")

        state_text = _first_text_value(
            data,
            ("estado", "estado_sri", "estadoSri", "status", "estado_comprobante", "estadoComprobante"),
        )
        flattened = re.sub(r"\s+", " ", (state_text + " " + text).upper()).strip()
        negative = any(token in flattened for token in (
            "NO AUTORIZADO", "NO AUTORIZADA", "RECHAZADO", "RECHAZADA",
            "DEVUELTO", "DEVUELTA", "ANULADO", "ANULADA",
        ))
        authorized = ("AUTORIZADO" in flattened or "AUTORIZADA" in flattened) and not negative
        processing = any(token in flattened for token in (
            "EN PROCESO", "PROCESANDO", "PENDIENTE", "RECIBIDO", "RECIBIDA",
            "ENVIADO", "ENVIADA", "GENERADO", "GENERADA",
        ))
        if authorized:
            state = "AUTORIZADA"
        elif negative:
            state = "RECHAZADA"
        elif processing:
            state = "EN_PROCESO"
        else:
            state = "CONSULTADA"

        invoice_number = invoice_number_from_access_key(access) or _first_text_value(
            data,
            ("numero_factura", "numeroFactura", "numero_comprobante", "numeroComprobante", "numero", "secuencial"),
        ) or None
        pdf_url = _first_text_value(data, ("pdf", "pdf_url", "url_pdf", "ride", "ride_url", "url_ride")) or None
        xml_url = _first_text_value(data, ("xml", "xml_url", "url_xml")) or None
        authorization = _first_text_value(data, ("numero_autorizacion", "numeroAutorizacion", "autorizacion")) or None
        return {
            "ok": True,
            "endpoint": url,
            "status": response.status,
            "estado": state,
            "estado_origen": state_text or None,
            "numero_factura": invoice_number,
            "numero_autorizacion": authorization,
            "pdf_url": pdf_url,
            "xml_url": xml_url,
            "data": data if isinstance(data, (dict, list)) else {},
        }

    if last:
        raise AzurError(f"AZUR respondió con HTTP {last.status}, pero no se pudo usar el endpoint de consulta")
    raise AzurError("No se pudo conectar con AZUR para consultar el comprobante")
