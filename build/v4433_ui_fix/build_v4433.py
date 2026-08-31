from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"
OUT = ROOT / "updates" / "v4_4_33_ui_fix"
VERSION = "4.4.33"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


def main() -> None:
    src = SOURCE.read_text(encoding="utf-8")
    if 'APP_VERSION = "4.4.31"' not in src:
        raise SystemExit("La fuente ya no es v4.4.31")

    text = replace_once(src, 'APP_VERSION = "4.4.31"', f'APP_VERSION = "{VERSION}"', "APP_VERSION")
    text = replace_once(text, "const VERSION='4.4.31';", f"const VERSION='{VERSION}';", "VERSION frontend pago")

    # 1) Eliminar el observador global añadido en 4.4.31. Ese observer reaccionaba
    # a mutaciones generadas por los observers ya existentes de v4.4.28 y podía
    # crear un ciclo de trabajo continuo antes de DOMContentLoaded en Chromium/WebView2.
    old_fix = r'''  // Corrige cualquier distintivo heredado de una versión estática anterior.
  function fixVersionLabels(){
    const direct=document.querySelector('#currentVersionBadge');
    if(direct)direct.textContent='v'+VERSION;
    document.querySelectorAll('span,small,div').forEach(el=>{
      if(el.children.length)return;
      const t=String(el.textContent||'').trim();
      if(/^v4\.4\.(?:28|29|30)$/.test(t))el.textContent='v'+VERSION;
    });
  }

  const observer=new MutationObserver(()=>{
    hookBilling();decorate();fixVersionLabels();
  });
  observer.observe(document.documentElement,{childList:true,subtree:true});

  async function boot(){
    hookBilling();fixVersionLabels();
    setTimeout(refreshPaymentMap,200);
    setTimeout(fixVersionLabels,500);
  }
'''
    new_fix = r'''  // v4.4.33: NO observar todo el documento. loadBilling ya es el punto
  // correcto para volver a decorar las fichas y evita bucles entre observers.
  async function boot(){
    hookBilling();
    setTimeout(refreshPaymentMap,200);
  }
'''
    text = replace_once(text, old_fix, new_fix, "observer global de pago")

    # 2) El overlay estable tiene su versión visual compilada como 4.4.28. En vez
    # de otro MutationObserver que pelee por el texto, ajustamos ese literal una
    # sola vez en memoria antes de servir /v460/overlay.js.
    #
    # 3) v459 arrastra un error previo: q(selector, '#config') pasa un string como
    # root a querySelector y genera TypeError dos veces al iniciar. Lo corregimos
    # en memoria sin tocar static ni app_base_4428.py en disco.
    anchor = '''    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\\n" + PAYMENT_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\\n" + PAYMENT_JS
'''
    replacement = f'''    _v459_base = core.V459_SETTINGS_JS or ""
    _v459_bad_root = "const sub=q('.config-title-row .muted','#config');"
    _v459_good_root = "const sub=q('.config-title-row .muted',q('#config')||document);"
    if _v459_bad_root in _v459_base:
        _v459_base = _v459_base.replace(_v459_bad_root, _v459_good_root, 1)
    core.V459_SETTINGS_JS = _v459_base

    _overlay_base = core.V460_OVERLAY_JS or ""
    _overlay_version_marker = "const VERSION='4.4.28';"
    if _overlay_version_marker in _overlay_base:
        _overlay_base = _overlay_base.replace(
            _overlay_version_marker,
            "const VERSION='{VERSION}';",
            1,
        )
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\\n" + PAYMENT_CSS
    core.V460_OVERLAY_JS = _overlay_base + "\\n" + PAYMENT_JS
'''
    text = replace_once(text, anchor, replacement, "sincronización segura de recursos frontend")

    # Debe seguir siendo el mismo wrapper estable y conservar la protección de pago.
    required = [
        "import app_base_4428 as core",
        "PAYMENT_SENTINELS",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "Antes de emitir, marca Efectivo o Transferencia en la ficha.",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
        "window.__v4431BillingPayment",
        "core.V459_SETTINGS_JS = _v459_base",
        "_v459_bad_root",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"Se perdió funcionalidad requerida: {marker}")
    if "new MutationObserver(()=>{\n    hookBilling();decorate();fixVersionLabels();" in text:
        raise SystemExit("Quedó el observer regresivo")

    compile(text, "app.py", "exec")
    OUT.mkdir(parents=True, exist_ok=True)
    app_path = OUT / "app.py"
    app_path.write_text(text, encoding="utf-8")

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.100-standalone-7-dynamic-port",
        "updater_version": "integrado-en-launcher",
        "copy": ["app.py", "update_manifest.json"],
        "notes": "Parche mínimo sobre v4.4.31: elimina ciclo de MutationObserver del overlay de pago y corrige TypeError heredado de v459. No toca launcher, static, .env ni datos.",
    }
    manifest_path = OUT / "update_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.33: corrige pantalla blanca y dos errores JavaScript silenciosos de Configuración; conserva forma de pago Efectivo/Transferencia y launcher dinámico v4.4.32. No toca datos, .env, static ni bases.",
        "files": [
            {
                "path": "app.py",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_33_ui_fix/app.py",
                "sha256": sha256(app_path),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_33_ui_fix/update_manifest.json",
                "sha256": sha256(manifest_path),
                "encoding": "utf-8",
            },
        ],
    }
    (OUT / "candidate_latest.json").write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("V4433_BUILT", sha256(app_path))


if __name__ == "__main__":
    main()
