from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLOUD = REPO / "historia-clinica/app/cloud_sync.py"
MANIFEST = REPO / "historia-clinica/app/update_manifest.json"
SMOKE = REPO / "historia-clinica/tests/smoke_runtime_1374.py"

old = '''            cur = pg.cursor()\n            remote_now = _remote_now(cur)\n            pg.commit()\n\n            # v1.3.74: nunca permitimos que un pull pise primero un cambio\n            # local pendiente. Se sube lo local y después se incorporan cambios\n            # remotos. Los choques simultáneos se preservan en sync_conflicts.\n            pushed = self._push(pg)\n            pulled = self._pull(pg, remote_now) if pull_due else 0\n            self._register_device(pg)\n            pg.commit()\n            if pull_due:\n                self._last_pull_monotonic = time.monotonic()\n'''
new = '''            # v1.3.74: nunca permitimos que un pull pise primero un cambio\n            # local pendiente. Primero se sube lo local. Después tomamos un\n            # cursor remoto NUEVO, posterior a ese push, para que la siguiente\n            # vuelta no confunda nuestro propio push con un cambio de otra PC.\n            pushed = self._push(pg)\n            cur = pg.cursor()\n            remote_now = _remote_now(cur)\n            pg.commit()\n            effective_pull_due = pull_due or pushed > 0\n            pulled = self._pull(pg, remote_now) if effective_pull_due else 0\n            self._register_device(pg)\n            pg.commit()\n            if effective_pull_due:\n                self._last_pull_monotonic = time.monotonic()\n'''

text = CLOUD.read_text(encoding="utf-8-sig")
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("No encontré el bloque de cursor 1.3.74")
CLOUD.write_text(text, encoding="utf-8")

data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
data.setdefault("notes", {})["sync_cursor_captured_after_push"] = True
data["notes"]["sync_own_push_false_conflict_guard"] = True
MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

smoke = SMOKE.read_text(encoding="utf-8-sig")
old_test = '''assert cycle.index("pushed = self._push(pg)") < cycle.index("pulled = self._pull(pg, remote_now)")\nassert "pull_skipped_local_dirty" in cloud_text\n'''
new_test = '''assert cycle.index("pushed = self._push(pg)") < cycle.index("remote_now = _remote_now(cur)") < cycle.index("pulled = self._pull(pg, remote_now)")\nassert "effective_pull_due = pull_due or pushed > 0" in cycle\nassert "pull_skipped_local_dirty" in cloud_text\n'''
if old_test in smoke:
    smoke = smoke.replace(old_test, new_test, 1)
elif new_test not in smoke:
    raise SystemExit("No encontré ancla de smoke para cursor")
SMOKE.write_text(smoke, encoding="utf-8")

print("SYNC_CURSOR_1374_OK")
