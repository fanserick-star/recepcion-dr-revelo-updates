from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import html
import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from cloud_sync import build_sync_service, ensure_local_sync_schema, get_sync_status
import documentos_clinicos
import cloud_presence_patch
cloud_presence_patch.install()

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "historia_clinica.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DOCTOR_NAME = "Dr. Armando Revelo"
VERSION_PATH = ROOT / "historia-version.json"
try:
    APP_VERSION = str(json.loads(VERSION_PATH.read_text(encoding="utf-8-sig"))["version"]).strip()
except Exception as exc:
    raise RuntimeError("historia-version.json no contiene una versión válida") from exc
os.environ["HISTORIA_APP_VERSION"] = APP_VERSION
_CANONICAL_VERSION = APP_VERSION

app = FastAPI(title="Historia Clínica", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")




def _native_launcher_path() -> Path:
    return ROOT / "HistoriaClinicaLauncher.exe"


def _ensure_native_launcher() -> Path:
    """Devuelve el launcher nativo oficial instalado por Launcher v1."""
    target = _native_launcher_path()
    if not target.is_file():
        raise RuntimeError(
            "El launcher moderno de Historia Clínica todavía no está instalado."
        )
    return target


def _repair_shortcut_native() -> dict:
    if os.name != "nt":
        return {"ok": False, "message": "Esta herramienta solo se usa en Windows."}
    exe = _ensure_native_launcher()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [str(exe), "--repair-shortcut"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
        check=False,
        creationflags=flags,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Windows devolvió código {proc.returncode} al reparar el acceso directo."
        )
    return {"ok": True, "message": "Acceso directo e icono reparados correctamente."}

def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def new_id():
    return str(uuid.uuid4())


def e(value):
    return html.escape("" if value is None else str(value))


def audit(conn, action, entity_type, entity_id=None, details=None, actor=DOCTOR_NAME):
    conn.execute(
        "INSERT INTO audit_log(occurred_at,actor,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)",
        (now_iso(), actor, action, entity_type, entity_id, json.dumps(details or {}, ensure_ascii=False)),
    )


def ensure_column(conn, table, col, ddl):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def ensure_schema():
    with db() as conn:
        ensure_column(conn, "encounters", "note_status", "note_status TEXT NOT NULL DEFAULT 'signed'")
        ensure_column(conn, "encounters", "signed_at", "signed_at TEXT")
        ensure_column(conn, "encounters", "signed_by", "signed_by TEXT")
        ensure_column(conn, "encounters", "copied_from_encounter_id", "copied_from_encounter_id TEXT")
        ensure_column(conn, "encounters", "queue_id", "queue_id TEXT")
        ensure_column(conn, "encounters", "created_by", "created_by TEXT")
        # Compatibilidad total entre bases importadas y bases nuevas creadas desde Neon.
        # Estas columnas existían en Consulta Práctica / migraciones antiguas y algunas
        # rutas legacy todavía las consultan. Se agregan de forma aditiva, sin tocar datos.
        ensure_column(conn, "encounters", "legacy_images", "legacy_images BLOB")
        ensure_column(conn, "encounters", "legacy_history_t", "legacy_history_t TEXT")
        ensure_column(conn, "encounters", "first_time", "first_time INTEGER DEFAULT 0")
        ensure_column(conn, "encounters", "legacy_no_depurable", "legacy_no_depurable INTEGER DEFAULT 0")
        ensure_column(conn, "encounters", "responsible", "responsible TEXT")
        ensure_column(conn, "waiting_queue", "patient_status", "patient_status TEXT")
        ensure_column(conn, "waiting_queue", "reception_turn", "reception_turn INTEGER")
        # v1.3.63: bases creadas/restauradas desde el esquema mínimo podían no
        # tener estas columnas aunque las rutas de consulta las usan.
        ensure_column(conn, "waiting_queue", "started_at", "started_at TEXT")
        ensure_column(conn, "waiting_queue", "completed_at", "completed_at TEXT")
        ensure_column(conn, "patients", "merged_into_patient_id", "merged_into_patient_id TEXT")
        ensure_column(conn, "patients", "merged_at", "merged_at TEXT")
        conn.execute("UPDATE encounters SET note_status='legacy' WHERE source='legacy_consulta_practica' AND note_status!='legacy'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS encounter_revisions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
              revision_no INTEGER NOT NULL,
              saved_at TEXT NOT NULL,
              actor TEXT,
              clinical_note TEXT,
              diagnosis TEXT,
              treatment TEXT,
              reason TEXT,
              UNIQUE(encounter_id, revision_no)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS encounter_addenda (
              id TEXT PRIMARY KEY,
              encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
              text TEXT NOT NULL,
              created_at TEXT NOT NULL,
              actor TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_addenda_encounter ON encounter_addenda(encounter_id, created_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS macros (
              id TEXT PRIMARY KEY,
              label TEXT NOT NULL UNIQUE,
              text TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_encounters_status ON encounters(note_status, updated_at DESC)")
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('app_version',?)", (APP_VERSION,))
        conn.commit()


def cleanup_active_queue_duplicates():
    """
    Evita dos turnos activos del mismo paciente a la vez.
    Conserva primero una consulta ya iniciada; si ambos están en espera,
    conserva el más reciente. Nunca elimina la ficha ni sus historias.
    """
    stamp = now_iso()
    removed = []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id,reception_patient_id,clinical_patient_id,status,
                   queued_at,updated_at,display_name
            FROM waiting_queue
            WHERE status IN ('waiting','in_consultation')
            ORDER BY
              CASE WHEN status='in_consultation' THEN 0 ELSE 1 END,
              COALESCE(updated_at,queued_at,'') DESC,
              COALESCE(queued_at,'') DESC
            """
        ).fetchall()

        seen_reception = set()
        seen_clinical = set()

        for row in rows:
            reception_id = str(row["reception_patient_id"] or "").strip()
            clinical_id = str(row["clinical_patient_id"] or "").strip()

            duplicate = (
                (reception_id and reception_id in seen_reception)
                or (clinical_id and clinical_id in seen_clinical)
            )

            if duplicate:
                conn.execute(
                    """UPDATE waiting_queue
                       SET status='cancelled',updated_at=?
                       WHERE id=? AND status IN ('waiting','in_consultation')""",
                    (stamp, row["id"]),
                )
                removed.append(str(row["id"]))
                continue

            if reception_id:
                seen_reception.add(reception_id)
            if clinical_id:
                seen_clinical.add(clinical_id)

        if removed:
            audit(
                conn,
                "cleanup",
                "waiting_queue",
                "duplicate-active",
                {"cancelled_queue_ids": removed, "count": len(removed)},
            )
            conn.commit()

    return removed


def cleanup_cancelled_queue_drafts():
    """
    v1.3.19: una cancelación en Recepción NUNCA puede borrar texto clínico.

    Antes se eliminaba el encounter draft si su turno quedaba cancelado. Eso
    podía hacer desaparecer una consulta autoguardada después de reiniciar o
    después de que Recepción limpiara/duplicara un turno. Ahora el borrador se
    conserva y solamente se desvincula de la cola cancelada.
    """
    stamp = now_iso()
    preserved = []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT e.id,e.queue_id,e.patient_id,e.clinical_note,e.diagnosis,e.treatment
            FROM encounters e
            JOIN waiting_queue q ON q.id=e.queue_id
            WHERE e.note_status='draft' AND q.status='cancelled'
            """
        ).fetchall()
        for row in rows:
            audit(
                conn,
                "preserve_cancelled_draft",
                "encounter",
                row["id"],
                {
                    "queue_id": row["queue_id"],
                    "patient_id": row["patient_id"],
                    "has_text": bool(
                        str(row["clinical_note"] or "").strip()
                        or str(row["diagnosis"] or "").strip()
                        or str(row["treatment"] or "").strip()
                    ),
                },
            )
            conn.execute(
                "UPDATE encounters SET queue_id=NULL,updated_at=? "
                "WHERE id=? AND note_status='draft'",
                (stamp, row["id"]),
            )
            preserved.append(str(row["id"]))
        if preserved:
            conn.commit()
    return preserved



def ensure_base_schema():
    """Crea únicamente el esquema base cuando Historia se instala en una PC nueva.

    En bases existentes usa CREATE TABLE IF NOT EXISTS y no borra ni reemplaza datos.
    """
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta(
          key TEXT PRIMARY KEY,
          value TEXT
        );
        CREATE TABLE IF NOT EXISTS patients(
          id TEXT PRIMARY KEY,
          legacy_patient_id INTEGER,
          name TEXT,
          name_search TEXT,
          birth_date TEXT,
          sex TEXT,
          civil_status TEXT,
          address TEXT,
          phone TEXT,
          next_appointment_legacy TEXT,
          national_id TEXT,
          national_id_search TEXT,
          legacy_notes TEXT,
          legacy_photo BLOB,
          legacy_alert TEXT,
          email TEXT,
          insurer TEXT,
          legacy_no_depurable INTEGER DEFAULT 0,
          source TEXT,
          source_record_hash TEXT,
          created_at TEXT,
          updated_at TEXT,
          deleted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS encounters(
          id TEXT PRIMARY KEY,
          patient_id TEXT,
          legacy_history_id INTEGER,
          legacy_patient_id INTEGER,
          encounter_date TEXT,
          encounter_time TEXT,
          clinical_note TEXT,
          diagnosis TEXT,
          treatment TEXT,
          source TEXT,
          source_record_hash TEXT,
          is_legacy_locked INTEGER DEFAULT 0,
          created_at TEXT,
          updated_at TEXT,
          deleted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS patient_links(
          reception_patient_id TEXT PRIMARY KEY,
          clinical_patient_id TEXT,
          matched_by TEXT,
          verified INTEGER,
          verified_at TEXT,
          created_at TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS waiting_queue(
          id TEXT PRIMARY KEY,
          reception_event_id TEXT UNIQUE,
          reception_patient_id TEXT,
          clinical_patient_id TEXT,
          display_name TEXT,
          identification TEXT,
          attention_type TEXT,
          queued_at TEXT,
          status TEXT,
          source TEXT,
          created_at TEXT,
          updated_at TEXT,
          deleted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          occurred_at TEXT,
          actor TEXT,
          action TEXT,
          entity_type TEXT,
          entity_id TEXT,
          details_json TEXT
        );
        """)
        conn.commit()


def _merge_norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def _patient_identity_compatible(canonical, duplicate) -> bool:
    """Sólo fusiona automáticamente cuando hay una señal fuerte coincidente."""
    cid = _merge_norm(canonical["national_id_search"] or "")
    did = _merge_norm(duplicate["national_id_search"] or "")
    if cid and did and cid != did:
        return False

    cbirth = str(canonical["birth_date"] or "").strip()
    dbirth = str(duplicate["birth_date"] or "").strip()
    if cbirth and dbirth and cbirth != dbirth:
        return False

    cphone = re.sub(r"\D", "", str(canonical["phone"] or ""))
    dphone = re.sub(r"\D", "", str(duplicate["phone"] or ""))

    return bool(
        (cid and did and cid == did)
        or (cbirth and dbirth and cbirth == dbirth)
        or (cphone and dphone and cphone == dphone)
    )


def merge_safe_duplicate_patients() -> dict:
    """
    v1.3.25 — unificación conservadora de duplicados creados por el flujo Nuevo.

    Reglas:
    - mismo nombre normalizado;
    - exactamente UNA ficha tiene historias/encounters;
    - las otras NO tienen encounters;
    - cada duplicado vacío comparte cédula, nacimiento o teléfono con la ficha
      que tiene historia;
    - nunca borra físicamente la ficha: la marca como fusionada y la oculta.
    """
    stamp = now_iso()
    merged_groups = 0
    merged_records = 0
    skipped_groups = 0

    with db() as conn:
        groups = conn.execute(
            """
            SELECT name_search,COUNT(*) AS n
            FROM patients
            WHERE COALESCE(merged_into_patient_id,'')=''
              AND COALESCE(name_search,'')<>''
            GROUP BY name_search
            HAVING COUNT(*)>1
            """
        ).fetchall()

        for group in groups:
            rows = conn.execute(
                """
                SELECT p.*,
                  (SELECT COUNT(*) FROM encounters e WHERE e.patient_id=p.id) AS encounter_count,
                  (SELECT COUNT(*) FROM prescriptions r WHERE r.patient_id=p.id AND COALESCE(r.deleted_at,'')='') AS rx_count,
                  (SELECT COUNT(*) FROM certificates c WHERE c.patient_id=p.id AND COALESCE(c.deleted_at,'')='') AS cert_count
                FROM patients p
                WHERE p.name_search=?
                  AND COALESCE(p.merged_into_patient_id,'')=''
                ORDER BY p.updated_at DESC,p.id
                """,
                (group["name_search"],),
            ).fetchall()

            with_history = [r for r in rows if int(r["encounter_count"] or 0) > 0]
            if len(with_history) != 1:
                skipped_groups += 1
                continue

            canonical = with_history[0]
            duplicates = [r for r in rows if r["id"] != canonical["id"]]

            # Una ficha "vacía" no debe tener encounter alguno. Recetas o
            # certificados aislados sí se trasladan de forma segura.
            if any(int(r["encounter_count"] or 0) > 0 for r in duplicates):
                skipped_groups += 1
                continue
            if not all(_patient_identity_compatible(canonical, r) for r in duplicates):
                skipped_groups += 1
                continue

            canonical_id = str(canonical["id"])
            fields = [
                "birth_date","sex","civil_status","address","phone",
                "national_id","national_id_search","email","insurer",
                "legacy_notes","legacy_alert","legacy_photo",
            ]
            updates = {}
            for field in fields:
                current = canonical[field]
                if current not in (None, "", b""):
                    continue
                for dup in duplicates:
                    value = dup[field]
                    if value not in (None, "", b""):
                        updates[field] = value
                        break

            if updates:
                set_sql = ",".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE patients SET {set_sql},updated_at=? WHERE id=?",
                    [*updates.values(), stamp, canonical_id],
                )

            for dup in duplicates:
                dup_id = str(dup["id"])
                # Todo vínculo operativo pasa a la ficha con historia.
                conn.execute(
                    "UPDATE patient_links SET clinical_patient_id=?,updated_at=? "
                    "WHERE clinical_patient_id=?",
                    (canonical_id, stamp, dup_id),
                )
                conn.execute(
                    "UPDATE waiting_queue SET clinical_patient_id=?,updated_at=? "
                    "WHERE clinical_patient_id=?",
                    (canonical_id, stamp, dup_id),
                )
                conn.execute(
                    "UPDATE prescriptions SET patient_id=?,updated_at=? WHERE patient_id=?",
                    (canonical_id, stamp, dup_id),
                )
                conn.execute(
                    "UPDATE certificates SET patient_id=?,updated_at=? WHERE patient_id=?",
                    (canonical_id, stamp, dup_id),
                )

                conn.execute(
                    """UPDATE patients
                       SET merged_into_patient_id=?,merged_at=?,updated_at=?
                       WHERE id=?""",
                    (canonical_id, stamp, stamp, dup_id),
                )
                audit(
                    conn,
                    "merge_duplicate_patient",
                    "patient",
                    dup_id,
                    {
                        "canonical_patient_id": canonical_id,
                        "reason": "same_name_plus_identity_empty_duplicate",
                        "canonical_encounters": int(canonical["encounter_count"] or 0),
                    },
                )
                merged_records += 1

            merged_groups += 1

        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('v1325_duplicate_merge_result',?)",
            (json.dumps({
                "merged_groups": merged_groups,
                "merged_records": merged_records,
                "skipped_groups": skipped_groups,
                "at": stamp,
            }, ensure_ascii=False),),
        )
        conn.commit()

    return {
        "merged_groups": merged_groups,
        "merged_records": merged_records,
        "skipped_groups": skipped_groups,
    }


ensure_base_schema()
ensure_schema()
documentos_clinicos.ensure_schema(DB_PATH)
_DUPLICATE_MERGE_RESULT = merge_safe_duplicate_patients()
ensure_local_sync_schema(DB_PATH)
cleanup_active_queue_duplicates()
cleanup_cancelled_queue_drafts()
SYNC_SERVICE = build_sync_service(ROOT, DB_PATH)

import lan_bridge
LAN_SERVICE = lan_bridge.install(app, ROOT, DB_PATH, APP_VERSION, SYNC_SERVICE)


@app.on_event("startup")
def _startup_cloud_sync():
    SYNC_SERVICE.start()
    SYNC_SERVICE.mark_activity()


@app.on_event("shutdown")
def _shutdown_cloud_sync():
    SYNC_SERVICE.stop()


@app.middleware("http")
async def _cloud_activity(request: Request, call_next):
    """
    Sólo la actividad humana/real mantiene despierta la nube.
    Los sondeos automáticos de estado, cola y LAN son locales y NO deben
    impedir que Historia entre en AFK.
    """
    path = request.url.path
    method = request.method.upper()
    if path != "/api/activity":
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            SYNC_SERVICE.mark_activity()
        elif method == "GET" and not (
            path.startswith("/api/")
            or path.startswith("/static/")
            or path == "/favicon.ico"
        ):
            SYNC_SERVICE.mark_activity()
    return await call_next(request)


@app.post("/api/activity")
def api_user_activity():
    SYNC_SERVICE.mark_activity()
    return JSONResponse({"ok": True})




@app.post("/api/system/shortcut")
def api_repair_shortcut():
    try:
        return JSONResponse(_repair_shortcut_native())
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.post("/api/system/open-folder")
def api_open_program_folder():
    if os.name != "nt":
        return JSONResponse({"ok": False, "message": "Disponible solo en Windows."}, status_code=400)
    try:
        os.startfile(str(ROOT))
        return JSONResponse({"ok": True, "message": "Carpeta del programa abierta."})
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.get("/api/version")
def api_version():
    status = get_sync_status(ROOT / "data")
    return JSONResponse({"product": "historia-clinica-dr-revelo", "version": APP_VERSION, "cloud": status.get("state"), "online": bool(status.get("online"))})


@app.get("/api/sync/status")
def api_sync_status():
    return JSONResponse(get_sync_status(ROOT / "data"))


@app.post("/api/sync/now")
def api_sync_now():
    SYNC_SERVICE.mark_activity()
    SYNC_SERVICE.wake()
    return JSONResponse({"ok": True})


# Consulta Práctica guarda muchas notas antiguas como RTF (Rich Text Format).
_RTF_TOKEN_RE = re.compile(
    r"\\([a-zA-Z]+)(-?\d+)? ?"
    r"|\\'([0-9a-fA-F]{2})"
    r"|\\([^a-zA-Z0-9])"
    r"|([{}])"
    r"|([\r\n]+)"
    r"|([^\\{}\r\n]+)",
    re.MULTILINE,
)
_RTF_DESTINATIONS = {
    "fonttbl", "colortbl", "datastore", "themedata", "stylesheet", "info",
    "pict", "object", "header", "headerl", "headerr", "footer", "footerl",
    "footerr", "generator", "filetbl", "listtable", "listoverridetable",
    "rsidtbl", "xmlnstbl", "latentstyles", "colorschememapping",
}
_RTF_SPECIAL = {
    "par": "\n", "line": "\n", "tab": "\t", "emdash": "—", "endash": "–",
    "bullet": "•", "lquote": "‘", "rquote": "’", "ldblquote": "“", "rdblquote": "”",
    "~": "\u00a0", "-": "\u00ad", "_": "\u2011",
}


def rtf_to_text(value):
    if value is None:
        return ""
    text = str(value)
    if not text.lstrip().startswith("{\\rtf"):
        return text
    out, stack = [], []
    ignorable, ucskip, curskip = False, 1, 0
    for m in _RTF_TOKEN_RE.finditer(text):
        word, arg, hexchar, symbol, brace, newline, plain = m.groups()
        if brace:
            if brace == "{":
                stack.append((ignorable, ucskip))
            elif stack:
                ignorable, ucskip = stack.pop()
            curskip = 0
            continue
        if symbol:
            if symbol == "*":
                ignorable = True
            elif not ignorable:
                if symbol in "{}\\": out.append(symbol)
                elif symbol == "~": out.append("\u00a0")
                elif symbol == "_": out.append("\u2011")
            continue
        if word:
            w = word.lower()
            if w in _RTF_DESTINATIONS:
                ignorable = True
                continue
            if ignorable: continue
            if w == "uc" and arg is not None:
                try: ucskip = max(0, int(arg))
                except ValueError: ucskip = 1
                continue
            if w == "u" and arg is not None:
                try:
                    n = int(arg)
                    if n < 0: n += 65536
                    out.append(chr(n)); curskip = ucskip
                except (ValueError, OverflowError):
                    pass
                continue
            special = _RTF_SPECIAL.get(w)
            if special is not None: out.append(special)
            continue
        if hexchar:
            if ignorable: continue
            if curskip:
                curskip -= 1; continue
            try: out.append(bytes([int(hexchar, 16)]).decode("cp1252"))
            except Exception: out.append("?")
            continue
        if newline:
            continue
        if plain and not ignorable:
            if curskip:
                skip = min(curskip, len(plain)); plain = plain[skip:]; curskip -= skip
            if plain: out.append(plain)
    cleaned = "".join(out).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def display_text(value):
    return e(rtf_to_text(value)).replace("\n", "<br>")


# Consulta Práctica permitió acumular años de evoluciones dentro de un solo
# registro. Muchas de esas evoluciones fueron separadas manualmente por el
# doctor escribiendo la fecha en el propio texto. Esta capa detecta esas fechas
# SOLO para presentación; nunca reescribe ni fragmenta el registro original.
_LEGACY_MONTHS = {
    "ENE": 1, "ENERO": 1,
    "FEB": 2, "FEBRERO": 2,
    "MAR": 3, "MARZO": 3,
    "ABR": 4, "ABRIL": 4,
    "MAY": 5, "MAYO": 5,
    "JUN": 6, "JUNIO": 6,
    "JUL": 7, "JULIO": 7,
    "AGO": 8, "AGOSTO": 8,
    "SEP": 9, "SEPT": 9, "SEPTIEMBRE": 9, "SET": 9, "SETIEMBRE": 9,
    "OCT": 10, "OCTUBRE": 10,
    "NOV": 11, "NOVIEMBRE": 11,
    "DIC": 12, "DICIEMBRE": 12,
}
_LEGACY_MONTH_RE = (
    r"(?:ENE(?:RO)?|FEB(?:RERO)?|MAR(?:ZO)?|ABR(?:IL)?|MAY(?:O)?|"
    r"JUN(?:IO)?|JUL(?:IO)?|AGO(?:STO)?|SEP(?:T(?:IEMBRE)?)?|"
    r"SET(?:IEMBRE)?|OCT(?:UBRE)?|N[O0]V(?:IEMBRE)?|DIC(?:IEMBRE)?)"
)
_LEGACY_DATE_RE = re.compile(
    rf"""(?ix)
    (?<!\d)(?:
      (?P<wd>\d{{1,2}})\s*(?:[-/.]\s*|\s+DE\s+|\s+)
      (?P<wm>{_LEGACY_MONTH_RE})
      (?:\s*(?:[-/.]\s*|\s+DE(?:L)?\s+|\s+)(?P<wy>\d{{2,4}}))?
      |
      (?P<nd>\d{{1,2}})\s*[-/.]\s*(?P<nm>\d{{1,2}})\s*[-/.]\s*(?P<ny>\d{{2,4}})
    )(?!\d)
    """
)


def _legacy_month_number(raw):
    if not raw:
        return None
    token = raw.upper().replace("0", "O").strip().rstrip(".")
    return _LEGACY_MONTHS.get(token)


def _legacy_year_number(raw):
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if len(raw) == 2:
        return 2000 + value
    # El programa contiene años digitados como 005, 010 o 026.
    if len(raw) == 3 and raw.startswith("0"):
        return 2000 + int(raw[-2:])
    if len(raw) == 4:
        return value
    return None


def _valid_calendar_date(day, month, year=None):
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return False
    if year is not None:
        if not (1900 <= year <= 2099):
            return False
        try:
            datetime(year, month, day)
        except ValueError:
            return False
    else:
        # Sin año no podemos validar 29/febrero con exactitud; febrero se
        # admite hasta 29 y el resto usa sus límites naturales.
        max_days = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        if day > max_days[month - 1]:
            return False
    return True


def _normalize_legacy_marker(match):
    if match.group("wd"):
        day = int(match.group("wd"))
        month = _legacy_month_number(match.group("wm"))
        year = _legacy_year_number(match.group("wy"))
    else:
        day = int(match.group("nd"))
        month = int(match.group("nm"))
        year = _legacy_year_number(match.group("ny"))
    if not month or not _valid_calendar_date(day, month, year):
        return None
    raw = re.sub(r"\s+", " ", match.group(0).strip())
    normalized = f"{day:02d}/{month:02d}/{year:04d}" if year else None
    return {
        "start": match.start(), "end": match.end(), "raw": raw,
        "day": day, "month": month, "year": year, "normalized": normalized,
    }


def legacy_date_markers(value):
    text = rtf_to_text(value)
    markers = []
    for match in _LEGACY_DATE_RE.finditer(text):
        marker = _normalize_legacy_marker(match)
        if marker:
            markers.append(marker)
    return text, markers


def segment_legacy_history(value, encounter_date=""):
    """Divide visualmente una nota antigua usando las fechas escritas dentro.

    El texto fuente permanece intacto en encounters.clinical_note. El orden es
    exactamente el orden del documento, incluso si una fecha fue digitada con
    un año equivocado o quedó cronológicamente fuera de orden.
    """
    text, markers = legacy_date_markers(value)
    if not markers:
        return []
    segments = []
    prefix = text[:markers[0]["start"]].strip(" \t\r\n-–—")
    if prefix:
        try:
            root_label = datetime.strptime(encounter_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            root_label = encounter_date or "Registro inicial"
        segments.append({
            "label": root_label,
            "raw": "Fecha del registro original",
            "content": prefix,
            "kind": "base",
            "normalized": root_label if encounter_date else None,
        })
    for idx, marker in enumerate(markers):
        next_start = markers[idx + 1]["start"] if idx + 1 < len(markers) else len(text)
        content = text[marker["end"]:next_start].strip(" \t\r\n-–—")
        segments.append({
            "label": marker["normalized"] or marker["raw"].upper(),
            "raw": marker["raw"],
            "content": content,
            "kind": "detected",
            "normalized": marker["normalized"],
        })
    return segments


def render_legacy_segments(value, encounter_date=""):
    """Renderiza el historial antiguo por fechas, mostrando lo más reciente primero.

    La segmentación sigue siendo únicamente visual: el texto fuente no se
    modifica. Fechas con año conocido se ordenan de forma descendente; las
    fechas sin año se conservan al final en su orden original.
    """
    segments = segment_legacy_history(value, encounter_date)
    if not segments:
        return "", 0, 0

    detected = sum(1 for item in segments if item["kind"] == "detected")

    def sort_key(pair):
        idx, item = pair
        label = item.get("normalized")
        if label:
            try:
                dt = datetime.strptime(label, "%d/%m/%Y")
                return (1, dt.toordinal(), -idx)
            except Exception:
                pass
        return (0, 0, -idx)

    ordered = [item for _, item in sorted(enumerate(segments), key=sort_key, reverse=True)]
    cards = []
    for item in ordered:
        # El doctor solo necesita la fecha y el contenido que escribió.
        # No mostramos etiquetas técnicas de detección ni la grafía original.
        content = e(item["content"]).replace("\n", "<br>") if item["content"] else "<em>Sin texto registrado</em>"
        cards.append(f"""
        <section class='legacy-segment compact'>
          <div class='legacy-segment-date'><strong>{e(item['label'])}</strong></div>
          <div class='legacy-segment-body'>{content}</div>
        </section>""")
    return "".join(cards), detected, len(segments)


def clean_title(value, fallback="Consulta"):
    text = rtf_to_text(value).strip()
    if not text:
        return fallback
    first = next((x.strip() for x in text.splitlines() if x.strip()), fallback)
    return first[:110]


def age_from_birth(date_text):
    if not date_text: return ""
    try:
        born = datetime.strptime(date_text, "%Y-%m-%d").date()
        today = datetime.now().date()
        return str(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
    except Exception:
        return ""


def human_dt(text):
    if not text: return ""
    try:
        dt = datetime.fromisoformat(text)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return text


def human_date(text):
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return str(text)


def normalize_search(value):
    """Normaliza búsquedas para permitir nombres en cualquier orden y sin tildes."""
    raw = unicodedata.normalize("NFD", str(value or ""))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.upper()
    raw = re.sub(r"[^A-Z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _birth_from_query(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) != 8:
        return ""
    candidates = []
    if 1900 <= int(digits[:4]) <= 2100:
        candidates.append(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
    candidates.append(f"{digits[4:8]}-{digits[2:4]}-{digits[:2]}")
    for candidate in candidates:
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
        except Exception:
            pass
    return ""


def _name_rank(name_search, query_norm):
    name_norm = normalize_search(name_search)
    if not query_norm:
        return 9999
    if name_norm == query_norm:
        return 0
    if name_norm.startswith(query_norm):
        return 4
    q_tokens = query_norm.split()
    n_tokens = name_norm.split()
    score = 10
    for qt in q_tokens:
        if qt in n_tokens:
            score += 0
        elif any(nt.startswith(qt) for nt in n_tokens):
            score += 2
        elif any(qt in nt for nt in n_tokens):
            score += 4
        else:
            score += 20
    # Favorece coincidencias con menos palabras extra, sin exigir el orden escrito.
    score += max(0, len(n_tokens) - len(q_tokens))
    return score


def search_patients(conn, raw_query, limit=100):
    query_norm = normalize_search(raw_query)
    digits = re.sub(r"\D", "", raw_query or "")
    birth_iso = _birth_from_query(raw_query)
    tokens = [t for t in query_norm.split() if t]
    if not tokens and not digits and not birth_iso:
        return []

    name_where = " AND ".join("p.name_search LIKE ?" for _ in tokens) if tokens else "0"
    params = [f"%{t}%" for t in tokens]
    extra = []
    if digits:
        extra.extend([
            "p.national_id_search LIKE ?",
            "REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(p.phone,''),' ',''),'-',''),'(',''),')','') LIKE ?",
        ])
        params.extend([f"%{digits}%", f"%{digits}%"])
    if birth_iso:
        extra.append("p.birth_date = ?")
        params.append(birth_iso)

    clauses = []
    if tokens:
        clauses.append(f"({name_where})")
    clauses.extend(extra)
    where = " OR ".join(clauses) or "0"
    rows = conn.execute(f"""
        SELECT p.*,
          (SELECT COUNT(*) FROM encounters e WHERE e.patient_id=p.id AND e.note_status!='draft') AS n_hist
        FROM patients p
        WHERE COALESCE(p.merged_into_patient_id,'')=''
          AND ({where})
        LIMIT 350
    """, params).fetchall()

    def score(r):
        s = 500
        if tokens:
            s = _name_rank(r["name_search"] or r["name"], query_norm)
        rid = re.sub(r"\D", "", r["national_id_search"] or "")
        rphone = re.sub(r"\D", "", r["phone"] or "")
        if digits and rid:
            if rid == digits: s = min(s, 0)
            elif rid.startswith(digits): s = min(s, 2)
            elif digits in rid: s = min(s, 5)
        if digits and rphone:
            if rphone == digits: s = min(s, 1)
            elif rphone.startswith(digits): s = min(s, 3)
            elif digits in rphone: s = min(s, 6)
        if birth_iso and r["birth_date"] == birth_iso:
            s = min(s, 1)
        # Si existen fichas duplicadas con el mismo nombre, muestra primero la
        # que realmente tiene historia/identificación/datos útiles. No fusiona.
        return (
            s,
            -int(r["n_hist"] or 0),
            -int(bool(str(r["national_id_search"] or "").strip())),
            -int(bool(str(r["phone"] or "").strip())),
            normalize_search(r["name"]),
        )

    return sorted(rows, key=score)[:limit]


def clean_legacy_id(value):
    raw = str(value or "").strip()
    if not raw or re.fullmatch(r"[Xx\s.-]+", raw):
        return ""
    return raw


def sex_label(value):
    v = str(value or "").strip().upper()
    if v == "M": return "Masculino"
    if v == "F": return "Femenino"
    return value or ""


def base(title: str, body: str, active: str = "inicio", extra_head: str = "", extra_script: str = "") -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Historia Clínica</title><link rel="icon" type="image/png" href="/static/doctor_logo.png"><link rel="stylesheet" href="/static/style.css?v={e(APP_VERSION)}">{extra_head}</head>
<body class="cp-remaster-app">
<header class="topbar">
  <div class="brand">
    <a class="brand-home-link {'active' if active=='inicio' else ''}" href="/" title="Volver al inicio">⌂ <span>INICIO</span></a>
    <img class="brand-logo" src="/static/doctor_logo.png" alt="Logo del Dr. Armando Revelo">
    <div class="brand-copy"><strong>Historia Clínica</strong><small>{DOCTOR_NAME}</small></div>
    <span class="hc-runtime-version" title="Versión real del backend en ejecución">v{APP_VERSION}</span>
  </div>
  <nav aria-label="Navegación principal">
    <a class="{'active' if active=='macros' else ''}" href="/macros">Frases rápidas</a>
  </nav>
</header>
<main>{body}</main>
<footer><span>Historia Clínica v{APP_VERSION}</span><span>Base local protegida · Migrada de Consulta Práctica</span></footer>
<div id="app-toast" class="app-toast" role="status" aria-live="polite" hidden></div>
<script>
(()=>{{
  const toast=document.getElementById('app-toast'); let toastTimer=0;
  let lastActivityPing=0;
  const pingActivity=(force=false)=>{{
    const now=Date.now();
    if(!force && now-lastActivityPing<45000)return;
    lastActivityPing=now;
    fetch('/api/activity',{{method:'POST',cache:'no-store',keepalive:true}}).catch(()=>{{}});
  }};
  ['pointerdown','pointermove','keydown','wheel','touchstart'].forEach(ev=>document.addEventListener(ev,()=>pingActivity(false),{{passive:true}}));
  window.addEventListener('focus',()=>pingActivity(true));
  document.addEventListener('visibilitychange',()=>{{if(!document.hidden)pingActivity(true)}});
  window.showAppToast=(message,type='info')=>{{if(!toast)return;clearTimeout(toastTimer);toast.textContent=String(message||'');toast.className='app-toast '+type;toast.hidden=false;toastTimer=setTimeout(()=>{{toast.hidden=true}},3600)}};
  window.historiaNativePrint=async(url,kind='certificate')=>{{
    try{{
      let printer='';
      try{{
        const q=encodeURIComponent(String(kind||'certificate'));
        const r=await fetch('/api/documentos/impresora?kind='+q,{{cache:'no-store'}});
        if(r.ok){{const d=await r.json();printer=String(d.printer||'')}}
      }}catch(_e){{}}
      if(window.chrome&&window.chrome.webview&&typeof window.chrome.webview.postMessage==='function'){{
        window.chrome.webview.postMessage({{type:'historia-print-url',url:String(url||''),printer}});
        if(window.showAppToast)showAppToast('Documento enviado a la impresora.','success');
        return true;
      }}
      throw new Error('La impresión directa requiere Launcher Historia 1.0.8. Cierre y vuelva a abrir Historia Clínica.');
    }}catch(err){{
      if(window.showAppToast)showAppToast(err&&err.message?err.message:'No se pudo imprimir.','error');
      else alert(err&&err.message?err.message:'No se pudo imprimir.');
      return false;
    }}
  }};
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  document.querySelectorAll('[data-live-patient-search]').forEach(box=>{{
    const input=box.querySelector('input[name="q"]'), menu=box.querySelector('.live-search-results');
    if(!input||!menu)return;
    let timer=0, controller=null, active=-1;
    const hide=()=>{{menu.hidden=true;menu.innerHTML='';active=-1}};
    const select=(idx)=>{{const items=[...menu.querySelectorAll('a')];items.forEach(x=>x.classList.remove('active'));if(items[idx]){{active=idx;items[idx].classList.add('active');items[idx].scrollIntoView({{block:'nearest'}})}}}};
    const run=()=>{{
      clearTimeout(timer);
      const q=input.value.trim();
      if(q.length<2){{hide();return}}
      timer=setTimeout(async()=>{{
        try{{
          controller?.abort(); controller=new AbortController();
          const r=await fetch('/api/pacientes/buscar?q='+encodeURIComponent(q)+'&limit=8',{{signal:controller.signal}});
          if(!r.ok)return hide();
          const data=await r.json();
          if(!data.length){{menu.innerHTML='<div class="live-empty">No encontré coincidencias</div>';menu.hidden=false;return}}
          menu.innerHTML=data.map(x=>`<a href="${{esc(x.href)}}"><span class="live-avatar">${{esc((x.name||'?').slice(0,1))}}</span><span class="live-copy"><b>${{esc(x.name)}}</b><small>${{esc(x.detail)}}</small></span><span class="live-count">${{x.records}} reg.</span></a>`).join('');
          menu.hidden=false; active=-1;
        }}catch(err){{if(err.name!=='AbortError')hide()}}
      }},170);
    }};
    input.addEventListener('input',run);
    input.addEventListener('keydown',ev=>{{
      if(menu.hidden)return; const items=[...menu.querySelectorAll('a')];
      if(ev.key==='ArrowDown'){{ev.preventDefault();select(Math.min(active+1,items.length-1))}}
      else if(ev.key==='ArrowUp'){{ev.preventDefault();select(Math.max(active-1,0))}}
      else if(ev.key==='Enter'&&active>=0&&items[active]){{ev.preventDefault();location.href=items[active].href}}
      else if(ev.key==='Escape')hide();
    }});
    input.addEventListener('focus',()=>{{if(input.value.trim().length>=2)run()}});
    document.addEventListener('click',ev=>{{if(!box.contains(ev.target))hide()}});
  }});
}})();
</script>
{extra_script}</body></html>"""


def _queue_strong_candidates(conn, row):
    """Candidatos seguros para vincular un turno de Recepción con Historia."""
    identification = normalize_search(row["identification"] or "")
    if identification:
        exact = conn.execute(
            "SELECT * FROM patients WHERE national_id_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 3",
            (identification,),
        ).fetchall()
        if len(exact) == 1:
            return list(exact), "identification"

    wanted = normalize_search(row["display_name"] or "")
    tokens = [t for t in wanted.split() if t]
    if not tokens:
        return [], ""

    rows = search_patients(conn, row["display_name"] or "", limit=12)
    strong = []
    for candidate in rows:
        candidate_tokens = set(normalize_search(candidate["name"] or "").split())
        if tokens and all(t in candidate_tokens for t in tokens):
            strong.append(candidate)

    # Una sola coincidencia por todos los nombres escritos es suficientemente
    # clara para el flujo del consultorio; varias coincidencias requieren elección.
    if strong:
        return strong, "name"
    return rows[:8], "search"


def _queue_display_type(row):
    # v1.3.22: Nuevo/Subsecuente describe al paciente; Consulta/Procedimiento
    # describe la atención. Ya no se mezclan en el mismo campo.
    patient_status = ""
    try:
        patient_status = str(row["patient_status"] or "").strip().upper()
    except Exception:
        patient_status = ""

    status_mapping = {
        "N": "Nuevo",
        "NUEVO": "Nuevo",
        "S": "Subsecuente",
        "SUBSECUENTE": "Subsecuente",
    }
    if patient_status in status_mapping:
        return status_mapping[patient_status]

    raw = str(row["attention_type"] or "").strip()
    upper = raw.upper()

    # Compatibilidad con filas antiguas donde attention_type llevaba N/S.
    legacy_mapping = {
        "N": "Nuevo",
        "NUEVO": "Nuevo",
        "S": "Subsecuente",
        "SUBSECUENTE": "Subsecuente",
    }
    if upper in legacy_mapping:
        return legacy_mapping[upper]

    # Para procedimientos sin estado explícito mostramos el tipo de atención.
    if upper in {"P", "X", "PROCEDIMIENTO"}:
        return "Procedimiento"

    # Compatibilidad con turnos creados por versiones anteriores que mandaban
    # solamente "Consulta". Si existe una ficha única, inferimos Nuevo/Subsecuente
    # por presencia de historias previas, solo para presentación.
    if upper in {"", "CONSULTA"}:
        try:
            with db() as conn:
                candidates, _reason = _queue_strong_candidates(conn, row)
                if len(candidates) == 1:
                    pid = candidates[0]["id"]
                    n = conn.execute(
                        "SELECT COUNT(*) FROM encounters WHERE patient_id=? AND note_status!='draft'",
                        (pid,),
                    ).fetchone()[0]
                    return "Subsecuente" if int(n or 0) > 0 else "Nuevo"
        except Exception:
            pass
        return "Consulta"
    return raw or "Consulta"


def _queue_is_new(row) -> bool:
    return _queue_display_type(row) == "Nuevo"


def _queue_is_procedure(row) -> bool:
    """Un procedimiento aparece en la cola, pero no consume número de turno."""
    raw = normalize_search(str(row["attention_type"] or "")).upper().strip()
    if raw in {"P", "X", "PROCEDIMIENTO"}:
        return True
    if raw in {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}:
        return False
    # Compatibilidad con el puente antiguo: enviaba el nombre real del
    # procedimiento (ECOGRAFÍA, CURACIÓN, etc.) en attention_type.
    return True


def _queue_turn_number(conn, queue_id: str) -> int | None:
    """
    Número real de consulta del día.

    v1.3.31:
    La fuente de verdad para lo YA atendido son las historias firmadas del día,
    no solamente las filas completed de waiting_queue. Esto recupera la
    secuencia aunque un handoff antiguo no haya dejado su fila de cola completa.

    Para lo pendiente se suma la posición entre consultas activas del día.
    Procedimientos y cancelados nunca consumen turno.
    """
    current = conn.execute(
        "SELECT id,attention_type,reception_turn,reception_patient_id,queued_at,created_at "
        "FROM waiting_queue WHERE id=? LIMIT 1",
        (queue_id,),
    ).fetchone()
    if not current or _queue_is_procedure(current):
        return None

    # v1.3.37: Recepción es la fuente única. Busca el turno exacto más reciente
    # de ese mismo paciente, incluso si llegó por otro event_id/handoff.
    reception_patient_id = str(current["reception_patient_id"] or "").strip()
    exact_turn = None
    if reception_patient_id:
        turn_row = conn.execute(
            """
            SELECT reception_turn
              FROM waiting_queue
             WHERE reception_patient_id=?
               AND reception_turn IS NOT NULL
               AND reception_turn>0
             ORDER BY COALESCE(updated_at,queued_at,created_at,'') DESC, id DESC
             LIMIT 1
            """,
            (reception_patient_id,),
        ).fetchone()
        if turn_row:
            try:
                exact_turn = int(turn_row["reception_turn"])
            except Exception:
                exact_turn = None
    if exact_turn is None:
        try:
            exact_turn = int(current["reception_turn"]) if current["reception_turn"] not in (None, "") else None
        except Exception:
            exact_turn = None
    if exact_turn is not None and exact_turn > 0:
        return exact_turn

    stamp = str(current["queued_at"] or current["created_at"] or "")
    day = stamp[:10] or datetime.now().strftime("%Y-%m-%d")

    # Consultas ya finalizadas hoy. Si conservan queue_id y esa cola existe,
    # respetamos el tipo real para no contar procedimientos. Si la fila vieja
    # ya no existe, una historia firmada sigue considerándose consulta.
    signed_rows = conn.execute(
        """
        SELECT e.id,e.queue_id,q.attention_type
        FROM encounters e
        LEFT JOIN waiting_queue q ON q.id=e.queue_id
        WHERE e.note_status='signed'
          AND e.source='historia_clinica'
          AND e.encounter_date=?
        ORDER BY COALESCE(e.signed_at,e.updated_at,e.created_at) ASC,e.id ASC
        """,
        (day,),
    ).fetchall()

    completed_consultations = 0
    signed_queue_ids = set()
    for item in signed_rows:
        qid = str(item["queue_id"] or "").strip()
        if qid:
            signed_queue_ids.add(qid)
        # Si existe fila de cola, úsela para distinguir procedimiento.
        if item["attention_type"] is not None:
            proxy = {"attention_type": item["attention_type"]}
            if _queue_is_procedure(proxy):
                continue
        completed_consultations += 1

    active_rows = conn.execute(
        """
        SELECT id,attention_type,queued_at,created_at,status
        FROM waiting_queue
        WHERE status IN ('waiting','in_consultation')
          AND substr(COALESCE(NULLIF(queued_at,''),created_at),1,10)=?
        ORDER BY CASE status WHEN 'in_consultation' THEN 0 ELSE 1 END,
                 COALESCE(NULLIF(queued_at,''),created_at) ASC,id ASC
        """,
        (day,),
    ).fetchall()

    active_position = 0
    for item in active_rows:
        item_id = str(item["id"])
        if item_id in signed_queue_ids:
            continue
        if _queue_is_procedure(item):
            if item_id == str(queue_id):
                return None
            continue
        active_position += 1
        if item_id == str(queue_id):
            return completed_consultations + active_position

    return None

def _create_new_patient_from_queue(conn, row) -> str:
    """
    Crea una ficha mínima y segura para un turno marcado como Nuevo.
    Si Recepción envió identificación y ya existe exactamente esa identificación,
    reutiliza la ficha existente para no duplicarla.
    """
    identification = normalize_search(row["identification"] or "")
    if identification:
        exact = conn.execute(
            "SELECT id FROM patients WHERE national_id_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 2",
            (identification,),
        ).fetchall()
        if len(exact) == 1:
            patient_id = str(exact[0]["id"])
            _link_queue_patient(conn, row, patient_id, "auto_identification_new")
            return patient_id
        if len(exact) > 1:
            raise ValueError("La identificación coincide con más de una ficha existente.")

    name = re.sub(r"\s+", " ", str(row["display_name"] or "")).strip().upper()
    if not name:
        raise ValueError("El turno no tiene un nombre válido para crear la ficha.")

    # Si Recepción marcó "Nuevo" pero no envió identificación, no creamos otra
    # ficha a ciegas si ya existe exactamente ese nombre. Obligamos a revisar y
    # seleccionar la ficha correcta; así evitamos triplicados por reingresos.
    if not identification:
        same_name = conn.execute(
            "SELECT id,name,national_id FROM patients WHERE name_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 4",
            (normalize_search(name),),
        ).fetchall()
        if same_name:
            raise ValueError(
                "Ya existe una o más fichas con exactamente ese nombre. "
                "Seleccione la ficha correcta antes de crear otra."
            )

    # Recepción y Historia deben hablar de UNA SOLA ficha para un paciente
    # nuevo. El puente de Recepción ya usa este UUID determinístico en Neon.
    # Historia reutiliza exactamente el mismo ID aunque la sincronización aún
    # no haya alcanzado a bajar esa fila; así dos procesos nunca crean dos PK.
    reception_patient_id = str(row["reception_patient_id"] or "").strip()
    linked_id = str(row["clinical_patient_id"] or "").strip()
    if linked_id:
        patient_id = linked_id
    elif reception_patient_id:
        patient_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            "historia-reception-patient:" + reception_patient_id,
        ))
    else:
        patient_id = new_id()

    existing_same_id = conn.execute(
        "SELECT id,merged_into_patient_id FROM patients WHERE id=? LIMIT 1",
        (patient_id,),
    ).fetchone()
    if existing_same_id:
        canonical_id = str(existing_same_id["merged_into_patient_id"] or "").strip() or patient_id
        _link_queue_patient(conn, row, canonical_id, "reuse_reception_patient_id")
        return canonical_id

    stamp = now_iso()
    raw_id = str(row["identification"] or "").strip()
    digest = hashlib.sha256(
        f"{patient_id}|{name}|{raw_id}|{stamp}|reception_new".encode("utf-8")
    ).hexdigest()

    conn.execute(
        """INSERT INTO patients(
             id,legacy_patient_id,name,name_search,birth_date,sex,civil_status,
             address,phone,next_appointment_legacy,national_id,national_id_search,
             legacy_notes,legacy_photo,legacy_alert,email,insurer,
             legacy_no_depurable,source,source_record_hash,created_at,updated_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            patient_id, None, name, normalize_search(name), None, None, None,
            None, None, None, raw_id or None, identification if raw_id else "",
            None, None, None, None, None, 0, "reception_new", digest, stamp, stamp,
        ),
    )
    audit(
        conn,
        "create_from_reception",
        "patient",
        patient_id,
        {
            "name": name,
            "reception_patient_id": str(row["reception_patient_id"] or ""),
            "queue_id": str(row["id"]),
            "attention_type": _queue_display_type(row),
        },
    )
    conn.commit()

    # Vincula en una segunda operación reutilizando la lógica auditada existente.
    fresh_row = conn.execute(
        "SELECT * FROM waiting_queue WHERE id=? LIMIT 1",
        (row["id"],),
    ).fetchone()
    _link_queue_patient(conn, fresh_row or row, patient_id, "auto_new_from_reception")
    return patient_id


def _link_queue_patient(conn, row, patient_id: str, matched_by: str):
    stamp = now_iso()
    conn.execute(
        "UPDATE waiting_queue SET clinical_patient_id=?,updated_at=? WHERE id=?",
        (patient_id, stamp, row["id"]),
    )
    conn.execute(
        """
        INSERT INTO patient_links(
          reception_patient_id,clinical_patient_id,matched_by,verified,
          verified_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(reception_patient_id) DO UPDATE SET
          clinical_patient_id=excluded.clinical_patient_id,
          matched_by=excluded.matched_by,
          verified=1,
          verified_at=excluded.verified_at,
          updated_at=excluded.updated_at
        """,
        (
            str(row["reception_patient_id"]),
            patient_id,
            matched_by,
            1,
            stamp,
            stamp,
            stamp,
        ),
    )
    conn.commit()


def _queue_validated_link(conn, row) -> str:
    """
    Devuelve un vínculo existente sólo si sigue siendo confiable.

    v1.3.20:
    - la identificación exacta de Recepción tiene prioridad absoluta;
    - si un vínculo automático apunta a una ficha sin identificación pero existe
      otra ficha con la identificación exacta, corrige el vínculo;
    - si no hay identificación y existen varias fichas con exactamente el mismo
      nombre, un vínculo automático no se toma a ciegas: se obliga a elegir.
    - un vínculo seleccionado manualmente por el doctor sí se respeta.
    """
    linked_id = str(row["clinical_patient_id"] or "").strip()
    if not linked_id:
        return ""

    linked = conn.execute(
        "SELECT id,name,name_search,national_id_search,merged_into_patient_id FROM patients WHERE id=? LIMIT 1",
        (linked_id,),
    ).fetchone()
    if not linked:
        return ""
    merged_to = str(linked["merged_into_patient_id"] or "").strip()
    if merged_to:
        canonical = conn.execute(
            "SELECT id,name,name_search,national_id_search,merged_into_patient_id "
            "FROM patients WHERE id=? LIMIT 1",
            (merged_to,),
        ).fetchone()
        if canonical:
            linked_id = str(canonical["id"])
            linked = canonical
            _link_queue_patient(conn, row, linked_id, "repair_merged_patient")

    link_meta = conn.execute(
        "SELECT matched_by,verified FROM patient_links WHERE reception_patient_id=? LIMIT 1",
        (str(row["reception_patient_id"] or ""),),
    ).fetchone()
    matched_by = str(link_meta["matched_by"] or "") if link_meta else ""
    if matched_by == "manual_doctor":
        return linked_id

    identification = normalize_search(row["identification"] or "")
    if identification:
        exact = conn.execute(
            "SELECT id FROM patients WHERE national_id_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 3",
            (identification,),
        ).fetchall()
        if len(exact) == 1:
            exact_id = str(exact[0]["id"])
            if exact_id != linked_id:
                _link_queue_patient(
                    conn,
                    row,
                    exact_id,
                    "repair_exact_identification",
                )
            return exact_id

        linked_ident = normalize_search(linked["national_id_search"] or "")
        if linked_ident == identification:
            return linked_id

        # La identificación del turno no confirma el vínculo actual.
        return ""

    wanted = normalize_search(row["display_name"] or "")
    if wanted:
        same_name = conn.execute(
            "SELECT id FROM patients WHERE name_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 4",
            (wanted,),
        ).fetchall()
        if len(same_name) > 1:
            # Hay duplicados reales del mismo nombre. No adivinamos cuál usar.
            return ""

    return linked_id


@app.get("/cola/{queue_id}/atender")
def attend_from_queue(queue_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM waiting_queue WHERE id=? AND status IN ('waiting','in_consultation') LIMIT 1",
            (queue_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Turno no encontrado")

        patient_id = _queue_validated_link(conn, row)
        if patient_id:
            return RedirectResponse(
                f"/paciente/{patient_id}/nueva?queue_id={queue_id}",
                status_code=303,
            )

        # Un turno marcado como NUEVO tiene flujo propio: la ficha se crea
        # automáticamente, salvo que la misma identificación ya exista.
        if _queue_is_new(row):
            try:
                patient_id = _create_new_patient_from_queue(conn, row)
                return RedirectResponse(
                    f"/paciente/{patient_id}/nueva?queue_id={queue_id}",
                    status_code=303,
                )
            except ValueError:
                # Si "Nuevo" choca con una ficha ya existente, no creamos otra
                # ni detenemos el flujo: mostramos las fichas candidatas para
                # que el doctor elija la correcta.
                pass

        candidates, reason = _queue_strong_candidates(conn, row)
        if len(candidates) == 1:
            patient_id = str(candidates[0]["id"])
            _link_queue_patient(conn, row, patient_id, "auto_" + (reason or "search"))
            return RedirectResponse(
                f"/paciente/{patient_id}/nueva?queue_id={queue_id}",
                status_code=303,
            )

        title = e(row["display_name"] or "Paciente")
        if candidates:
            cards = []
            for candidate in candidates:
                detail = []
                if candidate["birth_date"]:
                    age = age_from_birth(candidate["birth_date"])
                    if age is not None:
                        detail.append(f"{age} años")
                sx = sex_label(candidate["sex"])
                if sx:
                    detail.append(sx)
                if candidate["national_id"]:
                    detail.append("ID " + str(candidate["national_id"]))
                n_hist = conn.execute(
                    "SELECT COUNT(*) FROM encounters WHERE patient_id=? AND note_status!='draft'",
                    (candidate["id"],),
                ).fetchone()[0]
                detail.append(f"{int(n_hist or 0)} historia{'s' if int(n_hist or 0)!=1 else ''}")
                detail_text = " · ".join(detail) or "Ficha existente"
                cards.append(
                    f"<a class='patient-row queue-link-choice' href='/cola/{e(queue_id)}/vincular/{e(candidate['id'])}'>"
                    f"<span class='avatar'>{e((candidate['name'] or '?')[:1])}</span>"
                    f"<span class='patient-main'><b>{e(candidate['name'])}</b><span>{e(detail_text)}</span></span>"
                    f"<span class='chev'>›</span></a>"
                )
            body = f"""
            <section class='page-head'><span class='eyebrow'>Vincular ficha</span>
              <h1>{title}</h1>
              <p>Encontré más de una ficha posible. Seleccione la correcta para abrir su ficha antes de iniciar la atención.</p>
            </section>
            <section class='panel'>{''.join(cards)}</section>
            <p style='margin-top:12px'><a class='secondary btn-link' href='/pacientes?q={e(row["display_name"] or "")}'>Buscar manualmente</a></p>
            """
        else:
            body = f"""
            <section class='page-head'><span class='eyebrow'>Paciente por vincular</span>
              <h1>{title}</h1>
              <p>No encontré una ficha única con seguridad. Busque la ficha existente antes de iniciar la atención.</p>
            </section>
            <p><a class='primary btn-link' href='/pacientes?q={e(row["display_name"] or "")}'>Buscar ficha</a></p>
            """
        return HTMLResponse(base("Vincular paciente", body, "inicio"))


@app.get("/cola/{queue_id}/vincular/{patient_id}")
def link_and_attend_queue(queue_id: str, patient_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM waiting_queue WHERE id=? AND status IN ('waiting','in_consultation') LIMIT 1",
            (queue_id,),
        ).fetchone()
        patient = conn.execute("SELECT id FROM patients WHERE id=? LIMIT 1", (patient_id,)).fetchone()
        if not row or not patient:
            raise HTTPException(status_code=404, detail="Turno o paciente no encontrado")
        _link_queue_patient(conn, row, patient_id, "manual_doctor")
    return RedirectResponse(
        f"/paciente/{patient_id}?queue_id={queue_id}",
        status_code=303,
    )


@app.get("/", response_class=HTMLResponse)
def home():
    cleanup_active_queue_duplicates()
    cleanup_cancelled_queue_drafts()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    hour = now.hour
    greeting = "Buenos días" if hour < 12 else ("Buenas tardes" if hour < 19 else "Buenas noches")
    with db() as conn:
        patient_count = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE COALESCE(merged_into_patient_id,'')=''"
        ).fetchone()[0]
        encounter_count = conn.execute("SELECT COUNT(*) FROM encounters WHERE note_status!='draft'").fetchone()[0]
        today_count = conn.execute("SELECT COUNT(*) FROM encounters WHERE note_status='signed' AND source='historia_clinica' AND encounter_date=?", (today,)).fetchone()[0]
        queue = conn.execute("""
            SELECT * FROM waiting_queue WHERE status IN ('waiting','in_consultation')
            ORDER BY CASE status WHEN 'in_consultation' THEN 0 ELSE 1 END, queued_at ASC LIMIT 20
        """).fetchall()
        queue_turns = {
            str(r["id"]): _queue_turn_number(conn, str(r["id"]))
            for r in queue
        }
        recent = conn.execute("""
            SELECT p.id,p.name,p.birth_date,p.sex,MAX(a.occurred_at) AS last_opened
            FROM audit_log a
            JOIN patients p ON p.id=a.entity_id
            WHERE a.action='view' AND a.entity_type='patient'
            GROUP BY p.id,p.name,p.birth_date,p.sex
            ORDER BY last_opened DESC
            LIMIT 6
        """).fetchall()
        pending_draft = conn.execute("""
            SELECT e.id AS encounter_id,e.patient_id,e.updated_at,p.name
            FROM encounters e
            JOIN patients p ON p.id=e.patient_id
            WHERE e.note_status='draft'
              AND COALESCE(e.deleted_at,'')=''
              AND (
                TRIM(COALESCE(e.clinical_note,''))<>''
                OR TRIM(COALESCE(e.diagnosis,''))<>''
                OR TRIM(COALESCE(e.treatment,''))<>''
                OR EXISTS (SELECT 1 FROM prescriptions r WHERE r.encounter_id=e.id AND COALESCE(r.deleted_at,'')='')
                OR EXISTS (SELECT 1 FROM certificates c WHERE c.encounter_id=e.id AND COALESCE(c.deleted_at,'')='')
              )
            ORDER BY e.updated_at DESC
            LIMIT 1
        """).fetchone()
        pending_draft_count = int(conn.execute("""
            SELECT COUNT(*) FROM encounters
            WHERE note_status='draft'
              AND COALESCE(deleted_at,'')=''
              AND (
                TRIM(COALESCE(clinical_note,''))<>''
                OR TRIM(COALESCE(diagnosis,''))<>''
                OR TRIM(COALESCE(treatment,''))<>''
                OR EXISTS (SELECT 1 FROM prescriptions r WHERE r.encounter_id=encounters.id AND COALESCE(r.deleted_at,'')='')
                OR EXISTS (SELECT 1 FROM certificates c WHERE c.encounter_id=encounters.id AND COALESCE(c.deleted_at,'')='')
              )
        """).fetchone()[0])

    queue_count = len(queue)
    if queue:
        parts = []
        for r in queue:
            is_procedure = _queue_is_procedure(r)
            real_turn = queue_turns.get(str(r["id"]))
            turn_badge = (
                f"<div class='queue-turn-number'><span>TURNO</span><b>#{real_turn}</b></div>"
                if not is_procedure and real_turn is not None
                else "<div class='queue-turn-number queue-turn-procedure'><span>ATENCIÓN</span><b>PROC.</b></div>"
            )
            status_text = "En consulta" if r["status"] == "in_consultation" else "En espera"
            attention_label = _queue_display_type(r)
            is_new = attention_label == "Nuevo"
            if r["status"] == "in_consultation":
                action_label = "Ver ficha"
            elif r["clinical_patient_id"]:
                action_label = "Abrir ficha"
            elif is_new:
                action_label = "Revisar ficha"
            else:
                action_label = "Vincular ficha"
            attention_key = normalize_search(attention_label).lower().replace(" ", "-") or "consulta"
            service_tag = (
                "<span class='queue-type queue-type-procedimiento'>PROCEDIMIENTO</span>"
                if is_procedure else ""
            )
            queued = e((r["queued_at"] or "")[-8:-3])
            href = f"/cola/{e(r['id'])}/atender"
            parts.append(
                f"<div class='queue-row queue-row-clickable {'queue-row-new' if is_new else ''}'>"
                f"<a class='queue-row-main' href='{href}' title='{e(action_label)}'>"
                f"{turn_badge}"
                f"<div class='queue-avatar'>{e((r['display_name'] or '?')[:1])}</div>"
                f"<span class='queue-patient-copy'><b>{e(r['display_name'])}</b>"
                f"<span class='queue-tags'><span class='queue-type queue-type-{e(attention_key)}'>{'★ PACIENTE NUEVO' if is_new else e(attention_label)}</span>"
                f"{service_tag}<span class='queue-status'>{e(status_text)}</span></span></span>"
                f"<time>{queued}</time><span class='queue-row-action'>{e(action_label)} ›</span></a>"
                f"<form class='queue-dismiss-form' method='post' action='/cola/{e(r['id'])}/descartar' "
                f"onsubmit=\"return confirm('¿Quitar este turno de Pacientes en espera? No se eliminará la ficha ni la historia clínica.')\">"
                f"<button type='submit' class='queue-dismiss-btn' title='Quitar de espera'>×</button></form>"
                f"</div>"
            )
        qhtml = "".join(parts)
    else:
        qhtml = "<div class='empty queue-empty'><div class='empty-icon'>✓</div><strong>No hay pacientes en espera</strong><span>Cuando Recepción envíe un paciente al pulsar Atender, aparecerá aquí automáticamente.</span></div>"

    next_row = next((r for r in queue if r["status"] == "waiting"), None)
    if next_row is None:
        next_row = next((r for r in queue), None)
    next_button = (
        f"<a class='home-action primary' href='/cola/{e(next_row['id'])}/atender'>Abrir siguiente</a>"
        if next_row else "<span class='home-action disabled'>Abrir siguiente</span>"
    )

    if recent:
        recent_parts = []
        for r in recent:
            detail = []
            if r["birth_date"]:
                age = age_from_birth(r["birth_date"])
                if age is not None:
                    detail.append(f"{age} años")
            sx = sex_label(r["sex"])
            if sx:
                detail.append(sx)
            try:
                opened = datetime.fromisoformat(r["last_opened"]).strftime("%H:%M")
            except Exception:
                opened = ""
            suffix = (" · " + " · ".join(detail)) if detail else ""
            recent_parts.append(
                f"<a class='recent-row' href='/paciente/{e(r['id'])}'><span class='recent-avatar'>{e((r['name'] or '?')[:1])}</span>"
                f"<span class='recent-copy'><b>{e(r['name'])}</b><small>Abierto {e(opened)}{e(suffix)}</small></span><span class='recent-arrow'>›</span></a>"
            )
        recent_html = "".join(recent_parts)
        last_patient = recent[0]
        continue_button = f"<a class='home-action secondary' href='/paciente/{e(last_patient['id'])}'>Continuar último paciente</a>"
    else:
        recent_html = "<div class='recent-empty'>Los pacientes que abra aparecerán aquí para volver rápidamente.</div>"
        continue_button = "<span class='home-action disabled subtle'>Continuar último paciente</span>"

    cloud = get_sync_status(ROOT / "data")
    if cloud.get("state") == "afk":
        cloud_class = "ok"
        cloud_mark = "◷"
        cloud_text = "En reposo (AFK) · LAN activa"
    elif cloud.get("state") == "synced" and cloud.get("online"):
        cloud_class = "ok"
        cloud_mark = "✓"
        cloud_text = "Sincronizada"
    elif cloud.get("configured"):
        cloud_class = "pending"
        cloud_mark = "•"
        cloud_text = cloud.get("message") or "Sincronizando…"
    else:
        cloud_class = "pending"
        cloud_mark = "•"
        cloud_text = "Pendiente de configurar"
    if cloud.get("backup_ok"):
        backup_class = "ok"
        backup_mark = "✓"
        backup_text = "Respaldo local diario activo"
    else:
        backup_class = "pending"
        backup_mark = "•"
        backup_text = "Preparando respaldo"

    pending_banner = ""
    if pending_draft:
        extra = f" · {pending_draft_count} pendientes" if pending_draft_count > 1 else ""
        pending_banner = (
            f"<section class='pending-consult-banner'>"
            f"<div><span class='pending-consult-mark'>!</span><span><b>CONSULTA PENDIENTE</b>"
            f"<strong>{e(pending_draft['name'])}</strong><small>La consulta está autoguardada, pero todavía no ha sido finalizada{e(extra)}.</small></span></div>"
            f"<a href='/paciente/{e(pending_draft['patient_id'])}/nueva?encounter_id={e(pending_draft['encounter_id'])}'>Continuar consulta</a>"
            f"</section>"
        )

    body = f"""
<section class="home-heading home-heading-v107">
  <div><span class="eyebrow">PANEL MÉDICO</span><h1>{greeting}, Dr. Revelo</h1><p>Acceda a una historia clínica o continúe con el siguiente paciente.</p></div>
  <div class="stats">
    <div><span>Pacientes</span><strong>{patient_count:,}</strong></div>
    <div><span>Historias</span><strong>{encounter_count:,}</strong></div>
    <div><span>Atendidos hoy</span><strong>{today_count}</strong></div>
    <div><span>En espera</span><strong id="home-queue-count">{queue_count}</strong></div>
  </div>
</section>
{pending_banner}
<section class="search-card home-search home-search-v107">
  <div class="home-search-line">
    <div class="patient-live-search" data-live-patient-search>
      <form action="/pacientes" method="get"><label class="sr-only">Buscar historia clínica</label><div class="searchbox"><input name="q" autofocus autocomplete="off" placeholder="Escriba nombres en cualquier orden, identificación o teléfono"><button>Buscar paciente</button></div></form>
      <div class="live-search-results" hidden></div>
    </div>
    <a class="new-patient-home" href="/pacientes/nuevo">+ Nuevo paciente</a>
  </div>
  <p class="search-help">Puede escribir, por ejemplo, <b>CARLOS BRAVO</b> aunque la ficha esté registrada como BRAVO BURBANO CARLOS EMILIO.</p>
</section>
<section class="home-workspace">
  <section class="panel queue-panel home-queue-v107">
    <div class="panel-title"><div><span class="dot"></span><div><h2>Pacientes en espera</h2><p>{queue_count} paciente{'s' if queue_count!=1 else ''} en la cola del doctor</p></div></div>{next_button}</div>
    <div class="home-scroll-region">{qhtml}</div>
  </section>
  <aside class="home-side-stack">
    <section class="panel recent-panel">
      <div class="panel-title compact"><div><div><h2>Pacientes recientes</h2><p>Acceso rápido a las últimas fichas abiertas</p></div></div>{continue_button}</div>
      <div class="recent-list">{recent_html}</div>
    </section>
    <section class="panel system-panel">
      <div class="system-panel-head"><div><span class="eyebrow">ESTADO DEL SISTEMA</span><h2>Todo lo importante, de un vistazo</h2></div></div>
      <div class="system-status-grid">
        <div class="system-status ok"><span class="status-mark">✓</span><span><b>Base local</b><small>Activa y disponible</small></span></div>
        <div class="system-status pending" id="lan-status-card"><span class="status-mark" id="lan-status-mark">•</span><span><b>LAN</b><small id="lan-status-text">Preparando enlace con Recepción…</small></span></div>
        <div class="system-status {cloud_class}" id="cloud-status-card"><span class="status-mark" id="cloud-status-mark">{cloud_mark}</span><span><b>Nube</b><small id="cloud-status-text">{e(cloud_text)}</small><div class="cloud-progress-wrap" id="cloud-progress-wrap" hidden><div class="cloud-progress-track"><i id="cloud-progress-bar"></i></div><em id="cloud-progress-caption"></em></div></span></div>
        <div class="system-status {backup_class}"><span class="status-mark">{backup_mark}</span><span><b>Respaldo</b><small>{e(backup_text)}</small></span></div>
      </div>
    </section>
  </aside>
</section>
"""
    home_script = r"""
<script>
(()=>{
  let lastQueueKey='';
  const cloudCard=document.getElementById('cloud-status-card');
  const cloudMark=document.getElementById('cloud-status-mark');
  const cloudText=document.getElementById('cloud-status-text');
  const progressWrap=document.getElementById('cloud-progress-wrap');
  const progressBar=document.getElementById('cloud-progress-bar');
  const progressCaption=document.getElementById('cloud-progress-caption');
  function fmt(n){return Number(n||0).toLocaleString('es-EC')}
  function lanAge(value){
    if(!value)return '';
    const t=Date.parse(value); if(!Number.isFinite(t))return '';
    const s=Math.max(0,Math.floor((Date.now()-t)/1000));
    if(s<15)return 'ahora';
    if(s<60)return 'hace '+s+' s';
    return 'hace '+Math.floor(s/60)+' min';
  }
  async function refreshLan(){
    const card=document.getElementById('lan-status-card');
    const mark=document.getElementById('lan-status-mark');
    const text=document.getElementById('lan-status-text');
    if(!card||!mark||!text)return;
    try{
      const r=await fetch('/api/lan/status?t='+Date.now(),{cache:'no-store'}); if(!r.ok)throw 0;
      const s=await r.json();
      card.classList.remove('ok','pending','error');
      if(!s.ok){
        card.classList.add('error'); mark.textContent='!'; text.textContent=s.last_error||'No se pudo iniciar el servicio LAN';
      }else if(s.last_reception_seen){
        card.classList.add('ok'); mark.textContent='✓'; text.textContent='Recepción conectada '+lanAge(s.last_reception_seen);
      }else if(s.firewall_rule===false){
        card.classList.add('pending'); mark.textContent='•'; text.textContent='Servicio activo · active el permiso de Windows';
      }else{
        card.classList.add('pending'); mark.textContent='•'; text.textContent='Servicio activo · esperando Recepción';
      }
    }catch(_e){
      card.classList.remove('ok','pending');card.classList.add('error');mark.textContent='!';text.textContent='No se pudo comprobar la LAN';
    }
  }
  async function refreshCloud(){
    try{
      const r=await fetch('/api/sync/status?t='+Date.now(),{cache:'no-store'}); if(!r.ok)return;
      const s=await r.json();
      const pending=Number(s.pending||0), total=Math.max(Number(s.initial_total||0),pending);
      cloudCard?.classList.remove('ok','pending','error');
      if(s.state==='afk'){
        cloudCard?.classList.add('ok'); if(cloudMark)cloudMark.textContent='◷'; if(cloudText)cloudText.textContent='En reposo (AFK) · LAN activa';
        if(progressWrap)progressWrap.hidden=true;
      }else if(s.state==='synced'&&s.online){
        cloudCard?.classList.add('ok'); if(cloudMark)cloudMark.textContent='✓'; if(cloudText)cloudText.textContent='Sincronizada';
        if(progressWrap)progressWrap.hidden=true;
      }else if(s.configured){
        cloudCard?.classList.add(s.state==='offline'?'error':'pending'); if(cloudMark)cloudMark.textContent=s.state==='offline'?'!':'•';
        if(cloudText)cloudText.textContent=s.message||'Sincronizando…';
        if(progressWrap){progressWrap.hidden=pending<=0; if(pending>0){
          const done=total>0?Math.max(0,total-pending):0, pct=total>0?Math.min(100,Math.max(2,(done/total)*100)):8;
          if(progressBar)progressBar.style.width=pct.toFixed(1)+'%';
          if(progressCaption)progressCaption.textContent=fmt(pending)+' pendientes'+(total?(' · '+Math.round(pct)+'% completado'):'');
        }}
      }else{
        cloudCard?.classList.add('pending'); if(cloudMark)cloudMark.textContent='•'; if(cloudText)cloudText.textContent='Pendiente de configurar'; if(progressWrap)progressWrap.hidden=true;
      }
    }catch(_e){}
  }
  async function refreshQueue(){
    try{
      const r=await fetch('/api/queue/status?t='+Date.now(),{cache:'no-store'}); if(!r.ok)return; const q=await r.json();
      const key=String(q.count||0)+'|'+String(q.latest||'')+'|'+String(q.updated_at||'');
      const el=document.getElementById('home-queue-count'); if(el)el.textContent=String(q.count||0);
      if(lastQueueKey&&key!==lastQueueKey) location.reload();
      lastQueueKey=key;
    }catch(_e){}
  }
  async function runTool(id,url,okText){
    const btn=document.getElementById(id); if(!btn)return;
    btn.addEventListener('click',async()=>{
      const old=btn.innerHTML; btn.disabled=true; btn.classList.add('working');
      try{
        const r=await fetch(url,{method:'POST',cache:'no-store'}); const d=await r.json();
        if(!r.ok||!d.ok) throw new Error(d.message||'No se pudo completar la acción');
        showAppToast(d.message||okText,'success');
        if(id==='sync-now-btn') setTimeout(refreshCloud,500);
      }catch(err){ showAppToast(err.message||String(err),'error'); }
      finally{ btn.disabled=false; btn.classList.remove('working'); btn.innerHTML=old; }
    });
  }
  runTool('repair-shortcut-btn','/api/system/shortcut','Acceso directo reparado');
  runTool('repair-lan-btn','/api/system/lan-firewall','Permiso LAN solicitado');
  runTool('sync-now-btn','/api/sync/now','Sincronización solicitada');
  runTool('open-folder-btn','/api/system/open-folder','Carpeta abierta');
  refreshCloud(); refreshQueue(); refreshLan();
  setInterval(refreshCloud,2000); setInterval(refreshQueue,4000); setInterval(refreshLan,3000);
})();
</script>
"""
    return base("Inicio", body, "inicio", extra_script=home_script)


@app.post("/cola/{queue_id}/descartar")
def discard_queue_item(queue_id: str):
    stamp = now_iso()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM waiting_queue WHERE id=? LIMIT 1",
            (queue_id,),
        ).fetchone()
        if row and row["status"] in ("waiting", "in_consultation"):
            conn.execute(
                "UPDATE waiting_queue SET status='cancelled',updated_at=? WHERE id=?",
                (stamp, queue_id),
            )
            audit(
                conn,
                "discard",
                "waiting_queue",
                queue_id,
                {
                    "display_name": row["display_name"] or "",
                    "reason": "removed_from_waiting_room",
                },
            )
            conn.commit()
    SYNC_SERVICE.mark_activity()
    SYNC_SERVICE.wake()
    return RedirectResponse("/", status_code=303)


@app.get("/api/queue/status")
def api_queue_status():
    cleanup_active_queue_duplicates()
    cleanup_cancelled_queue_drafts()
    with db() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM waiting_queue WHERE status IN ('waiting','in_consultation')").fetchone()[0])
        latest = conn.execute("SELECT id,updated_at FROM waiting_queue WHERE status IN ('waiting','in_consultation') ORDER BY updated_at DESC LIMIT 1").fetchone()
    return JSONResponse({"count": count, "latest": (latest["id"] if latest else ""), "updated_at": (latest["updated_at"] if latest else "")})


@app.get("/api/pacientes/buscar")
def api_patient_search(q: str = Query(default="", max_length=120), limit: int = Query(default=8, ge=1, le=20)):
    with db() as conn:
        rows = search_patients(conn, q, limit=limit)
    result = []
    for r in rows:
        ident = clean_legacy_id(r["national_id"])
        pieces = []
        if ident:
            pieces.append(f"ID {ident}")
        if r["phone"]:
            pieces.append(str(r["phone"]))
        if r["birth_date"]:
            pieces.append(human_date(r["birth_date"]))
        result.append({
            "id": r["id"],
            "name": r["name"],
            "detail": " · ".join(pieces) if pieces else "Sin datos de contacto registrados",
            "records": int(r["n_hist"] or 0),
            "href": f"/paciente/{r['id']}",
        })
    return JSONResponse(result)



def render_new_patient_form(values=None, error=""):
    values = values or {}
    def v(key):
        return e(values.get(key, ""))
    error_html = f"<div class='form-error'><strong>No se pudo guardar el paciente.</strong><span>{e(error)}</span></div>" if error else ""
    sex = str(values.get("sex", "") or "").upper()
    civil = str(values.get("civil_status", "") or "").upper()
    return f"""
<a class='back cp-back' href='/pacientes'>← Volver a pacientes</a>
<section class='new-patient-shell'>
  <div class='new-patient-title'>
    <div><span class='eyebrow'>IDENTIFICACIÓN</span><h1>Nuevo paciente</h1><p>Registre los datos disponibles. La identificación no es obligatoria.</p></div>
  </div>
  {error_html}
  <form method='post' action='/pacientes/nuevo' class='new-patient-form' autocomplete='off'>
    <fieldset>
      <legend>Datos principales</legend>
      <label class='span-2'>Apellidos y nombres <input name='name' value='{v("name")}' maxlength='180' required autofocus placeholder='APELLIDOS Y NOMBRES'></label>
      <label>Fecha de nacimiento <input type='date' name='birth_date' value='{v("birth_date")}'></label>
      <label>Sexo
        <select name='sex'>
          <option value='' {'selected' if not sex else ''}>No registrado</option>
          <option value='M' {'selected' if sex=='M' else ''}>Masculino</option>
          <option value='F' {'selected' if sex=='F' else ''}>Femenino</option>
        </select>
      </label>
      <label>Estado civil
        <select name='civil_status'>
          <option value='' {'selected' if not civil else ''}>No registrado</option>
          <option value='S' {'selected' if civil=='S' else ''}>Soltero/a</option>
          <option value='C' {'selected' if civil=='C' else ''}>Casado/a</option>
          <option value='D' {'selected' if civil=='D' else ''}>Divorciado/a</option>
          <option value='V' {'selected' if civil=='V' else ''}>Viudo/a</option>
          <option value='U' {'selected' if civil=='U' else ''}>Unión libre</option>
        </select>
      </label>
      <label>Identificación <input name='national_id' value='{v("national_id")}' maxlength='40' placeholder='Opcional'></label>
      <label>Teléfono <input name='phone' value='{v("phone")}' maxlength='80' placeholder='Opcional'></label>
    </fieldset>
    <fieldset>
      <legend>Contacto y otros datos</legend>
      <label class='span-2'>Domicilio <textarea name='address' rows='3' placeholder='Dirección del paciente'>{v("address")}</textarea></label>
      <label>Email <input type='email' name='email' value='{v("email")}' maxlength='160' placeholder='Opcional'></label>
      <label>Aseguradora <input name='insurer' value='{v("insurer")}' maxlength='160' placeholder='Opcional'></label>
      <label class='span-2'>Otros datos / observaciones <textarea name='notes' rows='4' placeholder='Información adicional que convenga conservar'>{v("notes")}</textarea></label>
      <label class='span-2'>Alerta clínica <textarea name='alert' rows='3' placeholder='Solo si existe una alerta importante'>{v("alert")}</textarea></label>
    </fieldset>
    <div class='new-patient-actions'><a class='secondary btn-link' href='/pacientes'>Cancelar</a><button class='primary' type='submit'>Guardar paciente</button></div>
  </form>
</section>
"""


@app.get("/pacientes/nuevo", response_class=HTMLResponse)
def new_patient_page():
    return base("Nuevo paciente", render_new_patient_form(), "pacientes")


@app.post("/pacientes/nuevo", response_class=HTMLResponse)
async def create_patient(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(raw, keep_blank_values=True)
    values = {k: (parsed.get(k, [""])[0] or "").strip() for k in (
        "name", "birth_date", "sex", "civil_status", "national_id", "phone", "address", "email", "insurer", "notes", "alert"
    )}
    name = re.sub(r"\s+", " ", values["name"]).strip().upper()
    values["name"] = name
    if not name:
        return HTMLResponse(base("Nuevo paciente", render_new_patient_form(values, "El nombre del paciente es obligatorio."), "pacientes"), status_code=400)
    birth = values["birth_date"]
    if birth:
        try:
            datetime.strptime(birth, "%Y-%m-%d")
        except ValueError:
            return HTMLResponse(base("Nuevo paciente", render_new_patient_form(values, "La fecha de nacimiento no es válida."), "pacientes"), status_code=400)
    national_id = values["national_id"]
    with db() as conn:
        if national_id:
            exact = conn.execute(
                "SELECT id,name FROM patients WHERE national_id_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 1",
                (normalize_search(national_id),),
            ).fetchone()
            if exact:
                msg = f"Ya existe un paciente con esa identificación: {exact['name']}. Revise la ficha antes de crear otro registro."
                return HTMLResponse(base("Nuevo paciente", render_new_patient_form(values, msg), "pacientes"), status_code=409)
        else:
            # Sin identificación no creamos otra ficha con exactamente el mismo
            # nombre sin advertirlo. Esto evita duplicados silenciosos.
            same_name = conn.execute(
                "SELECT id,name,national_id FROM patients WHERE name_search=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 4",
                (normalize_search(name),),
            ).fetchall()
            if same_name:
                msg = (
                    "Ya existe una o más fichas con exactamente ese nombre. "
                    "Búsquelas primero y confirme que realmente se trata de otra persona."
                )
                return HTMLResponse(
                    base("Nuevo paciente", render_new_patient_form(values, msg), "pacientes"),
                    status_code=409,
                )
        pid, stamp = new_id(), now_iso()
        digest = hashlib.sha256(f"{pid}|{name}|{stamp}".encode("utf-8")).hexdigest()
        conn.execute(
            """INSERT INTO patients(id,legacy_patient_id,name,name_search,birth_date,sex,civil_status,address,phone,next_appointment_legacy,national_id,national_id_search,legacy_notes,legacy_photo,legacy_alert,email,insurer,legacy_no_depurable,source,source_record_hash,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, None, name, normalize_search(name), birth or None, values["sex"] or None, values["civil_status"] or None,
             values["address"] or None, values["phone"] or None, None, national_id or None, normalize_search(national_id) if national_id else "",
             values["notes"] or None, None, values["alert"] or None, values["email"] or None, values["insurer"] or None,
             0, "historia_clinica", digest, stamp, stamp),
        )
        audit(conn, "create", "patient", pid, {"name": name})
        conn.commit()
    return RedirectResponse(f"/paciente/{pid}", status_code=303)


def render_edit_patient_form(patient_id: str, values=None, error=""):
    values = values or {}
    def v(key):
        return e(values.get(key, ""))
    error_html = f"<div class='form-error'><strong>No se pudieron guardar los cambios.</strong><span>{e(error)}</span></div>" if error else ""
    sex = str(values.get("sex", "") or "").upper()
    civil = str(values.get("civil_status", "") or "").upper()
    return f"""
<a class='back cp-back' href='/paciente/{e(patient_id)}'>← Volver a la ficha</a>
<section class='new-patient-shell edit-patient-shell'>
  <div class='new-patient-title'>
    <div><span class='eyebrow'>DATOS DEL PACIENTE</span><h1>Editar ficha</h1><p>Las consultas e historias anteriores no se modifican al corregir estos datos.</p></div>
  </div>
  {error_html}
  <form method='post' action='/paciente/{e(patient_id)}/editar' class='new-patient-form edit-patient-form' autocomplete='off'>
    <fieldset>
      <legend>Datos principales</legend>
      <label class='span-2'>Apellidos y nombres <input name='name' value='{v("name")}' maxlength='180' required autofocus placeholder='APELLIDOS Y NOMBRES'></label>
      <label>Fecha de nacimiento <input type='date' name='birth_date' value='{v("birth_date")}'></label>
      <label>Sexo
        <select name='sex'>
          <option value='' {'selected' if not sex else ''}>No registrado</option>
          <option value='M' {'selected' if sex=='M' else ''}>Masculino</option>
          <option value='F' {'selected' if sex=='F' else ''}>Femenino</option>
        </select>
      </label>
      <label>Estado civil
        <select name='civil_status'>
          <option value='' {'selected' if not civil else ''}>No registrado</option>
          <option value='S' {'selected' if civil=='S' else ''}>Soltero/a</option>
          <option value='C' {'selected' if civil=='C' else ''}>Casado/a</option>
          <option value='D' {'selected' if civil=='D' else ''}>Divorciado/a</option>
          <option value='V' {'selected' if civil=='V' else ''}>Viudo/a</option>
          <option value='U' {'selected' if civil=='U' else ''}>Unión libre</option>
        </select>
      </label>
      <label>Identificación <input name='national_id' value='{v("national_id")}' maxlength='40' placeholder='Opcional'></label>
      <label>Teléfono <input name='phone' value='{v("phone")}' maxlength='80' placeholder='Opcional'></label>
    </fieldset>
    <fieldset>
      <legend>Contacto y otros datos</legend>
      <label class='span-2'>Domicilio <textarea name='address' rows='3' placeholder='Dirección del paciente'>{v("address")}</textarea></label>
      <label>Email <input type='email' name='email' value='{v("email")}' maxlength='160' placeholder='Opcional'></label>
      <label>Aseguradora <input name='insurer' value='{v("insurer")}' maxlength='160' placeholder='Opcional'></label>
      <label class='span-2'>Otros datos / observaciones <textarea name='notes' rows='4'>{v("notes")}</textarea></label>
      <label class='span-2'>Alerta clínica <textarea name='alert' rows='3'>{v("alert")}</textarea></label>
    </fieldset>
    <div class='new-patient-actions'>
      <a class='secondary btn-link' href='/paciente/{e(patient_id)}'>Cancelar</a>
      <button class='primary' type='submit'>Guardar cambios</button>
    </div>
  </form>
</section>
"""


@app.get("/paciente/{patient_id}/editar", response_class=HTMLResponse)
def edit_patient_page(patient_id: str):
    with db() as conn:
        p = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not p:
            raise HTTPException(404)
        merged_to = str(p["merged_into_patient_id"] or "").strip()
        if merged_to:
            return RedirectResponse(f"/paciente/{merged_to}/editar", status_code=303)
        values = {
            "name": p["name"] or "",
            "birth_date": p["birth_date"] or "",
            "sex": p["sex"] or "",
            "civil_status": p["civil_status"] or "",
            "national_id": clean_legacy_id(p["national_id"]),
            "phone": p["phone"] or "",
            "address": rtf_to_text(p["address"] or ""),
            "email": p["email"] or "",
            "insurer": p["insurer"] or "",
            "notes": rtf_to_text(p["legacy_notes"] or ""),
            "alert": rtf_to_text(p["legacy_alert"] or ""),
        }
    return base("Editar paciente", render_edit_patient_form(patient_id, values), "pacientes")


@app.post("/paciente/{patient_id}/editar", response_class=HTMLResponse)
async def edit_patient_save(patient_id: str, request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(raw, keep_blank_values=True)
    values = {k: (parsed.get(k, [""])[0] or "").strip() for k in (
        "name", "birth_date", "sex", "civil_status", "national_id", "phone",
        "address", "email", "insurer", "notes", "alert"
    )}
    name = re.sub(r"\s+", " ", values["name"]).strip().upper()
    values["name"] = name
    if not name:
        return HTMLResponse(
            base("Editar paciente", render_edit_patient_form(patient_id, values, "El nombre del paciente es obligatorio."), "pacientes"),
            status_code=400,
        )
    birth = values["birth_date"]
    if birth:
        try:
            datetime.strptime(birth, "%Y-%m-%d")
        except ValueError:
            return HTMLResponse(
                base("Editar paciente", render_edit_patient_form(patient_id, values, "La fecha de nacimiento no es válida."), "pacientes"),
                status_code=400,
            )

    national_id = values["national_id"]
    with db() as conn:
        current = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not current:
            raise HTTPException(404)
        merged_to = str(current["merged_into_patient_id"] or "").strip()
        if merged_to:
            return RedirectResponse(f"/paciente/{merged_to}/editar", status_code=303)

        if national_id:
            duplicate = conn.execute(
                "SELECT id,name FROM patients WHERE national_id_search=? AND id<>? AND COALESCE(merged_into_patient_id,'')='' LIMIT 1",
                (normalize_search(national_id), patient_id),
            ).fetchone()
            if duplicate:
                msg = f"Esa identificación ya pertenece a {duplicate['name']}. No se guardaron los cambios."
                return HTMLResponse(
                    base("Editar paciente", render_edit_patient_form(patient_id, values, msg), "pacientes"),
                    status_code=409,
                )

        before = {
            "name": current["name"] or "",
            "birth_date": current["birth_date"] or "",
            "sex": current["sex"] or "",
            "civil_status": current["civil_status"] or "",
            "national_id": current["national_id"] or "",
            "phone": current["phone"] or "",
            "address": current["address"] or "",
            "email": current["email"] or "",
            "insurer": current["insurer"] or "",
            "notes": current["legacy_notes"] or "",
            "alert": current["legacy_alert"] or "",
        }
        after = dict(values)
        changed = [key for key in after if str(before.get(key, "") or "") != str(after.get(key, "") or "")]
        stamp = now_iso()

        conn.execute(
            """UPDATE patients SET
                 name=?,name_search=?,birth_date=?,sex=?,civil_status=?,address=?,phone=?,
                 national_id=?,national_id_search=?,legacy_notes=?,legacy_alert=?,email=?,insurer=?,updated_at=?
               WHERE id=?""",
            (
                name, normalize_search(name), birth or None, values["sex"] or None,
                values["civil_status"] or None, values["address"] or None, values["phone"] or None,
                national_id or None, normalize_search(national_id) if national_id else "",
                values["notes"] or None, values["alert"] or None, values["email"] or None,
                values["insurer"] or None, stamp, patient_id,
            ),
        )
        conn.execute(
            """UPDATE waiting_queue
               SET display_name=?,identification=?,updated_at=?
               WHERE clinical_patient_id=? AND status IN ('waiting','in_consultation')""",
            (name, national_id or None, stamp, patient_id),
        )
        audit(conn, "update", "patient", patient_id, {"fields": changed})
        conn.commit()

    SYNC_SERVICE.mark_activity()
    SYNC_SERVICE.wake()
    return RedirectResponse(f"/paciente/{patient_id}", status_code=303)


@app.get("/pacientes", response_class=HTMLResponse)
def patients(q: str = Query(default="", max_length=120)):
    term = q.strip()
    with db() as conn:
        rows = search_patients(conn, term, limit=100) if term else []
    cards = "".join(
        f"""<a class="patient-row" href="/paciente/{e(r['id'])}"><div class="avatar">{e((r['name'] or '?')[:1])}</div><div class="patient-main"><b>{e(r['name'])}</b><span>{e(clean_legacy_id(r['national_id']) or 'Sin identificación')} · {e(r['phone'] or 'Sin teléfono')}</span></div><div class="patient-meta"><strong>{r['n_hist']}</strong><span>registro{'s' if r['n_hist']!=1 else ''}</span></div><div class="chev">›</div></a>"""
        for r in rows
    )
    if term and not rows:
        cards = "<div class='empty'><strong>No encontré pacientes.</strong><span>Pruebe con nombres en otro orden, parte de un apellido, identificación o teléfono.</span></div>"
    elif not term:
        cards = "<div class='empty'><strong>Empiece a escribir para buscar.</strong><span>Los resultados aparecen mientras escribe y los nombres pueden ponerse en cualquier orden.</span></div>"
    body = f"""
<section class="page-head page-head-with-action"><div><span class="eyebrow">PACIENTES</span><h1>Buscar historia clínica</h1><p>Búsqueda flexible por nombres, apellidos, identificación, teléfono o fecha de nacimiento.</p></div><a class="primary btn-link new-patient-btn" href="/pacientes/nuevo">+ Nuevo paciente</a></section>
<section class="search-card compact"><div class="patient-live-search" data-live-patient-search><form action="/pacientes" method="get"><div class="searchbox"><input name="q" value="{e(q)}" autofocus autocomplete="off" placeholder="Ej.: CARLOS BRAVO, BRAVO CARLOS, 099…"><button>Buscar</button></div></form><div class="live-search-results" hidden></div><p class="search-help">No importa el orden de los nombres. También puede escribir solo una parte de cada apellido.</p></div></section>
<section class="panel"><div class="panel-title"><h2>{len(rows) if term else ''} {'resultado' if len(rows)==1 else 'resultados' if term else 'Pacientes'}</h2>{'<span class="pill">Máximo 100</span>' if len(rows)==100 else ''}</div>{cards}</section>
"""
    return base("Pacientes", body, "pacientes")



def _v1370_encounter_has_documents(conn, encounter_id: str) -> bool:
    """Una consulta también tiene actividad clínica cuando emitió documentos."""
    encounter_id = str(encounter_id or "").strip()
    if not encounter_id:
        return False
    try:
        row = conn.execute(
            """SELECT 1
               FROM prescriptions
               WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
               UNION ALL
               SELECT 1
               FROM certificates
               WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
               LIMIT 1""",
            (encounter_id, encounter_id),
        ).fetchone()
        return bool(row)
    except sqlite3.OperationalError:
        return False


def _v1370_encounter_documents(encounter_id: str) -> list[dict]:
    encounter_id = str(encounter_id or "").strip()
    if not encounter_id:
        return []
    try:
        with db() as conn:
            rows = conn.execute(
                """SELECT 'rx' AS kind,id,issued_at,COALESCE(series_no,'') AS ref,
                          COALESCE(diagnosis,'') AS diagnosis,'' AS certificate_type
                   FROM prescriptions
                   WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
                   UNION ALL
                   SELECT 'cert' AS kind,id,issued_at,COALESCE(certificate_no,'') AS ref,
                          COALESCE(diagnosis,'') AS diagnosis,COALESCE(certificate_type,'medical') AS certificate_type
                   FROM certificates
                   WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
                   ORDER BY issued_at DESC""",
                (encounter_id, encounter_id),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _v1370_render_encounter_documents(encounter_id: str, compact: bool = False) -> str:
    docs = _v1370_encounter_documents(encounter_id)
    if not docs:
        return ""
    rows = []
    for item in docs:
        kind = str(item.get("kind") or "")
        doc_id = str(item.get("id") or "")
        issued = str(item.get("issued_at") or "")
        date_label = human_dt(issued) if issued else ""
        diagnosis = str(item.get("diagnosis") or "").strip()
        if kind == "rx":
            label = "Receta médica"
            ref = str(item.get("ref") or "").strip()
            detail = ("Serie " + ref) if ref else diagnosis
            url = f"/recetas/{e(doc_id)}/vista"
        else:
            cert_type = str(item.get("certificate_type") or "medical")
            label = "Certificado de reposo" if cert_type == "rest_isolation" else "Certificado médico"
            detail = diagnosis
            url = (
                f"/certificados/reposo/{e(doc_id)}/vista"
                if cert_type == "rest_isolation"
                else f"/certificados/{e(doc_id)}/vista"
            )
        meta = " · ".join(x for x in (date_label, detail) if x)
        print_kind = "recipe" if kind == "rx" else "certificate"
        print_button = (
            f"<button type='button' class='encounter-document-action primary' "
            f"data-print-url='{e(url)}' data-print-kind='{e(print_kind)}' "
            "onclick='historiaNativePrint(this.dataset.printUrl,this.dataset.printKind)'>"
            "Imprimir</button>"
        )
        rows.append(
            "<div class='encounter-document-row'>"
            + f"<span class='encounter-document-icon'>{'Rx' if kind == 'rx' else 'DOC'}</span>"
            + f"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>"
            + "<span class='encounter-document-actions'>"
            + f"<a class='encounter-document-action' href='{url}' target='_blank'>Ver</a>"
            + print_button
            + "</span></div>"
        )
    cls = " encounter-documents-compact" if compact else ""
    return (
        f"<section class='encounter-documents{cls}'>"
        "<div class='encounter-documents-title'><span>DOCUMENTOS DE ESTA CONSULTA</span>"
        f"<strong>{len(rows)}</strong></div>"
        + "".join(rows)
        + "</section>"
    )


def render_history_card(h, addenda, open_by_default=False):
    note = display_text(h["clinical_note"])
    status = h["note_status"] or ("legacy" if h["is_legacy_locked"] else "signed")
    segment_html, detected_dates, _segment_count = render_legacy_segments(h["clinical_note"], h["encounter_date"]) if status == "legacy" else ("", 0, 0)
    if detected_dates:
        note_block = f"<div class='legacy-segments history-legacy-segments'>{segment_html}</div>"
    else:
        note_block = note or '<em>Sin texto</em>'
    add_html = "".join(
        f"<div class='addendum'><div><strong>Continuación de historia</strong><time>{e(human_dt(a['created_at']))}</time></div><p>{display_text(a['text'])}</p></div>" for a in addenda
    )
    documents_html = _v1370_render_encounter_documents(h["id"])
    actions = f"<a class='text-btn' href='/encuentro/{e(h['id'])}/imprimir?print_now=1' target='_blank'>Imprimir</a>"
    # Los registros importados permanecen de solo lectura. Las notas nuevas sí
    # admiten complementos sin alterar el contenido firmado.
    if status == "signed":
        actions += f"<button class='text-btn js-addendum' data-id='{e(h['id'])}'>Seguir editando historia</button>"
    summary_title = clean_title(h["clinical_note"], "Registro clínico")
    date_label = human_date(h["encounter_date"]) or h["encounter_date"] or "Sin fecha"
    time_label = (h["encounter_time"] or "")[:5]
    origin = "Registro histórico" if status == "legacy" else "Consulta registrada"
    return f"""
<article class="history-card cp-history-card{' open' if open_by_default else ''}">
  <button class="history-toggle cp-history-toggle" onclick="this.parentElement.classList.toggle('open')">
    <div class="cp-history-toggle-main">
      <div class="cp-history-date"><span>Fecha de consulta:</span><strong>{e(date_label)}</strong>{f'<time>{e(time_label)}</time>' if time_label else ''}</div>
      <b>{e(summary_title)}</b>
      <small>{origin}</small>
    </div>
    <span class="cp-chevron">⌄</span>
  </button>
  <div class="history-content cp-history-content">
    <div class='history-actions'>{actions}</div>
    <div class="cp-note-frame">
      <div class="cp-note-title">Historia / evolución</div>
      <div class="cp-note-body">{note_block}</div>
    </div>
    {documents_html}
    {add_html}
  </div>
</article>
"""


@app.get("/paciente/{patient_id}", response_class=HTMLResponse)
def patient(patient_id: str, histq: str = Query(default="", max_length=100)):
    term = histq.strip()
    with db() as conn:
        p = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not p: raise HTTPException(404)
        merged_to = str(p["merged_into_patient_id"] or "").strip()
        if merged_to:
            return RedirectResponse(f"/paciente/{merged_to}", status_code=303)
        all_histories = conn.execute(
            "SELECT * FROM encounters WHERE patient_id=? AND note_status!='draft' ORDER BY encounter_date DESC, encounter_time DESC, legacy_history_id DESC",
            (patient_id,),
        ).fetchall()
        if term:
            like = f"%{term}%"
            histories = conn.execute("""
                SELECT * FROM encounters WHERE patient_id=? AND
                note_status!='draft' AND (clinical_note LIKE ? OR legacy_history_t LIKE ?)
                ORDER BY encounter_date DESC, encounter_time DESC, legacy_history_id DESC
            """, (patient_id, like, like)).fetchall()
        else:
            histories = all_histories
        total_histories = len(all_histories)
        active_edit = conn.execute("""
            SELECT id,updated_at FROM encounters
            WHERE patient_id=? AND note_status='draft'
              AND COALESCE(deleted_at,'')=''
              AND (
                TRIM(COALESCE(clinical_note,''))<>''
                OR TRIM(COALESCE(diagnosis,''))<>''
                OR TRIM(COALESCE(treatment,''))<>''
                OR EXISTS (SELECT 1 FROM prescriptions r WHERE r.encounter_id=encounters.id AND COALESCE(r.deleted_at,'')='')
                OR EXISTS (SELECT 1 FROM certificates c WHERE c.encounter_id=encounters.id AND COALESCE(c.deleted_at,'')='')
              )
            ORDER BY updated_at DESC LIMIT 1
        """, (patient_id,)).fetchone()
        last_signed = all_histories[0] if all_histories else None
        addenda_rows = conn.execute("SELECT * FROM encounter_addenda WHERE encounter_id IN (SELECT id FROM encounters WHERE patient_id=?) ORDER BY created_at", (patient_id,)).fetchall()
        audit(conn, "view", "patient", patient_id)
        conn.commit()

    addenda_by = {}
    for a in addenda_rows:
        addenda_by.setdefault(a["encounter_id"], []).append(a)

    age = age_from_birth(p["birth_date"])
    ident = clean_legacy_id(p["national_id"])
    alert_text = rtf_to_text(p["legacy_alert"] or "").strip()
    alert_html = f"<section class='alert-card patient-alert'><strong>Alerta clínica</strong><span>{display_text(alert_text)}</span></section>" if alert_text else ""

    timeline = "".join(render_history_card(h, addenda_by.get(h["id"], []), open_by_default=(i == 0)) for i, h in enumerate(histories))
    last_date = human_date(last_signed["encounter_date"]) if last_signed else "Sin registros"

    consult_action = (
        f'<a class="primary btn-link cp-new-consult" href="/paciente/{e(patient_id)}/nueva?encounter_id={e(active_edit["id"])}">Continuar consulta</a>'
        if active_edit else
        f'<a class="primary btn-link cp-new-consult" href="/paciente/{e(patient_id)}/nueva">+ Nueva consulta</a>'
    )
    action = (
        f"<div class='cp-patient-actions'>"
        f"<a class='secondary btn-link cp-edit-patient' href='/paciente/{e(patient_id)}/editar'>Editar datos</a>"
        f"<a class='secondary btn-link cp-prescription' target='_blank' href='/recetas/nueva?patient_id={e(patient_id)}'>Receta médica</a>"
        f"<a class='secondary btn-link cp-certificate' target='_blank' href='/certificados/nuevo?patient_id={e(patient_id)}'>Certificado médico</a>"
        f"{consult_action}</div>"
    )

    def value_or_empty(value, transform=False):
        if not value:
            return "<span class='cp-empty-value'>No registrado</span>"
        return display_text(value) if transform else e(value)

    body = f"""
<div class="legacy-remaster">
<a class="back cp-back" href="/pacientes">← Volver a pacientes</a>
<section class="cp-patient-card">
  <div class="cp-box-caption">Identificación</div>
  <div class="cp-patient-topline">
    <div class="cp-name-field"><label>Nombre:</label><div>{e(p['name'])}</div></div>
    <div class="cp-short-field"><label>Sexo:</label><div>{e(sex_label(p['sex']) or '—')}</div></div>
    <div class="cp-short-field age"><label>Edad:</label><div>{e(str(age) + ' años') if age else '—'}</div></div>
    <div class="cp-id-field"><label>ID Num:</label><div>{value_or_empty(ident)}</div></div>
    <div class="cp-patient-action">{action}</div>
  </div>
  <div class="cp-patient-grid">
    <div class="cp-data-field"><label>Fecha de nacimiento</label><div>{value_or_empty(human_date(p['birth_date']))}</div></div>
    <div class="cp-data-field"><label>Teléfono</label><div>{value_or_empty(p['phone'])}</div></div>
    <div class="cp-data-field wide"><label>Domicilio</label><div>{value_or_empty(p['address'], True)}</div></div>
    <div class="cp-data-field"><label>Estado civil</label><div>{value_or_empty(p['civil_status'])}</div></div>
    <div class="cp-data-field"><label>Email</label><div>{value_or_empty(p['email'])}</div></div>
    <div class="cp-data-field wide"><label>Aseguradora</label><div>{value_or_empty(p['insurer'])}</div></div>
  </div>
  {f'<div class="cp-observations"><label>Otros datos / observaciones</label><div>{display_text(p["legacy_notes"])}</div></div>' if p['legacy_notes'] else ''}
</section>
{alert_html}
<section class="cp-history-window">
  <div class="cp-history-window-head">
    <div class="cp-history-titlebar"><span>Historia Clínica:</span></div>
    <div class="cp-history-summary"><span>Último control</span><strong>{e(last_date)}</strong></div>
    <div class="cp-history-summary"><span>Número de registros</span><strong>{total_histories}</strong></div>
  </div>
  <div class="cp-history-tools">
    <div><strong>Historial del paciente</strong><span>Los controles más recientes aparecen primero.</span></div>
    <form class='history-search cp-history-search' method='get'><input name='histq' value='{e(histq)}' placeholder='Buscar dentro del historial clínico…'><button>Buscar</button>{f"<a href='/paciente/{e(patient_id)}'>Limpiar</a>" if term else ''}</form>
  </div>
  <section class="timeline cp-timeline">{timeline if timeline else '<div class="empty"><strong>No hay registros que coincidan.</strong><span>Pruebe otra palabra o limpie la búsqueda.</span></div>'}</section>
</section>
<div id='addendum-modal' class='modal-backdrop' hidden><div class='modal'><h3>Seguir editando historia</h3><p>Escriba la continuación. Se guardará con su propia fecha y hora sin modificar lo que ya fue finalizado.</p><textarea id='addendum-text' rows='7' placeholder='Continúe escribiendo la historia clínica…'></textarea><div class='modal-actions'><button class='secondary' id='cancel-addendum'>Cancelar</button><button class='primary' id='save-addendum'>Guardar continuación</button></div></div></div>
</div>
"""
    script = """<script>
let addendumId=null; const modal=document.getElementById('addendum-modal');
document.querySelectorAll('.js-addendum').forEach(b=>b.addEventListener('click',()=>{addendumId=b.dataset.id;modal.hidden=false;document.getElementById('addendum-text').focus()}));
document.getElementById('cancel-addendum')?.addEventListener('click',()=>{modal.hidden=true;document.getElementById('addendum-text').value=''})
document.getElementById('save-addendum')?.addEventListener('click',async()=>{const text=document.getElementById('addendum-text').value.trim();if(!text)return;const r=await fetch('/encuentro/'+addendumId+'/addendum',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});if(r.ok) location.reload(); else showAppToast('No se pudo guardar la continuación de la historia.','error')});
</script>"""
    return base(p["name"], body, "pacientes", extra_script=script)


@app.get("/paciente/{patient_id}/nueva", response_class=HTMLResponse)
def new_consultation(patient_id: str, encounter_id: str = "", queue_id: str = ""):
    with db() as conn:
        p = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not p: raise HTTPException(404)
        merged_to = str(p["merged_into_patient_id"] or "").strip()
        if merged_to:
            params = []
            if encounter_id:
                params.append("encounter_id=" + str(encounter_id))
            if queue_id:
                params.append("queue_id=" + str(queue_id))
            suffix = ("?" + "&".join(params)) if params else ""
            return RedirectResponse(f"/paciente/{merged_to}/nueva{suffix}", status_code=303)
        working = None
        if encounter_id:
            working = conn.execute("SELECT * FROM encounters WHERE id=? AND patient_id=?", (encounter_id, patient_id)).fetchone()
            if not working or working["note_status"] != "draft": raise HTTPException(404)
        else:
            # Recuperación silenciosa: una consulta no finalizada nunca se pierde,
            # pero no se presenta al doctor como un sistema de "borradores".
            working = conn.execute("SELECT * FROM encounters WHERE patient_id=? AND note_status='draft' ORDER BY updated_at DESC LIMIT 1", (patient_id,)).fetchone()
        previous_rows = conn.execute(
            "SELECT * FROM encounters WHERE patient_id=? AND note_status IN ('signed','legacy') ORDER BY encounter_date DESC, encounter_time DESC, updated_at DESC",
            (patient_id,),
        ).fetchall()
        previous = previous_rows[0] if previous_rows else None
        macros = conn.execute("SELECT * FROM macros ORDER BY label COLLATE NOCASE").fetchall()
        working_has_documents = bool(working and _v1370_encounter_has_documents(conn, working["id"]))

        if working and not queue_id:
            queue_id = str(working["queue_id"] or "")

        queue_context = None
        queue_turn = None
        queue_attention = ""
        if queue_id:
            queue_context = conn.execute(
                "SELECT * FROM waiting_queue WHERE id=? LIMIT 1",
                (queue_id,),
            ).fetchone()
            if queue_context:
                queue_turn = _queue_turn_number(conn, queue_id)
                queue_attention = _queue_display_type(queue_context)

    dt = datetime.now()
    date_value = working["encounter_date"] if working else dt.strftime("%Y-%m-%d")
    time_value = working["encounter_time"] if working else dt.strftime("%H:%M")
    note_value = (rtf_to_text(working["clinical_note"]) if working else "").upper()
    age = age_from_birth(p["birth_date"])
    info = []
    if age: info.append(f"{age} años")
    if p["sex"]: info.append(e(p["sex"]))
    if p["national_id"]: info.append("ID " + e(p["national_id"]))
    if p["phone"]: info.append(e(p["phone"]))

    queue_badges = []
    if queue_turn:
        queue_badges.append(f"<span class='consult-turn-badge'>TURNO #{queue_turn}</span>")
    if queue_attention == "Nuevo":
        queue_badges.append("<span class='consult-new-patient-badge'>★ PACIENTE NUEVO</span>")
    elif queue_attention:
        queue_badges.append(f"<span class='consult-attention-badge'>{e(queue_attention).upper()}</span>")
    queue_badges_html = "".join(queue_badges)

    previous_json = json.dumps({
        "id": previous["id"] if previous else None,
        "note": rtf_to_text(previous["clinical_note"]) if previous else "",
        "date": previous["encounter_date"] if previous else "",
        "time": previous["encounter_time"] if previous else "",
        "source": previous["source"] if previous else "",
    }, ensure_ascii=False)
    macros_json = json.dumps([{"label":m["label"],"text":m["text"]} for m in macros], ensure_ascii=False)
    recovered = bool(working)
    if previous_rows:
        with db() as _prev_conn:
            _previous_addenda_rows = _prev_conn.execute(
                """SELECT a.*
                   FROM encounter_addenda a
                   JOIN encounters e ON e.id=a.encounter_id
                   WHERE e.patient_id=?
                   ORDER BY a.created_at""",
                (patient_id,),
            ).fetchall()
        _previous_addenda_by = {}
        for _a in _previous_addenda_rows:
            _previous_addenda_by.setdefault(_a["encounter_id"], []).append(_a)

        previous_cards = []
        for index, h in enumerate(previous_rows):
            is_legacy = h["source"] == "legacy_consulta_practica"
            segment_html, detected_dates, _segment_count = render_legacy_segments(
                h["clinical_note"], h["encounter_date"]
            ) if is_legacy else ("", 0, 0)

            if is_legacy and detected_dates:
                record_body = f"<div class='legacy-segments'>{segment_html}</div>"
            else:
                record_text = display_text(h["clinical_note"]) or "<em>Sin texto registrado</em>"
                record_body = f"<div class='previous-record-text'>{record_text}</div>"

            _continuations = _previous_addenda_by.get(h["id"], [])
            if _continuations:
                _continuation_html = "".join(
                    "<div style='margin-top:10px;padding:9px 10px;border:1px solid #e7d5b3;background:#fff8ea;border-radius:7px'>"
                    "<div style='display:flex;justify-content:space-between;gap:10px;margin-bottom:5px'>"
                    "<strong style='font-size:11px'>Continuación de historia</strong>"
                    f"<time style='font-size:10px;color:#64748b'>{e(human_dt(_a['created_at']))}</time>"
                    "</div>"
                    f"<div class='previous-record-text'>{display_text(_a['text'])}</div>"
                    "</div>"
                    for _a in _continuations
                )
                record_body += _continuation_html

            record_body += _v1370_render_encounter_documents(h["id"], compact=True)

            date_label = human_date(h["encounter_date"]) or h["encounter_date"] or "Sin fecha"
            time_label = (h["encounter_time"] or "")[:5]
            title = clean_title(h["clinical_note"], "Registro clínico")
            origin = "Histórico importado" if is_legacy else "Consulta registrada"
            open_attr = " open" if index == 0 else ""

            previous_cards.append(f"""
            <details class='previous-record'{open_attr}>
              <summary>
                <span class='previous-record-date'><b>{e(date_label)}</b>{f"<time>{e(time_label)}</time>" if time_label else ""}</span>
                <span class='previous-record-summary'><strong>{e(title)}</strong><small>{origin}</small></span>
                <span class='previous-record-chevron'>⌄</span>
              </summary>
              <div class='previous-record-body'>{record_body}</div>
            </details>
            """)

        previous_panel = f"""
<aside class='previous-panel'>
  <div class='previous-panel-head simple'>
    <div><h2>Historial anterior</h2><span class='previous-count'>{len(previous_rows)} registro{"s" if len(previous_rows) != 1 else ""}</span></div>
    <a class='text-btn' href='/paciente/{e(patient_id)}'>Ver historia completa</a>
  </div>
  <div class='previous-scroll clean-reference previous-record-list'>
    {"".join(previous_cards)}
  </div>
</aside>
"""
    else:
        previous_panel = f"""
<aside class='previous-panel previous-empty'>
  <div class='previous-panel-head simple'><h2>Historial anterior</h2></div>
  <div class='empty previous-empty-state'><strong>Sin registros anteriores</strong><span>Esta será la primera consulta registrada para este paciente.</span></div>
</aside>
"""
    body = f"""
<a class='back' href='/paciente/{e(patient_id)}'>← Volver a la historia clínica</a>
<section class='consult-patient-bar'>
  <div class='avatar'>{e((p['name'] or '?')[:1])}</div>
  <div class='consult-patient-copy'><div class='consult-queue-badges'>{queue_badges_html}</div><span class='eyebrow'>CONSULTA MÉDICA</span><h1>{e(p['name'])}</h1><div class='consult-meta'>{''.join(f'<span>{x}</span>' for x in info)}</div></div>
  <div id='save-state' class='save-state saved'>Autoguardado activo</div>
</section>
{"<div class='recovery-note'>Se recuperó automáticamente la consulta que estaba en edición. Puede continuar donde la dejó.</div>" if recovered else ""}
<section class='editor-layout comparison-layout'>
<div class='editor-main clinical-editor'>
  <div class='editor-section-head'><div><h2>Nueva consulta</h2></div><div class='date-fields'><label>Fecha<input id='enc-date' type='date' value='{e(date_value)}'></label><label>Hora<input id='enc-time' type='time' value='{e(time_value)}'></label></div></div>
  <div class='consult-tools'><button id='toggle-macros' class='secondary'>Frases rápidas</button></div>
  <label class='editor-field main-note single-note'><span>Historia / evolución</span><textarea id='clinical-note' autofocus rows='22' placeholder='Escriba aquí la consulta, evolución, hallazgos, diagnóstico, tratamiento e indicaciones…'>{e(note_value)}</textarea></label>
  <div class='editor-footer'><div class='autosave-help'>Los cambios se guardan automáticamente.</div><div class='editor-actions'><button id='save-now' class='secondary'>Guardar</button><button id='sign-note' class='primary finish-btn'>Finalizar consulta</button></div></div>
</div>
{previous_panel}
</section>
<aside id='macro-panel' class='macro-panel macro-drawer' hidden><div class='macro-head'><div><span class='section-kicker'>Apoyo de escritura</span><strong>Frases rápidas</strong></div><div class='macro-head-actions'><a href='/macros' target='_blank'>Administrar</a><button id='close-macros' class='drawer-close' type='button' aria-label='Cerrar'>×</button></div></div><p>Haga clic en el campo donde desea insertar la frase y luego selecciónela.</p><div id='macro-list'></div></aside>
<div id='finalize-modal' class='modal-backdrop clinical-confirm' hidden><div class='modal'><span class='section-kicker'>FINALIZAR ATENCIÓN</span><h3>¿Finalizar esta consulta?</h3><p>La consulta quedará cerrada. Si después necesita agregar algo, podrá usar <b>Seguir editando historia</b> sin alterar el registro original.</p><div class='modal-actions'><button class='secondary' id='cancel-finalize' type='button'>Seguir editando</button><button class='primary' id='confirm-finalize' type='button'>Finalizar consulta</button></div></div></div>
<div id='leave-consult-modal' class='modal-backdrop clinical-confirm leave-consult-confirm' hidden><div class='modal'><span class='section-kicker'>CONSULTA ABIERTA</span><h3>Hay una consulta sin finalizar</h3><p>Lo escrito ya está protegido por el autoguardado. Para evitar que la consulta quede olvidada, finalícela antes de volver al Inicio.</p><div class='modal-actions'><button class='secondary' id='stay-consult' type='button'>Seguir escribiendo</button><button class='primary finish-btn' id='finish-and-home' type='button'>Finalizar consulta y volver al Inicio</button></div></div></div>
"""
    script = r"""<script>
const PATIENT_ID=__PATIENT_ID__, QUEUE_ID=__QUEUE_ID__, PREVIOUS=__PREVIOUS__, MACROS=__MACROS__;
let encounterId=__WORKING_ID__ || null, timer=null, dirty=false, leavingAfterFinalize=false, documentActivity=__HAS_DOCUMENTS__;
const state=document.getElementById('save-state');
const noteEl=document.getElementById('clinical-note');
const finalizeModal=document.getElementById('finalize-modal');
const leaveModal=document.getElementById('leave-consult-modal');
const signBtn=document.getElementById('sign-note');
const confirmFinalize=document.getElementById('confirm-finalize');
const cancelFinalize=document.getElementById('cancel-finalize');
const stayConsult=document.getElementById('stay-consult');
const finishAndHome=document.getElementById('finish-and-home');
let lastFocused=noteEl;
window.addEventListener('message',ev=>{
  if(ev.origin!==location.origin)return;
  const data=ev.data||{};
  if(data.type!=='clinical-document-saved')return;
  if(data.encounter_id)encounterId=String(data.encounter_id);
  documentActivity=true;
  state.textContent='Documento guardado en esta consulta';
  state.className='save-state saved';
});

function upperClinical(el){
  const start=el.selectionStart, end=el.selectionEnd;
  const value=String(el.value||'').toUpperCase();
  if(el.value!==value){
    el.value=value;
    try{el.setSelectionRange(start,end)}catch(_e){}
  }
}
upperClinical(noteEl);

noteEl.addEventListener('focus',()=>lastFocused=noteEl);
noteEl.addEventListener('input',()=>{upperClinical(noteEl);changed()});
['enc-date','enc-time'].forEach(id=>document.getElementById(id).addEventListener('change',changed));

function changed(){
  dirty=true;
  state.textContent='Guardando cambios…';
  state.className='save-state saving';
  clearTimeout(timer);
  timer=setTimeout(()=>save(false).catch(()=>{}),900);
}

function payload(manual=false){
  return {
    encounter_id:encounterId,
    patient_id:PATIENT_ID,
    queue_id:QUEUE_ID,
    encounter_date:document.getElementById('enc-date').value,
    encounter_time:document.getElementById('enc-time').value,
    clinical_note:String(noteEl.value||'').toUpperCase(),
    manual_snapshot:manual
  };
}

async function save(manual=false){
  if(documentActivity && encounterId && !String(noteEl.value||'').trim()){
    dirty=false;
    if(manual){state.textContent='Documento guardado · sin texto adicional';state.className='save-state saved'}
    return encounterId;
  }
  if(!dirty && encounterId){
    if(manual){state.textContent='Todo guardado';state.className='save-state saved'}
    return encounterId;
  }
  state.textContent='Guardando…';
  state.className='save-state saving';
  try{
    const r=await fetch('/api/encounters/save',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload(manual))
    });
    if(!r.ok){
      let detail='', raw='';
      try{
        raw=await r.text();
        try{
          const j=JSON.parse(raw);
          detail=String(j.detail||j.error||'');
        }catch(_e){
          if(raw && raw!=='Internal Server Error')detail=String(raw).slice(0,240);
        }
      }catch(_e){}
      throw new Error(
        detail
          ? ('No se pudo guardar: '+detail)
          : ('No se pudo guardar la consulta (HTTP '+r.status+').')
      );
    }
    const j=await r.json();
    if(j.empty){
      encounterId=null;
      dirty=false;
      state.textContent='Sin contenido clínico que guardar';
      state.className='save-state saved';
      return null;
    }
    encounterId=j.encounter_id;
    dirty=false;
    state.textContent='Guardado '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    state.className='save-state saved';
    return encounterId;
  }catch(_e){
    state.textContent='No se pudo guardar';
    state.className='save-state error';
    throw _e;
  }
}

function keepaliveSave(){
  if(!dirty)return;
  try{
    fetch('/api/encounters/save',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload(false)),
      keepalive:true
    }).catch(()=>{});
  }catch(_e){}
}

document.getElementById('save-now').addEventListener('click',async()=>{
  dirty=true;
  try{await save(true)}catch(_e){}
});
document.addEventListener('keydown',async e=>{
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){
    e.preventDefault();dirty=true;
    try{await save(true)}catch(_e){}
  }
});

const macroPanel=document.getElementById('macro-panel');
document.getElementById('toggle-macros').addEventListener('click',()=>{macroPanel.hidden=!macroPanel.hidden});
document.getElementById('close-macros').addEventListener('click',()=>{macroPanel.hidden=true});
const ml=document.getElementById('macro-list');
if(!MACROS.length){
  ml.innerHTML='<div class="empty small"><strong>No hay frases creadas.</strong><span>Puede agregarlas desde Administrar.</span></div>';
}else{
  MACROS.forEach(m=>{
    const b=document.createElement('button');
    b.className='macro-btn';b.type='button';
    b.innerHTML='<b>'+escapeHtml(m.label)+'</b><span>'+escapeHtml(String(m.text||'').slice(0,90))+'</span>';
    b.onclick=()=>{
      const el=noteEl,start=el.selectionStart,end=el.selectionEnd,before=el.value.slice(0,start),after=el.value.slice(end);
      const spacer=before && !before.endsWith('\n')?'\n':'';
      const insertion=String(m.text||'').toUpperCase();
      el.value=(before+spacer+insertion+after).toUpperCase();
      el.focus();
      el.selectionStart=el.selectionEnd=(before+spacer+insertion).length;
      changed();
    };
    ml.appendChild(b);
  });
}
function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}

function hasOpenConsultation(){
  // Una consulta vacía nunca debe atrapar al doctor.
  // El simple hecho de que exista un borrador/encounterId no cuenta como
  // contenido clínico pendiente. Sólo protegemos texto real o cambios hechos.
  return Boolean(String(noteEl.value||'').trim() || dirty || documentActivity);
}

async function finalizeAndHome(button){
  const original=button?.textContent||'Finalizar consulta';
  if(button){button.disabled=true;button.textContent='Finalizando…'}
  signBtn.disabled=true;
  try{
    upperClinical(noteEl);
    const hasText=Boolean(String(noteEl.value||'').trim());
    if(!hasText && !documentActivity){
      const r=await fetch('/api/encounters/empty/complete',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({encounter_id:encounterId,patient_id:PATIENT_ID,queue_id:QUEUE_ID})
      });
      if(!r.ok){
        let msg='No se pudo cerrar la atención vacía.';
        try{const j=await r.json();if(j.detail)msg+=' '+j.detail}catch(_e){}
        throw new Error(msg);
      }
      encounterId=null;dirty=false;leavingAfterFinalize=true;location.href='/';return;
    }

    let id=encounterId;
    if(hasText){
      dirty=true;
      id=await save(true);
    }
    if(!id)throw new Error('No se pudo identificar la consulta para finalizarla.');
    const r=await fetch('/api/encounters/'+encodeURIComponent(id)+'/sign',{method:'POST'});
    if(!r.ok){
      let msg='No se pudo finalizar la consulta.';
      try{const j=await r.json();if(j.detail)msg+=' '+j.detail}catch(_e){}
      throw new Error(msg);
    }
    dirty=false;leavingAfterFinalize=true;location.href='/';
  }catch(err){
    if(button){button.disabled=false;button.textContent=original}
    signBtn.disabled=false;finalizeModal.hidden=true;leaveModal.hidden=true;
    showAppToast(err && err.message ? err.message : 'No se pudo finalizar la consulta.','error');
  }
}

signBtn.addEventListener('click',()=>{
  const blank=!String(noteEl.value||'').trim() && !documentActivity;
  const title=finalizeModal.querySelector('h3');
  const text=finalizeModal.querySelector('p');
  if(blank){
    if(title)title.textContent='¿Finalizar esta atención sin historia?';
    if(text)text.textContent='No se creará una historia clínica vacía. La atención se cerrará y dejará de aparecer como pendiente.';
  }else{
    if(title)title.textContent='¿Finalizar esta consulta?';
    if(text)text.innerHTML='La consulta quedará cerrada. Si después necesita agregar algo, podrá usar <b>Seguir editando historia</b> sin alterar el registro original.';
  }
  finalizeModal.hidden=false;
});
cancelFinalize.addEventListener('click',()=>{finalizeModal.hidden=true;signBtn.focus()});
finalizeModal.addEventListener('click',e=>{if(e.target===finalizeModal)finalizeModal.hidden=true});
confirmFinalize.addEventListener('click',()=>finalizeAndHome(confirmFinalize));

stayConsult.addEventListener('click',()=>{leaveModal.hidden=true;noteEl.focus()});
finishAndHome.addEventListener('click',()=>{
  finalizeAndHome(finishAndHome);
});

// Evita que el doctor abandone una consulta escrita sin darse cuenta.
document.addEventListener('click',e=>{
  const a=e.target.closest('a[href]');
  if(!a || a.target==='_blank' || a.hasAttribute('download'))return;
  let url;
  try{url=new URL(a.href,location.href)}catch(_e){return}
  if(url.origin!==location.origin)return;
  if(!hasOpenConsultation())return;
  e.preventDefault();
  save(false).catch(()=>{});
  leaveModal.hidden=false;
},{capture:true});

document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){
    if(!finalizeModal.hidden)finalizeModal.hidden=true;
    if(!leaveModal.hidden)leaveModal.hidden=true;
  }
});

// El debounce guarda al parar de escribir y este reloj garantiza guardado
// aunque el doctor escriba de forma continua durante varios minutos.
setInterval(()=>{if(dirty)save(false).catch(()=>{})},5000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&dirty)save(false).catch(()=>{})});
window.addEventListener('pagehide',()=>{if(!leavingAfterFinalize)keepaliveSave()});
</script>"""
    script = (
        script.replace("__PATIENT_ID__", json.dumps(patient_id))
        .replace("__QUEUE_ID__", json.dumps(queue_id))
        .replace("__PREVIOUS__", previous_json)
        .replace("__MACROS__", macros_json)
        .replace("__WORKING_ID__", json.dumps(working["id"] if working else ""))
        .replace("__HAS_DOCUMENTS__", "true" if working_has_documents else "false")
    )
    return base("Nueva consulta", body, "pacientes", extra_script=script)


def _v1364_log_save_error(context: str, exc: Exception):
    """Registra errores técnicos sin escribir texto clínico ni datos del paciente."""
    try:
        path = ROOT / "data" / "save_errors.log"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{now_iso()} [{context}] {type(exc).__name__}: {exc}\n")
    except Exception:
        pass


def _v1364_ensure_encounter_schema(conn):
    """Compatibilidad aditiva para SQLite antiguas/restauradas."""
    required = [
        ("encounters", "encounter_date", "encounter_date TEXT"),
        ("encounters", "encounter_time", "encounter_time TEXT"),
        ("encounters", "clinical_note", "clinical_note TEXT"),
        ("encounters", "diagnosis", "diagnosis TEXT"),
        ("encounters", "treatment", "treatment TEXT"),
        ("encounters", "source", "source TEXT"),
        ("encounters", "source_record_hash", "source_record_hash TEXT"),
        ("encounters", "is_legacy_locked", "is_legacy_locked INTEGER DEFAULT 0"),
        ("encounters", "created_at", "created_at TEXT"),
        ("encounters", "updated_at", "updated_at TEXT"),
        ("encounters", "deleted_at", "deleted_at TEXT"),
        ("encounters", "note_status", "note_status TEXT NOT NULL DEFAULT 'signed'"),
        ("encounters", "signed_at", "signed_at TEXT"),
        ("encounters", "signed_by", "signed_by TEXT"),
        ("encounters", "copied_from_encounter_id", "copied_from_encounter_id TEXT"),
        ("encounters", "queue_id", "queue_id TEXT"),
        ("encounters", "created_by", "created_by TEXT"),
    ]
    for table, col, ddl in required:
        ensure_column(conn, table, col, ddl)


def _v1364_save_revision_best_effort(encounter_id, stamp, note, diagnosis, treatment, reason):
    try:
        with db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS encounter_revisions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
                  revision_no INTEGER NOT NULL,
                  saved_at TEXT NOT NULL,
                  actor TEXT,
                  clinical_note TEXT,
                  diagnosis TEXT,
                  treatment TEXT,
                  reason TEXT,
                  UNIQUE(encounter_id, revision_no)
                )
            """)
            rev = conn.execute(
                "SELECT COALESCE(MAX(revision_no),0)+1 FROM encounter_revisions WHERE encounter_id=?",
                (encounter_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO encounter_revisions(encounter_id,revision_no,saved_at,actor,clinical_note,diagnosis,treatment,reason) VALUES(?,?,?,?,?,?,?,?)",
                (encounter_id, rev, stamp, DOCTOR_NAME, note, diagnosis, treatment, reason),
            )
            conn.commit()
    except Exception as exc:
        _v1364_log_save_error("revision", exc)


def _v1364_audit_best_effort(action, entity_type, entity_id, details):
    try:
        with db() as conn:
            audit(conn, action, entity_type, entity_id, details)
            conn.commit()
    except Exception as exc:
        _v1364_log_save_error("audit", exc)


def _v1368_has_clinical_content(note="", diagnosis="", treatment="") -> bool:
    """Una atención vacía no es una historia clínica pendiente."""
    return bool(
        str(note or "").strip()
        or str(diagnosis or "").strip()
        or str(treatment or "").strip()
    )


def _v1368_reset_queue_after_empty_save(queue_id, stamp):
    """Un guardado vacío no debe dejar artificialmente el turno 'En consulta'."""
    if not queue_id:
        return
    try:
        with db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(waiting_queue)")}
            if "status" not in cols or "id" not in cols:
                return
            sets = ["status='waiting'"]
            params = []
            if "completed_at" in cols:
                sets.append("completed_at=NULL")
            if "updated_at" in cols:
                sets.append("updated_at=?")
                params.append(stamp)
            params.append(queue_id)
            conn.execute(
                f"UPDATE waiting_queue SET {','.join(sets)} "
                "WHERE id=? AND status='in_consultation'",
                params,
            )
            conn.commit()
    except Exception as exc:
        _v1364_log_save_error("empty_queue_reset", exc)


def _v1364_queue_best_effort(queue_id, patient_id, status, stamp):
    """La cola nunca debe impedir guardar o firmar la historia clínica."""
    if not queue_id:
        return
    try:
        with db() as conn:
            # Intentamos reparar columnas, pero si una migración secundaria falla,
            # todavía actualizamos todas las columnas existentes.
            for col, ddl in (
                ("started_at", "started_at TEXT"),
                ("completed_at", "completed_at TEXT"),
                ("clinical_patient_id", "clinical_patient_id TEXT"),
                ("updated_at", "updated_at TEXT"),
                ("status", "status TEXT"),
            ):
                try:
                    ensure_column(conn, "waiting_queue", col, ddl)
                except Exception as exc:
                    _v1364_log_save_error(f"queue_schema_{col}", exc)

            cols = {r[1] for r in conn.execute("PRAGMA table_info(waiting_queue)")}
            sets = []
            params = []
            if "status" in cols:
                sets.append("status=?")
                params.append(status)
            if status == "in_consultation" and "started_at" in cols:
                sets.append("started_at=COALESCE(started_at,?)")
                params.append(stamp)
            if status == "completed" and "completed_at" in cols:
                sets.append("completed_at=?")
                params.append(stamp)
            if patient_id and "clinical_patient_id" in cols:
                sets.append("clinical_patient_id=COALESCE(clinical_patient_id,?)")
                params.append(patient_id)
            if "updated_at" in cols:
                sets.append("updated_at=?")
                params.append(stamp)

            if sets and "id" in cols:
                params.append(queue_id)
                conn.execute(
                    f"UPDATE waiting_queue SET {','.join(sets)} WHERE id=?",
                    params,
                )
                conn.commit()
    except Exception as exc:
        _v1364_log_save_error("queue_update", exc)


@app.post("/api/encounters/save")
async def save_encounter(request: Request):
    try:
        data = await request.json()
        patient_id = (data.get("patient_id") or "").strip()
        if not patient_id:
            raise HTTPException(400, "Falta el paciente.")
        enc_id = (data.get("encounter_id") or "").strip() or new_id()
        enc_date = data.get("encounter_date") or datetime.now().strftime("%Y-%m-%d")
        enc_time = data.get("encounter_time") or datetime.now().strftime("%H:%M")
        note = str(data.get("clinical_note") or "").upper()
        diagnosis = (str(data.get("diagnosis") or "").upper() if "diagnosis" in data else None)
        treatment = (str(data.get("treatment") or "").upper() if "treatment" in data else None)
        copied = data.get("copied_from_encounter_id") or None
        queue_id = data.get("queue_id") or None
        manual = bool(data.get("manual_snapshot"))
        stamp = now_iso()
        created = False
        empty_queue_id = queue_id
        empty_result = False

        # El núcleo clínico se guarda y confirma PRIMERO.
        with db() as conn:
            _v1364_ensure_encounter_schema(conn)
            if not conn.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
                raise HTTPException(404, "La ficha del paciente no existe en esta base local.")

            existing = conn.execute("SELECT * FROM encounters WHERE id=?", (enc_id,)).fetchone()
            if existing and existing["note_status"] != "draft":
                raise HTTPException(409, "La consulta ya está finalizada.")

            if diagnosis is None:
                diagnosis = (existing["diagnosis"] or "") if existing else ""
            if treatment is None:
                treatment = (existing["treatment"] or "") if existing else ""

            if (
                not _v1368_has_clinical_content(note, diagnosis, treatment)
                and not (existing and _v1370_encounter_has_documents(conn, enc_id))
            ):
                # Nunca firmamos ni conservamos como pendiente una historia vacía.
                # Si venía de una versión anterior, la soft-delete mantiene trazabilidad
                # sin mostrarla como historia ni como consulta pendiente.
                if existing:
                    empty_queue_id = queue_id or existing["queue_id"]
                    conn.execute(
                        """UPDATE encounters
                           SET queue_id=NULL,deleted_at=?,updated_at=?
                           WHERE id=? AND note_status='draft'""",
                        (stamp, stamp, enc_id),
                    )
                    audit(
                        conn,
                        "discard_empty_draft",
                        "encounter",
                        enc_id,
                        {"patient_id": patient_id, "reason": "empty_save"},
                    )
                conn.commit()
                empty_result = True
            elif existing:
                conn.execute(
                    """UPDATE encounters
                       SET encounter_date=?,encounter_time=?,clinical_note=?,diagnosis=?,treatment=?,
                           copied_from_encounter_id=?,queue_id=COALESCE(?,queue_id),deleted_at=NULL,updated_at=?
                       WHERE id=?""",
                    (enc_date, enc_time, note, diagnosis, treatment, copied, queue_id, stamp, enc_id),
                )
                conn.commit()
            else:
                created = True
                digest = hashlib.sha256((enc_id + stamp).encode()).hexdigest()
                conn.execute(
                    """INSERT INTO encounters(
                        id,patient_id,encounter_date,encounter_time,clinical_note,diagnosis,treatment,
                        source,source_record_hash,is_legacy_locked,created_at,updated_at,deleted_at,
                        note_status,signed_at,signed_by,copied_from_encounter_id,queue_id,created_by
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        enc_id, patient_id, enc_date, enc_time, note, diagnosis, treatment,
                        "historia_clinica", digest, 0, stamp, stamp, None,
                        "draft", None, None, copied, queue_id, DOCTOR_NAME,
                    ),
                )
                conn.commit()

        if empty_result:
            _v1368_reset_queue_after_empty_save(empty_queue_id, stamp)
            SYNC_SERVICE.mark_activity()
            SYNC_SERVICE.wake()
            return JSONResponse({"ok": True, "encounter_id": None, "empty": True})

        # Acciones secundarias: importantes, pero nunca ponen en riesgo el texto.
        if created:
            _v1364_audit_best_effort(
                "start_encounter", "encounter", enc_id, {"patient_id": patient_id}
            )
        if manual:
            _v1364_save_revision_best_effort(
                enc_id, stamp, note, diagnosis or "", treatment or "", "guardado_manual"
            )
        _v1364_queue_best_effort(queue_id, patient_id, "in_consultation", stamp)

        return JSONResponse({"ok": True, "encounter_id": enc_id, "empty": False})
    except HTTPException:
        raise
    except Exception as exc:
        _v1364_log_save_error("save_core", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            },
        )


@app.post("/api/encounters/empty/complete")
async def complete_empty_attention(request: Request):
    """Cierra una atención sin crear una historia clínica vacía."""
    data = await request.json()
    patient_id = str(data.get("patient_id") or "").strip()
    queue_id = str(data.get("queue_id") or "").strip() or None
    encounter_id = str(data.get("encounter_id") or "").strip() or None
    if not patient_id:
        raise HTTPException(400, "Falta el paciente.")

    stamp = now_iso()
    discarded = []
    signed_document_only = []
    with db() as conn:
        _v1364_ensure_encounter_schema(conn)
        if not conn.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
            raise HTTPException(404, "La ficha del paciente no existe en esta base local.")

        if encounter_id:
            rows = conn.execute(
                "SELECT * FROM encounters WHERE id=? AND patient_id=? LIMIT 1",
                (encounter_id, patient_id),
            ).fetchall()
        elif queue_id:
            rows = conn.execute(
                """SELECT * FROM encounters
                   WHERE patient_id=? AND queue_id=? AND note_status='draft'
                     AND COALESCE(deleted_at,'')=''""",
                (patient_id, queue_id),
            ).fetchall()
        else:
            rows = []

        for row in rows:
            if row["note_status"] != "draft":
                raise HTTPException(409, "La consulta ya está finalizada.")
            if _v1368_has_clinical_content(
                row["clinical_note"], row["diagnosis"], row["treatment"]
            ):
                raise HTTPException(
                    409,
                    "La consulta contiene información clínica y debe finalizarse normalmente.",
                )
            if _v1370_encounter_has_documents(conn, row["id"]):
                conn.execute(
                    """UPDATE encounters
                       SET note_status='signed',signed_at=?,signed_by=?,deleted_at=NULL,updated_at=?
                       WHERE id=? AND note_status='draft'""",
                    (stamp, DOCTOR_NAME, stamp, row["id"]),
                )
                signed_document_only.append(str(row["id"]))
            else:
                conn.execute(
                    """UPDATE encounters
                       SET queue_id=NULL,deleted_at=?,updated_at=?
                       WHERE id=? AND note_status='draft'""",
                    (stamp, stamp, row["id"]),
                )
                discarded.append(str(row["id"]))

        audit(
            conn,
            "complete_empty_attention",
            "waiting_queue" if queue_id else "patient",
            queue_id or patient_id,
            {"patient_id": patient_id, "discarded_empty_drafts": discarded, "signed_document_only": signed_document_only},
        )
        conn.commit()

    if queue_id:
        _v1364_queue_best_effort(queue_id, patient_id, "completed", stamp)
    SYNC_SERVICE.mark_activity()
    SYNC_SERVICE.wake()
    return JSONResponse({"ok": True, "empty": not bool(signed_document_only), "discarded": len(discarded), "signed_document_only": len(signed_document_only)})


@app.post("/api/encounters/{encounter_id}/sign")
def sign_encounter(encounter_id: str):
    try:
        stamp = now_iso()
        with db() as conn:
            _v1364_ensure_encounter_schema(conn)
            h = conn.execute("SELECT * FROM encounters WHERE id=?", (encounter_id,)).fetchone()
            if not h:
                raise HTTPException(404, "No se encontró la consulta.")
            if h["note_status"] != "draft":
                raise HTTPException(409, "La consulta ya está finalizada.")
            if (
                not (h["clinical_note"] or "").strip()
                and not (h["diagnosis"] or "").strip()
                and not (h["treatment"] or "").strip()
                and not _v1370_encounter_has_documents(conn, encounter_id)
            ):
                raise HTTPException(400, "La consulta está vacía.")

            # Primero cerramos y confirmamos el registro clínico.
            conn.execute(
                "UPDATE encounters SET note_status='signed',signed_at=?,signed_by=?,updated_at=? WHERE id=?",
                (stamp, DOCTOR_NAME, stamp, encounter_id),
            )
            conn.commit()

        # Lo secundario se hace después de que la historia ya quedó firmada.
        _v1364_save_revision_best_effort(
            encounter_id,
            stamp,
            h["clinical_note"] or "",
            h["diagnosis"] or "",
            h["treatment"] or "",
            "firma",
        )
        _v1364_audit_best_effort(
            "sign_lock", "encounter", encounter_id, {"patient_id": h["patient_id"]}
        )
        _v1364_queue_best_effort(
            h["queue_id"], h["patient_id"], "completed", stamp
        )
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as exc:
        _v1364_log_save_error("sign_core", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            },
        )


@app.post("/encuentro/{encounter_id}/addendum")
async def add_addendum(encounter_id: str, request: Request):
    data = await request.json()
    text = (data.get("text") or "").strip().upper()
    if not text: raise HTTPException(400)
    with db() as conn:
        h = conn.execute("SELECT * FROM encounters WHERE id=?", (encounter_id,)).fetchone()
        if not h: raise HTTPException(404)
        if h["note_status"] == "draft": raise HTTPException(409)
        aid, stamp = new_id(), now_iso()
        conn.execute("INSERT INTO encounter_addenda(id,encounter_id,text,created_at,actor) VALUES(?,?,?,?,?)", (aid, encounter_id, text, stamp, DOCTOR_NAME))
        audit(conn, "addendum", "encounter", encounter_id, {"addendum_id": aid})
        conn.commit()
    return JSONResponse({"ok": True})


@app.get("/encuentro/{encounter_id}/imprimir", response_class=HTMLResponse)
def print_encounter(encounter_id: str, print_now: int = 0):
    with db() as conn:
        h = conn.execute("SELECT e.*,p.name,p.birth_date,p.national_id,p.phone FROM encounters e JOIN patients p ON p.id=e.patient_id WHERE e.id=?", (encounter_id,)).fetchone()
        if not h: raise HTTPException(404)
        adds = conn.execute("SELECT * FROM encounter_addenda WHERE encounter_id=? ORDER BY created_at", (encounter_id,)).fetchall()
        audit(conn, "print", "encounter", encounter_id)
        conn.commit()
    adds_html = "".join(f"<section><h3>Continuación de historia — {e(human_dt(a['created_at']))}</h3><div>{display_text(a['text'])}</div></section>" for a in adds)
    return f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Historia clínica · {e(h['name'])}</title><style>
body{{font-family:Arial,sans-serif;color:#111;margin:34px;line-height:1.45}}header{{border-bottom:2px solid #111;padding-bottom:12px;margin-bottom:22px}}h1{{font-size:20px;margin:0 0 4px}}h2{{font-size:16px;margin:24px 0 8px}}h3{{font-size:14px;margin:22px 0 6px}}.meta{{font-size:12px;color:#444}}section{{margin:18px 0}}.box{{white-space:pre-wrap;border:1px solid #ccc;padding:12px;border-radius:6px}}footer{{margin-top:34px;border-top:1px solid #aaa;padding-top:12px;font-size:12px}}@media print{{button{{display:none}}body{{margin:15mm}}}}
</style></head><body><button onclick='window.print()'>Imprimir</button><header><h1>{e(h['name'])}</h1><div class='meta'>Fecha: {e(h['encounter_date'])} {e(h['encounter_time'] or '')} · ID: {e(h['national_id'] or '—')} · Tel: {e(h['phone'] or '—')}</div></header><section><h2>Historia / evolución</h2><div class='box'>{display_text(h['clinical_note']) or '—'}</div></section>{adds_html}<footer>{e(h['signed_by'] or DOCTOR_NAME)} · {('Firmada '+e(human_dt(h['signed_at']))) if h['note_status']=='signed' else 'Registro histórico importado'}</footer>{"<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),250));</script>" if print_now else ""}</body></html>"""


@app.get("/macros", response_class=HTMLResponse)
def macros_page():
    with db() as conn:
        rows = conn.execute("SELECT * FROM macros ORDER BY label COLLATE NOCASE").fetchall()
    items = "".join(f"<div class='macro-admin-row'><div><b>{e(r['label'])}</b><span>{e(r['text'])}</span></div><form method='post' action='/macros/{e(r['id'])}/delete'><button class='danger-text'>Eliminar</button></form></div>" for r in rows)
    body = f"""
<section class='page-head'><span class='eyebrow'>PERSONALIZACIÓN</span><h1>Frases rápidas</h1><p class='muted'>Guarde expresiones que el doctor repite con frecuencia. Después se insertan con un clic durante la consulta.</p></section>
<section class='macro-manager'><form method='post' action='/macros' class='macro-create'><label>Nombre corto<input name='label' maxlength='50' placeholder='Ej. Control normal' required></label><label>Texto<textarea name='text' rows='5' placeholder='Texto que se insertará en la historia…' required></textarea></label><button class='primary'>Guardar frase</button></form><section class='panel'><div class='panel-title'><h2>{len(rows)} frase{'s' if len(rows)!=1 else ''}</h2></div>{items if items else "<div class='empty'><strong>Aún no hay frases rápidas.</strong><span>Créelas según la forma real de escribir del doctor.</span></div>"}</section></section>
"""
    return base("Frases rápidas", body, "macros")


@app.post("/macros")
async def create_macro(request: Request):
    body = (await request.body()).decode("utf-8", errors="replace")
    data = parse_qs(body)
    label = (data.get("label", [""])[0]).strip()
    text = (data.get("text", [""])[0]).strip().upper()
    if not label or not text: raise HTTPException(400)
    stamp = now_iso()
    with db() as conn:
        try:
            conn.execute("INSERT INTO macros(id,label,text,created_at,updated_at) VALUES(?,?,?,?,?)", (new_id(), label, text, stamp, stamp))
            audit(conn, "create", "macro", None, {"label": label})
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Ya existe una frase con ese nombre")
    return RedirectResponse("/macros", status_code=303)


@app.post("/macros/{macro_id}/delete")
def delete_macro(macro_id: str):
    with db() as conn:
        row = conn.execute("SELECT label FROM macros WHERE id=?", (macro_id,)).fetchone()
        if row:
            conn.execute("DELETE FROM macros WHERE id=?", (macro_id,))
            audit(conn, "delete", "macro", macro_id, {"label": row["label"]})
            conn.commit()
    return RedirectResponse("/macros", status_code=303)

# ---------------------------------------------------------------------------
# v1.3.2 — paciente NUEVO: confirmar ficha antes de iniciar la consulta.
# ---------------------------------------------------------------------------
# APP_VERSION proviene de historia-version.json (fuente única).
try:
    with db() as _v132_conn:
        _v132_conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('app_version',?)",
            (APP_VERSION,),
        )
        _v132_conn.commit()
except Exception:
    pass
try:
    if hasattr(LAN_SERVICE, "version"):
        LAN_SERVICE.version = APP_VERSION
except Exception:
    pass

_v132_base_original = base
_v132_attend_original = attend_from_queue
_v132_edit_page_original = edit_patient_page
_v132_edit_save_original = edit_patient_save
_v132_new_consultation_original = new_consultation

_V132_STYLE = """
<style>
.v132-new-confirm{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  margin:0 0 14px;padding:11px 13px;border:1px solid #b9d9c7;
  border-radius:12px;background:#f1faf4;color:#285f40
}
.v132-new-confirm strong{font-size:12px;font-weight:950}
.v132-new-confirm span{font-size:10px;font-weight:850}
.v132-confirmed-banner{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  margin:0 0 12px;padding:12px 14px;border:1px solid #a8d2b8;
  border-radius:12px;background:#edf9f1;color:#245e3d
}
.v132-confirmed-banner strong{font-size:12px;font-weight:950}
.v132-confirmed-banner span{font-size:10px;font-weight:850}
.cp-new-consult.v132-attend{
  min-width:150px!important;font-size:13px!important;font-weight:950!important
}
</style>
"""

_V132_SCRIPT = """
<script>
(()=>{
  try{
    const p=new URLSearchParams(location.search);
    const q=p.get('queue_id')||'';
    const confirmed=p.get('confirmado')==='1';
    const isNew=p.get('nuevo')==='1';
    if(!q)return;
    const card=document.querySelector('.cp-patient-card');
    if(!card)return;
    const path=location.pathname.split('/').filter(Boolean);
    const patientId=path.length>=2&&path[0]==='paciente'?path[1]:'';
    const btn=document.querySelector('.cp-new-consult');
    if(btn&&patientId){
      btn.textContent='Atender';
      btn.classList.add('v132-attend');
      btn.href='/paciente/'+encodeURIComponent(patientId)+'/nueva?queue_id='+encodeURIComponent(q);
    }
    if(confirmed&&isNew&&!document.querySelector('.v132-confirmed-banner')){
      const turn=p.get('turno')||'';
      const b=document.createElement('div');
      b.className='v132-confirmed-banner';
      b.innerHTML='<strong>✓ FICHA CONFIRMADA · PACIENTE NUEVO</strong><span>'
        +(turn?('TURNO #'+turn+' · '):'')+'Ya puede iniciar la atención</span>';
      card.insertAdjacentElement('beforebegin',b);
    }
  }catch(_e){}
})();
</script>
"""

def base(title: str, body: str, active: str = "inicio", extra_head: str = "", extra_script: str = "") -> str:
    html = _v132_base_original(title, body, active, extra_head, extra_script)
    if "</head>" in html:
        html = html.replace("</head>", _V132_STYLE + "</head>", 1)
    if "</body>" in html:
        html = html.replace("</body>", _V132_SCRIPT + "</body>", 1)
    return html


def _v132_remove_route(path: str, method: str):
    wanted = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and wanted in set(getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)


def _v132_queue_confirmed(conn, row) -> bool:
    if not row or not _queue_is_new(row):
        return True
    reception_id = str(row["reception_patient_id"] or "").strip()
    patient_id = str(row["clinical_patient_id"] or "").strip()
    if not reception_id or not patient_id:
        return False
    link = conn.execute(
        """SELECT matched_by,clinical_patient_id
           FROM patient_links
           WHERE reception_patient_id=? LIMIT 1""",
        (reception_id,),
    ).fetchone()
    return bool(
        link
        and str(link["clinical_patient_id"] or "") == patient_id
        and str(link["matched_by"] or "") == "doctor_confirmed_new"
    )


def _v132_mark_queue_confirmed(conn, row, patient_id: str) -> None:
    stamp = now_iso()
    reception_id = str(row["reception_patient_id"] or "").strip()
    if not reception_id:
        return
    conn.execute(
        """
        INSERT INTO patient_links(
          reception_patient_id,clinical_patient_id,matched_by,verified,
          verified_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(reception_patient_id) DO UPDATE SET
          clinical_patient_id=excluded.clinical_patient_id,
          matched_by=excluded.matched_by,
          verified=1,
          verified_at=excluded.verified_at,
          updated_at=excluded.updated_at
        """,
        (
            reception_id, patient_id, "doctor_confirmed_new", 1,
            stamp, stamp, stamp,
        ),
    )
    conn.execute(
        """UPDATE waiting_queue
           SET clinical_patient_id=?,updated_at=?
           WHERE id=?""",
        (patient_id, stamp, row["id"]),
    )
    audit(
        conn,
        "confirm_new_patient_demographics",
        "patient",
        patient_id,
        {"queue_id": str(row["id"]), "reception_patient_id": reception_id},
    )
    conn.commit()


def _v132_edit_html(html: str, patient_id: str, queue_id: str, turn: int | None = None) -> str:
    turn_label = f"TURNO #{turn}" if turn else "PACIENTE NUEVO"
    banner = (
        "<div class='v132-new-confirm'><strong>PACIENTE NUEVO · CONFIRMAR DATOS</strong>"
        f"<span>{e(turn_label)}</span></div>"
    )
    html = html.replace(
        "<section class='new-patient-shell edit-patient-shell'>",
        "<section class='new-patient-shell edit-patient-shell'>" + banner,
        1,
    )
    html = html.replace("<h1>Editar ficha</h1>", "<h1>Confirmar ficha</h1>", 1)
    html = html.replace(
        "Las consultas e historias anteriores no se modifican al corregir estos datos.",
        "Revise los datos enviados desde Recepción. Guarde la ficha antes de iniciar la atención.",
        1,
    )
    marker = (
        f"<form method='post' action='/paciente/{e(patient_id)}/editar' "
        "class='new-patient-form edit-patient-form' autocomplete='off'>"
    )
    html = html.replace(
        marker,
        marker + f"<input type='hidden' name='queue_id' value='{e(queue_id)}'>",
        1,
    )
    html = html.replace(
        f"<a class='secondary btn-link' href='/paciente/{e(patient_id)}'>Cancelar</a>",
        "<a class='secondary btn-link' href='/'>Cancelar</a>",
        1,
    )
    html = html.replace(
        "<button class='primary' type='submit'>Guardar cambios</button>",
        "<button class='primary' type='submit'>Guardar y continuar</button>",
        1,
    )
    return html


for _path, _method in (
    ("/cola/{queue_id}/atender", "GET"),
    ("/paciente/{patient_id}/editar", "GET"),
    ("/paciente/{patient_id}/editar", "POST"),
    ("/paciente/{patient_id}/nueva", "GET"),
):
    _v132_remove_route(_path, _method)


@app.get("/cola/{queue_id}/atender")
def attend_from_queue_v132(queue_id: str):
    with db() as conn:
        row = conn.execute(
            """SELECT * FROM waiting_queue
               WHERE id=? AND status IN ('waiting','in_consultation')
               LIMIT 1""",
            (queue_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Turno no encontrado")

        if not _queue_is_new(row):
            patient_id = _queue_validated_link(conn, row)
            if not patient_id:
                candidates, reason = _queue_strong_candidates(conn, row)
                if len(candidates) == 1:
                    patient_id = str(candidates[0]["id"])
                    _link_queue_patient(
                        conn,
                        row,
                        patient_id,
                        "auto_" + (reason or "search"),
                    )
            if patient_id:
                return RedirectResponse(
                    f"/paciente/{patient_id}?queue_id={queue_id}",
                    status_code=303,
                )
            # Si hay ambigüedad, reutilizamos la pantalla segura de selección.
            return _v132_attend_original(queue_id)

        # Nunca aceptar a ciegas el clinical_patient_id de un turno nuevo:
        # puede venir de un vínculo viejo/duplicado. La lógica v1.3.20+ valida
        # identificación, existencia local y ambigüedad de nombre.
        patient_id = _queue_validated_link(conn, row)
        if not patient_id:
            try:
                patient_id = _create_new_patient_from_queue(conn, row)
            except ValueError:
                return _v132_attend_original(queue_id)
            row = conn.execute(
                "SELECT * FROM waiting_queue WHERE id=? LIMIT 1",
                (queue_id,),
            ).fetchone()

        turn = _queue_turn_number(conn, queue_id)
        if _v132_queue_confirmed(conn, row):
            url = f"/paciente/{patient_id}?queue_id={queue_id}&nuevo=1&confirmado=1"
            if turn:
                url += f"&turno={turn}"
            return RedirectResponse(url, status_code=303)

        url = f"/paciente/{patient_id}/editar?queue_id={queue_id}&nuevo=1"
        if turn:
            url += f"&turno={turn}"
        return RedirectResponse(url, status_code=303)


@app.get("/paciente/{patient_id}/editar", response_class=HTMLResponse)
def edit_patient_page_v132(
    patient_id: str,
    queue_id: str = Query(default="", max_length=120),
    nuevo: str = Query(default="", max_length=8),
    turno: str = Query(default="", max_length=12),
):
    if not queue_id:
        return _v132_edit_page_original(patient_id)

    with db() as conn:
        row = conn.execute(
            """SELECT * FROM waiting_queue
               WHERE id=? AND clinical_patient_id=?
                 AND status IN ('waiting','in_consultation')
               LIMIT 1""",
            (queue_id, patient_id),
        ).fetchone()
        if not row or not _queue_is_new(row):
            return _v132_edit_page_original(patient_id)
        real_turn = _queue_turn_number(conn, queue_id)

    original = _v132_edit_page_original(patient_id)
    # Al llamar directamente a una ruta de FastAPI no interviene response_class:
    # la función original devuelve HTML como str. v1.3.2 intentaba leer .body
    # de ese str y provocaba Internal Server Error al atender un paciente nuevo.
    if isinstance(original, HTMLResponse):
        html = original.body.decode("utf-8", errors="replace")
        status_code = int(original.status_code)
    elif isinstance(original, (bytes, bytearray)):
        html = bytes(original).decode("utf-8", errors="replace")
        status_code = 200
    else:
        html = str(original)
        status_code = 200
    html = _v132_edit_html(html, patient_id, queue_id, real_turn)
    return HTMLResponse(html, status_code=status_code)


@app.post("/paciente/{patient_id}/editar", response_class=HTMLResponse)
async def edit_patient_save_v132(patient_id: str, request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(raw, keep_blank_values=True)
    queue_id = (parsed.get("queue_id", [""])[0] or "").strip()

    result = await _v132_edit_save_original(patient_id, request)
    if not queue_id:
        return result

    with db() as conn:
        row = conn.execute(
            """SELECT * FROM waiting_queue
               WHERE id=? AND clinical_patient_id=?
                 AND status IN ('waiting','in_consultation')
               LIMIT 1""",
            (queue_id, patient_id),
        ).fetchone()
        turn = _queue_turn_number(conn, queue_id) if row else None

        if (
            row
            and _queue_is_new(row)
            and isinstance(result, RedirectResponse)
            and int(result.status_code) in (302, 303, 307, 308)
        ):
            _v132_mark_queue_confirmed(conn, row, patient_id)
            url = f"/paciente/{patient_id}?queue_id={queue_id}&nuevo=1&confirmado=1"
            if turn:
                url += f"&turno={turn}"
            SYNC_SERVICE.mark_activity()
            SYNC_SERVICE.wake()
            return RedirectResponse(url, status_code=303)

    if isinstance(result, HTMLResponse):
        html = result.body.decode("utf-8", errors="replace")
        html = _v132_edit_html(html, patient_id, queue_id, turn)
        return HTMLResponse(html, status_code=result.status_code)
    return result


@app.get("/paciente/{patient_id}/nueva", response_class=HTMLResponse)
def new_consultation_v132(patient_id: str, encounter_id: str = "", queue_id: str = ""):
    if queue_id:
        with db() as conn:
            row = conn.execute(
                """SELECT * FROM waiting_queue
                   WHERE id=? AND clinical_patient_id=?
                     AND status IN ('waiting','in_consultation')
                   LIMIT 1""",
                (queue_id, patient_id),
            ).fetchone()
            if row and _queue_is_new(row) and not _v132_queue_confirmed(conn, row):
                turn = _queue_turn_number(conn, queue_id)
                url = f"/paciente/{patient_id}/editar?queue_id={queue_id}&nuevo=1"
                if turn:
                    url += f"&turno={turn}"
                return RedirectResponse(url, status_code=303)
    return _v132_new_consultation_original(patient_id, encounter_id, queue_id)


@app.get("/api/v132/health")
def v132_health():
    return JSONResponse({
        "ok": True,
        "version": APP_VERSION,
        "new_patient_confirm_before_consult": True,
        "new_patient_edit_first": True,
        "new_patient_attend_after_confirm": True,
        "database_schema_changes": False,
        "new_patient_edit_response_hotfix": True,
    })


# v1.3.8 integra documentos sobre la ruta ya blindada de paciente nuevo.
new_consultation = new_consultation_v132
import cloud_sync as _v139_cloud_sync
# ---------------------------------------------------------------------------
# v1.3.8 — nube completa + recetas/certificados/configuración.
# ---------------------------------------------------------------------------
APP_VERSION = _CANONICAL_VERSION
try:
    with db() as _v135_conn:
        _v135_conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('app_version',?)",
            (APP_VERSION,),
        )
        _v135_conn.commit()
except Exception:
    pass
try:
    if hasattr(LAN_SERVICE, "version"):
        LAN_SERVICE.version = APP_VERSION
except Exception:
    pass

_V135_BASE_ORIGINAL = base

_V135_STYLE = """
<style>
.topbar nav{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.topbar nav a{white-space:nowrap}
.editor-actions .document-action{
  background:#edf3f9!important;color:#173b66!important;border:1px solid #b9cce0!important
}
.editor-actions .document-action:hover{background:#dfeaf5!important}
@media(max-width:1000px){.topbar nav{gap:4px}.topbar nav a{font-size:11px}}
.pending-draft-warning{
  margin:14px 0;padding:14px 16px;border:1px solid #f0c36a;border-radius:12px;
  background:#fff8e7;color:#6b4a00;display:flex;gap:10px;align-items:flex-start
}
.pending-draft-warning strong{display:block;margin-bottom:3px}
.emergency-recovery-note{
  margin:0 0 14px;padding:12px 14px;border:1px solid #8fd4bc;border-radius:12px;
  background:#eefaf5;color:#155a43;font-weight:600
}
.save-state.error{font-weight:700}
</style>
"""

def base(title: str, body: str, active: str = "inicio", extra_head: str = "", extra_script: str = "") -> str:
    html = _V135_BASE_ORIGINAL(title, body, active, extra_head, extra_script)
    nav_parts = []
    if 'href="/recetas"' not in html:
        nav_parts.append(f'<a class="{"active" if active=="recetas" else ""}" href="/recetas">Recetas</a>')
    if 'href="/certificados"' not in html:
        nav_parts.append(f'<a class="{"active" if active=="certificados" else ""}" href="/certificados">Certificados</a>')
    if 'href="/configuracion"' not in html:
        nav_parts.append(f'<a class="{"active" if active=="configuracion" else ""}" href="/configuracion">Configuración</a>')
    if 'href="/recuperacion/borradores"' not in html:
        nav_parts.append(f'<a class="{"active" if active=="recuperacion" else ""}" href="/recuperacion/borradores">Recuperación</a>')
    if "</nav>" in html and nav_parts:
        html = html.replace("</nav>", "".join(nav_parts) + "</nav>", 1)
    if "</head>" in html:
        html = html.replace("</head>", _V135_STYLE + "</head>", 1)

    # Un borrador autoguardado no forma parte todavía del historial firmado.
    # Lo hacemos muy visible para que nadie piense que se perdió.
    if ">Continuar consulta</a>" in html and "<section class=\"cp-history-window\">" in html:
        warning = (
            "<div class='pending-draft-warning'>"
            "<span>●</span><div><strong>Consulta sin finalizar guardada</strong>"
            "El texto está protegido como borrador y todavía no aparece en el historial definitivo. "
            "Use <b>Continuar consulta</b> para recuperarlo y finalizarlo.</div></div>"
        )
        html = html.replace("<section class=\"cp-history-window\">", warning + "<section class=\"cp-history-window\">", 1)
    return html


# Migración cloud v1.3.8: una sola relectura total y sembrado de módulos nuevos.
try:
    with db() as _v138:
        _v138.execute("CREATE TABLE IF NOT EXISTS sync_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        _v138.execute("CREATE TABLE IF NOT EXISTS sync_dirty(table_name TEXT NOT NULL,row_key TEXT NOT NULL,changed_at TEXT NOT NULL,PRIMARY KEY(table_name,row_key))")
        _flag = _v138.execute("SELECT value FROM sync_state WHERE key='migration_v138_full_cloud'").fetchone()
        if not _flag:
            _v138.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES('last_pull','1970-01-01T00:00:00+00:00')")
            _v138.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES('cloud_bootstrap_complete','0')")
            for _table, _pk in (("prescriptions","id"),("certificates","id"),("clinic_settings","setting_key")):
                _v138.execute(f"INSERT OR IGNORE INTO sync_dirty(table_name,row_key,changed_at) SELECT ?,CAST({_pk} AS TEXT),datetime('now') FROM {_table}", (_table,))
            _v138.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES('migration_v138_full_cloud','1')")
            _v138.commit()
except Exception:
    pass

documentos_clinicos.install(app, globals())


# Integra los dos documentos en la consulta sin cerrar ni finalizar la atención.
_V135_NEW_CONSULTATION_ORIGINAL = new_consultation
_v132_remove_route("/paciente/{patient_id}/nueva", "GET")

@app.get("/paciente/{patient_id}/nueva", response_class=HTMLResponse)
def new_consultation_v135(patient_id: str, encounter_id: str = "", queue_id: str = ""):
    result = _V135_NEW_CONSULTATION_ORIGINAL(patient_id, encounter_id, queue_id)

    # Las rutas FastAPI con response_class pueden devolver str al invocarse
    # directamente desde otro wrapper. v1.3.8 asumía HTMLResponse y por eso
    # los botones de receta/certificado podían no inyectarse aunque el módulo
    # estuviera instalado.
    if isinstance(result, HTMLResponse):
        try:
            html = bytes(result.body).decode(result.charset or "utf-8")
        except Exception:
            return result
        status_code = result.status_code
        headers = {
            k: v for k, v in dict(result.headers).items()
            if k.lower() not in {"content-length", "content-type"}
        }
    elif isinstance(result, str):
        html = result
        status_code = 200
        headers = {}
    else:
        return result

    # Los documentos deben estar visibles mientras el doctor escribe, junto a
    # Frases rápidas. Se conserva un fallback en el pie por compatibilidad con
    # layouts anteriores.
    if "id='open-prescription'" not in html:
        tools_marker = "<div class='consult-tools'><button id='toggle-macros' class='secondary'>Frases rápidas</button>"
        tools_replacement = (
            "<div class='consult-tools'>"
            "<button id='toggle-macros' class='secondary'>Frases rápidas</button>"
            "<button id='open-prescription' class='secondary document-action' type='button'>Receta médica</button>"
            "<button id='open-certificate' class='secondary document-action' type='button'>Certificado médico</button>"
        )
        if tools_marker in html:
            html = html.replace(tools_marker, tools_replacement, 1)
        else:
            footer_marker = "<div class='editor-actions'>"
            footer_replacement = (
                "<div class='editor-actions'>"
                "<button id='open-prescription' class='secondary document-action' type='button'>Receta médica</button>"
                "<button id='open-certificate' class='secondary document-action' type='button'>Certificado médico</button>"
            )
            if footer_marker in html:
                html = html.replace(footer_marker, footer_replacement, 1)

    helper = r"""
<script>
(()=>{
  const rx=document.getElementById('open-prescription');
  const cert=document.getElementById('open-certificate');
  async function openClinicalDocument(kind,button){
    const original=button.textContent;
    button.disabled=true;
    button.textContent='Guardando…';
    try{
      let id='';
      if(typeof save==='function'){
        id=await save(true) || '';
      }
      const route=kind==='rx'?'/recetas/nueva':'/certificados/nuevo';
      const qs=new URLSearchParams({patient_id:PATIENT_ID});
      if(id)qs.set('encounter_id',id);
      qs.set('from_consultation','1');
      if(QUEUE_ID)qs.set('queue_id',QUEUE_ID);
      qs.set('encounter_date',document.getElementById('enc-date')?.value||'');
      qs.set('encounter_time',document.getElementById('enc-time')?.value||'');
      window.open(route+'?'+qs.toString(),'_blank');
      button.textContent=original;
      button.disabled=false;
    }catch(err){
      button.textContent=original;
      button.disabled=false;
      if(window.showAppToast)showAppToast(
        err && err.message ? err.message : 'No se pudo guardar antes de emitir el documento.',
        'error'
      );
    }
  }
  if(rx)rx.addEventListener('click',()=>openClinicalDocument('rx',rx));
  if(cert)cert.addEventListener('click',()=>openClinicalDocument('cert',cert));
})();

// v1.3.18 — segunda capa local, independiente de SQLite/Neon.
// Cada cambio escrito se copia inmediatamente en localStorage del WebView.
// Si Windows o el programa se reinician antes de que el autoguardado llegue
// al backend, la misma consulta recupera ese texto al volver a abrirla.
(()=>{
  const PREFIX='historia_emergency_draft_v1:';
  const TEMP=PREFIX+'patient:'+String(PATIENT_ID)+':queue:'+String(QUEUE_ID||'none');
  const note=document.getElementById('clinical-note');
  if(!note)return;

  function keyForEncounter(id){
    return PREFIX+'encounter:'+String(id||'');
  }
  function safeParse(raw){
    try{return raw?JSON.parse(raw):null}catch(_e){return null}
  }
  function snapshot(){
    try{
      const data={
        patient_id:String(PATIENT_ID||''),
        queue_id:String(QUEUE_ID||''),
        encounter_id:String(encounterId||''),
        note:String(note.value||''),
        encounter_date:String(document.getElementById('enc-date')?.value||''),
        encounter_time:String(document.getElementById('enc-time')?.value||''),
        saved_at:new Date().toISOString()
      };
      const raw=JSON.stringify(data);
      if(encounterId){
        localStorage.setItem(keyForEncounter(encounterId),raw);
        localStorage.removeItem(TEMP);
      }else{
        localStorage.setItem(TEMP,raw);
      }
    }catch(_e){}
  }
  function clearBackup(id){
    try{
      localStorage.removeItem(TEMP);
      if(id)localStorage.removeItem(keyForEncounter(id));
    }catch(_e){}
  }
  function recoveryCandidate(){
    try{
      if(encounterId){
        const byId=safeParse(localStorage.getItem(keyForEncounter(encounterId)));
        if(byId)return byId;
      }
      return safeParse(localStorage.getItem(TEMP));
    }catch(_e){return null}
  }

  const candidate=recoveryCandidate();
  if(
    candidate &&
    String(candidate.patient_id||'')===String(PATIENT_ID||'') &&
    String(candidate.note||'').trim()
  ){
    const sameDraft = !encounterId || !candidate.encounter_id ||
      String(candidate.encounter_id)===String(encounterId);
    if(sameDraft && String(candidate.note||'')!==String(note.value||'')){
      note.value=String(candidate.note||'').toUpperCase();
      const d=document.getElementById('enc-date');
      const t=document.getElementById('enc-time');
      if(d && candidate.encounter_date)d.value=candidate.encounter_date;
      if(t && candidate.encounter_time)t.value=candidate.encounter_time;
      upperClinical(note);
      dirty=true;
      const editor=document.querySelector('.clinical-editor');
      if(editor){
        const msg=document.createElement('div');
        msg.className='emergency-recovery-note';
        msg.textContent='Se recuperó texto que estaba protegido localmente antes del reinicio.';
        editor.insertBefore(msg,editor.firstChild);
      }
      state.textContent='Texto recuperado · guardando…';
      state.className='save-state saving';
      setTimeout(()=>save(false).catch(()=>{}),150);
    }
  }

  note.addEventListener('input',snapshot,{capture:true});
  ['enc-date','enc-time'].forEach(id=>{
    document.getElementById(id)?.addEventListener('change',snapshot,{capture:true});
  });
  window.addEventListener('pagehide',snapshot);
  window.addEventListener('beforeunload',snapshot);
  setInterval(snapshot,1000);

  // Después de cada guardado al SQLite mantenemos una copia local asociada
  // al encounter; solo se elimina cuando la consulta queda FINALIZADA.
  const serverSave=save;
  save=async function(manual=false){
    snapshot();
    try{
      const id=await serverSave(manual);
      snapshot();
      return id;
    }catch(err){
      snapshot();
      // El watchdog automático reintenta periódicamente, pero no debe
      // interrumpir al doctor con un popup cada 5 segundos.
      try{
        state.textContent='Protegido localmente · reintentando';
        state.className='save-state error';
        if(manual && window.showAppToast){
          showAppToast(
            err && err.message
              ? err.message
              : 'No se pudo guardar en la base. El texto sigue protegido localmente en esta PC.',
            'error'
          );
        }
      }catch(_e){}
      throw err;
    }
  };

  const serverFinalize=finalizeAndHome;
  finalizeAndHome=async function(button){
    const idBefore=encounterId;
    await serverFinalize(button);
    if(leavingAfterFinalize){
      clearBackup(encounterId||idBefore);
    }
  };
})();
</script>
"""
    if "</body>" in html:
        html = html.replace("</body>", helper + "</body>", 1)

    return HTMLResponse(
        content=html,
        status_code=status_code,
        headers=headers,
    )



# ---------------------------------------------------------------------------
# v1.3.19 — recuperación segura de borradores que una versión anterior pudo
# desvincular/borrar al cancelarse un turno de Recepción.
# ---------------------------------------------------------------------------

def _v139_remote_draft_candidates(raw_query: str) -> list[dict]:
    query = normalize_search(raw_query or "")
    tokens = [t for t in query.split() if t]
    if not tokens or not getattr(SYNC_SERVICE, "url", ""):
        return []

    pg = _v139_cloud_sync._pg_connect(SYNC_SERVICE.url)
    try:
        cur = pg.cursor()
        conditions = []
        params = []
        for token in tokens:
            conditions.append("UPPER(COALESCE(p.name,'')) LIKE %s")
            params.append("%" + token.upper() + "%")
        where_name = " AND ".join(conditions) or "1=1"
        cur.execute(
            f"""
            SELECT
              e.id,e.patient_id,e.encounter_date,e.encounter_time,
              e.updated_at,e.created_at,e.deleted_at,e.note_status,
              p.name,p.national_id
            FROM historia.encounters e
            JOIN historia.patients p ON p.id=e.patient_id
            WHERE e.note_status='draft'
              AND COALESCE(e.clinical_note,'') <> ''
              AND ({where_name})
            ORDER BY e.updated_at DESC NULLS LAST
            LIMIT 50
            """,
            tuple(params),
        )
        names = [d[0] for d in cur.description]
        remote_rows = [dict(zip(names, row)) for row in cur.fetchall()]
        cur.close()
    finally:
        try: pg.close()
        except Exception: pass

    # Sólo ofrecemos recuperar si el borrador remoto falta localmente o si la
    # copia local quedó vacía. Así jamás sobrescribimos una consulta activa.
    out = []
    with db() as conn:
        for row in remote_rows:
            local = conn.execute(
                "SELECT id,clinical_note,note_status,updated_at FROM encounters WHERE id=?",
                (str(row.get("id") or ""),),
            ).fetchone()
            local_text = str(local["clinical_note"] or "").strip() if local else ""
            if local and local_text:
                continue
            clean = dict(row)
            for key in ("updated_at","created_at","deleted_at"):
                value = clean.get(key)
                if value is not None and not isinstance(value, str):
                    try: clean[key] = value.isoformat()
                    except Exception: clean[key] = str(value)
            out.append(clean)
    return out


def _v139_remote_row(table: str, key_col: str, key_value: str) -> dict | None:
    if table not in {"patients","encounters"}:
        raise ValueError("Tabla de recuperación no permitida")
    pg = _v139_cloud_sync._pg_connect(SYNC_SERVICE.url)
    try:
        cur = pg.cursor()
        cur.execute(
            f'SELECT * FROM historia.{table} WHERE CAST({key_col} AS TEXT)=%s LIMIT 1',
            (str(key_value),),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            return None
        names = [d[0] for d in cur.description]
        data = dict(zip(names, row))
        cur.close()
        return data
    finally:
        try: pg.close()
        except Exception: pass


def _v139_sqlite_value(value):
    if value is None or isinstance(value, (str,int,float,bytes)):
        return value
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _v139_insert_common_row(conn, table: str, remote: dict, *, overrides: dict | None = None):
    local_cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    data = {
        k: _v139_sqlite_value(v)
        for k,v in remote.items()
        if k in local_cols and k != "cloud_updated_at"
    }
    data.update(overrides or {})
    cols = [k for k in local_cols if k in data]
    if not cols:
        raise RuntimeError("No hay columnas compatibles para recuperar")
    sql = (
        f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join(['?']*len(cols))})"
    )
    conn.execute(sql, [data[k] for k in cols])


@app.get("/recuperacion/borradores", response_class=HTMLResponse)
def v139_recovery_page(q: str = Query(default="", max_length=120)):
    term = (q or "").strip()
    rows = []
    error = ""
    if len(term) >= 2:
        try:
            rows = _v139_remote_draft_candidates(term)
        except Exception as exc:
            error = f"No se pudo consultar la copia de nube en este momento ({type(exc).__name__})."

    with db() as conn:
        old_discards = int(conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='discard_cancelled_draft'"
        ).fetchone()[0] or 0)

    cards = []
    for row in rows:
        date = human_date(str(row.get("encounter_date") or "")) or str(row.get("encounter_date") or "Sin fecha")
        time_txt = str(row.get("encounter_time") or "")[:5]
        cloud_state = "copia eliminada recuperable" if row.get("deleted_at") else "borrador existente en nube"
        cards.append(
            "<article class='panel' style='margin-top:10px'>"
            f"<div class='panel-title'><div><strong>{e(row.get('name') or 'Paciente')}</strong>"
            f"<span>{e(date)} {e(time_txt)} · {e(cloud_state)}</span></div></div>"
            f"<form method='post' action='/recuperacion/borradores/{e(row.get('id') or '')}/restaurar'>"
            "<button class='primary' type='submit'>Restaurar borrador en esta PC</button></form>"
            "</article>"
        )

    if term and not rows and not error:
        result_html = (
            "<div class='empty'><strong>No encontré un borrador recuperable en la nube con ese nombre.</strong>"
            "<span>Esto no modifica nada; puede probar con uno o dos apellidos.</span></div>"
        )
    else:
        result_html = "".join(cards)

    notice = ""
    if old_discards:
        notice = (
            "<div class='pending-draft-warning'><span>●</span><div>"
            f"<strong>Se detectaron {old_discards} descartes de borrador hechos por versiones anteriores.</strong>"
            "La versión actual ya no permite que una cancelación de Recepción borre texto clínico. "
            "Si alguno alcanzó a sincronizarse, puede recuperarse desde esta pantalla."
            "</div></div>"
        )

    body = f"""
<section class='page-head'>
  <span class='eyebrow'>SEGURIDAD DE HISTORIAS</span>
  <h1>Recuperar borradores</h1>
  <p>Busca en la copia de nube borradores que no estén presentes en esta PC. Esta búsqueda es de solo lectura hasta que pulse Restaurar.</p>
</section>
{notice}
<section class='search-card compact'>
  <form method='get' action='/recuperacion/borradores'>
    <div class='searchbox'><input name='q' value='{e(term)}' autofocus placeholder='Ej.: HONG SHEN JAIME DAVID'><button>Buscar</button></div>
  </form>
</section>
{f"<div class='form-error'><strong>No se pudo consultar la nube.</strong><span>{e(error)}</span></div>" if error else ""}
<section>{result_html}</section>
"""
    return base("Recuperación", body, "recuperacion")


@app.post("/recuperacion/borradores/{encounter_id}/restaurar")
def v139_restore_remote_draft(encounter_id: str):
    if not getattr(SYNC_SERVICE, "url", ""):
        raise HTTPException(503, "La nube de Historia no está configurada.")

    remote_enc = _v139_remote_row("encounters", "id", encounter_id)
    if not remote_enc:
        raise HTTPException(404, "No encontré ese borrador en la nube.")
    if str(remote_enc.get("note_status") or "") != "draft":
        raise HTTPException(409, "El registro remoto ya no es un borrador.")
    if not str(remote_enc.get("clinical_note") or "").strip():
        raise HTTPException(409, "El borrador remoto no contiene texto clínico.")

    patient_id = str(remote_enc.get("patient_id") or "")
    if not patient_id:
        raise HTTPException(409, "El borrador remoto no tiene paciente vinculado.")

    with db() as conn:
        existing = conn.execute(
            "SELECT id,clinical_note,note_status FROM encounters WHERE id=?",
            (encounter_id,),
        ).fetchone()
        if existing and str(existing["clinical_note"] or "").strip():
            raise HTTPException(409, "Ya existe una copia local con texto; no se sobrescribió.")

        patient = conn.execute("SELECT id FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not patient:
            remote_patient = _v139_remote_row("patients", "id", patient_id)
            if not remote_patient:
                raise HTTPException(409, "No se pudo recuperar la ficha del paciente.")
            _v139_insert_common_row(
                conn,
                "patients",
                remote_patient,
                overrides={"deleted_at": None},
            )

        if existing:
            stamp = now_iso()
            conn.execute(
                """UPDATE encounters
                   SET clinical_note=?,diagnosis=?,treatment=?,
                       encounter_date=?,encounter_time=?,
                       note_status='draft',queue_id=NULL,deleted_at=NULL,updated_at=?
                   WHERE id=?""",
                (
                    _v139_sqlite_value(remote_enc.get("clinical_note")),
                    _v139_sqlite_value(remote_enc.get("diagnosis")),
                    _v139_sqlite_value(remote_enc.get("treatment")),
                    _v139_sqlite_value(remote_enc.get("encounter_date")),
                    _v139_sqlite_value(remote_enc.get("encounter_time")),
                    stamp,
                    encounter_id,
                ),
            )
        else:
            overrides = {
                "id": encounter_id,
                "patient_id": patient_id,
                "note_status": "draft",
                "queue_id": None,
                "deleted_at": None,
                "updated_at": now_iso(),
            }
            _v139_insert_common_row(conn, "encounters", remote_enc, overrides=overrides)

        audit(
            conn,
            "recover_cloud_draft",
            "encounter",
            encounter_id,
            {"patient_id": patient_id, "source": "historia_cloud_recovery"},
        )
        conn.commit()

    SYNC_SERVICE.mark_activity()
    SYNC_SERVICE.wake()
    return RedirectResponse(
        f"/paciente/{e(patient_id)}/nueva?encounter_id={e(encounter_id)}",
        status_code=303,
    )


@app.get("/api/v138/health")
def v138_health():
    return JSONResponse({
        "ok": True,
        "version": APP_VERSION,
        "canonical_version_source": "historia-version.json",
        "launcher_v1_ready": True,
        "prescriptions": True,
        "certificates": True,
        "configuration": True,
        "cloud_full_bootstrap": True,
        "cloud_patients": True,
        "cloud_encounters": True,
        "cloud_prescriptions": True,
        "cloud_certificates": True,
        "cloud_shared_settings": True,
        "database_schema_changes": True,
        "emergency_local_draft_backup": True,
        "draft_visible_on_patient_page": True,
        "restart_recovery": True,
        "cancelled_queue_never_deletes_draft": True,
        "cloud_deleted_draft_recovery": True,
        "duplicate_creation_guard": True,
        "patient_card_recipe_button": True,
        "patient_card_certificate_button": True,
        "global_recipe_nav_visible": True,
        "consultation_only_turn_numbers": True,
        "empty_draft_pending_fix": True,
        "empty_attention_closes_without_signed_history": True,
    })
