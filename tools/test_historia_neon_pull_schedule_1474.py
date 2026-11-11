"""Historia 1.4.74: cloud scheduling tests, no database or network needed."""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
from cloud_sync import _should_pull_cloud


def main() -> None:
    # The very first bootstrap and recovery must never wait for ordinary polling.
    assert _should_pull_cloud(False, False, 0, 0.0)
    assert _should_pull_cloud(False, True, 0, 0.0)
    # While active with no pending changes, ordinary read-only pulls are 5 min apart.
    assert not _should_pull_cloud(True, True, 0, 89.0)
    assert not _should_pull_cloud(True, True, 0, 299.9)
    assert _should_pull_cloud(True, True, 0, 300.0)
    # AFK without pending work should not read Neon.
    assert not _should_pull_cloud(True, False, 0, 3600.0)
    # Existing pending-work behavior and immediate push path are preserved.
    assert not _should_pull_cloud(True, True, 1, 89.0)
    assert _should_pull_cloud(True, True, 1, 90.0)
    assert not _should_pull_cloud(True, False, 1, 3600.0)
    print("HISTORIA_NEON_PULL_SCHEDULE_1474_OK")


if __name__ == "__main__":
    main()
