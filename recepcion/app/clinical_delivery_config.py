"""Local-only credential setup for manual clinical delivery.

This module never reads Neon, talks to Meta, or accesses the GitHub secrets.
Updates only explicitly allowlisted keys inside Reception's existing .env file,
which the canonical launcher preserves across app updates.
"""
from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
BUCKET = "dr-revelo-clinical-2026"
ALLOWED = {
    "CLINICAL_R2_ACCOUNT_ID",
    "CLINICAL_R2_BUCKET",
    "CLINICAL_R2_ACCESS_KEY_ID",
    "CLINICAL_R2_SECRET_ACCESS_KEY",
    "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED",
    "WHATSAPP_GRAPH_VERSION",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_TEST_PHONE",
    "WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE",
    "WHATSAPP_CLINICAL_VIDEO_TEMPLATE",
    "WHATSAPP_CLINICAL_LANGUAGE",
    "CLINICAL_DELIVERY_LAN_SECRET",
    "CLINICAL_DELIVERY_LIVE_ENABLED",
    "WHATSAPP_CLINICAL_TEMPLATES_APPROVED",
}
# All values are single-line .env scalars. A newline would allow injecting other
# settings and an accidental quote can change python-dotenv parsing.
def _validate(key: str, value: str) -> None:
    if key not in ALLOWED:
        raise ValueError("No se permite modificar esta configuración")
    if not isinstance(value, str) or not value or len(value) > 1000:
        raise ValueError("Campo obligatorio o demasiado largo: " + key)
    if any(c in value for c in "\r\n\0\"'\\") or value.strip() != value:
        raise ValueError("Caracteres no permitidos: " + key)
    if key == "CLINICAL_R2_ACCOUNT_ID" and not re.fullmatch(r"[a-fA-F0-9]{32}", value):
        raise ValueError("El identificador de la cuenta Cloudflare debe tener 32 caracteres hexadecimales")
    if key == "CLINICAL_R2_BUCKET" and value != BUCKET:
        raise ValueError("Bucket clínico distinto del verificado")
    if key == "CLINICAL_R2_ACCESS_KEY_ID" and not re.fullmatch(r"[a-zA-Z0-9]{16,128}", value):
        raise ValueError("Access Key ID R2 inválido")
    if key == "CLINICAL_R2_SECRET_ACCESS_KEY" and not re.fullmatch(r"[a-zA-Z0-9/+=_-]{32,256}", value):
        raise ValueError("Secret Access Key R2 inválida")
    if key == "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED" and value != "1":
        raise ValueError("La política privada R2 ya se verificó; no modificarla aquí")
    if key in ("CLINICAL_DELIVERY_LIVE_ENABLED", "WHATSAPP_CLINICAL_TEMPLATES_APPROVED") and value not in ("0", "1"):
        raise ValueError("Indicador no válido: " + key)
    if key == "CLINICAL_DELIVERY_LAN_SECRET" and not re.fullmatch(r"[a-zA-Z0-9]{32,128}",value):
        raise ValueError("La clave LAN debe tener al menos 32 caracteres")
    if key == "WHATSAPP_TEST_PHONE" and not re.fullmatch(r"(?:09[0-9]{8}|5939[0-9]{8})",value):
        raise ValueError("Número de prueba de Ecuador inválido")
    if key == "WHATSAPP_PHONE_NUMBER_ID" and not re.fullmatch(r"[0-9]{8,32}",value):
        raise ValueError("ID de número de Meta inválido")
    if key == "WHATSAPP_GRAPH_VERSION" and not re.fullmatch(r"v[0-9]{2,3}\\.[0-9]+",value):
        raise ValueError("Versión Graph inválida, por ejemplo v26.0")
    if key in ("WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE", "WHATSAPP_CLINICAL_VIDEO_TEMPLATE") and not re.fullmatch(r"[a-z0-9_]{3,70}",value):
        raise ValueError("Nombre de plantilla inválido")
    if key == "WHATSAPP_CLINICAL_LANGUAGE" and value != "es_EC":
        raise ValueError("El idioma clínico debe ser es_EC")
    if key == "WHATSAPP_ACCESS_TOKEN" and not re.fullmatch(r"[a-zA-Z0-9|._+=/-]{25,1000}",value):
        raise ValueError("Token Meta inválido")


def parse_existing(path: Path=ENV_PATH) -> dict[str, str]:
    result = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", raw)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def save_local_settings(updates: dict[str, str], path: Path=ENV_PATH) -> None:
    """Safely preserve unrelated local settings without ever logging any secrets."""
    if not updates:
        return
    for key,value in updates.items():
        _validate(key,value)
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    replaced = set()
    result = []
    for line in lines:
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        key = m.group(1) if m else None
        if key in updates:
            if key not in replaced:
                result.append(f"{key}={updates[key]}")
                replaced.add(key)
        else:
            result.append(line)
    for key,value in updates.items():
        if key not in replaced:
            result.append(f"{key}={value}")
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp = None
    try:
        fd,tmp = tempfile.mkstemp(prefix=".clinical_setup_", dir=str(path.parent))
        # Keep the original mode on POSIX, where chmod is reliable.
        if os.name != "nt":
            os.fchmod(fd, stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600)
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            f.write("\n".join(result) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
