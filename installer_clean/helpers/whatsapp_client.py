from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Iterable, Optional


class WhatsAppError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, code: str = "", response: object = None):
        super().__init__(message)
        self.status = status
        self.code = str(code or "")
        self.response = response


def _phone(value: str) -> str:
    d = re.sub(r"\D", "", str(value or ""))
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("0") and len(d) == 10:
        d = "593" + d[1:]
    return d


def build_template_payload(*, to: str, template_name: str, language_code: str,
                           body_params: Optional[Iterable[str]] = None,
                           header_image_id: Optional[str] = None,
                           quick_reply_payloads: Optional[Iterable[str]] = None) -> dict:
    phone = _phone(to)
    if not phone:
        raise WhatsAppError("Número de WhatsApp vacío o inválido")
    name = str(template_name or "").strip()
    lang = str(language_code or "").strip()
    if not name or not lang:
        raise WhatsAppError("La plantilla o el idioma de WhatsApp están vacíos")

    components: list[dict] = []
    if str(header_image_id or "").strip():
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": str(header_image_id).strip()}}],
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

    template = {"name": name, "language": {"code": lang}}
    if components:
        template["components"] = components
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "template",
        "template": template,
    }


def send_template(*, graph_version: str, phone_number_id: str, access_token: str,
                  payload: dict, timeout: float = 20.0) -> dict:
    version = str(graph_version or "").strip().lstrip("/") or "v26.0"
    if not re.fullmatch(r"v\d+(?:\.\d+)?", version):
        raise WhatsAppError("Versión de Meta Graph inválida")
    phone_id = re.sub(r"\D", "", str(phone_number_id or ""))
    token = str(access_token or "").strip()
    if not phone_id or not token:
        raise WhatsAppError("Faltan credenciales de WhatsApp Cloud")

    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Recepcion-Dr-Revelo/WhatsAppClient",
    })
    try:
        with urllib.request.urlopen(req, timeout=max(3.0, float(timeout))) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {"raw": body}
        err = data.get("error") if isinstance(data, dict) else None
        msg = str((err or {}).get("message") or body or f"HTTP {exc.code}")
        code = str((err or {}).get("code") or exc.code)
        raise WhatsAppError(msg, status=int(exc.code), code=code, response=data) from exc
    except Exception as exc:
        raise WhatsAppError(f"No se pudo conectar con WhatsApp Cloud: {exc}") from exc
