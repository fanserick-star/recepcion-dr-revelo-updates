from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Historia 1.3.83: expose identity lookup/link over the already-authenticated LAN
# bridge. No database credential is copied to Reception.
# ---------------------------------------------------------------------------
h_path = "historia-clinica/app/lan_bridge.py"
h = read(h_path)
if "# v1.3.83 — identidad clínica segura por LAN para Recepción." not in h:
    h = replace_once(
        h,
        "import time\nimport uuid\n",
        "import time\nimport unicodedata\nimport uuid\n",
        "Historia unicodedata import",
    )
    h = replace_once(
        h,
        "def _normalize_id(value: object) -> str:\n    return re.sub(r\"[^A-Z0-9]\", \"\", _clean(value, 160).upper())\n\n\nclass LanService:",
        "def _normalize_id(value: object) -> str:\n    return re.sub(r\"[^A-Z0-9]\", \"\", _clean(value, 160).upper())\n\n\ndef _normalize_text(value: object) -> str:\n    raw = unicodedata.normalize(\"NFD\", _clean(value, 500))\n    raw = \"\".join(ch for ch in raw if unicodedata.category(ch) != \"Mn\")\n    return re.sub(r\"\\s+\", \" \", raw).strip().upper().replace(\"Z\", \"S\")\n\n\ndef _normalize_phone(value: object) -> str:\n    digits = re.sub(r\"\\D\", \"\", _clean(value, 80))\n    if len(digits) == 12 and digits.startswith(\"593\"):\n        digits = \"0\" + digits[3:]\n    return digits\n\n\nclass LanService:",
        "Historia normalizers",
    )

    methods = '''    # v1.3.83 — identidad clínica segura por LAN para Recepción.
    def _identity_summary(self, conn: sqlite3.Connection, patient_id: str) -> dict:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT CASE
                     WHEN COALESCE(deleted_at,'')=''
                      AND COALESCE(note_status,'signed')<>'draft'
                      AND TRIM(COALESCE(encounter_date,''))<>''
                     THEN encounter_date END),
                   MAX(CASE
                     WHEN COALESCE(deleted_at,'')=''
                      AND COALESCE(note_status,'signed')<>'draft'
                      AND TRIM(COALESCE(encounter_date,''))<>''
                     THEN encounter_date END)
            FROM encounters
            WHERE patient_id=?
            """,
            (str(patient_id),),
        ).fetchone() or (0, None)
        return {
            "history_date_count": int(row[0] or 0),
            "last_history_date": _clean(row[1], 20),
        }

    def _identity_patient(self, conn: sqlite3.Connection, patient_id: str) -> dict | None:
        row = conn.execute(
            """
            SELECT id,name,name_search,national_id,national_id_search,birth_date,
                   phone,email,address,merged_into_patient_id
            FROM patients
            WHERE id=? AND COALESCE(deleted_at,'')=''
            LIMIT 1
            """,
            (str(patient_id),),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        merged = _clean(data.get("merged_into_patient_id"), 120)
        if merged and merged != str(data.get("id") or ""):
            canonical = conn.execute(
                """
                SELECT id,name,name_search,national_id,national_id_search,birth_date,
                       phone,email,address,merged_into_patient_id
                FROM patients
                WHERE id=? AND COALESCE(deleted_at,'')=''
                LIMIT 1
                """,
                (merged,),
            ).fetchone()
            if canonical:
                data = dict(canonical)
        data.update(self._identity_summary(conn, str(data["id"])))
        return data

    def _identity_link_id(self, conn: sqlite3.Connection, reception_patient_id: str) -> str:
        row = conn.execute(
            "SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id=? LIMIT 1",
            (str(reception_patient_id),),
        ).fetchone()
        return _clean(row[0], 120) if row and row[0] else ""

    def _identity_upsert_link(self, conn: sqlite3.Connection, reception_patient_id: str,
                              clinical_patient_id: str, matched_by: str) -> None:
        stamp = _now()
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
                str(reception_patient_id), str(clinical_patient_id),
                _clean(matched_by, 80), 1, stamp, stamp, stamp,
            ),
        )
        conn.execute(
            """
            UPDATE waiting_queue
               SET clinical_patient_id=?,updated_at=?
             WHERE reception_patient_id=?
               AND status IN ('waiting','in_consultation')
            """,
            (str(clinical_patient_id), stamp, str(reception_patient_id)),
        )

    def identity_status(self, payload: dict, remote_ip: str, *, auto_link: bool = False) -> dict:
        reception_patient_id = _clean(payload.get("reception_patient_id"), 120)
        identification = _clean(payload.get("identification"), 120)
        if not reception_patient_id:
            raise ValueError("Falta el identificador del paciente de Recepción")
        auto_linked = False
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            clinical_id = self._identity_link_id(conn, reception_patient_id)
            if not clinical_id and auto_link:
                ident = _normalize_id(identification)
                if ident:
                    rows = conn.execute(
                        """
                        SELECT id FROM patients
                        WHERE national_id_search=?
                          AND COALESCE(deleted_at,'')=''
                          AND COALESCE(merged_into_patient_id,'')=''
                        LIMIT 3
                        """,
                        (ident,),
                    ).fetchall()
                    if len(rows) == 1:
                        clinical_id = str(rows[0][0])
                        self._identity_upsert_link(
                            conn, reception_patient_id, clinical_id,
                            "reception_lan_exact_identification",
                        )
                        conn.commit()
                        auto_linked = True
            patient = self._identity_patient(conn, clinical_id) if clinical_id else None
            if clinical_id and patient and str(patient.get("id")) != clinical_id:
                clinical_id = str(patient["id"])
                self._identity_upsert_link(
                    conn, reception_patient_id, clinical_id,
                    "reception_lan_canonical",
                )
                conn.commit()
        self._touch_reception(remote_ip)
        if auto_linked:
            self._wake_sync()
        return {
            "ok": True,
            "reachable": True,
            "transport": "lan",
            "reception_patient_id": reception_patient_id,
            "linked": bool(patient),
            "auto_linked": auto_linked,
            "clinical_patient": patient,
            "history_date_count": int((patient or {}).get("history_date_count") or 0),
            "last_history_date": _clean((patient or {}).get("last_history_date"), 20),
            "warnings": [],
        }

    def _wake_sync(self) -> None:
        try:
            if self.sync_service is not None:
                self.sync_service.mark_activity()
                self.sync_service.wake()
        except Exception:
            pass

    def identity_search(self, payload: dict, remote_ip: str) -> dict:
        query = _clean(payload.get("q"), 180)
        wanted_name = _normalize_text(payload.get("name") or query)
        wanted_id = _normalize_id(payload.get("identification") or query)
        wanted_birth = _clean(payload.get("birth_date"), 20)
        wanted_phone = _normalize_phone(payload.get("phone") or query)
        query_tokens = [t for t in _normalize_text(query).split() if len(t) >= 2]
        wanted_tokens = [t for t in wanted_name.split() if len(t) >= 2]
        try:
            limit = max(1, min(int(payload.get("limit") or 30), 40))
        except Exception:
            limit = 30

        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            raw_rows = conn.execute(
                """
                SELECT id,name,name_search,national_id,national_id_search,birth_date,
                       phone,email,address,merged_into_patient_id
                FROM patients
                WHERE COALESCE(deleted_at,'')=''
                  AND COALESCE(merged_into_patient_id,'')=''
                """
            ).fetchall()
            scored = []
            for raw in raw_rows:
                row = dict(raw)
                row_name = _normalize_text(row.get("name_search") or row.get("name"))
                row_id = _normalize_id(row.get("national_id_search") or row.get("national_id"))
                row_birth = _clean(row.get("birth_date"), 20)
                row_phone = _normalize_phone(row.get("phone"))
                score = 0
                reasons = []
                if wanted_id and len(wanted_id) >= 6 and row_id == wanted_id:
                    score += 140
                    reasons.append("misma identificación")
                if wanted_phone and len(wanted_phone) >= 7 and row_phone and row_phone[-9:] == wanted_phone[-9:]:
                    score += 85
                    reasons.append("mismo celular")
                if wanted_birth and row_birth and row_birth[:10] == wanted_birth[:10]:
                    score += 70
                    reasons.append("misma fecha de nacimiento")
                if wanted_name and row_name:
                    if row_name == wanted_name:
                        score += 90
                        reasons.append("mismo nombre")
                    matches = sum(1 for token in wanted_tokens if token in row_name.split())
                    if matches:
                        score += min(70, matches * 16)
                        if matches >= max(2, len(wanted_tokens) - 1):
                            reasons.append("nombre muy parecido")
                if query_tokens:
                    qmatches = sum(1 for token in query_tokens if token in row_name.split())
                    score += min(45, qmatches * 12)
                if score <= 0:
                    continue
                row["match_score"] = score
                row["match_reasons"] = list(dict.fromkeys(reasons))
                scored.append(row)

            scored.sort(key=lambda r: int(r.get("match_score") or 0), reverse=True)
            results = []
            for row in scored[: max(80, limit * 2)]:
                row.update(self._identity_summary(conn, str(row["id"])))
                results.append(row)
            results.sort(
                key=lambda r: (
                    int(r.get("match_score") or 0),
                    int(r.get("history_date_count") or 0),
                    _clean(r.get("last_history_date"), 20),
                ),
                reverse=True,
            )
            results = results[:limit]

        self._touch_reception(remote_ip)
        return {
            "ok": True,
            "reachable": True,
            "transport": "lan",
            "results": [
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "national_id": r.get("national_id"),
                    "birth_date": r.get("birth_date"),
                    "phone": r.get("phone"),
                    "email": r.get("email"),
                    "address": r.get("address"),
                    "history_date_count": int(r.get("history_date_count") or 0),
                    "last_history_date": r.get("last_history_date") or "",
                    "match_score": int(r.get("match_score") or 0),
                    "match_reasons": r.get("match_reasons") or [],
                }
                for r in results
            ],
        }

    def identity_link(self, payload: dict, remote_ip: str) -> dict:
        reception_patient_id = _clean(payload.get("reception_patient_id"), 120)
        clinical_patient_id = _clean(payload.get("clinical_patient_id"), 120)
        reception_ident = _normalize_id(payload.get("identification"))
        if not reception_patient_id or not clinical_patient_id:
            raise ValueError("Faltan identificadores para vincular la ficha")

        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            patient = self._identity_patient(conn, clinical_patient_id)
            if not patient:
                raise ValueError("La ficha seleccionada ya no existe en Historia Clínica")
            target_ident = _normalize_id(patient.get("national_id_search") or patient.get("national_id"))
            if reception_ident and target_ident and reception_ident != target_ident:
                raise ValueError("La ficha seleccionada tiene otra cédula/identificación")
            clinical_patient_id = str(patient["id"])
            self._identity_upsert_link(
                conn, reception_patient_id, clinical_patient_id,
                "reception_lan_manual_verified",
            )
            try:
                conn.execute(
                    """
                    INSERT INTO audit_log(
                      occurred_at,actor,action,entity_type,entity_id,details_json
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        _now(), "Recepción", "historia_identity_manual_link_lan",
                        "patient_link", reception_patient_id,
                        json.dumps({"clinical_patient_id": clinical_patient_id}, ensure_ascii=False),
                    ),
                )
            except sqlite3.Error:
                pass
            conn.commit()
            patient = self._identity_patient(conn, clinical_patient_id)

        self._touch_reception(remote_ip)
        self._wake_sync()
        return {
            "ok": True,
            "reachable": True,
            "transport": "lan",
            "linked": True,
            "reception_patient_id": reception_patient_id,
            "clinical_patient": patient,
            "history_date_count": int((patient or {}).get("history_date_count") or 0),
            "last_history_date": _clean((patient or {}).get("last_history_date"), 20),
            "warnings": [],
        }

'''
    h = replace_once(
        h,
        "    def accept_handoff(self, payload: dict, remote_ip: str) -> dict:\n",
        methods + "    def accept_handoff(self, payload: dict, remote_ip: str) -> dict:\n",
        "Historia LAN identity methods",
    )
    h = replace_once(
        h,
        '                if path not in {"/handoff", "/cancel", "/restore"}:\n',
        '                if path not in {"/handoff", "/cancel", "/restore", "/identity/status", "/identity/prepare", "/identity/search", "/identity/link"}:\n',
        "Historia LAN allowed paths",
    )
    h = replace_once(
        h,
        '''                    if path == "/cancel":
                        result = service.accept_cancel(payload, self.remote_ip)
                    elif path == "/restore":
                        result = service.accept_restore(payload, self.remote_ip)
                    else:
                        result = service.accept_handoff(payload, self.remote_ip)
''',
        '''                    if path == "/cancel":
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
''',
        "Historia LAN identity dispatch",
    )
    write(h_path, h)


# ---------------------------------------------------------------------------
# Reception 4.6.18: call the identity bridge through LAN when the private
# Historia cloud credential is intentionally absent on the Reception PC.
# ---------------------------------------------------------------------------
rt_path = "recepcion/app/historia_lan_transport.py"
rt = read(rt_path)
if "def identity_prepare(payload: dict) -> dict | None:" not in rt:
    helpers = '''

def _identity_request(path: str, payload: dict, *, timeout: float = 2.4) -> dict | None:
    state = _snapshot()
    host = str(state.get("lan_host") or "")
    token = str(state.get("token") or "")
    if not host or not token or not state.get("lan_online"):
        state = probe_once()
        host = str(state.get("lan_host") or "")
        token = str(state.get("token") or "")
    if not host or not token:
        return None

    for attempt in range(2):
        try:
            result = _http_json(
                host, path, method="POST", payload=payload,
                token=token, timeout=timeout,
            )
            if result.get("ok") is False:
                raise RuntimeError(str(result.get("error") or "Historia rechazó la consulta"))
            _set_state(
                lan_online=True,
                lan_last_seen=_now(),
                lan_last_error="",
            )
            return result
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and attempt == 0:
                _set_state(token="", token_host="")
                fresh = probe_once()
                host = str(fresh.get("lan_host") or "")
                token = str(fresh.get("token") or "")
                if host and token:
                    continue
            _set_state(lan_last_error=f"HTTP {getattr(exc, 'code', '?')}")
            return None
        except Exception as exc:
            _set_state(lan_last_error=f"{type(exc).__name__}: {str(exc)[:160]}")
            return None
    return None


def identity_status(payload: dict) -> dict | None:
    return _identity_request("/identity/status", payload)


def identity_prepare(payload: dict) -> dict | None:
    return _identity_request("/identity/prepare", payload)


def identity_search(payload: dict) -> dict | None:
    return _identity_request("/identity/search", payload, timeout=3.5)


def identity_link(payload: dict) -> dict | None:
    return _identity_request("/identity/link", payload, timeout=3.5)

'''
    rt = replace_once(
        rt,
        "\ndef _send_control_lan(action: str, target_event_id: str, visit_id: object = \"\") -> bool:\n",
        helpers + "\ndef _send_control_lan(action: str, target_event_id: str, visit_id: object = \"\") -> bool:\n",
        "Reception LAN identity helpers",
    )
    write(rt_path, rt)

ri_path = "recepcion/app/reception_history_identity_consolidated.py"
ri = read(ri_path)
if "# v4.6.18 — fallback de identidad por LAN sin credenciales clínicas en Recepción." not in ri:
    ri = replace_once(
        ri,
        "import core_runtime as core\nimport historia_bridge\n",
        "import core_runtime as core\nimport historia_bridge\nimport historia_lan_transport as historia_lan\n",
        "Reception identity LAN import",
    )
    old_condition = "    const attentionIsSubsequent=attentionModal&&norm(host.querySelector('#attentionStatus')?.textContent||'').includes('SUBSECUENTE');"
    new_condition = "    const attentionIsSubsequent=attentionModal&&(()=>{try{return typeof attentionContext!=='undefined'&&!!attentionContext?.manualSubsequent}catch(_e){return false}})();"
    ri = replace_once(
        ri,
        old_condition,
        new_condition,
        "manual legacy subsequent UI condition",
    )

    wrappers = '''

# v4.6.18 — fallback de identidad por LAN sin credenciales clínicas en Recepción.
def _v4618_lan_payload(db, reception_patient_id: int, *, q: str = "", clinical_patient_id: str = "") -> dict:
    patient = _reception_patient(db, reception_patient_id)
    demo = _demographics(patient)
    return {
        "reception_patient_id": str(patient.id),
        "name": demo.get("name") or "",
        "identification": demo.get("national_id") or "",
        "birth_date": demo.get("birth_date") or "",
        "phone": demo.get("phone") or "",
        "email": demo.get("email") or "",
        "address": demo.get("address") or "",
        "q": _clean(q, 180),
        "clinical_patient_id": _clean(clinical_patient_id, 120),
        "limit": 30,
    }


def _v4618_unavailable(message: str = "") -> dict:
    detail = _clean(message, 180)
    friendly = (
        "Historia Clínica no está disponible en la red local. "
        "Abra Historia Clínica en la PC del doctor y pulse Reintentar."
    )
    return {
        "ok": False,
        "reachable": False,
        "linked": False,
        "history_date_count": 0,
        "last_history_date": "",
        "error": friendly,
        "technical_error": detail,
    }


_v4618_status_cloud = historia_identity_status
_v4618_prepare_cloud = historia_identity_prepare
_v4618_search_cloud = historia_identity_search
_v4618_link_cloud = historia_identity_link

for _route in list(app.router.routes):
    _path = getattr(_route, "path", None)
    _methods = set(getattr(_route, "methods", set()) or set())
    if _path == "/api/historia-identity/status/{reception_patient_id}" and "GET" in _methods:
        app.router.routes.remove(_route)
    elif _path == "/api/historia-identity/prepare/{reception_patient_id}" and "POST" in _methods:
        app.router.routes.remove(_route)
    elif _path == "/api/historia-identity/sync/{reception_patient_id}" and "POST" in _methods:
        app.router.routes.remove(_route)
    elif _path == "/api/historia-identity/search" and "GET" in _methods:
        app.router.routes.remove(_route)
    elif _path == "/api/historia-identity/link" and "POST" in _methods:
        app.router.routes.remove(_route)


@app.get("/api/historia-identity/status/{reception_patient_id}")
def v4618_historia_identity_status(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    cloud = _v4618_status_cloud(reception_patient_id, db, user)
    if cloud.get("ok") is not False and cloud.get("reachable") is not False:
        return cloud
    payload = _v4618_lan_payload(db, reception_patient_id)
    lan = historia_lan.identity_status(payload)
    return lan or _v4618_unavailable(cloud.get("error") or "")


@app.post("/api/historia-identity/prepare/{reception_patient_id}")
def v4618_historia_identity_prepare(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    cloud = _v4618_prepare_cloud(reception_patient_id, db, user)
    if cloud.get("ok") is not False and cloud.get("reachable") is not False:
        return cloud
    payload = _v4618_lan_payload(db, reception_patient_id)
    lan = historia_lan.identity_prepare(payload)
    return lan or _v4618_unavailable(cloud.get("error") or "")


@app.post("/api/historia-identity/sync/{reception_patient_id}")
def v4618_historia_identity_sync(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return v4618_historia_identity_prepare(reception_patient_id, db, user)


@app.get("/api/historia-identity/search")
def v4618_historia_identity_search(
    q: str = "",
    reception_patient_id: int = 0,
    limit: int = 30,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    cloud = _v4618_search_cloud(q, reception_patient_id, limit, db, user)
    if cloud.get("ok") is not False and cloud.get("reachable") is not False:
        return cloud
    if not reception_patient_id:
        return cloud
    payload = _v4618_lan_payload(db, reception_patient_id, q=q)
    payload["limit"] = max(1, min(int(limit or 30), 40))
    lan = historia_lan.identity_search(payload)
    return lan or {
        "ok": False,
        "reachable": False,
        "results": [],
        "error": _v4618_unavailable(cloud.get("error") or "")["error"],
    }


@app.post("/api/historia-identity/link")
def v4618_historia_identity_link(
    data: _HistoryLinkIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    cloud_error = ""
    try:
        return _v4618_link_cloud(data, db, user)
    except Exception as exc:
        cloud_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    payload = _v4618_lan_payload(
        db, data.reception_patient_id,
        clinical_patient_id=data.clinical_patient_id,
    )
    lan = historia_lan.identity_link(payload)
    if lan:
        try:
            core.audit(
                db, user, "historia_identity_manual_link_lan",
                json.dumps(
                    {
                        "reception_patient_id": int(data.reception_patient_id),
                        "clinical_patient_id": str(data.clinical_patient_id),
                    },
                    ensure_ascii=False,
                ),
            )
            db.commit()
        except Exception:
            pass
        return lan
    raise core.HTTPException(503, _v4618_unavailable(cloud_error)["error"])

'''
    ri = replace_once(
        ri,
        "\nV4613_CSS = r\"\"\"\n",
        wrappers + "\nV4613_CSS = r\"\"\"\n",
        "Reception LAN fallback routes",
    )
    write(ri_path, ri)


# Versions and manifests.
def bump(path: str, expected: str, target: str) -> None:
    doc = json.loads(read(path))
    current = str(doc.get("version") or "").strip()
    if current != expected:
        raise AssertionError(f"{path}: expected {expected}, found {current}")
    doc["version"] = target
    write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


bump("historia-clinica/app/historia-version.json", "1.3.82", "1.3.83")
bump("recepcion/app/recepcion-version.json", "4.6.17", "4.6.18")

hm_path = "historia-clinica/app/update_manifest.json"
hm = json.loads(read(hm_path))
for key in ("version", "app_version", "runtime_version"):
    if str(hm.get(key) or "").strip() != "1.3.82":
        raise AssertionError((hm_path, key, hm.get(key)))
    hm[key] = "1.3.83"
hnotes = hm.setdefault("notes", {})
hnotes.update({
    "purpose": "Agrega consulta y vinculación de identidad por el puente LAN autenticado para que Recepción no necesite credenciales privadas de Historia.",
    "previous_version": "1.3.82",
    "lan_identity_status": True,
    "lan_identity_exact_id_autolink": True,
    "lan_identity_manual_search": True,
    "lan_identity_manual_link": True,
    "lan_identity_updates_pending_queue": True,
    "clinical_database_credentials_exposed_to_reception": False,
    "database_schema_changes": False,
    "clinical_data_destructive_changes": False,
})
write(hm_path, json.dumps(hm, ensure_ascii=False, indent=2) + "\n")

rm_path = "recepcion/app/update_manifest.json"
rm = json.loads(read(rm_path))
for key in ("version", "app_version", "runtime_version"):
    if str(rm.get(key) or "").strip() != "4.6.17":
        raise AssertionError((rm_path, key, rm.get(key)))
    rm[key] = "4.6.18"
rnotes = rm.setdefault("notes", {})
rnotes.update({
    "purpose": "Corrige el panel de vínculo de Historia para que aparezca solo al marcar manualmente un subsecuente antiguo y usa LAN como fallback sin pedir HISTORIA_DATABASE_URL en Recepción.",
    "previous_version": "4.6.17",
    "history_link_panel_manual_legacy_only": True,
    "history_identity_lan_fallback": True,
    "history_database_url_required_on_reception": False,
    "history_raw_runtime_error_hidden": True,
    "waiting_queue_logic_changes": False,
    "billing_logic_changes": False,
    "printing_changes": False,
    "database_schema_changes": False,
    "patient_data_destructive_changes": False,
})
write(rm_path, json.dumps(rm, ensure_ascii=False, indent=2) + "\n")

print("PATCH_OK Reception 4.6.18 + Historia 1.3.83")
