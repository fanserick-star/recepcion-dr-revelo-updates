from pathlib import Path

base = Path(__file__).with_name("tmp_build_waiting_1373.py")
source = base.read_text(encoding="utf-8")
old = '''    app,
    \'\'\'def home():
    today = datetime.now().strftime("%Y-%m-%d")\'\'\',
    \'\'\'def home():
    _v1373_reconcile_signed_queue_items()
    today = datetime.now().strftime("%Y-%m-%d")\'\'\','''
new = '''    app,
    \'\'\'def home():
    cleanup_active_queue_duplicates()
    cleanup_cancelled_queue_drafts()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")\'\'\',
    \'\'\'def home():
    cleanup_active_queue_duplicates()
    cleanup_cancelled_queue_drafts()
    _v1373_reconcile_signed_queue_items()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")\'\'\','''
if source.count(old) != 1:
    raise RuntimeError(f"generator home anchor patch expected 1, found {source.count(old)}")
source = source.replace(old, new)
namespace = {"__file__": str(base), "__name__": "__main__"}
exec(compile(source, str(base), "exec"), namespace)
