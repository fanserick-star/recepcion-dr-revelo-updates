from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2618_BUILDER = ROOT / "build" / "whatsapp_v2618_private_enroll" / "build_worker_v2618.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_18_PRIVATE_ENROLL_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_19_AUTOAGENDA_EMOJIS_STANDALONE.js"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    require(text.count(old) == 1, f"Reemplazo ambiguo: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    subprocess.run([sys.executable, str(V2618_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    require('worker_version: "2.6.18"' in text, "Fuente no es Worker 2.6.18")
    require('autoagenda_enrollment: "one_time_v1"' in text, "Falta enrolamiento v2.6.18")

    replacements = [
        ('return `CITA AGENDADA\\n\\n${detail}\\n\\nLa cita se registró correctamente.`;',
         'return `✅ CITA AGENDADA\\n\\n${detail}\\n\\nLa cita se registró correctamente.`;',
         'cita creada'),
        ('return `CITA YA REGISTRADA\\n\\n${detail}\\n\\nEsa cita ya estaba en la agenda. No se creó un duplicado.`;',
         'return `♻️ CITA YA REGISTRADA\\n\\n${detail}\\n\\nEsa cita ya estaba en la agenda. No se creó un duplicado.`;',
         'cita existente'),
        ('return `MENSAJE YA PROCESADO\\n\\n${detail}\\n\\nNo se creó un duplicado.`;',
         'return `🔁 MENSAJE YA PROCESADO\\n\\n${detail}\\n\\nNo se creó un duplicado.`;',
         'mensaje repetido'),
        ('return `HORARIO OCUPADO\\n\\n${dateLabel(parsed.date)}\\n${timeLabel(parsed.time)}\\n\\nNo se creó ninguna cita.`;',
         'return `⚠️ HORARIO OCUPADO\\n\\n${dateLabel(parsed.date)}\\n${timeLabel(parsed.time)}\\n\\nNo se creó ninguna cita.`;',
         'horario ocupado'),
        ('`NO SE AGENDÓ\\n\\n${parsed.error}\\n\\nFormato esperado:\\nJueves 9y20\\nApellidos y nombres\\n09XXXXXXXX`',
         '`❌ NO SE AGENDÓ\\n\\n${parsed.error}\\n\\nFormato esperado:\\nJueves 9y20\\nApellidos y nombres\\n09XXXXXXXX`',
         'error de formato'),
        ('"NO SE AGENDÓ\\n\\nOcurrió un problema al consultar la agenda. No se creó ninguna cita."',
         '"❌ NO SE AGENDÓ\\n\\nOcurrió un problema al consultar la agenda. No se creó ninguna cita."',
         'error de consulta'),
    ]
    for old, new, label in replacements:
        text = replace_once(text, old, new, label)

    health_anchor = 'autoagenda_enrollment: "one_time_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0'
    text = replace_once(
        text,
        health_anchor,
        'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0',
        'health emojis',
    )

    text = replace_once(text, 'worker_version: "2.6.18"', 'worker_version: "2.6.19"', 'versión')
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.18"', '"Dr-Revelo-WhatsApp-Worker/2.6.19"')

    for needle in [
        'worker_version: "2.6.19"',
        'autoagenda_ui: "emoji_v1"',
        '✅ CITA AGENDADA',
        '♻️ CITA YA REGISTRADA',
        '🔁 MENSAJE YA PROCESADO',
        '⚠️ HORARIO OCUPADO',
        '❌ NO SE AGENDÓ',
        'autoagenda_enrollment: "one_time_v1"',
        'diagnostics_export: "cf_token_aesgcm_v1"',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2619_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
