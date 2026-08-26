from __future__ import annotations

import json
import re
import socket
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
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **({"api-key": api_key} if api_key else {}),
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        status = int(exc.code or 500)
        raw = exc.read().decode("utf-8", errors="replace")
    except (URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise AzurError(f"No se pudo conectar con AZUR: {reason}") from exc
    except Exception as exc:
        raise AzurError(f"No se pudo conectar con AZUR: {exc}") from exc

    safe = _safe_text(raw, api_key)
    try:
        data = json.loads(safe) if safe.strip() else {}
    except Exception:
        data = None
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
    field_words = ("items", "comprador", "emisor", "obligatorio", "required", "campo")
    return any(x in s for x in field_words) and not _auth_rejected(s)


def _candidate_origins(base: str) -> list[str]:
    parsed = urlparse(base)
    host = (parsed.hostname or "").lower()
    origins = [base.rstrip("/")]
    if host == "azur.com.ec":
        origins.append("https://api.azur.com.ec")
        origins.append("https://central.azur.com.ec")
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
        if any(x in flat for x in ("comprobante", "clave", "api_key", "api key", "no encontrado")):
            return False
    return ("<html" in text or "<!doctype" in text or response.data is None or not text.strip())


def test_connection(base_url: str, api_key: str, timeout: int = 12) -> dict[str, Any]:
    """Locate AZUR API v2 without emitting a real document."""
    base = normalize_base_url(base_url)
    key = (api_key or "").strip()
    if not key:
        raise AzurError("La API key de AZUR no está configurada")

    attempts: list[dict[str, Any]] = []
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
        if isinstance(response.data, (dict, list)) or response.status < 500:
            return {
                "ok": True,
                "reachable": True,
                "api_key_valid": True,
                "endpoint": url,
                "status": response.status,
                "message": "Conexión con AZUR confirmada. La prueba consultó una clave inexistente y no emitió ningún comprobante.",
            }

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
            raise AzurError("AZUR respondió de una forma inesperada; se detuvo la prueba por seguridad")
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

    statuses = ", ".join(f"{a.get('status', 'sin respuesta')}" for a in attempts[-6:])
    detail = f" (respuestas: {statuses})" if statuses else ""
    raise AzurError("No se pudo localizar la API v2 de AZUR en los endpoints oficiales" + detail)


def emit_invoice(base_url: str, api_key: str, invoice_payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
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
