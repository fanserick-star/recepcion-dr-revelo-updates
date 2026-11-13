from __future__ import annotations

import os
import json
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_KEY = "HISTORIA_DATABASE_URL"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _read_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return {}
    return out


def _connection_identity(value: str) -> tuple[str, int, str, str] | None:
    raw = _clean(value, 4000)
    if not raw:
        return None
    try:
        parts = urllib.parse.urlsplit(raw)
        return (
            (parts.hostname or "").lower(),
            int(parts.port or 5432),
            urllib.parse.unquote((parts.path or "/neondb").lstrip("/")) or "neondb",
            urllib.parse.unquote(parts.username or ""),
        )
    except Exception:
        return None


HISTORIA_OFFICIAL_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"
HISTORIA_EMERGENCY_ENDPOINT_ID = "ep-noisy-paper-arf28291"


ACTIVE_NEON_SELECTION = ROOT / "data" / "historia_neon_selection.json"


def _validated_target(value: str) -> str:
    target = _clean(value, 30).lower()
    if target not in {"official", "emergency"}:
        raise RuntimeError("Destino clínico desconocido: conexión bloqueada")
    return target


def _startup_history_target() -> str:
    """Freeze once at Reception startup: a pending switch never splits requests."""
    if ACTIVE_NEON_SELECTION.exists():
        try:
            settings = json.loads(ACTIVE_NEON_SELECTION.read_text(encoding="utf-8"))
            if settings.get("schema") != 1:
                raise ValueError("Esquema de selección inválido")
            return _validated_target(str(settings.get("target") or ""))
        except (OSError, ValueError, TypeError) as exc:
            # Do not silently fall back to the old Neon after a corrupt choice.
            raise RuntimeError("Selección de Neon de Historia dañada; acceso clínico bloqueado") from exc
    env = _read_env_file()
    return _validated_target(env.get("HISTORIA_NEON_TARGET")
                             or os.getenv("HISTORIA_NEON_TARGET") or "official")


_PROCESS_HISTORY_TARGET = _startup_history_target()


def _history_target() -> str:
    """Immutable for this running process; changed by a deliberate restart only."""
    return _PROCESS_HISTORY_TARGET


def _database_url_for_target(target: str) -> str:
    """Resolve a privately saved credential; never use Reception's own Neon."""
    target = _validated_target(target)
    env = _read_env_file()
    key = "HISTORIA_EMERGENCY_DATABASE_URL" if target == "emergency" else ENV_KEY
    historia_url = _clean(env.get(key) or os.getenv(key), 4000)
    if not historia_url:
        if target == "emergency":
            raise RuntimeError(
                "Neon Emergencia de Historia no configurado en Recepción. "
                "No se usará el Neon Original como reemplazo silencioso."
            )
        return ""
    expected = (HISTORIA_EMERGENCY_ENDPOINT_ID if target == "emergency"
                else HISTORIA_OFFICIAL_ENDPOINT_ID)
    cfg = _parse_pg_url(historia_url)
    host = str(cfg["host"]).lower().split(".", 1)[0].removesuffix("-pooler")
    if host != expected:
        raise RuntimeError(
            "Se bloqueó una conexión a un proyecto distinto del Neon de Historia seleccionado"
        )
    reception_url = _clean(env.get("DATABASE_URL") or os.getenv("DATABASE_URL"), 4000)
    historia_id = _connection_identity(historia_url)
    reception_id = _connection_identity(reception_url)
    if historia_id and reception_id and historia_id == reception_id:
        raise RuntimeError(
            "Configuración bloqueada: Historia Clínica y Recepción apuntan a la misma base de datos"
        )
    return historia_url


def _database_url() -> str:
    """Single clinical Neon route for identity, search, queue, and documents."""
    return _database_url_for_target(_history_target())


def _parse_pg_url(url: str) -> dict:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower().split("+", 1)[0] not in {"postgres", "postgresql"}:
        raise RuntimeError("HISTORIA_DATABASE_URL no es PostgreSQL")
    return {
        "user": urllib.parse.unquote(parts.username or ""),
        "password": urllib.parse.unquote(parts.password or ""),
        "host": parts.hostname or "",
        "port": int(parts.port or 5432),
        "database": urllib.parse.unquote((parts.path or "/neondb").lstrip("/")) or "neondb",
    }


def _event_id(reception_patient_id: object, visit_ids: list[object] | None) -> str:
    ids = ",".join(str(x) for x in (visit_ids or []) if x is not None)
    raw = f"reception:{reception_patient_id}:{ids or _now()}"
    return "reception:" + str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


# These are interface placeholders. historia_lan_transport.install() replaces
# them at application startup. They intentionally perform no cloud queue I/O.
def queue_attention(**_kwargs) -> str:
    raise RuntimeError("El transporte LAN de Historia todavía no está instalado")


def cancel_attention(**_kwargs) -> list[str]:
    return []


def restore_attention(**_kwargs) -> list[str]:
    return []


def bridge_status() -> dict:
    return {
        "configured": False,
        "pending": 0,
        "sent": 0,
        "cloud_reachable": False,
        "doctor_online": False,
        "lan_online": False,
        "transport": "not-installed",
        "waiting_queue_transport": "lan_only",
    }
