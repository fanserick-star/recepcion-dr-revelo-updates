from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.7"
SOURCE_VERSION = "4.3.64"
SOURCE_SHA256 = "33ba932ef73ae28722c5f8f1a75d439a82cfb4a67adb78d837430522b786f9a8"
OUT = ROOT / "updates" / "v4_4_7_recovery"
PART_SIZE = 70000


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def stable_app() -> str:
    src = ROOT / "updates" / "v464"
    parts = sorted(src.glob("app.part*"), key=lambda p: int(p.name.split("part")[-1]))
    if len(parts) != 7:
        raise SystemExit(f"v4.3.64 incompleta: {len(parts)} partes")
    raw = b"".join(p.read_bytes() for p in parts)
    got = sha256_bytes(raw)
    if got != SOURCE_SHA256:
        raise SystemExit(f"La fuente estable cambió: {got}")
    return raw.decode("utf-8-sig")


def patch_runtime(text: str) -> str:
    text = replace_once(text, 'APP_VERSION = "4.3.64"', 'APP_VERSION = "4.4.7"', "APP_VERSION")
    # Marcadores visuales internos de la estable: solo se cambia el cache-bust de versión.
    text = text.replace("4.3.64", "4.4.7")

    text = replace_once(
        text,
        "from urllib.parse import urlparse\n",
        "from urllib.parse import urlparse, urlunparse, unquote\nimport ssl\n",
        "urllib/ssl",
    )
    text = replace_once(text, "import psycopg\n", "import pg8000.dbapi as pg8000_dbapi\n", "driver PostgreSQL")

    old_normalize = (
        'def normalize_cloud_url(url: str) -> str:\n'
        '    if url.startswith("postgres://"):\n'
        '        return url.replace("postgres://", "postgresql+psycopg://", 1)\n'
        '    if url.startswith("postgresql://"):\n'
        '        return url.replace("postgresql://", "postgresql+psycopg://", 1)\n'
        '    return url\n'
    )
    new_normalize = (
        'def normalize_cloud_url(url: str) -> str:\n'
        '    """Convierte la URL de Neon al driver puro pg8000 incluido en el runtime."""\n'
        '    if not url:\n'
        '        return url\n'
        '    parsed = urlparse(url)\n'
        '    scheme = parsed.scheme.lower()\n'
        '    if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+pg8000"}:\n'
        '        parsed = parsed._replace(scheme="postgresql+pg8000", query="")\n'
        '        return urlunparse(parsed)\n'
        '    return url\n'
    )
    text = replace_once(text, old_normalize, new_normalize, "normalize_cloud_url")
    text = replace_once(
        text,
        'cloud_connect_args = {"connect_timeout": 12}\n',
        'cloud_connect_args = {"timeout": 12, "ssl_context": ssl.create_default_context()}\n',
        "connect_args Neon",
    )

    old_raw = (
        'def _raw_psycopg_url() -> str:\n'
        '    """Devuelve la URL sin el prefijo de driver de SQLAlchemy."""\n'
        '    url = CONFIGURED_DB_URL\n'
        '    if url.startswith("postgresql+psycopg://"):\n'
        '        return url.replace("postgresql+psycopg://", "postgresql://", 1)\n'
        '    return url\n'
    )
    new_raw = (
        'def _raw_psycopg_url() -> str:\n'
        '    """Devuelve la URL PostgreSQL limpia para la sonda directa con pg8000."""\n'
        '    url = CONFIGURED_DB_URL\n'
        '    for prefix in ("postgresql+psycopg://", "postgresql+pg8000://", "postgres://"):\n'
        '        if url.startswith(prefix):\n'
        '            url = "postgresql://" + url[len(prefix):]\n'
        '            break\n'
        '    parsed = urlparse(url)\n'
        '    if parsed.scheme.lower() == "postgresql":\n'
        '        parsed = parsed._replace(query="")\n'
        '        return urlunparse(parsed)\n'
        '    return url\n'
    )
    text = replace_once(text, old_raw, new_raw, "URL directa Neon")

    old_probe = (
        '    # Conexión nueva e independiente del pool. SELECT 1 no modifica ningún dato.\n'
        '    with psycopg.connect(raw_url, connect_timeout=12, autocommit=True) as conn:\n'
        '        with conn.cursor() as cur:\n'
        '            cur.execute("SELECT 1")\n'
        '            row = cur.fetchone()\n'
        '            if not row or int(row[0]) != 1:\n'
        '                raise RuntimeError("Neon no respondió correctamente a la prueba")\n'
    )
    new_probe = (
        '    # Conexión nueva e independiente del pool. SELECT 1 no modifica ningún dato.\n'
        '    parsed = urlparse(raw_url)\n'
        '    database = unquote((parsed.path or "").lstrip("/"))\n'
        '    if not parsed.hostname or not parsed.username or not database:\n'
        '        raise RuntimeError("La URL de Neon está incompleta")\n'
        '    conn = pg8000_dbapi.connect(\n'
        '        user=unquote(parsed.username),\n'
        '        password=unquote(parsed.password or ""),\n'
        '        host=parsed.hostname,\n'
        '        port=parsed.port or 5432,\n'
        '        database=database,\n'
        '        timeout=12,\n'
        '        ssl_context=ssl.create_default_context(),\n'
        '    )\n'
        '    try:\n'
        '        conn.autocommit = True\n'
        '        cur = conn.cursor()\n'
        '        try:\n'
        '            cur.execute("SELECT 1")\n'
        '            row = cur.fetchone()\n'
        '        finally:\n'
        '            cur.close()\n'
        '    finally:\n'
        '        conn.close()\n'
        '    if not row or int(row[0]) != 1:\n'
        '        raise RuntimeError("Neon no respondió correctamente a la prueba")\n'
    )
    text = replace_once(text, old_probe, new_probe, "sonda directa Neon")

    if "import psycopg" in text or "psycopg.connect" in text:
        raise SystemExit("Quedó una dependencia psycopg activa")
    if "pg8000_dbapi.connect" not in text or "postgresql+pg8000" not in text:
        raise SystemExit("No quedó aplicado pg8000")
    compile(text, "app.py", "exec")
    return text


def write_parts(raw: bytes) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("app.part*"):
        old.unlink()
    out = []
    for n, start in enumerate(range(0, len(raw), PART_SIZE), 1):
        p = OUT / f"app.part{n}"
        p.write_bytes(raw[start:start + PART_SIZE])
        out.append(p)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "static").mkdir(parents=True, exist_ok=True)

    app_text = patch_runtime(stable_app())
    app_raw = app_text.encode("utf-8")
    parts = write_parts(app_raw)

    # Mantiene los recursos visuales que ya fueron verificados por la recuperación 4.4.6.
    for rel in ("static/index.html", "static/app.js", "static/app_base.js"):
        src = ROOT / "updates" / "v4_4_6_recovery" / rel
        dst = OUT / rel
        if not src.is_file():
            raise SystemExit(f"Falta recurso recuperado: {rel}")
        dst.write_bytes(src.read_bytes())

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.100-standalone-7",
        "updater_version": "integrado-en-launcher",
        "copy": [
            "ABRIR_RECEPCION.py",
            "app.py",
            "static/index.html",
            "static/app.js",
            "static/app_base.js",
            "update_manifest.json",
        ],
    }
    manifest_path = OUT / "update_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    current = json.loads((ROOT / "latest-v3.json").read_text(encoding="utf-8"))
    launcher = next((x for x in current.get("files", []) if x.get("path") == "ABRIR_RECEPCION.py"), None)
    if not launcher:
        raise SystemExit("No se encontró launcher acumulativo")

    def entry(rel: str) -> dict:
        p = OUT / rel
        return {
            "path": rel,
            "url": f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_7_recovery/{rel}",
            "sha256": sha256(p),
            "encoding": "utf-8",
        }

    latest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.7 recuperación segura: restaura la base estable con pg8000, compatible con el runtime instalado, y añade validación de dependencias antes de publicar.",
        "files": [
            launcher,
            {
                "path": "app.py",
                "parts": [f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_7_recovery/{p.name}" for p in parts],
                "sha256": sha256_bytes(app_raw),
                "encoding": "utf-8",
            },
            entry("static/index.html"),
            entry("static/app.js"),
            entry("static/app_base.js"),
            entry("update_manifest.json"),
        ],
    }
    payload = json.dumps(latest, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "latest-v3.json").write_text(payload, encoding="utf-8")
    (ROOT / "latest.json").write_text(payload, encoding="utf-8")

    meta = {
        "version": VERSION,
        "source_version": SOURCE_VERSION,
        "source_sha256": SOURCE_SHA256,
        "app_sha256": sha256_bytes(app_raw),
        "parts_count": len(parts),
        "driver": "pg8000",
    }
    (OUT / "recovery_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("V447_BUILT", json.dumps(meta, sort_keys=True))


if __name__ == "__main__":
    main()
