"""Historia 1.4.69: contraste de turnos en tarjeta de revisión y en consulta."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
app = root / "historia-clinica/app"
css = (app / "static/style.css").read_text(encoding="utf-8")
version = json.loads((app / "historia-version.json").read_text(encoding="utf-8"))["version"]
manifest = json.loads((app / "update_manifest.json").read_text(encoding="utf-8"))

assert tuple(map(int, version.split("."))) >= (1,4,69)
assert all(manifest[k] == version for k in ("version","app_version","runtime_version"))
assert "static/style.css" in manifest["copy"]
assert "static/style.css" in manifest["required_dependencies"]

marker = "/* Historia v1.4.69 · número de turno legible en revisión y en consulta."
assert marker in css
latest = css[css.index(marker):]

for status in (".hc-b-wait-card.hc-b-review", ".hc-b-wait-card.queue-row-attending"):
    assert status + " .hc-b-wait-turn .queue-turn-number" in latest, status
    assert status + " .hc-b-wait-turn .queue-turn-number b" in latest, status
    assert status + " .hc-b-wait-turn .queue-turn-number span" in latest, status

assert "background:linear-gradient(180deg,#0969d3 0%,#06428e 100%)!important" in latest
assert "color:#ffffff!important" in latest
assert "opacity:1!important" in latest
assert css.count("{") == css.count("}"), "CSS desbalanceado"
assert "queue-row-attending" in latest and "hc-b-review" in latest
# No cambiar la definición de los turnos ni sus números: el parche es CSS puro.
assert ".queue-turn-number" in latest
print("HISTORIA_1469_WAIT_TURN_CONTRAST_OK")
