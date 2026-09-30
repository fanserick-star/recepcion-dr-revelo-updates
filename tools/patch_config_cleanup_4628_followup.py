from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# Cache-bust app.js with the canonical app version too, not an old literal query string.
features_path = APP / "features_runtime.py"
features = read(features_path)
if "import re\n" not in features:
    features = replace_once(features, "import os\n", "import os\nimport re\n", "features import re")
old = '''        with open(\n            os.path.join(core_runtime.BASE_DIR, "static", "index.html"),\n            encoding="utf-8",\n        ) as handle:\n            html = handle.read()\n        version = _read_current_app_version()\n        addon = ('''
new = '''        with open(\n            os.path.join(core_runtime.BASE_DIR, "static", "index.html"),\n            encoding="utf-8",\n        ) as handle:\n            html = handle.read()\n        version = _read_current_app_version()\n        html = re.sub(r'(/static/app\\.js\\?v=)[^"\\\']+', rf'\\g<1>{version}', html, count=1)\n        addon = ('''
if "html = re.sub(r'(/static/app\\.js\\?v=)" not in features:
    features = replace_once(features, old, new, "dynamic app.js cache buster")
write(features_path, features)

# Compatibility helpers: opening AZUR/Bendo from elsewhere should land on the right advanced block.
cfg_path = APP / "static" / "configuration.js"
cfg = read(cfg_path)
anchor = "const originalShow=window.showConfigTab;\n"
helpers = r'''window.openAzurConfig=function(){
  if(typeof window.show==='function')window.show('config');
  const btn=q('[data-config-tab="facturacion"]');
  window.showConfigTab?.('facturacion',btn);
  const panel=q('#azurConfigPanel');if(panel){panel.open=true;setTimeout(()=>panel.scrollIntoView({behavior:'smooth',block:'start'}),60)}
};
window.openDataphoneConfig=function(){
  if(typeof window.show==='function')window.show('config');
  const btn=q('[data-config-tab="facturacion"]');
  window.showConfigTab?.('facturacion',btn);
  const body=q('#configDataphoneBody');const details=body?.closest('details');if(details){details.open=true;setTimeout(()=>details.scrollIntoView({behavior:'smooth',block:'start'}),60)}
};
window.configOpenAgenda=async function(){
  let btn=q('#cloudAgendaLinks .cloud-single-actions button');
  if(!btn&&typeof window.loadMobileConfigLinks==='function'){await window.loadMobileConfigLinks(false);btn=q('#cloudAgendaLinks .cloud-single-actions button')}
  if(btn)btn.click();
};

'''
if "window.openAzurConfig=function" not in cfg:
    cfg = replace_once(cfg, anchor, helpers + anchor, "compatibility config openers")
old_validate = "window.configValidateDataphone=async function(){try{const d=await call('/api/v4506/dataphone/validate',{method:'POST',body:'{}'});const target=q('#configDataphoneSummary');if(target)target.textContent=d.message||'';await window.loadConsolidatedDataphone()}catch(e){alert(e.message||e)}};"
new_validate = "window.configValidateDataphone=async function(){try{const d=await call('/api/v4506/dataphone/validate',{method:'POST',body:'{}'});await window.loadConsolidatedDataphone();const target=q('#configDataphoneDetail')||q('#configDataphoneSummary');if(target)target.textContent=d.message||''}catch(e){alert(e.message||e)}};"
if old_validate in cfg:
    cfg = cfg.replace(old_validate, new_validate, 1)
# Remove the earlier simple configOpenAgenda definition now superseded by the async compatibility helper.
cfg = cfg.replace("window.configOpenAgenda=function(){const btn=q('#cloudAgendaLinks .cloud-single-actions button');if(btn)btn.click()};\n", "", 1)
write(cfg_path, cfg)

print("CONFIG FOLLOW-UP POLISH READY")
