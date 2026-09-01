from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_40_diag_transport_resilient"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE_REF = "18ad823ce89a36393fdeba1c6c1c0bd62020a077"
SOURCE_PREFIX = "updates/v4_4_39_diag_transport"
VERSION = "4.4.40"
APP_VERSION = "4.4.36"
SOURCE_LAUNCHER_SHA = "acad51902adc1160253dfccc9a77b144e801b8ab1cc744ab1fdbcd9c532523c2"
EXPECTED = {
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


NEW_CONNECT = r'''def _rp_diag_db_connect():
    """Abre Neon con el primer driver disponible; no depende de un único driver."""
    url = _rp_diag_connection_url()
    if not url:
        raise RuntimeError("Conexión privada de diagnóstico no configurada")
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in {"postgres", "postgresql", "postgresql+pg8000", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError("Esquema de base privada no compatible")
    base_scheme = scheme.split("+", 1)[0]
    clean_parts = parts._replace(scheme=base_scheme)
    user = urllib.parse.unquote(parts.username or "")
    password = urllib.parse.unquote(parts.password or "")
    host = parts.hostname or ""
    database = urllib.parse.unquote((parts.path or "/").lstrip("/")) or "neondb"
    if not user or not password or not host:
        raise RuntimeError("Conexión privada incompleta")

    failures = []
    try:
        from pg8000 import dbapi as _pg8000
        import ssl as _ssl
        return _pg8000.connect(
            user=user, password=password, host=host, port=int(parts.port or 5432),
            database=database, ssl_context=_ssl.create_default_context(), timeout=12,
        )
    except Exception as exc:
        failures.append("pg8000:" + type(exc).__name__)

    dsn = urllib.parse.urlunsplit(clean_parts)
    try:
        import psycopg as _psycopg
        return _psycopg.connect(dsn, connect_timeout=12)
    except Exception as exc:
        failures.append("psycopg:" + type(exc).__name__)

    try:
        import psycopg2 as _psycopg2
        # psycopg2 puede no entender channel_binding en versiones antiguas.
        q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if str(k).lower() != "channel_binding"]
        dsn2 = urllib.parse.urlunsplit((base_scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment))
        return _psycopg2.connect(dsn2, connect_timeout=12)
    except Exception as exc:
        failures.append("psycopg2:" + type(exc).__name__)

    raise RuntimeError("No se pudo abrir transporte Neon [" + ", ".join(failures) + "]")
'''

NEW_UPLOAD = r'''def _rp_diag_upload_payload_direct(payload: dict) -> None:
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
                str(payload.get("incident_id") or ""), int(payload.get("created_epoch") or 0),
                str(payload.get("package_version") or "")[:32], str(payload.get("app_version") or "")[:32],
                str(payload.get("launcher_version") or "")[:120], str(payload.get("stage") or "")[:80],
                str(payload.get("error_class") or "")[:120], str(payload.get("error_message") or "")[:6000],
                str(payload.get("signature") or "")[:64], str(payload.get("launcher_log") or "")[:48000],
                str(payload.get("backend_log") or "")[:48000], str(payload.get("update_state") or "")[:16000],
                str(payload.get("machine_hash") or "")[:64],
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, separators=(",", ":"))[:8000],
            ),
        )
        conn.commit()
    finally:
        try:
            if cur is not None: cur.close()
        except Exception:
            pass
        try: conn.close()
        except Exception: pass


def _rp_diag_upload_via_venv(payload: dict) -> None:
    """Segundo camino: ejecuta el mismo uploader con el Python real de .venv."""
    outbox, _, _ = _rp_diag_paths()
    outbox.mkdir(parents=True, exist_ok=True)
    incident = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(payload.get("incident_id") or "INC"))[:80]
    temp = outbox / (".transport_" + incident + "_" + str(os.getpid()) + ".json")
    _rp_diag_save_json(temp, payload)
    try:
        py = _python_exe(windowless=False)
        flags = _hidden_flags()
        proc = subprocess.run(
            [str(py), str(ROOT / "ABRIR_RECEPCION.py"), "--diag-upload-file", str(temp)],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=28, check=False, creationflags=flags,
        )
        if proc.returncode != 0:
            marker = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["sin-detalle"]
            safe = re.sub(r"[^A-Za-z0-9_.:-]+", "_", marker[0])[:120]
            raise RuntimeError("Uploader .venv falló: " + safe)
    finally:
        try: temp.unlink(missing_ok=True)
        except Exception: pass


def _rp_diag_upload_payload(payload: dict) -> None:
    first = None
    try:
        _rp_diag_upload_payload_direct(payload)
        return
    except Exception as exc:
        first = exc
    try:
        _rp_diag_upload_via_venv(payload)
        return
    except Exception as second:
        raise RuntimeError(
            "Transporte diagnóstico agotó rutas [directo=" + type(first).__name__ +
            ", venv=" + type(second).__name__ + "]"
        ) from second
'''

CLI_PATCH = r'''    if "--diag-upload-file" in sys.argv:
        i = sys.argv.index("--diag-upload-file")
        try:
            payload = _rp_diag_load_json(Path(sys.argv[i + 1]))
            if not payload.get("incident_id"):
                raise RuntimeError("payload_sin_incident_id")
            _rp_diag_upload_payload_direct(payload)
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            # Nunca imprimir el mensaje del driver: podría contener host/usuario.
            sys.stderr.write("DIAG_UPLOAD_ERROR:" + type(exc).__name__ + "\n")
            raise SystemExit(73)
'''


def split_four(text: str) -> list[bytes]:
    lines = text.splitlines(keepends=True)
    target = max(1, len(text) // 4)
    chunks, buf, n = [], [], 0
    for line in lines:
        if len(chunks) < 3 and buf and n + len(line) > target:
            chunks.append("".join(buf).encode("utf-8")); buf=[]; n=0
        buf.append(line); n += len(line)
    chunks.append("".join(buf).encode("utf-8"))
    while len(chunks) < 4: chunks.append(b"")
    require(len(chunks) == 4 and b"".join(chunks).decode("utf-8") == text, "Partición launcher inválida")
    return chunks


def build() -> None:
    old_launcher = b"".join(git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5))
    require(sha(old_launcher) == SOURCE_LAUNCHER_SHA, "Launcher 4.4.39 fuente no coincide")
    text = old_launcher.decode("utf-8-sig")
    require(text.count('LAUNCHER_VERSION = "4.4.39-dynamic-port-dependency-diagnostics-transport-1"') == 1, "Versión fuente cambió")
    text = text.replace('LAUNCHER_VERSION = "4.4.39-dynamic-port-dependency-diagnostics-transport-1"', 'LAUNCHER_VERSION = "4.4.40-dynamic-port-dependency-diagnostics-resilient-1"', 1)
    text = text.replace('_RP_DIAGNOSTICS_VERSION = "4.4.39-private-neon-transport-1"', '_RP_DIAGNOSTICS_VERSION = "4.4.40-private-neon-resilient-1"', 1)

    s = text.find("def _rp_diag_db_connect():")
    e = text.find("\n\ndef _rp_diag_paths()", s)
    require(s >= 0 and e > s, "No se encontró conexión diagnóstica")
    text = text[:s] + NEW_CONNECT + text[e:]

    s = text.find("def _rp_diag_upload_payload(payload: dict) -> None:")
    e = text.find("\n\ndef _rp_diag_load_json", s)
    require(s >= 0 and e > s, "No se encontró uploader diagnóstico")
    text = text[:s] + NEW_UPLOAD + text[e:]

    marker = 'if __name__ == "__main__":\n'
    require(text.count(marker) == 1, "Bloque main ambiguo")
    text = text.replace(marker, marker + CLI_PATCH, 1)

    compile(text, "ABRIR_RECEPCION.py", "exec")
    require("--diag-upload-file" in text and "_rp_diag_upload_via_venv" in text, "Falta fallback .venv")
    require("import psycopg as _psycopg" in text and "import psycopg2 as _psycopg2" in text, "Faltan drivers alternos")
    require("_rp_v4437_required_files" in text and "_choose_app_port" in text, "Se perdió blindaje previo")

    parts = split_four(text)
    for i, data in enumerate(parts, 1): (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    fixed = {}
    for rel in EXPECTED:
        data = git_bytes(rel)
        require(sha(data) == EXPECTED[rel], f"Bytes funcionales cambiaron: {rel}")
        target = OUT / rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data); fixed[rel] = data

    paths = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    inner = {
        "product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
        "launcher_version":"4.4.40-dynamic-port-dependency-diagnostics-resilient-1","updater_version":"integrado-en-launcher",
        "required_dependencies":["app_base_4428.py"],"copy":paths,
    }
    inner_bytes = dump(inner); (OUT / "update_manifest.json").write_bytes(inner_bytes)
    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_40_diag_transport_resilient/"
    launcher = b"".join(parts)
    files = [
        {"path":"ABRIR_RECEPCION.py","parts":[raw+f"ABRIR_RECEPCION.part{i}" for i in range(1,5)],"sha256":sha(launcher),"encoding":"utf-8"},
        {"path":"app_base_4428.py","url":raw+"app_base_4428.py","sha256":sha(fixed["app_base_4428.py"]),"encoding":"utf-8"},
        {"path":"app.py","url":raw+"app.py","sha256":sha(fixed["app.py"]),"encoding":"utf-8"},
        {"path":"static/app.js","url":raw+"static/app.js","sha256":sha(fixed["static/app.js"]),"encoding":"utf-8"},
        {"path":"static/index.html","url":raw+"static/index.html","sha256":sha(fixed["static/index.html"]),"encoding":"utf-8"},
        {"path":"update_manifest.json","url":raw+"update_manifest.json","sha256":sha(inner_bytes),"encoding":"utf-8"},
    ]
    candidate = {
        "product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
        "mandatory":True,"channel":"files-v3",
        "message":"v4.4.40: transporte diagnóstico resiliente. Mantiene el envío directo a Neon, agrega drivers alternos y un segundo intento obligatorio mediante el Python de .venv, evitando depender del intérprete con que se abrió el launcher. Los INC pendientes permanecen en data y se reintentan. No cambia app.py, facturación, agenda, .env ni bases locales.",
        "files":files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4440_OK")
    print("LAUNCHER_SHA", sha(launcher))


if __name__ == "__main__":
    build()
