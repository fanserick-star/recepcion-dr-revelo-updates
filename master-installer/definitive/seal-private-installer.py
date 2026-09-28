from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

BEGIN = b"\nDRREVELO_PRIVATE_CONFIG_V1\n"
END = b"DRREVELO_PRIVATE_CONFIG_END\n"

# Sólo las dos conexiones de base son información privada imprescindible.
# Los tokens móviles se generan criptográficamente en bootstrap.ps1 cuando no
# vienen en el paquete, por lo que jamás deben pedirse al usuario al instalar.
REQUIRED = (
    "DATABASE_URL",
    "HISTORIA_DATABASE_URL",
)


def validate_config(data: bytes) -> None:
    text = data.decode("utf-8-sig")
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    missing = [name for name in REQUIRED if not values.get(name)]
    if missing:
        raise SystemExit("Configuración incompleta. Faltan: " + ", ".join(missing))


def seal(base: Path, config: Path, output: Path) -> str:
    base_bytes = base.read_bytes()
    if b"DRREVELO_PRIVATE_CONFIG_V1" in base_bytes[-524288:]:
        raise SystemExit("El EXE base ya contiene un bloque privado; usa una copia base limpia.")

    config_bytes = config.read_bytes()
    validate_config(config_bytes)
    digest = hashlib.sha256(config_bytes).hexdigest()
    encoded = base64.b64encode(config_bytes)
    trailer = (
        BEGIN
        + f"SHA256={digest}\n".encode("ascii")
        + b"BASE64="
        + encoded
        + b"\n"
        + END
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base_bytes + trailer)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sella en privado el instalador liviano del consultorio.")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    digest = seal(args.base, args.config, args.output)
    print(f"INSTALLER_SEALED_OK sha256={digest}")


if __name__ == "__main__":
    main()
