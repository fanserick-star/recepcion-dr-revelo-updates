from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "updates/v4_4_13_patient_profile"
CHANNEL = HERE / "candidate_latest.json"

# Ejecuta el constructor principal reproducible.
runpy.run_path(str(HERE / "build_v4413.py"), run_name="__main__")

# Afinado pequeño: los helpers históricos esperan el paciente con el resumen
# anidado, no el objeto summary aislado. No cambia datos, solo presentación.
js_path = OUT / "static/app.js"
js = js_path.read_text(encoding="utf-8")
js = js.replace("historicalLastLabel(p.historical)", "historicalLastLabel(p)")
js = js.replace("historicalYears(p.historical)", "historicalYears(p)")
js = js.replace("(p.historical?.historical_last_visit_date?fmtDate(p.historical.historical_last_visit_date):'Sin fecha registrada')", "(historicalLastDate(p)?fmtDate(historicalLastDate(p)):'Sin fecha registrada')")
js_path.write_text(js, encoding="utf-8", newline="\n")

# Recalcula hashes del canal después del afinado.
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

data = json.loads(CHANNEL.read_text(encoding="utf-8"))
for item in data["files"]:
    item["sha256"] = sha(OUT / item["path"])
CHANNEL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

assert "historicalLastLabel(p.historical)" not in js
assert "historicalLastDate(p)?fmtDate(historicalLastDate(p))" in js
print("V4413_RELEASE_REFINED")
