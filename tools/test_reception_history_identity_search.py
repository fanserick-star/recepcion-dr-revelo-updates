from __future__ import annotations

import importlib.util
import re
import sys
import types
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def fuzzy(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.upper().replace("Z", "S").split())


def install_stub():
    identity = types.ModuleType("reception_history_identity_consolidated")
    identity._fuzzy_text = fuzzy
    identity._usable_id = lambda v: (
        re.sub("[^A-Z0-9]", "", str(v or "").upper())
        if len(re.sub("[^A-Z0-9]", "", str(v or "").upper())) >= 6 else ""
    )
    identity._norm_phone = lambda v: re.sub(r"[^0-9]", "", str(v or ""))
    identity._iso_date = lambda v: str(v or "")[:10]
    identity._clean = lambda v, limit=500: str(v or "").strip()[:limit]
    identity._dict_row = lambda cur, row: dict(row)
    identity._patient_row = lambda cur, patient_id: None
    identity.APP_VERSION = "4.8.1"
    identity.core = types.SimpleNamespace(
        APP_VERSION="4.8.1",
        V460_OVERLAY_JS="",
        V460_OVERLAY_CSS="",
        Depends=lambda function: None,
        current_user=lambda: None,
    )
    class DummyApp:
        def get(self, *_args, **_kwargs):
            return lambda f: f
    identity.app = DummyApp()
    sys.modules["reception_history_identity_consolidated"] = identity


class FakeCursor:
    """Emulates result selection and SQL LIMIT; no real Neon is contacted."""
    def __init__(self, rows):
        self.rows = rows
        self.filtered = []
        self.queries = []

    def execute(self, sql, params):
        self.queries.append((sql, params))
        # Exact match uses an AND between token expressions; fallback uses OR.
        name_query = bool("TRANSLATE(UPPER(CONCAT_WS" in sql)
        strict = " LIKE %s AND TRANSLATE(" in sql
        tokens = [
            x[1:-1] for x in params[:-1]
            if isinstance(x, str) and x.startswith("%") and x.endswith("%")
            and re.search(r"[A-Z]", x)
        ]
        results = []
        for r in self.rows:
            value = fuzzy((r["name_search"] or "") + " " + (r["name"] or ""))
            matched = all(t in value for t in tokens) if strict else any(t in value for t in tokens)
            if name_query and tokens and matched:
                results.append(r)
            elif (r.get("national_id_search") or "") in params[:-1] and r.get("national_id_search"):
                results.append(r)
        results.sort(key=lambda row: (row["name"], row["id"]))
        self.filtered = results[:int(params[-1])]

    def fetchall(self):
        return list(self.filtered)


def person(pid, name, cedula="", search=None, count=0):
    return {
        "id": pid, "name": name,
        "name_search": name if search is None else search,
        "national_id": cedula,
        "national_id_search": cedula,
        "birth_date": "",
        "phone": "",
        "history_date_count": count,
        "last_history_date": "2020-01-05" if count else "",
        "merged_into_patient_id": "",
    }


def main():
    install_stub()
    path = APP / "reception_history_identity_name_search.py"
    spec = importlib.util.spec_from_file_location("reception_identity_search_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    old = APP / "reception_history_identity_consolidated.py"
    js = old.read_text(encoding="utf-8-sig")
    begin = js.index("  function labelFrom(host){")
    end = js.index("\n  function place(", begin)
    label_source = js[begin:end]
    assert "host.querySelector('.v4413-profile-name h2')" in label_source
    assert "host.querySelector('.v4413-profile-identity b')" not in label_source, (
        "Bug: el modal está usando la cédula como nombre"
    )
    assert "const receptionPatient=await call('/api/patients/'" in js
    assert "if(!input.value)" in js

    # 190 recent records with the first surname only should never displace an
    # old chart that matches BOTH surnames. The old SQL OR+LIMIT=90 did.
    samples = [person(f"extra{i}", f"PICO PACIENTE {i}") for i in range(190)]
    samples += [
        person("target", "VELIZ PICO SAUL AARON", "0912345678", search="", count=8),
        person("other", "VELIZ PICO MARIA ANA", "", count=3),
        person("wrong", "VELIZ VALENCIA SAUL AARON", "", count=11),
        person("accent", "MERO IZQUIERDO ÑOÑO RAÚL", "", count=2),
    ]
    reception = {
        "name": "VELIZ PICO SAUL AARON",
        "national_id": "0912345678",
        "phone": "",
        "birth_date": "",
    }
    cur = FakeCursor(samples)
    found = module._search_candidates_name_first(cur, reception, "PICO VELIZ", 20)
    assert [r["id"] for r in found][:2] == ["target", "other"], found
    assert all("VELIZ" in r["name"] and "PICO" in r["name"] for r in found)
    assert len(cur.queries) == 1, "Si hay coincidencias de ambos apellidos no se debe hacer búsqueda amplia"
    sql, params = cur.queries[0]
    assert " LIKE %s AND TRANSLATE(" in sql, "Los apellidos deben buscarse con AND"
    assert "ORDER BY p.name ASC" in sql, "La antigüedad no debe ocultar fichas correctas"
    assert "COALESCE(p.name_search,'')" in sql and "COALESCE(p.name,'')" in sql
    assert params[:2] == ("%PICO%", "%VELIS%"), params
    assert "0912345678" not in params, "La cédula de Recepción no debe diluir un nombre escrito"

    cur2 = FakeCursor(samples)
    reversed_rows = module._search_candidates_name_first(cur2, reception, "VELIZ PICO", 20)
    assert [r["id"] for r in reversed_rows][:2] == ["target", "other"]
    cur3 = FakeCursor(samples)
    accents = module._search_candidates_name_first(cur3, {"name": ""}, "IZQUIERDO MERO", 20)
    assert accents and accents[0]["name"] == "MERO IZQUIERDO ÑOÑO RAÚL"

    # Only suggestion/ranking code changes. Clinical identity confirmation and
    # waiting-room/database mutations remain in their existing modules.
    search_source = path.read_text(encoding="utf-8-sig")
    assert "identity._search_candidates = _search_candidates_name_first" in search_source
    assert "INSERT INTO" not in search_source and "UPDATE public." not in search_source
    print("RECEPTION_NAME_LINK_SEARCH_OK")


if __name__ == "__main__":
    main()
