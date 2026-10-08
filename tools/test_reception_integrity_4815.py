"""4.8.15 — El chequeo de Historia jamás modifica fichas ni vínculos."""
from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]
status = (ROOT/"recepcion/app/reception_system_status.py").read_text(encoding="utf-8")
front = (ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
ast.parse(status)
head = status.index("def reception_4815_integrity(")
tail = status.index("@app.get('/api/v4501/health')",head)
function = status[head:tail]
assert "@app.get('/api/ops/clinical-integrity')" in status
assert "core.LocalSessionLocal()" in function
assert "identity._connect_public()" in function
assert ".limit(60)" in function
assert "cursor.fetchall()" in function
assert "WHERE l.deleted_at IS NULL" in function
assert "reception_patient_id IN (" in function
assert "if reception_birth and clinical_birth" in function
assert "if reception_ident and clinical_ident" in function
assert "int(record.get('verified') or 0) != 1" in function
assert "issues[:60]" in function
assert "'no_mutations': True" in function
assert "'manual_only': True" in function
assert all(word not in function for word in ("db.commit(", "conn.commit(", "INSERT INTO", "UPDATE public.", "DELETE FROM", "_upsert_link(", "_sync_demographics(", "sendMeta(", "send_whatsapp"))
assert "async function openClinicalIntegrityReview()" in front
assert "api('/api/ops/clinical-integrity')" in front
assert "closeModal();openPatient(" in front
assert "Nunca fusiona, crea ni modifica fichas clínicas" in front
snippet = front.split("async function openClinicalIntegrityReview()",1)[1].split("async function goHomeToday()",1)[0]
assert "setInterval(" not in snippet and "setTimeout(" not in snippet
print("RECEPTION_HISTORY_INTEGRITY_4815_MANUAL_NO_MUTATION_OK")
