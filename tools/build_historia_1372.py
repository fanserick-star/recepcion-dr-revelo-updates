from pathlib import Path
import json
import py_compile
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "historia-clinica/updates/v1_3_71_document_ui_native_print"
DST = ROOT / "historia-clinica/updates/v1_3_72_waiting_opens_card"


def rep(text, old, new, count=1, label="replacement"):
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count}, found {found}")
    return text.replace(old, new, count)


if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)

app_path = DST / "app.py"
app = app_path.read_text(encoding="utf-8")

# 1) En la ficha, cualquier paciente que venga desde la cola conserva queue_id
#    y el botón principal pasa a Atender. El banner especial sigue siendo solo
#    para pacientes nuevos ya confirmados.
app = rep(
    app,
    "    if(!q||!confirmed||!isNew)return;\n",
    "    if(!q)return;\n",
    label="patient card queue context",
)
app = rep(
    app,
    "    if(!document.querySelector('.v132-confirmed-banner')){\n",
    "    if(confirmed&&isNew&&!document.querySelector('.v132-confirmed-banner')){\n",
    label="new patient confirmation banner scope",
)

# 2) Paciente existente/subsecuente: resolver vínculo como antes, pero abrir la
#    ficha en vez de crear/abrir inmediatamente una consulta.
old_existing = '''        if not _queue_is_new(row):
            return _v132_attend_original(queue_id)
'''
new_existing = '''        if not _queue_is_new(row):
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
'''
app = rep(app, old_existing, new_existing, label="existing waiting patient opens card")

# 3) Si el doctor tuvo que escoger manualmente una ficha, después de vincularla
#    también abre la ficha, no la consulta. El botón Atender conserva queue_id.
app = rep(
    app,
    '''    return RedirectResponse(
        f"/paciente/{patient_id}/nueva?queue_id={queue_id}",
        status_code=303,
    )


@app.get("/", response_class=HTMLResponse)
''',
    '''    return RedirectResponse(
        f"/paciente/{patient_id}?queue_id={queue_id}",
        status_code=303,
    )


@app.get("/", response_class=HTMLResponse)
''',
    label="manual queue link opens card",
)

# 4) Texto de la cola coherente con el nuevo flujo.
old_labels = '''            if r["status"] == "in_consultation":
                action_label = "Continuar"
            elif r["clinical_patient_id"]:
                action_label = "Atender"
            elif is_new:
                action_label = "Crear ficha y atender"
            else:
                action_label = "Vincular y atender"
'''
new_labels = '''            if r["status"] == "in_consultation":
                action_label = "Ver ficha"
            elif r["clinical_patient_id"]:
                action_label = "Abrir ficha"
            elif is_new:
                action_label = "Revisar ficha"
            else:
                action_label = "Vincular ficha"
'''
app = rep(app, old_labels, new_labels, label="waiting queue action labels")
app = rep(
    app,
    '''    next_button = (
        f"<a class='home-action primary' href='/cola/{e(next_row['id'])}/atender'>Atender siguiente</a>"
        if next_row else "<span class='home-action disabled'>Atender siguiente</span>"
    )
''',
    '''    next_button = (
        f"<a class='home-action primary' href='/cola/{e(next_row['id'])}/atender'>Abrir siguiente</a>"
        if next_row else "<span class='home-action disabled'>Abrir siguiente</span>"
    )
''',
    label="next waiting action label",
)

# 5) Ajusta el texto de la selección ambigua para que no prometa entrar directo
#    a consulta.
app = app.replace("Vincular y atender", "Vincular ficha")
app = app.replace(
    "Encontré más de una ficha posible. Seleccione la correcta para iniciar la atención.",
    "Encontré más de una ficha posible. Seleccione la correcta para abrir su ficha antes de iniciar la atención.",
)

app_path.write_text(app, encoding="utf-8")

# 6) Versionado y canal.
version_path = DST / "historia-version.json"
version = json.loads(version_path.read_text(encoding="utf-8-sig"))
version["version"] = "1.3.72"
version_path.write_text(json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

manifest_path = DST / "update_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
for key in ("version", "app_version", "runtime_version"):
    manifest[key] = "1.3.72"
manifest["launcher_version"] = "historia-launcher-v1.0.8"
manifest["launcher_minimum"] = "1.0.8"
manifest.setdefault("notes", {})
manifest["notes"].update({
    "previous_version": "1.3.71",
    "waiting_queue_opens_patient_card": True,
    "queue_context_preserved_to_consultation": True,
    "new_patient_confirmation_flow_preserved": True,
    "database_schema_changes": False,
    "patient_data_destructive_changes": False,
})
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

channel_path = ROOT / "historia-clinica/launcher-v1/app-channel-source.json"
channel = json.loads(channel_path.read_text(encoding="utf-8-sig"))
channel["appVersion"] = "1.3.72"
channel["minimumLauncher"] = "1.0.8"
channel["mandatory"] = True
channel["notes"] = (
    "Historia Clínica 1.3.72: al abrir un paciente en espera se muestra primero su ficha; "
    "desde la ficha el botón Atender conserva el turno y abre la consulta. "
    "Pacientes nuevos mantienen confirmación de datos antes de atender."
)
for item in channel.get("files", []):
    item["sourcePath"] = str(item["sourcePath"]).replace(
        "v1_3_71_document_ui_native_print",
        "v1_3_72_waiting_opens_card",
    )
channel_path.write_text(json.dumps(channel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Contratos de seguridad.
assert "if(!q)return;" in app
assert "if(!q||!confirmed||!isNew)return;" not in app
assert 'f"/paciente/{patient_id}?queue_id={queue_id}"' in app
assert "Abrir siguiente" in app
assert "Revisar ficha" in app
assert "doctor_confirmed_new" in app
assert "new_consultation_v132" in app
py_compile.compile(str(app_path), doraise=True)
print("Historia 1.3.72 candidate generated")
