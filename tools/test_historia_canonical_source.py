from __future__ import annotations

import json
import subprocess
from pathlib import Path

from validate_historia_runtime import validate_runtime

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica/app"
SOURCE = ROOT / "historia-clinica/launcher-v1/app-channel-source.json"
FROZEN_UPDATES_TREE = "e30f1eedeffc44860ea0d174f5728a942f923442"
BASELINE_1373_TREE = "0053461d898cdf2b8d245c9396094c55309e8139"
ROLLBACK_1372_TREE = "23f1714a3620a5fd49c2adc7ec6c1bfc636b1591"


def git_tree(path: str) -> str:
    return subprocess.check_output(["git", "rev-parse", f"HEAD:{path}"], cwd=ROOT, text=True).strip()


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    assert source.get("product") == "historia-clinica-dr-revelo"
    assert source.get("status") == "stable"
    assert source.get("mandatory") is True
    assert source.get("sourceRoot") == "historia-clinica/app"
    assert "appVersion" not in source, "La versión no debe duplicarse en app-channel-source.json"
    assert "files" not in source, "El payload no debe duplicarse en app-channel-source.json"

    version = validate_runtime(APP)

    # Verifica con SQLite temporal que la ficha verificada llega ANTES del
    # turno LAN incluso si un esquema anterior exige integridad referencial.
    import runpy
    runpy.run_path(str(ROOT / "tools/test_historia_lan_new_patient_handoff_1472.py"), run_name="__main__")

    # No regresion: el monitor LAN/TV no puede mantener Neon despierto.
    cloud = (APP / "cloud_sync.py").read_text(encoding="utf-8")
    presence = (APP / "cloud_presence_patch.py").read_text(encoding="utf-8")
    tv = (APP / "tv_turn_bridge.py").read_text(encoding="utf-8")
    assert "HISTORIA_NEON_ECO_MODE = True" in cloud
    assert "type_recovery_due = active and not type_recovery_done" in cloud
    assert "HEARTBEAT_SECONDS = 1800" in presence
    assert 'path != "/tv-state"' in tv
    assert "sync_service.mark_activity()" not in tv

    updates_tree = git_tree("historia-clinica/updates")
    assert updates_tree == FROZEN_UPDATES_TREE, (
        "historia-clinica/updates dejó de estar congelado",
        updates_tree,
        FROZEN_UPDATES_TREE,
    )

    rollback_tree = git_tree("releases/historia/1.3.72")
    assert rollback_tree == ROLLBACK_1372_TREE, (rollback_tree, ROLLBACK_1372_TREE)

    if version == "1.3.73":
        app_tree = git_tree("historia-clinica/app")
        assert app_tree == BASELINE_1373_TREE, (
            "La fuente canónica inicial 1.3.73 no es byte-equivalente al release publicado",
            app_tree,
            BASELINE_1373_TREE,
        )

    print("HISTORIA_CANONICAL_SOURCE_OK", version)
    print("UPDATES_FROZEN_OK", updates_tree)
    print("ROLLBACK_1_3_72_OK", rollback_tree)


if __name__ == "__main__":
    main()
