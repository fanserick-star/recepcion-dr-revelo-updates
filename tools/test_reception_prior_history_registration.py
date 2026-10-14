"""Regresiones del registro histórico y la reasignación de turnos en espera."""
from __future__ import annotations
import ast
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
read = lambda rel: (root / rel).read_text(encoding="utf-8")

core = read("recepcion/app/core_runtime.py")
front = read("recepcion/app/static/app.js")
ident = read("recepcion/app/reception_history_identity_consolidated.py")
transport = read("recepcion/app/historia_lan_transport.py")
doctor = read("historia-clinica/app/lan_bridge.py")

for rel in (
    "recepcion/app/core_runtime.py",
    "recepcion/app/reception_history_identity_consolidated.py",
    "recepcion/app/historia_lan_transport.py",
    "historia-clinica/app/lan_bridge.py",
):
    ast.parse(read(rel), filename=rel)

subprocess.run(["node", "--check", str(root / "recepcion/app/static/app.js")], check=True)

assert 'values.pop("clinical_registration_kind", None)' in core
assert 'needs_old_chart = clinical_kind == "S"' in core
assert '"status": "needs_link"' in core
assert "clinical_registration_kind" in front
assert "Antes de registrar, indica si el paciente es Nuevo o Subsecuente" in front
assert "window.openRegistrationHistoryLink" in ident
assert "Marcar como subsecuente" not in front
assert "void refreshAttentionClinicalHistory(id)" in front
assert "clinical.history_date_count" in front
assert "status='waiting'" in ident
assert "started_at IS NULL AND completed_at IS NULL" in ident
assert "refresh_sent_waiting_handoffs_after_link" in transport
assert doctor.count("status='waiting' AND started_at IS NULL") >= 3
assert "reception_turn=?" in doctor
print("OK: sintaxis Python/JS, selección obligatoria, no duplicados S y relevo seguro.")
