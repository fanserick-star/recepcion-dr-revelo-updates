"""Behavior checks for globals that schema/import equivalence cannot detect."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import json, os, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, os.getcwd())
import app
core = app.core
core.Base.metadata.create_all(core.local_engine)
out = {}
try:
    with core.LocalSessionLocal() as db:
        out['empty_billing_group'] = core.billing_group_records(db, 987654321, date(2026, 1, 1))
except RecursionError:
    out['empty_billing_group'] = 'RecursionError'
bindings = {}
for route in app.app.router.routes:
    fn = getattr(route, 'endpoint', None)
    if not hasattr(fn, '__globals__'):
        continue
    for key in ('_print_payment_proof_windows', '_print_billing_data_form_windows', 'APP_VERSION'):
        if key in fn.__code__.co_names and key in fn.__globals__:
            value = fn.__globals__[key]
            bindings[fn.__name__ + ':' + key] = getattr(value, '__name__', value)
out['endpoint_bindings'] = bindings
Path(os.environ['RESULT_PATH']).write_text(json.dumps(out, sort_keys=True), encoding='utf-8')
'''


def probe(runtime: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix='rp-bindings-') as tmp:
        result_path = Path(tmp) / 'result.json'
        env = dict(os.environ, RP_DATA_DIR=str(Path(tmp) / 'data'), RP_FORCE_OFFLINE='1',
                   DATABASE_URL='', NEON_DATABASE_URL='', HISTORIA_DATABASE_URL='',
                   REMOTE_AGENDA_AUTOSTART='0', WHATSAPP_ENABLED='0',
                   RESULT_PATH=str(result_path), PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, '-c', PROBE], cwd=runtime, env=env,
                                text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(result_path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    original = probe(ROOT / 'updates/v4_6_6_fast_attention_save')
    candidate = probe(ROOT / 'refactor_build/reception_flat_466')
    assert original['empty_billing_group'] == [], original
    assert candidate == original, {'original': original, 'candidate': candidate}
    print('RUNTIME BINDINGS OK: billing without recursion; print renderers and endpoint versions preserved')
