from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


class WhatsAppError(RuntimeError):
    pass


def build_template_payload(
    *,
    to: str,
    template_name: str,
    language_code: str,
    body_params: list[str],
    header_image_id: Optional[str] = None,
    quick_reply_payloads: Optional[list[str]] = None,
) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    if header_image_id:
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": header_image_id}}],
        })
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(value)} for value in body_params],
        })
    for index, payload in enumerate(quick_reply_payloads or []):
        components.append({
            "type": "button",
            "sub_type": "quick_reply",
            "index": str(index),
            "parameters": [{"type": "payload", "payload": str(payload)}],
        })
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": str(to),
        "type": "template",
        "template": {
            "name": str(template_name),
            "language": {"code": str(language_code)},
            "components": components,
        },
    }


def send_template(
    *,
    graph_version: str,
    phone_number_id: str,
    access_token: str,
    payload: dict[str, Any],
    timeout: float = 15.0,
) -> dict[str, Any]:
    version = str(graph_version or "").strip().lstrip("/")
    phone_id = str(phone_number_id or "").strip()
    token = str(access_token or "").strip()
    if not version:
        raise WhatsAppError("Falta WHATSAPP_GRAPH_VERSION")
    if not phone_id:
        raise WhatsAppError("Falta WHATSAPP_PHONE_NUMBER_ID")
    if not token:
        raise WhatsAppError("Falta WHATSAPP_ACCESS_TOKEN")

    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Recepcion-Dr-Revelo-WhatsApp/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
            message = detail.get("error", {}).get("message") or raw
        except Exception:
            message = raw or str(exc)
        raise WhatsAppError(f"Meta respondió HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise WhatsAppError(f"No se pudo conectar con Meta: {exc.reason}") from exc
    except Exception as exc:
        raise WhatsAppError(str(exc)) from exc