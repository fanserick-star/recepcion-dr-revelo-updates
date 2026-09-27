from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "updates" / "v4_6_6_fast_attention_save"
FLAT = ROOT / "refactor_build" / "reception_flat_466"

PROBE = r'''
import os, sys
from pathlib import Path
os.environ['RP_FORCE_OFFLINE']='1'
os.environ['DATABASE_URL']=''
os.environ['HISTORIA_DATABASE_URL']=''
os.environ['REMOTE_AGENDA_AUTOSTART']='0'
os.environ['WHATSAPP_ENABLED']='0'
sys.path.insert(0, os.getcwd())
import app
core=getattr(app,'core',None)
if core is None and hasattr(app,'_rf_legacy'):
    core=app._rf_legacy._rf_layers['app_base_4428']
Path(os.environ['JS_OUT']).write_text(str(getattr(core,'V460_OVERLAY_JS','') or ''),encoding='utf-8')
Path(os.environ['CSS_OUT']).write_text(str(getattr(core,'V460_OVERLAY_CSS','') or ''),encoding='utf-8')
'''


def collect(runtime: Path, label: str):
    tmp=Path(tempfile.mkdtemp(prefix=f'rp-overlay-{label}-'))
    env=os.environ.copy()
    env.update({
        'RP_DATA_DIR':str(tmp/'data'), 'RP_FORCE_OFFLINE':'1', 'DATABASE_URL':'',
        'HISTORIA_DATABASE_URL':'', 'REMOTE_AGENDA_AUTOSTART':'0', 'WHATSAPP_ENABLED':'0',
        'JS_OUT':str(tmp/'overlay.js'), 'CSS_OUT':str(tmp/'overlay.css'), 'PYTHONIOENCODING':'utf-8',
    })
    p=subprocess.run([sys.executable,'-c',PROBE],cwd=runtime,env=env,text=True,capture_output=True,timeout=60)
    if p.returncode:
        print(p.stdout); print(p.stderr); raise SystemExit(label)
    return (tmp/'overlay.js').read_text(encoding='utf-8'), (tmp/'overlay.css').read_text(encoding='utf-8')


def diagnose(kind: str, a: str, b: str):
    print(f'{kind}: original chars={len(a)} flat chars={len(b)} equal={a==b}')
    if a==b: return
    n=min(len(a),len(b)); idx=next((i for i in range(n) if a[i]!=b[i]),n)
    print(f'{kind}: first diff index={idx}')
    lo=max(0,idx-600); hi=min(max(len(a),len(b)),idx+1200)
    print('--- ORIGINAL CONTEXT ---')
    print(a[lo:min(len(a),hi)])
    print('--- FLAT CONTEXT ---')
    print(b[lo:min(len(b),hi)])
    # Compare logical line position.
    aline=a[:idx].count('\n')+1; bline=b[:idx].count('\n')+1
    print(f'{kind}: original line~{aline} flat line~{bline}')

orig_js,orig_css=collect(ORIGINAL,'original')
flat_js,flat_css=collect(FLAT,'flat')
diagnose('JS',orig_js,flat_js)
diagnose('CSS',orig_css,flat_css)
