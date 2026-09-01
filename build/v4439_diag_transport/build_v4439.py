from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_39_diag_transport"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE_REF = "953ab521d95e6ca3aa0bc65aba1ddc02100fa4cd"
SOURCE_PREFIX = "updates/v4_4_38_auto_diagnostics"
VERSION = "4.4.39"
APP_VERSION = "4.4.36"
SOURCE_LAUNCHER_SHA = "3f0faea16530cd0e79ecb35f090068549af87e34f27cb2f895065c096b423ad9"
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
    """Conexión corta de diagnóstico con la misma compatibilidad que la app estable."""
    url = _rp_diag_connection_url()
    if not url:
        raise RuntimeError("Conexión privada de diagnóstico no configurada")
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in {"postgres", "postgresql", "postgresql+pg8000", "postgresql+psycopg"}:
        raise RuntimeError("Esquema de base privada no compatible")
    # El backend estable normaliza postgresql+<driver>. Para conexión directa con
    # pg8000 quitamos solamente el sufijo del driver y conservamos host/credenciales.
    if "+" in scheme:
        base_scheme = scheme.split("+", 1)[0]
        parts = parts._replace(scheme=base_scheme)
    from pg8000 import dbapi as _dbapi
    import ssl as _ssl
    user = urllib.parse.unquote(parts.username or "")
    password = urllib.parse.unquote(parts.password or "")
    host = parts.hostname or ""
    database = urllib.parse.unquote((parts.path or "/").lstrip("/")) or "neondb"
    if not user or not password or not host:
        raise RuntimeError("Conexión privada incompleta")
    # Igual que la conexión normal de Recepción: solo timeout + SSL. Neon puede
    # rechazar parámetros de arranque extra, por eso NO se envía application_name.
    return _dbapi.connect(
        user=user,
        password=password,
        host=host,
        port=int(parts.port or 5432),
        database=database,
        ssl_context=_ssl.create_default_context(),
        timeout=12,
    )
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
    while len(chunks) < 4:
        chunks.append(b"")
    require(len(chunks) == 4 and b"".join(chunks).decode("utf-8") == text, "Partición launcher inválida")
    return chunks


def build() -> None:
    old_parts = [git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5)]
    old_launcher = b"".join(old_parts)
    require(sha(old_launcher) == SOURCE_LAUNCHER_SHA, "Launcher 4.4.38 publicado no coincide")
    text = old_launcher.decode("utf-8-sig")
    require(text.count('LAUNCHER_VERSION = "4.4.38-dynamic-port-dependency-diagnostics-1"') == 1, "Cambió versión fuente")
    text = text.replace(
        'LAUNCHER_VERSION = "4.4.38-dynamic-port-dependency-diagnostics-1"',
        'LAUNCHER_VERSION = "4.4.39-dynamic-port-dependency-diagnostics-transport-1"', 1,
    )
    text = text.replace('_RP_DIAGNOSTICS_VERSION = "4.4.38-private-neon-1"', '_RP_DIAGNOSTICS_VERSION = "4.4.39-private-neon-transport-1"', 1)

    start = text.find("def _rp_diag_db_connect():")
    end = text.find("\n\ndef _rp_diag_paths()", start)
    require(start >= 0 and end > start, "No se encontró bloque de conexión diagnóstica")
    text = text[:start] + NEW_CONNECT + text[end:]

    old_msg = "Se enviará automáticamente cuando haya conexión."
    new_msg = "Quedó guardado localmente y se reintentará automáticamente en el próximo arranque."
    require(text.count(old_msg) == 1, "Cambió mensaje de cola 4.4.38")
    text = text.replace(old_msg, new_msg, 1)
    compile(text, "ABRIR_RECEPCION.py", "exec")
    require("application_name=\"recepcion-diagnostics\"" not in text, "Persistió parámetro Neon incompatible")
    require("postgresql+pg8000" in text and "postgresql+psycopg" in text, "Falta compatibilidad de URL")
    require("_rp_v4437_required_files" in text and "_choose_app_port" in text and 'env["RP_PORT"] = str(APP_PORT)' in text, "Se perdió blindaje previo")

    parts = split_four(text)
    for i, data in enumerate(parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    fixed = {}
    for rel in ("app_base_4428.py", "app.py", "static/app.js", "static/index.html"):
        data = git_bytes(rel)
        require(sha(data) == EXPECTED[rel], f"Bytes funcionales cambiaron: {rel}")
        target = OUT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        fixed[rel] = data

    paths = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    inner = {
        "product": "recepcion-pacientes", "version": VERSION,
        "app_version": APP_VERSION, "runtime_version": APP_VERSION,
        "launcher_version": "4.4.39-dynamic-port-dependency-diagnostics-transport-1",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"], "copy": paths,
    }
    inner_bytes = dump(inner)
    (OUT / "update_manifest.json").write_bytes(inner_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_39_diag_transport/"
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
        "message":"v4.4.39: corrige el transporte del diagnóstico automático sin cambiar la app funcional. El launcher acepta las mismas variantes de URL PostgreSQL que Recepción, elimina parámetros de arranque extra que Neon puede rechazar y usa timeout/SSL conservadores. Los INC pendientes de v4.4.38 permanecen en data y se reintentan al siguiente arranque. El mensaje de cola ya no culpa necesariamente a Internet. Conserva puertos dinámicos, RP_PORT, guardia de dependencias, sanitización y paquete acumulativo. No modifica .env, data, pacientes, citas, facturas ni bases locales.",
        "files": files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    require([x["path"] for x in files] == paths, "Release dejó de ser acumulativo")
    print("BUILD_V4439_OK")
    print("LAUNCHER_SHA", sha(launcher))
    print("APP_SHA", sha(fixed["app.py"]))


if __name__ == "__main__":
    build()
