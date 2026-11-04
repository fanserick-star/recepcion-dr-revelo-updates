"""Remove the white matte from the original TV logo without redrawing the brand."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "recepcion/app/static/doctor_isotype.png"
TV = ROOT / "recepcion/app/tv_display.html"
VERSION = ROOT / "recepcion/app/recepcion-version.json"
MANIFEST = ROOT / "recepcion/app/update_manifest.json"
CHANNEL = ROOT / "launcher-v1/app-channel-source.json"


def main() -> None:
    icon = Image.open(ICON).convert("RGBA")
    converted = []
    for r, g, b, a in icon.getdata():
        minimum = min(r, g, b)
        maximum = max(r, g, b)
        # Only desaturate near-neutral light pixels; coloured kidneys/ripples
        # and dark outlines remain opaque. Respect any existing alpha.
        if minimum >= 245 and maximum - minimum <= 26:
            opacity = 0
        elif minimum > 210 and maximum - minimum <= 28:
            opacity = round((245 - minimum) * 255 / 35)
        else:
            opacity = 255
        opacity = max(0, min(255, opacity))
        converted.append((r, g, b, min(a, opacity)))
    icon.putdata(converted)
    assert icon.getpixel((0, 0))[3] == 0, "Expected transparent background in the top-left corner"
    assert icon.getpixel((icon.width - 1, icon.height - 1))[3] == 0, "Expected transparent background in the bottom-right corner"
    assert 1000 < sum(p[3] > 220 for p in converted), "Logo unexpectedly empty"
    icon.save(ICON, format="PNG", optimize=True)
    print("Transparent PNG:", ICON, icon.size)

    previous = json.loads(VERSION.read_text(encoding="utf-8"))["version"]
    major, minor, patch = map(int, previous.split("."))
    current = f"{major}.{minor}.{patch + 1}"
    VERSION.write_text(json.dumps({"version": current}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("version", "app_version", "runtime_version"):
        manifest[key] = current
    manifest.setdefault("notes", {})["purpose"] = (
        f"Recepción {current}: elimina el fondo blanco del isotipo en la TV "
        "mediante PNG con transparencia real, conservando la forma original. "
        "Cambia únicamente la imagen y la caché del logo. Sin cambios de pacientes, "
        "pagos, Neon, mensajería ni Historia Clínica."
    )
    manifest["notes"]["previous_version"] = previous
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    channel = json.loads(CHANNEL.read_text(encoding="utf-8"))
    channel["notes"] = (
        f"Recepción {current}: logo del doctor con fondo transparente en la TV; "
        "conserva el isotipo original, sin cambios funcionales ni de bases de datos."
    )
    CHANNEL.write_text(json.dumps(channel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markup = TV.read_text(encoding="utf-8")
    markup = markup.replace('/assets/logo-icon.png"', f'/assets/logo-icon.png?v={current}"')
    assert markup.count(f"/assets/logo-icon.png?v={current}") == 2, "Expected 2 logo references"
    TV.write_text(markup, encoding="utf-8")
    print("Prepared Reception release", previous, "->", current)


if __name__ == "__main__":
    main()
