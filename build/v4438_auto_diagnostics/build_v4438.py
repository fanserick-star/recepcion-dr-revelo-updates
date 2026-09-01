from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_38_auto_diagnostics"
OUT.mkdir(parents=True, exist_ok=True)

# Fuente exacta ya publicada y validada de v4.4.37. No se vuelve a ningún launcher viejo.
SOURCE_REF = "38399d6767db0c79e81ec357db1176e39ff3d7e5"
SOURCE_PREFIX = "updates/v4_4_37_dependency_guard"
VERSION = "4.4.38"
APP_VERSION = "4.4.36"

EXPECTED = {
    "launcher": "b7b95250a3d517c8993b16a911f4b357124a55787ab757499a749e7d40c84ec4",
    "app_base_4428.py": "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
    "app.py": "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e",
    "static/app.js": "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
    "static/index.html": "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


DIAGNOSTICS = r'''

# ---------------------------------------------------------------------------
# v4.4.38 — diagnóstico automático privado de fallos fatales
# ---------------------------------------------------------------------------
# Solo se ejecuta cuando Recepción NO puede arrancar (o para reenviar una cola
# pendiente). No sube .env, SQLite, Excel, pacientes, citas ni facturas.
# Antes de salir de la PC los textos pasan por sanitización de secretos/PII.
_RP_DIAGNOSTICS_VERSION = "4.4.38-private-neon-1"
_RP_DIAGNOSTIC_TABLE = "rp_diagnostics_incidents"
_RP_DIAGNOSTIC_DEDUPE_SECONDS = 1800


def _rp_diag_enabled() -> bool:
    raw = str(os.getenv("RP_DIAGNOSTICS_ENABLED", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def _rp_diag_sanitize(value: object) -> str:
    text = str(value or "")
    try:
        text = text.replace(str(ROOT), "[APP_ROOT]")
    except Exception:
        pass
    # Credenciales/URLs de base de datos completas.
    text = re.sub(r"(?i)postgres(?:ql)?://[^\\s\\'\\\"<>\\]]+", "[DATABASE_URL_REDACTADA]", text)
    # Cabeceras y claves comunes.
    text = re.sub(
        r"(?i)\\b(database_url|neon_database_url|password|passwd|secret|token|api[_-]?key|authorization)\\b\\s*[:=]\\s*([^\\s,;|]+)",
        lambda m: f"{m.group(1)}=[REDACTADO]",
        text,
    )
    text = re.sub(r"(?i)\\bBearer\\s+[A-Za-z0-9._~+\\/=-]+", "Bearer [REDACTADO]", text)
    # Correos.
    text = re.sub(r"(?i)\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b", "[CORREO_REDACTADO]", text)
    # Usuario de Windows en rutas.
    text = re.sub(r"(?i)C:\\\\Users\\\\[^\\\\\\r\\n\\t ]+", r"C:\\Users\\[USUARIO]", text)
    # Campos que podrían contener datos de pacientes.
    text = re.sub(
        r"(?i)\\b(c[eé]dula|ruc|correo|e-?mail|celular|tel[eé]fono|patient_id|patient|cliente)\\b\\s*[:=]\\s*[^,\\r\\n|]+",
        lambda m: m.group(1) + "=[REDACTADO]",
        text,
    )
    # Cédulas, teléfonos, RUC, IDs largos. Puertos/líneas cortas no se alteran.
    text = re.sub(r"(?<!\\d)\\d{7,20}(?!\\d)", "[NUMERO_REDACTADO]", text)

    def _ip_repl(match):
        ip = match.group(0)
        return ip if ip.startswith("127.") else "[IP_REDACTADA]"

    text = re.sub(r"(?<!\\d)(?:\\d{1,3}\\.){3}\\d{1,3}(?!\\d)", _ip_repl, text)
    return text


def _rp_diag_read_tail(path: Path, *, max_bytes: int = 131072, max_lines: int = 350, max_chars: int = 48000) -> str:
    try:
        if not path.is_file():
            return ""
        size = path.stat().st_size
        with path.open("rb") as fh:
            start = max(0, size - max_bytes)
            fh.seek(start)
            raw = fh.read(max_bytes)
        text = raw.decode("utf-8", errors="replace")
        if start > 0 and "\n" in text:
            text = text.split("\n", 1)[1]
        text = "\n".join(text.splitlines()[-max_lines:])
        return _rp_diag_sanitize(text)[-max_chars:]
    except Exception as exc:
        return "[No se pudo leer log: " + _rp_diag_sanitize(type(exc).__name__) + "]"


def _rp_diag_connection_url() -> str:
    for key in ("DATABASE_URL", "NEON_DATABASE_URL"):
        value = str(os.getenv(key, "") or "").strip()
        if value:
            return value
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() in {"DATABASE_URL", "NEON_DATABASE_URL"}:
                return value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _rp_diag_db_connect():
    url = _rp_diag_connection_url()
    if not url:
        raise RuntimeError("Conexión privada de diagnóstico no configurada")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in {"postgres", "postgresql"}:
        raise RuntimeError("Esquema de base privada no compatible")
    from pg8000 import dbapi as _dbapi
    import ssl as _ssl
    user = urllib.parse.unquote(parts.username or "")
    password = urllib.parse.unquote(parts.password or "")
    host = parts.hostname or ""
    database = urllib.parse.unquote((parts.path or "/").lstrip("/")) or "neondb"
    if not user or not password or not host:
        raise RuntimeError("Conexión privada incompleta")
    return _dbapi.connect(
        user=user,
        password=password,
        host=host,
        port=int(parts.port or 5432),
        database=database,
        ssl_context=_ssl.create_default_context(),
        timeout=5,
        application_name="recepcion-diagnostics",
    )


def _rp_diag_paths() -> tuple[Path, Path, Path]:
    data = _data_dir(ROOT)
    return data / "diagnostic_outbox", data / "diagnostic_last.json", data / "last_diagnostic_incident.txt"


def _rp_diag_machine_hash() -> str:
    seed = (str(os.getenv("COMPUTERNAME", "")) + "|" + str(ROOT)).encode("utf-8", errors="ignore")
    return hashlib.sha256(seed).hexdigest()[:20]


def _rp_diag_update_state() -> str:
    path = _data_dir(ROOT) / "auto_update_state.json"
    return _rp_diag_read_tail(path, max_bytes=32768, max_lines=120, max_chars=16000)


def _rp_diag_build_payload(stage: str, exc: BaseException) -> dict:
    launcher_log = _rp_diag_read_tail(_data_dir(ROOT) / "launcher_errors.log")
    backend_log = _rp_diag_read_tail(_data_dir(ROOT) / "backend_startup.log")
    err = _rp_diag_sanitize(str(exc) or repr(exc))[:6000]
    error_class = _rp_diag_sanitize(type(exc).__name__)[:120]
    clean_stage = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(stage or "launcher_fatal"))[:80]
    signature_source = (clean_stage + "|" + error_class + "|" + err + "|" + backend_log[-5000:]).encode("utf-8", errors="ignore")
    signature = hashlib.sha256(signature_source).hexdigest()
    now_epoch = int(time.time())
    suffix = hashlib.sha256(os.urandom(24)).hexdigest()[:6].upper()
    incident_id = "INC-" + time.strftime("%Y%m%d-%H%M%S", time.localtime(now_epoch)) + "-" + suffix
    metadata = {
        "diagnostics_version": _RP_DIAGNOSTICS_VERSION,
        "port": int(APP_PORT or 0),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": os.name,
        "source_epoch": now_epoch,
    }
    return {
        "incident_id": incident_id,
        "created_epoch": now_epoch,
        "package_version": _local_package_version(ROOT),
        "app_version": _installed_app_version(ROOT),
        "launcher_version": str(LAUNCHER_VERSION),
        "stage": clean_stage,
        "error_class": error_class,
        "error_message": err,
        "signature": signature,
        "launcher_log": launcher_log,
        "backend_log": backend_log,
        "update_state": _rp_diag_update_state(),
        "machine_hash": _rp_diag_machine_hash(),
        "metadata": metadata,
    }


def _rp_diag_upload_payload(payload: dict) -> None:
    conn = _rp_diag_db_connect()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS rp_diagnostics_incidents (
                incident_id VARCHAR(64) PRIMARY KEY,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                source_created_epoch BIGINT,
                package_version VARCHAR(32),
                app_version VARCHAR(32),
                launcher_version VARCHAR(120),
                stage VARCHAR(80),
                error_class VARCHAR(120),
                error_message TEXT,
                signature VARCHAR(64),
                launcher_log TEXT,
                backend_log TEXT,
                update_state TEXT,
                machine_hash VARCHAR(64),
                metadata_json TEXT
            )"""
        )
        cur.execute(
            """INSERT INTO rp_diagnostics_incidents (
                incident_id, source_created_epoch, package_version, app_version,
                launcher_version, stage, error_class, error_message, signature,
                launcher_log, backend_log, update_state, machine_hash, metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (incident_id) DO UPDATE SET
                received_at=NOW(), error_message=EXCLUDED.error_message,
                launcher_log=EXCLUDED.launcher_log, backend_log=EXCLUDED.backend_log,
                update_state=EXCLUDED.update_state, metadata_json=EXCLUDED.metadata_json""",
            (
                str(payload.get("incident_id") or ""),
                int(payload.get("created_epoch") or 0),
                str(payload.get("package_version") or "")[:32],
                str(payload.get("app_version") or "")[:32],
                str(payload.get("launcher_version") or "")[:120],
                str(payload.get("stage") or "")[:80],
                str(payload.get("error_class") or "")[:120],
                str(payload.get("error_message") or "")[:6000],
                str(payload.get("signature") or "")[:64],
                str(payload.get("launcher_log") or "")[:48000],
                str(payload.get("backend_log") or "")[:48000],
                str(payload.get("update_state") or "")[:16000],
                str(payload.get("machine_hash") or "")[:64],
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, separators=(",", ":"))[:8000],
            ),
        )
        conn.commit()
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def _rp_diag_load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _rp_diag_save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _rp_diag_mark_last(payload: dict, status: str) -> dict:
    _, last_path, id_path = _rp_diag_paths()
    result = {
        "incident_id": str(payload.get("incident_id") or ""),
        "signature": str(payload.get("signature") or ""),
        "created_epoch": int(payload.get("created_epoch") or time.time()),
        "status": str(status),
    }
    try:
        _rp_diag_save_json(last_path, result)
        id_path.parent.mkdir(parents=True, exist_ok=True)
        id_path.write_text(result["incident_id"] + "\n", encoding="utf-8")
    except Exception:
        pass
    return result


def _rp_diag_flush_outbox(max_items: int = 3) -> int:
    if not _rp_diag_enabled():
        return 0
    outbox, last_path, _ = _rp_diag_paths()
    if not outbox.is_dir():
        return 0
    sent = 0
    for path in sorted(outbox.glob("INC-*.json"))[:max(0, int(max_items))]:
        try:
            payload = _rp_diag_load_json(path)
            if not payload.get("incident_id"):
                path.unlink(missing_ok=True)
                continue
            _rp_diag_upload_payload(payload)
            path.unlink(missing_ok=True)
            sent += 1
            last = _rp_diag_load_json(last_path)
            if last.get("incident_id") == payload.get("incident_id"):
                _rp_diag_mark_last(payload, "sent")
        except Exception as exc:
            _log("Diagnóstico pendiente no enviado: " + _rp_diag_sanitize(type(exc).__name__ + ": " + str(exc)), ROOT)
            break
    return sent


def _rp_diag_report(stage: str, exc: BaseException) -> dict:
    if not _rp_diag_enabled():
        return {"incident_id": "", "status": "disabled"}
    payload = _rp_diag_build_payload(stage, exc)
    outbox, last_path, _ = _rp_diag_paths()
    last = _rp_diag_load_json(last_path)
    if (
        last.get("signature") == payload.get("signature")
        and int(payload["created_epoch"]) - int(last.get("created_epoch") or 0) <= _RP_DIAGNOSTIC_DEDUPE_SECONDS
        and last.get("incident_id")
    ):
        # Evita inundar Neon si el usuario intenta abrir varias veces el mismo fallo.
        _rp_diag_flush_outbox(max_items=3)
        refreshed = _rp_diag_load_json(last_path)
        return refreshed or last

    outbox.mkdir(parents=True, exist_ok=True)
    queued = outbox / (payload["incident_id"] + ".json")
    _rp_diag_save_json(queued, payload)
    status = "queued"
    try:
        _rp_diag_upload_payload(payload)
        queued.unlink(missing_ok=True)
        status = "sent"
    except Exception as upload_exc:
        # Nunca registrar credenciales ni URL: solo tipo/mensaje ya sanitizado.
        _log("Diagnóstico en cola: " + _rp_diag_sanitize(type(upload_exc).__name__ + ": " + str(upload_exc)), ROOT)
    return _rp_diag_mark_last(payload, status)


def _rp_diag_message(base: str, result: dict) -> str:
    incident = str((result or {}).get("incident_id") or "").strip()
    status = str((result or {}).get("status") or "")
    if not incident:
        return base
    if status == "sent":
        return base + "\n\nDiagnóstico enviado automáticamente: " + incident
    return base + "\n\nDiagnóstico preparado: " + incident + "\nSe enviará automáticamente cuando haya conexión."

'''


def build() -> None:
    parts = [git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5)]
    base = git_bytes("app_base_4428.py")
    app = git_bytes("app.py")
    static_app = git_bytes("static/app.js")
    static_index = git_bytes("static/index.html")

    require(sha(b"".join(parts)) == EXPECTED["launcher"], "Launcher v4.4.37 publicado cambió")
    for path, data in (("app_base_4428.py", base), ("app.py", app), ("static/app.js", static_app), ("static/index.html", static_index)):
        require(sha(data) == EXPECTED[path], f"Bytes publicados cambiaron: {path}")

    p1 = parts[0].decode("utf-8-sig")
    old_lv = 'LAUNCHER_VERSION = "4.4.32-dynamic-port-patch-1"'
    new_lv = 'LAUNCHER_VERSION = "4.4.38-dynamic-port-dependency-diagnostics-1"'
    require(p1.count(old_lv) == 1, "No se encontró versión exacta del launcher 4.4.37")
    p1 = p1.replace(old_lv, new_lv, 1)

    p3 = parts[2].decode("utf-8-sig")
    splash_anchor = "    splash = Splash()\n    try:\n"
    require(p3.count(splash_anchor) == 1, "Cambió ancla de inicio del launcher")
    p3 = p3.replace(
        splash_anchor,
        "    splash = Splash()\n"
        "    try:\n"
        "        _rp_diag_flush_outbox(max_items=3)\n"
        "    except Exception as diag_exc:\n"
        "        _log(\"No se pudo reenviar diagnóstico pendiente: \" + _rp_diag_sanitize(type(diag_exc).__name__ + \": \" + str(diag_exc)), ROOT)\n"
        "    try:\n",
        1,
    )

    blocked_old = (
        '        if result.get("blocked"):\n'
        '            splash.close()\n'
        '            _message(result.get("error") or "La instalación local necesita reparación.")\n'
        '            return\n'
    )
    require(p3.count(blocked_old) == 1, "Cambió ancla de actualización bloqueada")
    blocked_new = (
        '        if result.get("blocked"):\n'
        '            splash.close()\n'
        '            _blocked_text = result.get("error") or "La instalación local necesita reparación."\n'
        '            _diag = _rp_diag_report("update_blocked", RuntimeError(_blocked_text))\n'
        '            _message(_rp_diag_message(_blocked_text, _diag))\n'
        '            return\n'
    )
    p3 = p3.replace(blocked_old, blocked_new, 1)

    fatal_old = (
        '    except Exception as exc:\n'
        '        _log("Fallo general del launcher: " + repr(exc) + " | " + traceback.format_exc(limit=6).replace("\\n", " | "))\n'
        '        splash.close()\n'
        '        _message("No se pudo iniciar Recepción.\\n\\nEl detalle quedó guardado en data\\\\launcher_errors.log.")\n'
    )
    require(p3.count(fatal_old) == 1, "Cambió ancla de error fatal")
    fatal_new = (
        '    except Exception as exc:\n'
        '        _log("Fallo general del launcher: " + repr(exc) + " | " + traceback.format_exc(limit=6).replace("\\n", " | "))\n'
        '        _diag = _rp_diag_report("launcher_fatal", exc)\n'
        '        splash.close()\n'
        '        _message(_rp_diag_message("No se pudo iniciar Recepción.\\n\\nEl detalle quedó guardado en data\\\\launcher_errors.log.", _diag))\n'
    )
    p3 = p3.replace(fatal_old, fatal_new, 1)

    p4 = parts[3].decode("utf-8-sig")
    main_anchor = '\nif __name__ == "__main__":\n'
    require(p4.count(main_anchor) == 1, "Cambió ancla final del launcher v4.4.37")
    p4 = p4.replace(main_anchor, DIAGNOSTICS + main_anchor, 1)

    patched = [p1.encode("utf-8"), parts[1], p3.encode("utf-8"), p4.encode("utf-8")]
    launcher = b"".join(patched)
    launcher_text = launcher.decode("utf-8-sig")
    compile(launcher_text, "ABRIR_RECEPCION.py", "exec")
    require('LAUNCHER_VERSION = "4.4.38-dynamic-port-dependency-diagnostics-1"' in launcher_text, "Launcher no quedó actualizado")
    require("_choose_app_port" in launcher_text and 'env["RP_PORT"] = str(APP_PORT)' in launcher_text, "Se perdió puerto dinámico/RP_PORT")
    require("_rp_v4437_required_files" in launcher_text and "_rp_diag_report" in launcher_text, "Se perdió guardia o diagnóstico")

    for i, data in enumerate(patched, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)
    (OUT / "app_base_4428.py").write_bytes(base)
    (OUT / "app.py").write_bytes(app)
    (OUT / "static").mkdir(parents=True, exist_ok=True)
    (OUT / "static" / "app.js").write_bytes(static_app)
    (OUT / "static" / "index.html").write_bytes(static_index)

    paths = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    inner = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "launcher_version": "4.4.38-dynamic-port-dependency-diagnostics-1",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "copy": paths,
    }
    inner_bytes = dump(inner)
    (OUT / "update_manifest.json").write_bytes(inner_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_38_auto_diagnostics/"
    files = [
        {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
        {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(base), "encoding": "utf-8"},
        {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
        {"path": "static/app.js", "url": raw + "static/app.js", "sha256": sha(static_app), "encoding": "utf-8"},
        {"path": "static/index.html", "url": raw + "static/index.html", "sha256": sha(static_index), "encoding": "utf-8"},
        {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(inner_bytes), "encoding": "utf-8"},
    ]
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.38: diagnóstico automático privado para fallos fatales. Conserva íntegramente el launcher dinámico y la guardia de dependencias de v4.4.37. Si Recepción no puede arrancar, crea un incidente INC-..., sanitiza secretos/datos sensibles y envía solo launcher_errors.log, backend_startup.log y estado técnico a la misma base Neon privada ya configurada; sin conexión queda en cola y se reintenta al próximo arranque. No sube .env, SQLite, Excel, pacientes, citas ni facturas. Incluye nuevamente el paquete acumulativo completo para autoreparación.",
        "files": files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    require([x["path"] for x in files] == paths, "Release 4.4.38 dejó de ser acumulativo")
    print("BUILD_V4438_OK")
    print("LAUNCHER_SHA", sha(launcher))
    print("APP_SHA", sha(app))


if __name__ == "__main__":
    build()
