from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = "updates/v4_4_14_ui_history"
OUT = ROOT / "updates/v4_4_15_historical_all"
VERSION = "4.4.15"


def git_text(path: str) -> str:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT).decode("utf-8-sig")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

app = git_text(f"{SRC}/app.py")
assert 'APP_VERSION = "4.4.14"' in app
assert 'if mode == "historical":' in app
assert "_historical_matches_current(h, current_rows)" in app
assert 'const VERSION=' in app and '4.4.14' in app

app = app.replace('APP_VERSION = "4.4.14"', 'APP_VERSION = "4.4.15"', 1)
app, n_badge = re.subn(r"(const VERSION=.*?)4\.4\.14(.*?;)", r"\g<1>4.4.15\g<2>", app, count=1)
assert n_badge == 1

old = '''    if mode == "historical":
        try:
            with LocalSessionLocal() as ldb:
                linked_keys = _historical_linked_keys(ldb)
                hist_rows = list(ldb.scalars(
                    select(HistoricalPatient)
                    .order_by(HistoricalPatient.last_visit_date.desc().nullslast(), HistoricalPatient.last_year.desc(), HistoricalPatient.nombre)
                    .limit(min(lim * 4, 120))
                ))
                current_rows = list(ldb.scalars(select(Patient)))
                result = []
                for h in hist_rows:
                    if h.source_key in linked_keys:
                        continue
                    if _historical_matches_current(h, current_rows):
                        continue
                    result.append(historical_dict(h))
                    if len(result) >= lim:
                        break
                return result
        except Exception:
            return []
'''
new = '''    if mode == "historical":
        # Este filtro es un visor del archivo histórico, no una lista de "sin vincular".
        # Debe mostrar TODO el índice 2020–2025 aunque la persona ya tenga ficha actual.
        # Al abrir un histórico, activate_historical_patient() sigue reutilizando una
        # coincidencia segura y evita crear duplicados.
        try:
            with LocalSessionLocal() as ldb:
                hist_rows = list(ldb.scalars(
                    select(HistoricalPatient)
                    .order_by(HistoricalPatient.last_visit_date.desc().nullslast(), HistoricalPatient.last_year.desc(), HistoricalPatient.nombre)
                    .limit(lim)
                ))
                return [historical_dict(h) for h in hist_rows]
        except Exception:
            return []
'''
assert app.count(old) == 1
app = app.replace(old, new, 1)
assert '_historical_matches_current(h, current_rows)' not in app[app.index('if mode == "historical":'):app.index('if mode == "review":')]

app_bytes = app.encode("utf-8")
(OUT / "app.py").write_bytes(app_bytes)

manifest = {
    "product": "recepcion-pacientes",
    "version": VERSION,
    "app_version": VERSION,
    "runtime_version": VERSION,
    "launcher_version": "4.3.100-standalone-7",
    "updater_version": "integrado-en-launcher",
    "copy": ["app.py", "update_manifest.json"],
}
manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
(OUT / "update_manifest.json").write_bytes(manifest_bytes)

base = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_15_historical_all"
latest = {
    "product": "recepcion-pacientes",
    "version": VERSION,
    "app_version": VERSION,
    "runtime_version": VERSION,
    "mandatory": True,
    "channel": "files-v3",
    "message": "v4.4.15: restaura Históricos 2020–2025 como visor completo; ya no oculta pacientes históricos que también tienen ficha actual.",
    "files": [
        {"path": "app.py", "url": f"{base}/app.py", "sha256": sha_bytes(app_bytes), "encoding": "utf-8"},
        {"path": "update_manifest.json", "url": f"{base}/update_manifest.json", "sha256": sha_bytes(manifest_bytes), "encoding": "utf-8"},
    ],
}
(ROOT / "build/v4415_historical_all/candidate_latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("V4415_BUILD_OK", sha_bytes(app_bytes))
