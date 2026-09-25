from __future__ import annotations

"""Cliente mínimo de Meta WhatsApp Cloud API usado por Recepción.

El envío automático principal vive en la nube. Este módulo conserva únicamente
la compatibilidad para pruebas/manual fallback sin hilos ni sondeos propios.
"""

import json
import re
import urllib.error
import urllib.request


class WhatsAppError(RuntimeError):
    pass


def _clean_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("0") and len(digits) == 10:
        digits = "593" + digits[1:]
    if not 8 <= len(digits) <= 15:
        raise WhatsAppError("Número de WhatsApp no válido")
    return digits


def build_template_payload(
    *,
    to: str,
    template_name: str,
    language_code: str,
    body_params=None,
    header_image_id=None,
    quick_reply_payloads=None,
):
    name = str(template_name or "").strip()
    lang = str(language_code or "").strip()
    if not name or not lang:
        raise WhatsAppError("Plantilla o idioma no configurado")

    components = []
    if header_image_id:
        components.append({
            "type": "header",
            "parameters": [{
                "type": "image",
                "image": {"id": str(header_image_id).strip()},
            }],
        })

    body = [str(x) for x in (body_params or [])]
    if body:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": x} for x in body],
        })

    for index, payload in enumerate(quick_reply_payloads or []):
        components.append({
            "type": "button",
            "sub_type": "quick_reply",
            "index": str(index),
            "parameters": [{"type": "payload", "payload": str(payload)}],
        })

    template = {
        "name": name,
        "language": {"code": lang},
    }
    if components:
        template["components"] = components

    return {
        "messaging_product": "whatsapp",
        "to": _clean_phone(to),
        "type": "template",
        "template": template,
    }


def send_template(
    *,
    graph_version: str,
    phone_number_id: str,
    access_token: str,
    payload: dict,
    timeout: float = 20.0,
):
    version = str(graph_version or "").strip().lstrip("v")
    phone_id = str(phone_number_id or "").strip()
    token = str(access_token or "").strip()
    if not version or not phone_id or not token:
        raise WhatsAppError("Configuración de Meta incompleta")

    url = f"https://graph.facebook.com/v{version}/{phone_id}/messages"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Recepcion-Dr-Revelo/4.6",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout)) as response:
            raw = response.read(1_000_000).decode("utf-8", "replace")
            return json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(1_000_000).decode("utf-8", "replace")
            data = json.loads(raw or "{}")
            detail = (
                ((data.get("error") or {}).get("message"))
                if isinstance(data, dict) else None
            )
        except Exception:
            detail = None
        raise WhatsAppError(detail or f"Meta respondió HTTP {exc.code}") from exc
    except Exception as exc:
        raise WhatsAppError(f"No se pudo conectar con Meta: {exc}") from exc
