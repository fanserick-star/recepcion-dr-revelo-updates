from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def top_function(text: str, name: str):
    tree = ast.parse(text)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise AssertionError(f"{name}: expected one top-level function, found {len(matches)}")
    return matches[0]


def replace_top_function(text: str, name: str, replacement: str) -> str:
    node = top_function(text, name)
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n"]
    return "".join(lines)


def remove_top_functions(text: str, names: set[str]) -> str:
    tree = ast.parse(text)
    spans = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            spans.append((node.lineno - 1, node.end_lineno))
            found.add(node.name)
    missing = names - found
    if missing:
        raise AssertionError(f"top functions not found: {sorted(missing)}")
    lines = text.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    return "".join(lines)


def remove_class_methods(text: str, class_name: str, names: set[str]) -> str:
    tree = ast.parse(text)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    if cls is None:
        raise AssertionError(f"class not found: {class_name}")
    spans = []
    found = set()
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            spans.append((node.lineno - 1, node.end_lineno))
            found.add(node.name)
    missing = names - found
    if missing:
        raise AssertionError(f"class methods not found: {sorted(missing)}")
    lines = text.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    return "".join(lines)


# ---------------------------------------------------------------------------
# Reception 4.6.20 — Neon is the sole identity/link authority.
# LAN is reserved for the waiting-room transport.
# ---------------------------------------------------------------------------
r_path = "recepcion/app/reception_history_identity_consolidated.py"
r = read(r_path)
r = r.replace("import historia_bridge\nimport historia_lan_transport as historia_lan\n", "import historia_bridge\n", 1)

r = replace_top_function(r, "_upsert_link", '''def _upsert_link(cur, reception_patient_id, clinical_patient_id, matched_by):
    stamp = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO public.patient_links(
          reception_patient_id,clinical_patient_id,matched_by,verified,
          verified_at,created_at,updated_at,deleted_at,cloud_updated_at
        )
        VALUES(%s,%s,%s,1,%s,%s,%s,NULL,now())
        ON CONFLICT(reception_patient_id) DO UPDATE SET
          clinical_patient_id=EXCLUDED.clinical_patient_id,
          matched_by=EXCLUDED.matched_by,
          verified=1,
          verified_at=EXCLUDED.verified_at,
          updated_at=EXCLUDED.updated_at,
          deleted_at=NULL,
          cloud_updated_at=now()
        """,
        (
            str(reception_patient_id),
            str(clinical_patient_id),
            _clean(matched_by, 80),
            stamp,
            stamp,
            stamp,
        ),
    )
''')

# The original cloud handlers are captured by these aliases before v4.6.18
# replaced the routes. Keep the routes but make them cloud-only.
r = remove_top_functions(r, {"_v4618_lan_payload", "_v4618_unavailable"})

r = replace_top_function(r, "v4618_historia_identity_status", '''def v4618_historia_identity_status(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return _v4618_status_cloud(reception_patient_id, db, user)
''')

r = replace_top_function(r, "v4618_historia_identity_prepare", '''def v4618_historia_identity_prepare(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return _v4618_prepare_cloud(reception_patient_id, db, user)
''')

r = replace_top_function(r, "v4618_historia_identity_sync", '''def v4618_historia_identity_sync(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return _v4618_prepare_cloud(reception_patient_id, db, user)
''')

r = replace_top_function(r, "v4618_historia_identity_search", '''def v4618_historia_identity_search(
    q: str = "",
    reception_patient_id: int = 0,
    limit: int = 30,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return _v4618_search_cloud(q, reception_patient_id, limit, db, user)
''')

r = replace_top_function(r, "v4618_historia_identity_link", '''def v4618_historia_identity_link(
    data: _HistoryLinkIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return _v4618_link_cloud(data, db, user)
''')

# Identity connection validates only the clinical tables used for search/link.
r = r.replace(
    "AND table_name IN ('patients','encounters','patient_links','waiting_queue')",
    "AND table_name IN ('patients','encounters','patient_links')",
    1,
)
waiting_required = '''            "waiting_queue": {"id", "reception_event_id", "reception_patient_id",
                              "clinical_patient_id", "status", "patient_status",
                              "reception_turn", "deleted_at",
                              "cloud_updated_at"},
'''
if waiting_required not in r:
    raise AssertionError("waiting_queue required-schema block not found")
r = r.replace(waiting_required, "", 1)

if "historia_lan.identity_" in r or "import historia_lan_transport as historia_lan" in r:
    raise AssertionError("Reception identity still references LAN")
if "typeof currentDetectedStatus==='function'&&norm(currentDetectedStatus())==='S'" not in r:
    raise AssertionError("subsequent UI detector was lost")
write(r_path, r)


# ---------------------------------------------------------------------------
# Reception LAN transport — waiting-room only, with a durable local retry queue.
# ---------------------------------------------------------------------------
l_path = "recepcion/app/historia_lan_transport.py"
l = read(l_path)
if "import sqlite3\n" not in l:
    l = l.replace("import socket\n", "import socket\nimport sqlite3\n", 1)
if "LAN_OUTBOX_DB" not in l:
    l = l.replace(
        'CACHE_PATH = ROOT / "data" / "historia_lan_cache.json"\n',
        'CACHE_PATH = ROOT / "data" / "historia_lan_cache.json"\nLAN_OUTBOX_DB = ROOT / "data" / "historia_lan_outbox.db"\n',
        1,
    )

l = remove_top_functions(l, {"_identity_request", "identity_status", "identity_prepare", "identity_search", "identity_link"})

helpers = r'''
def _ensure_lan_outbox() -> None:
    LAN_OUTBOX_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              sent_at TEXT,
              cancelled INTEGER NOT NULL DEFAULT 0,
              last_error TEXT
            )
            """
        )
        conn.commit()


def _lan_outbox_put(payload: dict) -> None:
    _ensure_lan_outbox()
    event_id = _clean(payload.get("event_id"), 180)
    if not event_id:
        raise ValueError("Falta event_id para la cola LAN")
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        conn.execute(
            """
            INSERT INTO events(event_id,payload_json,created_at,sent_at,cancelled,last_error)
            VALUES(?,?,?,NULL,0,NULL)
            ON CONFLICT(event_id) DO UPDATE SET
              payload_json=excluded.payload_json,
              sent_at=NULL,
              cancelled=0,
              last_error=NULL
            """,
            (event_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), _now()),
        )
        conn.commit()


def _lan_outbox_mark(event_id: str, *, sent: bool = False, error: str = "") -> None:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        if sent:
            conn.execute(
                "UPDATE events SET sent_at=?,last_error=NULL WHERE event_id=?",
                (_now(), str(event_id)),
            )
        else:
            conn.execute(
                "UPDATE events SET last_error=? WHERE event_id=?",
                (_clean(error, 240), str(event_id)),
            )
        conn.commit()


def _lan_outbox_counts() -> tuple[int, int]:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        pending = int(conn.execute(
            "SELECT COUNT(*) FROM events WHERE sent_at IS NULL AND cancelled=0"
        ).fetchone()[0] or 0)
        sent = int(conn.execute(
            "SELECT COUNT(*) FROM events WHERE sent_at IS NOT NULL"
        ).fetchone()[0] or 0)
    return pending, sent


def _cloud_link_id(reception_patient_id: object) -> str:
    """Reads only the verified patient link from Historia Neon."""
    try:
        import reception_history_identity_consolidated as identity
        conn = identity._connect_public()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT clinical_patient_id
                FROM public.patient_links
                WHERE reception_patient_id=%s AND deleted_at IS NULL
                LIMIT 1
                """,
                (str(reception_patient_id),),
            )
            row = cur.fetchone()
            return _clean(row[0], 120) if row and row[0] else ""
        finally:
            conn.close()
    except Exception:
        return ""


def _flush_lan_outbox(max_items: int = 30) -> None:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        rows = conn.execute(
            """
            SELECT event_id,payload_json
            FROM events
            WHERE sent_at IS NULL AND cancelled=0
            ORDER BY created_at
            LIMIT ?
            """,
            (max(1, int(max_items)),),
        ).fetchall()
    for event_id, payload_json in rows:
        try:
            payload = json.loads(payload_json)
            if send_lan(payload):
                _lan_outbox_mark(str(event_id), sent=True)
            else:
                _lan_outbox_mark(str(event_id), error=_snapshot().get("lan_last_error") or "Historia no disponible por LAN")
                break
        except Exception as exc:
            _lan_outbox_mark(str(event_id), error=f"{type(exc).__name__}: {str(exc)[:180]}")
            break


def _lan_event_targets(visit_id: object = "", reception_patient_id: object = "") -> list[str]:
    _ensure_lan_outbox()
    wanted_visit = str(visit_id or "").strip()
    wanted_patient = str(reception_patient_id or "").strip()
    found = []
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        rows = conn.execute("SELECT event_id,payload_json FROM events ORDER BY created_at DESC").fetchall()
    for event_id, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except Exception:
            continue
        visits = {str(x) for x in (payload.get("visit_ids") or []) if x is not None}
        same_visit = bool(wanted_visit and wanted_visit in visits)
        same_patient = bool(wanted_patient and str(payload.get("reception_patient_id") or "") == wanted_patient)
        if same_visit or (not wanted_visit and same_patient):
            found.append(str(event_id))
    return list(dict.fromkeys(found))


def _lan_set_cancelled(event_id: str, cancelled: bool) -> tuple[bool, dict | None]:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        row = conn.execute(
            "SELECT sent_at,payload_json FROM events WHERE event_id=? LIMIT 1",
            (str(event_id),),
        ).fetchone()
        if not row:
            return False, None
        conn.execute(
            "UPDATE events SET cancelled=? WHERE event_id=?",
            (1 if cancelled else 0, str(event_id)),
        )
        conn.commit()
    try:
        payload = json.loads(row[1])
    except Exception:
        payload = None
    return bool(row[0]), payload

'''
marker = "def _send_control_lan(action: str, target_event_id: str, visit_id: object = \"\") -> bool:\n"
if helpers.strip() not in l:
    if marker not in l:
        raise AssertionError("LAN control marker not found")
    l = l.replace(marker, helpers + marker, 1)

l = replace_top_function(l, "hybrid_queue_attention", '''def hybrid_queue_attention(*, reception_patient_id: object, display_name: object,
                           identification: object = "", attention_type: object = "Consulta",
                           patient_status: object = "", reception_turn: object = None,
                           visit_ids: list[object] | None = None,
                           birth_date: object = "", phone: object = "",
                           email: object = "", address: object = "") -> str:
    label = _clean(attention_type, 180).upper()
    if label.startswith("PROCEDIMIENTO"):
        return ""
    event_id = _cloud._event_id(reception_patient_id, visit_ids)
    payload = {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "clinical_patient_id": _cloud_link_id(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "patient_status": _clean(patient_status, 40),
        "reception_turn": reception_turn,
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "birth_date": _clean(birth_date, 40),
        "phone": _clean(phone, 120),
        "email": _clean(email, 180),
        "address": _clean(address, 360),
        "queued_at": _now(),
    }
    _lan_outbox_put(payload)
    if send_lan(payload):
        _lan_outbox_mark(event_id, sent=True)
    else:
        _lan_outbox_mark(event_id, error=_snapshot().get("lan_last_error") or "Pendiente de entrega LAN")
    return event_id
''')

l = replace_top_function(l, "_hybrid_control", '''def _hybrid_control(action: str, *, visit_id: object, reception_patient_id: object = "") -> list[str]:
    targets = _lan_event_targets(visit_id=visit_id, reception_patient_id=reception_patient_id)
    for target in targets:
        was_sent, payload = _lan_set_cancelled(target, action == "cancel")
        if action == "cancel":
            if was_sent:
                threading.Thread(
                    target=_send_control_lan,
                    args=("cancel", target, visit_id),
                    daemon=True,
                    name="historia-lan-cancel",
                ).start()
        else:
            if was_sent:
                threading.Thread(
                    target=_send_control_lan,
                    args=("restore", target, visit_id),
                    daemon=True,
                    name="historia-lan-restore",
                ).start()
            elif payload:
                threading.Thread(
                    target=_flush_lan_outbox,
                    daemon=True,
                    name="historia-lan-restore-pending",
                ).start()
    return targets
''')

l = replace_top_function(l, "hybrid_bridge_status", '''def hybrid_bridge_status() -> dict:
    lan = _snapshot()
    try:
        pending, sent = _lan_outbox_counts()
    except Exception:
        pending, sent = 0, 0
    return {
        "configured": True,
        "pending": pending,
        "sent": sent,
        "cloud_reachable": False,
        "doctor_online": bool(lan.get("lan_online")),
        "last_error": lan.get("lan_last_error") or "",
        "lan_online": bool(lan.get("lan_online")),
        "lan_host": lan.get("lan_host") or "",
        "lan_version": lan.get("lan_version") or "",
        "lan_last_seen": lan.get("lan_last_seen") or "",
        "lan_last_handoff_at": lan.get("lan_last_handoff_at") or "",
        "lan_latency_ms": lan.get("lan_latency_ms"),
        "transport": "lan" if lan.get("lan_online") else "local",
        "waiting_queue_transport": "lan_only",
    }
''')

l = replace_top_function(l, "_monitor_loop", '''def _monitor_loop():
    while True:
        try:
            state = probe_once()
            if state.get("lan_online"):
                _flush_lan_outbox()
        except Exception:
            pass
        time.sleep(20)
''')

if "def identity_status(" in l or "def identity_prepare(" in l or "def identity_search(" in l or "def identity_link(" in l:
    raise AssertionError("LAN identity helpers still present")
hq = ast.get_source_segment(l, top_function(l, "hybrid_queue_attention")) or ""
if "_ORIGINAL_QUEUE" in hq:
    raise AssertionError("waiting queue still writes through cloud queue")
write(l_path, l)


# ---------------------------------------------------------------------------
# Historia 1.3.84 — LAN endpoint is waiting-room transport only.
# ---------------------------------------------------------------------------
h_path = "historia-clinica/app/lan_bridge.py"
h = read(h_path)
h = remove_class_methods(
    h,
    "LanService",
    {"_identity_summary", "_identity_patient", "_identity_link_id", "_identity_upsert_link", "identity_status", "_wake_sync", "identity_search", "identity_link"},
)

old_allowed = '                if path not in {"/handoff", "/cancel", "/restore", "/identity/status", "/identity/prepare", "/identity/search", "/identity/link"}:\n'
new_allowed = '                if path not in {"/handoff", "/cancel", "/restore"}:\n'
if old_allowed not in h:
    raise AssertionError("Historia LAN identity path list not found")
h = h.replace(old_allowed, new_allowed, 1)

old_dispatch = '''                    if path == "/cancel":
                        result = service.accept_cancel(payload, self.remote_ip)
                    elif path == "/restore":
                        result = service.accept_restore(payload, self.remote_ip)
                    elif path == "/identity/status":
                        result = service.identity_status(payload, self.remote_ip, auto_link=False)
                    elif path == "/identity/prepare":
                        result = service.identity_status(payload, self.remote_ip, auto_link=True)
                    elif path == "/identity/search":
                        result = service.identity_search(payload, self.remote_ip)
                    elif path == "/identity/link":
                        result = service.identity_link(payload, self.remote_ip)
                    else:
                        result = service.accept_handoff(payload, self.remote_ip)
'''
new_dispatch = '''                    if path == "/cancel":
                        result = service.accept_cancel(payload, self.remote_ip)
                    elif path == "/restore":
                        result = service.accept_restore(payload, self.remote_ip)
                    else:
                        result = service.accept_handoff(payload, self.remote_ip)
'''
if old_dispatch not in h:
    raise AssertionError("Historia LAN identity dispatch not found")
h = h.replace(old_dispatch, new_dispatch, 1)

old_resolve = "            clinical_id = self._resolve_patient(conn, reception_patient_id, identification)\n"
new_resolve = "            clinical_id = _clean(payload.get(\"clinical_patient_id\"), 120) or self._resolve_patient(conn, reception_patient_id, identification)\n"
if h.count(old_resolve) != 1:
    raise AssertionError(f"clinical id resolution count: {h.count(old_resolve)}")
h = h.replace(old_resolve, new_resolve, 1)

for path in ("/identity/status", "/identity/prepare", "/identity/search", "/identity/link"):
    if path in h:
        raise AssertionError(f"Historia LAN still exposes {path}")
write(h_path, h)


# ---------------------------------------------------------------------------
# Versions and manifests.
# ---------------------------------------------------------------------------
def bump_version(path: str, version: str):
    doc = json.loads(read(path))
    doc["version"] = version
    write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def bump_manifest(path: str, version: str, purpose: str, previous: str, notes_update: dict):
    doc = json.loads(read(path))
    for key in ("version", "app_version", "runtime_version"):
        if key in doc:
            doc[key] = version
    notes = doc.setdefault("notes", {})
    notes["purpose"] = purpose
    notes["previous_version"] = previous
    notes.update(notes_update)
    write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


bump_version("recepcion/app/recepcion-version.json", "4.6.20")
bump_manifest(
    "recepcion/app/update_manifest.json",
    "4.6.20",
    "Neon es la autoridad única para buscar y vincular Historia desde Recepción; LAN queda reservado para Pacientes en espera con reintento local.",
    "4.6.19",
    {
        "history_identity_transport": "neon_only",
        "history_identity_lan_fallback": False,
        "history_database_url_required_on_reception": True,
        "waiting_queue_transport": "lan_only",
        "waiting_queue_cloud_write": False,
        "waiting_queue_local_retry": True,
        "waiting_queue_carries_clinical_patient_id": True,
        "normal_subsequent_history_link_visible": True,
        "manual_legacy_subsequent_history_link_visible": True,
        "new_patient_history_link_hidden": True,
        "waiting_queue_logic_changes": True,
        "database_schema_changes": False,
        "patient_data_destructive_changes": False,
    },
)

bump_version("historia-clinica/app/historia-version.json", "1.3.84")
bump_manifest(
    "historia-clinica/app/update_manifest.json",
    "1.3.84",
    "LAN queda reservado para Pacientes en espera; la identidad y vinculación se resuelven directamente en Neon desde Recepción.",
    "1.3.83",
    {
        "lan_handoff_preserved": True,
        "lan_identity_status": False,
        "lan_identity_exact_id_autolink": False,
        "lan_identity_manual_search": False,
        "lan_identity_manual_link": False,
        "lan_identity_updates_pending_queue": False,
        "waiting_queue_transport": "lan_only",
        "waiting_queue_accepts_verified_clinical_patient_id": True,
        "clinical_database_credentials_exposed_to_reception": False,
        "database_schema_changes": False,
        "clinical_data_changes": False,
        "patient_data_destructive_changes": False,
    },
)

print("PATCH_OK Reception 4.6.20 / Historia 1.3.84")
