from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v4438_builder_base", HERE / "build_v4438.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("No se pudo cargar build_v4438.py")
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)

# Sobrescribe únicamente el sanitizador. Todas las demás funciones del candidato
# permanecen exactamente como en el build original, pero las llamadas resuelven
# este nombre global más reciente en tiempo de ejecución.
SANITIZER_OVERRIDE = r'''

# v4.4.38 privacy filter revision 2 — probado con secretos y PII sintéticos.
def _rp_diag_sanitize(value: object) -> str:
    text = str(value or "")
    try:
        text = text.replace(str(ROOT), "[APP_ROOT]")
    except Exception:
        pass

    # 1) Credenciales completas de Postgres/Neon antes de cualquier otro filtro.
    text = re.sub(r"(?i)postgres(?:ql)?://[^\s'\"<>\]]+", "[DATABASE_URL_REDACTADA]", text)

    # 2) Bearer completo antes de redacción genérica de Authorization.
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTADO]", text)

    # 3) Claves/secretos comunes key=value o key:value.
    text = re.sub(
        r"(?i)\b(database_url|neon_database_url|password|passwd|secret|token|api[_-]?key|authorization)\b\s*[:=]\s*([^\s,;|]+)",
        lambda m: f"{m.group(1)}=[REDACTADO]",
        text,
    )

    # 4) Correo electrónico.
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[CORREO_REDACTADO]", text)

    # 5) Usuario de Windows en rutas; conserva el resto del path útil para traceback.
    text = re.sub(r"(?i)C:\\Users\\[^\\\r\n\t ]+", r"C:\\Users\\[USUARIO]", text)

    # 6) Campos que pueden contener PII explícita.
    text = re.sub(
        r"(?i)\b(c[eé]dula|ruc|correo|e-?mail|celular|tel[eé]fono|patient_id|patient|cliente)\b\s*[:=]\s*[^,\r\n|]+",
        lambda m: m.group(1) + "=[REDACTADO]",
        text,
    )

    # 7) Cédulas, teléfonos, RUC e identificadores numéricos largos.
    text = re.sub(r"(?<!\d)\d{7,20}(?!\d)", "[NUMERO_REDACTADO]", text)

    # 8) IP no-loopback.
    def _ip_repl(match):
        ip = match.group(0)
        return ip if ip.startswith("127.") else "[IP_REDACTADA]"
    text = re.sub(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", _ip_repl, text)
    return text

'''

b.DIAGNOSTICS += SANITIZER_OVERRIDE

if __name__ == "__main__":
    b.build()
