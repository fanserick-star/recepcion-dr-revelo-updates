from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.9"
SRC = ROOT / "updates" / "v443"
OUT = ROOT / "candidates" / "v4_4_9_clean_444"

# app.py sí conservó una huella SHA-256 válida en el canal histórico.
EXPECTED_APP_SHA = "97ea664ad7bebb8927eea4252e59e1bbb9223f83088d58340a1f701d50f68620"
# Para los dos archivos visuales usamos la identidad del blob Git histórico,
# porque los SHA-256 escritos en el manifiesto 4.4.4 fueron calculados antes de
# una normalización de saltos de línea y no representan los bytes publicados.
EXPECTED_INDEX_BLOB = "adc8fb4bf8c41ddddbb42a9950c18043882af27f"
EXPECTED_BASE_JS_BLOB = "7aa78b107556858d9e0d319c7554c6eae57eeca3"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def exact_blob(path: Path, expected_blob: str, label: str) -> bytes:
    raw = path.read_bytes()
    got = git_blob_sha(raw)
    if got != expected_blob:
        raise SystemExit(f"{label} cambió: blob {got}; esperado {expected_blob}")
    return raw


def source_app() -> str:
    parts = sorted(SRC.glob("app.part*"), key=lambda p: int(p.name.split("part")[-1]))
    if len(parts) != 7:
        raise SystemExit(f"Fuente v4.4.3 incompleta: {len(parts)} partes")
    raw = b"".join(p.read_bytes() for p in parts)
    got = sha256(raw)
    if got != EXPECTED_APP_SHA:
        raise SystemExit(f"app.py fuente no es el publicado en v4.4.4: {got}")
    return raw.decode("utf-8-sig")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def patch_app(text: str) -> str:
    # La 4.4.4 real usaba exactamente el backend 4.4.3. Solo cambiamos versión
    # y eliminamos la dependencia de respaldo psycopg que no existe en el runtime.
    text = replace_once(text, 'APP_VERSION = "4.4.3"', 'APP_VERSION = "4.4.9"', "APP_VERSION")

    old_driver = '''try:\n    import pg8000.dbapi as pg8000_dbapi\n    _POSTGRES_DRIVER = "pg8000"\nexcept Exception:\n    pg8000_dbapi = None\n    import psycopg\n    _POSTGRES_DRIVER = "psycopg"\n'''
    new_driver = '''import pg8000.dbapi as pg8000_dbapi\n_POSTGRES_DRIVER = "pg8000"\n'''
    text = replace_once(text, old_driver, new_driver, "driver PostgreSQL")

    # La sonda pg8000 ya estaba en la 4.4.3. Quitamos únicamente el fallback
    # de psycopg; no alteramos su lógica de conexión a Neon.
    old_probe_fallback = '''    else:\n        with psycopg.connect(raw_url, connect_timeout=12, autocommit=True) as conn:\n            with conn.cursor() as cur:\n                cur.execute("SELECT 1")\n                row = cur.fetchone()\n'''
    text = replace_once(text, old_probe_fallback, "", "fallback psycopg de sonda Neon")

    if "import psycopg" in text or "psycopg.connect" in text:
        raise SystemExit("Quedó una dependencia activa de psycopg")
    if 'LOCAL_HTTP_PORT = int((os.getenv("RP_PORT") or "8000").strip())' not in text:
        raise SystemExit("Se perdió la lectura de RP_PORT de la 4.4.3")
    if 'port=LOCAL_HTTP_PORT' not in text:
        raise SystemExit("El backend ya no usa el puerto elegido por el launcher")

    required = [
        'WHATSAPP_CLOUD_MODE', 'CONFIRMAFY_ATTENDED_ORIGIN', 'BILLING_QUEUE_START_DATE',
        '/api/ops/trash', '/api/ops/activity', 'V460_OVERLAY_JS', 'AZUR_API_KEY',
    ]
    missing = [x for x in required if x not in text]
    if missing:
        raise SystemExit("Regresión funcional en backend: faltan " + ", ".join(missing))

    compile(text, "app.py", "exec")
    return text


FOLDED_444_SEARCH = r'''

/* v4.4.9 — integra directamente el hotfix v4.4.4 sobre la base real v4.4.3.
   Ya NO carga app_base.js ni crea un segundo <script>. */
;(() => {
  'use strict';

  function normalizeGlobalPatientSearch() {
    const current = document.querySelector('#globalSearch');
    if (!current || current.dataset.v449SearchNormalized === '1') return;

    const input = current.cloneNode(true);
    const value = String(current.value || '');
    input.removeAttribute('oninput');
    input.removeAttribute('onfocus');
    input.removeAttribute('pattern');
    input.removeAttribute('maxlength');
    input.removeAttribute('inputmode');
    input.type = 'search';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = 'Buscar paciente por nombre, cédula, celular o correo…';
    input.value = value;
    input.dataset.v449SearchNormalized = '1';
    current.replaceWith(input);

    const wrap = input.closest('.global-search-wrap') || input.parentElement;
    if (wrap) {
      wrap.querySelectorAll('label, small, span, [data-search-label]').forEach(el => {
        const t = String(el.textContent || '').trim().toUpperCase();
        if (t === 'CÉDULA' || t === 'CEDULA') el.textContent = 'PACIENTE';
      });
    }

    const runSearch = (force = false) => {
      try {
        if (typeof upperSearchInput === 'function') upperSearchInput(input);
        else {
          const start = input.selectionStart, end = input.selectionEnd;
          input.value = String(input.value || '').toUpperCase();
          try { if (start != null) input.setSelectionRange(start, end); } catch {}
        }
        if (typeof globalSearchPatients === 'function') globalSearchPatients(force);
      } catch (err) {
        console.error('Búsqueda paciente v4.4.9:', err);
      }
    };

    input.addEventListener('input', () => runSearch(false));
    input.addEventListener('focus', () => runSearch(true));
  }

  function bootSearch444() {
    normalizeGlobalPatientSearch();
    document.addEventListener('click', () => {
      const input = document.querySelector('#globalSearch');
      if (input) input.placeholder = 'Buscar paciente por nombre, cédula, celular o correo…';
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootSearch444, { once: true });
  } else {
    bootSearch444();
  }
})();
'''


def build_frontend() -> tuple[str, str, dict]:
    index_raw = exact_blob(SRC / "static" / "index.html", EXPECTED_INDEX_BLOB, "index 4.4.3")
    base_js_raw = exact_blob(SRC / "static" / "app.js", EXPECTED_BASE_JS_BLOB, "app.js 4.4.3")

    index = index_raw.decode("utf-8-sig")
    index = replace_once(index, '/static/app.js?v=4.3.34', '/static/app.js?v=4.4.9', "cache-bust app.js")

    base_js = base_js_raw.decode("utf-8-sig")
    final_js = base_js.rstrip() + FOLDED_444_SEARCH + "\n"

    if "app_base.js" in final_js or "loadStableBase" in final_js:
        raise SystemExit("El frontend final todavía contiene el wrapper frágil de 4.4.4")
    for marker in ("globalSearchPatients", "Buscar paciente por nombre, cédula, celular o correo", "v449SearchNormalized"):
        if marker not in final_js:
            raise SystemExit(f"Falta marcador del buscador: {marker}")
    for marker in ('id="agenda"', 'id="facturacion"', 'id="reportes"', 'id="pacientes"', 'data-config-tab="agenda"'):
        if marker not in index:
            raise SystemExit(f"Se perdió sección visual: {marker}")

    source_meta = {
        "source_index_blob_sha1": EXPECTED_INDEX_BLOB,
        "source_index_sha256_actual": sha256(index_raw),
        "source_base_js_blob_sha1": EXPECTED_BASE_JS_BLOB,
        "source_base_js_sha256_actual": sha256(base_js_raw),
    }
    return index, final_js, source_meta


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "static").mkdir(parents=True, exist_ok=True)

    app = patch_app(source_app())
    index, js, source_meta = build_frontend()

    (OUT / "app.py").write_text(app, encoding="utf-8", newline="")
    (OUT / "static" / "index.html").write_text(index, encoding="utf-8", newline="")
    (OUT / "static" / "app.js").write_text(js, encoding="utf-8", newline="")

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.100-standalone-7",
        "updater_version": "integrado-en-launcher",
        "copy": ["app.py", "static/index.html", "static/app.js", "update_manifest.json"],
    }
    (OUT / "update_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
    )

    meta = {
        "version": VERSION,
        "source_package": "4.4.4",
        "source_app_version": "4.4.3",
        "source_app_sha256": EXPECTED_APP_SHA,
        **source_meta,
        "candidate_app_sha256": sha256((OUT / "app.py").read_bytes()),
        "candidate_index_sha256": sha256((OUT / "static" / "index.html").read_bytes()),
        "candidate_js_sha256": sha256((OUT / "static" / "app.js").read_bytes()),
        "frontend_layers": 1,
        "app_base_js": False,
        "published": False,
    }
    (OUT / "candidate_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline=""
    )
    print("V449_CANDIDATE_BUILT", json.dumps(meta, sort_keys=True))


if __name__ == "__main__":
    main()
