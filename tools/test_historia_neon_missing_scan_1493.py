"""Historia 1.4.93: protect automatic repair without redundant full-key downloads.

All tests are offline, with synthetic counts; no patient data or credentials.
"""
from __future__ import annotations

from unittest.mock import patch
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
from cloud_sync import CloudSyncService, HISTORIA_NEON_EMERGENCY_ENDPOINT_ID, HISTORIA_NEON_ENDPOINT_ID


def new_service(target=HISTORIA_NEON_EMERGENCY_ENDPOINT_ID, result=0, failure=False):
    svc = CloudSyncService.__new__(CloudSyncService)
    svc.target_endpoint = target
    calls = []

    def scan(pg):
        calls.append(pg)
        if failure:
            raise RuntimeError("transient cloud failure")
        return result

    svc._queue_missing_local_rows = scan
    return svc, calls


def exercise(svc, local_p=101, remote_p=100, local_e=201, remote_e=200, bootstrap_done=True, now=1000):
    with patch("cloud_sync.time.monotonic", return_value=now):
        return svc._maybe_queue_missing_local_rows(
            object(), local_patients=local_p, remote_patients=remote_p,
            local_encounters=local_e, remote_encounters=remote_e,
            bootstrap_done=bootstrap_done,
        )


# No count mismatch = no bulk query, including after local count converges.
svc, calls = new_service()
assert exercise(svc, local_p=100, remote_p=100, local_e=200, remote_e=200) == (0, "counts_match")
assert calls == []

# A confirmed count mismatch is ALWAYS scanned first, but never rescanned on
# every 90-second routine pull. The 30-minute fallback remains for old gaps.
assert exercise(svc) == (0, "full_repair_scan")
assert len(calls) == 1
assert exercise(svc, now=1090) == (0, "unchanged_counts_cooldown")
assert exercise(svc, now=1270) == (0, "unchanged_counts_cooldown")
assert exercise(svc, now=2799) == (0, "unchanged_counts_cooldown")
assert len(calls) == 1
assert svc._missing_scan_skipped_cycles == 3
assert exercise(svc, now=2800) == (0, "full_repair_scan")
assert len(calls) == 2

# Any LOCAL NEW PATIENT/ENCOUNTER count change forces immediate reconciliation.
# This is in addition to the unchanged sync_dirty immediate push path.
assert exercise(svc, local_p=102, now=2801) == (0, "full_repair_scan")
assert exercise(svc, local_p=102, local_e=202, now=2802) == (0, "full_repair_scan")
assert len(calls) == 4

# Changes in remote counts also override cooldown immediately.
assert exercise(svc, local_p=102, local_e=202, remote_p=101, now=2803) == (0, "full_repair_scan")
assert len(calls) == 5

# A recovery scan that found locally missing rows can recheck after FIVE
# minutes: the automatic push must not be disabled.
svc, calls = new_service(result=2)
assert exercise(svc, now=1000) == (2, "full_repair_scan")
assert exercise(svc, now=1299) == (0, "unchanged_counts_cooldown")
assert exercise(svc, now=1300) == (2, "full_repair_scan")
assert len(calls) == 2

# First bootstrap must not be delayed (applies even to emergency).
svc, calls = new_service()
assert exercise(svc, bootstrap_done=False, now=1000) == (0, "full_repair_scan")
assert exercise(svc, bootstrap_done=False, now=1090) == (0, "full_repair_scan")
assert len(calls) == 2

# Official server keeps the old repair behavior exactly.
svc, calls = new_service(target=HISTORIA_NEON_ENDPOINT_ID)
assert exercise(svc, now=1000) == (0, "full_repair_scan")
assert exercise(svc, now=1090) == (0, "full_repair_scan")
assert len(calls) == 2

# Failure never poisons the cache: next cycle retries even with same counts.
svc, calls = new_service(failure=True)
for now in (1000, 1090):
    try:
        exercise(svc, now=now)
    except RuntimeError as exc:
        assert "transient cloud" in str(exc)
    else:
        raise AssertionError("Failed scan must propagate")
assert len(calls) == 2
assert not hasattr(svc, "_missing_scan_signature")

# Protect the unmodified dirty queue + pull/push safety guards in the actual
# production code. No change to idle polling, new patient triggers or LAN.
source = (APP / "cloud_sync.py").read_text(encoding="utf8")
assert "_pending(sconn)" in source
assert "self._push(pg)" in source
assert "self._pull(pg, remote_now)" in source
assert "pending > 0" in source
assert "missing_local_scan_state=missing_scan_state" in source
assert "DELETE FROM sync_dirty WHERE table_name=? AND row_key=? AND changed_at=?" in source
print("HISTORIA_NEON_MISSING_SCAN_1493_OK")
