#!/usr/bin/env python3
"""Seal a public, credential-free bootstrap EXE on a trusted computer.

The result MUST remain private. Anyone who gets an unattended installer may
eventually extract the credentials: executable encryption is not access control.
"""
import argparse
import hashlib
import hmac
import os
import re
from pathlib import Path
import secrets
import struct

# The public executable contains this non-secret sentinel, replaced with a
# fresh key when sealing privately. The matching C bootstrap is version 2.
MARKER = bytes.fromhex(
    "19 6f 31 ad 9f 13 31 62 09 ce 97 72 d6 a8 7a de "
    "ee 4b 61 b4 25 18 0b 79 6d 21 43 6b 32 51 38 57 "
    "e3 ee da ba 6f b9 1b 43 3c 0c e6 35 d5 23 25 d5 "
    "91 43 98 df 0e 42 96 5f b9 3a 54 20 56 10 bd 9b"
)
MAGIC = b"DRRV2CFGFOOTER!!"
FOOTER_FORMAT = "<16sII16s32s"
HEADER = "DR_REVELO_CONFIG_V2\n"

def read_config(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) > 64 * 1024 or len(data) == 0:
        raise ValueError("Configuración privada vacía o demasiado grande.")
    content = data.decode("utf-8-sig")
    if not content.startswith(HEADER):
        raise ValueError("Falta cabecera DR_REVELO_CONFIG_V2.")
    section = None
    values = {"RECEPTION": {}, "HISTORIA": {}}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line == "DR_REVELO_CONFIG_V2":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section not in values:
                raise ValueError("Sección de configuración no admitida.")
            continue
        if section not in values or "=" not in line:
            raise ValueError("Línea de configuración fuera de sección.")
        k, v = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", k.strip()) or not v.strip():
            raise ValueError("Nombre de clave inválido o valor privado vacío.")
        if k.strip() in values[section]:
            raise ValueError("Clave privada duplicada.")
        values[section][k.strip()] = v.strip()
    a = values["RECEPTION"].get("DATABASE_URL")
    b = values["HISTORIA"].get("HISTORIA_DATABASE_URL")
    if not a or not b or a == b:
        raise ValueError("Se requieren dos conexiones Neon independientes.")
    # Do not print, save, upload, or log content or individual key values.
    return content.encode("utf-8")

def seal(base: bytes, config: bytes) -> bytes:
    if base.count(MARKER) != 1:
        raise ValueError("El ejecutable base no contiene una clave centinela única.")
    if MAGIC in base[-128:]:
        raise ValueError("El ejecutable ya está sellado; use una base limpia.")
    key = secrets.token_bytes(64)
    patched = base.replace(MARKER, key, 1)
    nonce = secrets.token_bytes(16)
    ciphertext = bytearray()
    for counter, i in enumerate(range(0, len(config), 32)):
        stream = hashlib.sha256(key[:32] + nonce + struct.pack("<I", counter)).digest()
        ciphertext.extend(bytes(a ^ b for a, b in zip(config[i:i + 32], stream)))
    mac_input = struct.pack("<II", 2, len(ciphertext)) + nonce + ciphertext
    tag = hmac.new(key[32:], mac_input, hashlib.sha256).digest()
    footer = struct.pack(FOOTER_FORMAT, MAGIC, 2, len(ciphertext), nonce, tag)
    assert len(footer) == 72
    return patched + ciphertext + footer

def main():
    ap = argparse.ArgumentParser(description="Crear instalador PRIVADO para PCs autorizadas")
    ap.add_argument("--base", required=True, type=Path, help="EXE base sin credenciales")
    ap.add_argument("--config", required=True, type=Path, help="Archivo privado con 2 secciones")
    ap.add_argument("--output", required=True, type=Path, help="EXE privado final (no publicar)")
    args = ap.parse_args()
    if args.output.resolve() == args.base.resolve():
        raise SystemExit("No sobrescribir la base pública.")
    cfg = read_config(args.config)
    exe = seal(args.base.read_bytes(), cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(exe)
    try:
        os.chmod(args.output, 0o600)
    except OSError:
        pass
    print("INSTALADOR_PRIVADO_CREADO (NO PUBLICAR)")

if __name__ == "__main__":
    main()
