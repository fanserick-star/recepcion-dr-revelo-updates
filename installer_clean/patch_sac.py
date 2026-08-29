from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILDROOT = ROOT / "buildroot"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def patch_app() -> None:
    path = BUILDROOT / "app.py"
    text = path.read_text(encoding="utf-8-sig")

    text = replace_once(
        text,
        "from urllib.parse import urlparse\n",
        "from urllib.parse import urlparse, urlunparse, unquote\nimport ssl\n",
        "imports urllib/ssl",
    )
    text = replace_once(
        text,
        "import psycopg\n",
        "import pg8000.dbapi as pg8000_dbapi\n",
        "driver PostgreSQL",
    )

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
        '    """Convierte la URL de Neon al driver puro pg8000."""\n'
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

    if "import psycopg" in text:
        raise SystemExit("Quedó import psycopg en app.py")
    if "postgresql+pg8000" not in text or "pg8000_dbapi.connect" not in text:
        raise SystemExit("No quedó aplicado pg8000 en app.py")
    compile(text, "app.py", "exec")
    path.write_text(text, encoding="utf-8")


def patch_launcher() -> None:
    path = BUILDROOT / "ABRIR_RECEPCION.py"
    text = path.read_text(encoding="utf-8-sig")
    old = (
        '    env = os.environ.copy()\n'
        '    env["RP_DESKTOP_LAUNCH"] = "1"\n'
    )
    new = (
        '    env = os.environ.copy()\n'
        '    env["RP_DESKTOP_LAUNCH"] = "1"\n'
        '    env["DISABLE_SQLALCHEMY_CEXT_RUNTIME"] = "1"\n'
    )
    text = replace_once(text, old, new, "launcher SQLAlchemy puro")
    compile(text, "ABRIR_RECEPCION.py", "exec")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_launcher()
    print("SMART_APP_CONTROL_PATCH_OK")


if __name__ == "__main__":
    main()
