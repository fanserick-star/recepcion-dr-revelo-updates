from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
MODULE_PATH = APP_DIR / "material_pacientes.py"

spec = importlib.util.spec_from_file_location("material_pacientes_smoke", MODULE_PATH)
material = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(material)

scratch = Path(tempfile.mkdtemp(prefix="historia-material-smoke-"))
material.ROOT = scratch
material.MATERIAL_ROOT = scratch / "data" / "material_pacientes"
material.INDEX_PATH = material.MATERIAL_ROOT / "material_index.json"

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

material.install_fastapi_hook()
app = FastAPI()

@app.get("/")
def home():
    return HTMLResponse(
        "<html><body><nav>"
        "<a href='/configuracion'>Configuración</a>"
        "<a href='/recuperacion/borradores'>Recuperación</a>"
        "</nav></body></html>"
    )

@app.get("/configuracion")
def config():
    return HTMLResponse(
        "<html><body><nav><a href='/configuracion'>Configuración</a>"
        "<a href='/recuperacion/borradores'>Recuperación</a></nav>"
        "<div class='config-nav'></div>"
        "<section class='docs-card' id='herramientas'></section></body></html>"
    )

@app.get("/paciente/abc/nueva")
def consult():
    return HTMLResponse(
        "<html><body><nav><a href='/configuracion'>Configuración</a>"
        "<a href='/recuperacion/borradores'>Recuperación</a></nav>"
        "<button id='open-certificate' class='secondary document-action' type='button'>Certificado médico</button>"
        "</body></html>"
    )

client = TestClient(app)

home_response = client.get("/")
assert home_response.status_code == 200
assert "href='/material'" in home_response.text
assert ">Recuperación</a>" not in home_response.text

config_response = client.get("/configuracion")
assert config_response.status_code == 200
assert "Abrir recuperación de borradores" in config_response.text
assert "/recuperacion/borradores" in config_response.text

consult_response = client.get("/paciente/abc/nueva")
assert consult_response.status_code == 200
assert "id='open-material'" in consult_response.text
assert "material-consult-helper" in consult_response.text

material_response = client.get("/material")
assert material_response.status_code == 200
assert "Documentos y multimedia" in material_response.text
assert "Dieta para prevenir formación de cálculos" in material_response.text

diet_response = client.get("/material/dieta-calculos")
assert diet_response.status_code == 200
assert "CHANCAPIEDRA" in diet_response.text
assert "HOJAS DIENTE DE LEÓN" in diet_response.text

upload_response = client.post(
    "/api/material/upload?filename=indicaciones.pdf",
    content=b"%PDF-1.4 smoke",
    headers={"content-type": "application/octet-stream"},
)
assert upload_response.status_code == 200, upload_response.text
stored = material.MATERIAL_ROOT / upload_response.json()["path"]
assert stored.is_file()

blocked_response = client.post(
    "/api/material/upload?filename=peligro.exe",
    content=b"MZ",
    headers={"content-type": "application/octet-stream"},
)
assert blocked_response.status_code == 400

try:
    material._safe_path("../../fuera.pdf")
except ValueError:
    pass
else:
    raise AssertionError("La protección contra traversal no bloqueó una ruta externa")

print("OK smoke_runtime_1389")
