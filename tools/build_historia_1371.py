from pathlib import Path
import json
import py_compile
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "historia-clinica/updates/v1_3_70_linked_documents"
DST = ROOT / "historia-clinica/updates/v1_3_71_document_ui_native_print"


def rep(text, old, new, count=1, label="replacement"):
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count}, found {found}")
    return text.replace(old, new, count)


def sub(text, pattern, replacement, count=1, label="regex", flags=0):
    out, n = re.subn(pattern, lambda m: replacement, text, count=count, flags=flags)
    if n != count:
        raise RuntimeError(f"{label}: expected {count}, found {n}")
    return out

if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)

app_path = DST / "app.py"
docs_path = DST / "documentos_clinicos.py"
css_path = DST / "static/style.css"
app = app_path.read_text(encoding="utf-8")
docs = docs_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

# 1) Evita que WebView reutilice CSS viejo entre versiones.
app = rep(
    app,
    '<link rel="stylesheet" href="/static/style.css">',
    '<link rel="stylesheet" href="/static/style.css?v={e(APP_VERSION)}">',
    label="css cache bust",
)

# 2) Puente JS global hacia el launcher nativo 1.0.8.
needle = "  window.showAppToast=(message,type='info')=>{{if(!toast)return;clearTimeout(toastTimer);toast.textContent=String(message||'');toast.className='app-toast '+type;toast.hidden=false;toastTimer=setTimeout(()=>{{toast.hidden=true}},3600)}};\n"
bridge = needle + r'''  window.historiaNativePrint=async(url,kind='certificate')=>{{
    try{{
      let printer='';
      try{{
        const q=encodeURIComponent(String(kind||'certificate'));
        const r=await fetch('/api/documentos/impresora?kind='+q,{{cache:'no-store'}});
        if(r.ok){{const d=await r.json();printer=String(d.printer||'')}}
      }}catch(_e){{}}
      if(window.chrome&&window.chrome.webview&&typeof window.chrome.webview.postMessage==='function'){{
        window.chrome.webview.postMessage({{type:'historia-print-url',url:String(url||''),printer}});
        if(window.showAppToast)showAppToast('Documento enviado a la impresora.','success');
        return true;
      }}
      throw new Error('La impresión directa requiere Launcher Historia 1.0.8. Cierre y vuelva a abrir Historia Clínica.');
    }}catch(err){{
      if(window.showAppToast)showAppToast(err&&err.message?err.message:'No se pudo imprimir.','error');
      else alert(err&&err.message?err.message:'No se pudo imprimir.');
      return false;
    }}
  }};
'''
app = rep(app, needle, bridge, label="native print global bridge")

# 3) Tarjetas profesionales dentro de la historia + impresión nativa.
old_row = '''        rows.append(
            "<div class='encounter-document-row'>"
            f"<span class='encounter-document-icon'>{'RX' if kind == 'rx' else 'DOC'}</span>"
            f"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>"
            f"<a href='{url}' target='_blank'>Ver</a>"
            f"<a href='{url}{'&' if '?' in url else '?'}print_now=1' target='_blank'>Imprimir</a>"
            "</div>"
        )
'''
new_row = '''        print_kind = "recipe" if kind == "rx" else "certificate"
        rows.append(
            "<div class='encounter-document-row'>"
            f"<span class='encounter-document-icon'>{'Rx' if kind == 'rx' else 'DOC'}</span>"
            f"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>"
            "<span class='encounter-document-actions'>"
            f"<a class='encounter-document-action' href='{url}' target='_blank'>Ver</a>"
            f"<button type='button' class='encounter-document-action primary' data-print-url='{url}' data-print-kind='{print_kind}' onclick=\"historiaNativePrint(this.dataset.printUrl,this.dataset.printKind)\">Imprimir</button>"
            "</span>"
            "</div>"
        )
'''
app = rep(app, old_row, new_row, label="history document professional actions")

# 4) Endpoint local: solo devuelve el nombre de la impresora configurada en ESTA PC.
install_anchor = '''def install(app, context: dict) -> None:
    db_path = Path(context["DB_PATH"])
    base = context["base"]
    get_sync_status = context.get("get_sync_status")
    data_dir = Path(context["ROOT"]) / "data"
    _ensure_official_doctor_logo(Path(context["ROOT"]))
'''
install_new = install_anchor + r'''

    @app.get("/api/documentos/impresora")
    def document_printer(kind: str = "certificate"):
        with _connect(db_path) as conn:
            local = _local_settings(conn)
        key = "prescription_printer" if str(kind or "").lower() in {"recipe", "receta", "rx"} else "certificate_printer"
        return JSONResponse({"ok": True, "printer": str(local.get(key) or "")})
'''
docs = rep(docs, install_anchor, install_new, label="printer settings api")

# 5) Eliminar about:blank y separar Ver/PDF de Imprimir directo.
rx_pattern = r'''        async function openPreview\(mode='preview'\)\{\{\n          const popup=window\.open\('about:blank','_blank'\);\n          try\{\{\n            const j=await saveRx\(false\);\n            let url=j\.preview_url;\n            if\(mode==='print'\)url\+=\(url\.includes\('\?'\)\?'&':'\?'\)\+'print_now=1';\n            if\(popup\)popup\.location\.replace\(url\);else window\.open\(url,'_blank'\);\n          \}\}catch\(e\)\{\{if\(popup\)popup\.close\(\);alert\(e\.message\)\}\}\n        \}\}'''
rx_new = r'''        async function openPreview(mode='preview'){{
          try{{
            const j=await saveRx(false);
            if(mode==='print'){{
              if(!window.historiaNativePrint)throw new Error('Reabra Historia Clínica para activar la impresión directa.');
              await window.historiaNativePrint(j.preview_url,'recipe');
              return;
            }}
            window.open(j.preview_url,'_blank');
          }}catch(e){{alert(e.message)}}
        }}'''
docs = sub(docs, rx_pattern, rx_new, label="recipe no about native print", flags=re.S)

cert_old = "        async function openCert(mode='preview'){{const popup=window.open('about:blank','_blank');try{{const j=await saveCert(false);let url=j.preview_url;if(mode==='print')url+=(url.includes('?')?'&':'?')+'print_now=1';if(popup)popup.location.replace(url);else window.open(url,'_blank')}}catch(e){{if(popup)popup.close();alert(e.message)}}}}\n"
cert_new = "        async function openCert(mode='preview'){{try{{const j=await saveCert(false);if(mode==='print'){{if(!window.historiaNativePrint)throw new Error('Reabra Historia Clínica para activar la impresión directa.');await window.historiaNativePrint(j.preview_url,'certificate');return;}}window.open(j.preview_url,'_blank')}}catch(e){{alert(e.message)}}}}\n"
docs = rep(docs, cert_old, cert_new, label="certificate no about native print")

rest_old = "        async function openRest(mode='preview'){{const popup=window.open('about:blank','_blank');try{{const j=await saveRest(false);let url=j.preview_url;if(mode==='print')url+=(url.includes('?')?'&':'?')+'print_now=1';if(popup)popup.location.replace(url);else window.open(url,'_blank')}}catch(e){{if(popup)popup.close();alert(e.message)}}}}\n"
rest_new = "        async function openRest(mode='preview'){{try{{const j=await saveRest(false);if(mode==='print'){{if(!window.historiaNativePrint)throw new Error('Reabra Historia Clínica para activar la impresión directa.');await window.historiaNativePrint(j.preview_url,'certificate');return;}}window.open(j.preview_url,'_blank')}}catch(e){{alert(e.message)}}}}\n"
docs = rep(docs, rest_old, rest_new, label="rest cert no about native print")

# 6) Remaster fuerte del bloque: limpio, separado y legible aun dentro del panel compacto.
css += r'''

/* v1.3.71 · Documentos de consulta: tarjeta profesional + acciones nativas */
.encounter-documents{
  margin:14px 0 4px!important;border:1px solid #d8e4ed!important;border-radius:14px!important;
  background:#fbfdff!important;overflow:hidden!important;box-shadow:0 3px 12px rgba(25,57,86,.06)!important
}
.encounter-documents-title{
  display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;
  padding:10px 12px!important;background:#eef5fa!important;border-bottom:1px solid #dce8f0!important;color:#284f70!important
}
.encounter-documents-title span{font:800 11px/1.2 "Segoe UI",sans-serif!important;letter-spacing:.08em!important}
.encounter-documents-title strong{
  display:inline-flex!important;align-items:center!important;justify-content:center!important;min-width:25px!important;height:25px!important;
  padding:0 7px!important;border-radius:999px!important;background:#d8e7f2!important;color:#214d70!important;font:800 11px/1 "Segoe UI",sans-serif!important
}
.encounter-document-row{
  display:grid!important;grid-template-columns:40px minmax(0,1fr) auto!important;align-items:center!important;gap:11px!important;
  padding:11px 12px!important;border:0!important;border-bottom:1px solid #e8eef3!important;background:#fff!important
}
.encounter-document-row:last-child{border-bottom:0!important}
.encounter-document-icon{
  display:grid!important;place-items:center!important;width:38px!important;height:38px!important;border-radius:10px!important;
  background:#eaf2f8!important;color:#214d70!important;font:900 11px/1 "Segoe UI",sans-serif!important;letter-spacing:.02em!important
}
.encounter-document-copy{display:flex!important;flex-direction:column!important;gap:3px!important;min-width:0!important}
.encounter-document-copy b{color:#173d5d!important;font:800 14px/1.25 "Segoe UI",sans-serif!important}
.encounter-document-copy small{color:#667b8c!important;font:500 12px/1.35 "Segoe UI",sans-serif!important;white-space:normal!important}
.encounter-document-actions{display:flex!important;align-items:center!important;gap:7px!important;flex-wrap:wrap!important;justify-content:flex-end!important}
.encounter-document-action{
  appearance:none!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;min-height:34px!important;
  padding:7px 11px!important;border:1px solid #c7d7e4!important;border-radius:9px!important;background:#fff!important;color:#285372!important;
  text-decoration:none!important;font:750 12px/1 "Segoe UI",sans-serif!important;cursor:pointer!important;white-space:nowrap!important
}
.encounter-document-action:hover{background:#f1f6fa!important;border-color:#9eb9cc!important}
.encounter-document-action.primary{background:#214f75!important;border-color:#214f75!important;color:#fff!important}
.encounter-document-action.primary:hover{background:#183e5e!important}
.encounter-documents-compact{margin-top:11px!important}
@media(max-width:800px){
  .encounter-document-row{grid-template-columns:36px minmax(0,1fr)!important}
  .encounter-document-actions{grid-column:1/-1!important;justify-content:flex-start!important;padding-left:47px!important}
}
'''

# 7) Versionado y manifiestos.
app_path.write_text(app, encoding="utf-8")
docs_path.write_text(docs, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")

version_path = DST / "historia-version.json"
version = json.loads(version_path.read_text(encoding="utf-8-sig"))
version["version"] = "1.3.71"
version_path.write_text(json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

manifest_path = DST / "update_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
manifest["version"] = "1.3.71"
manifest.setdefault("notes", {})
manifest["notes"].update({
    "document_cards_professional": True,
    "css_cache_bust": True,
    "about_blank_removed": True,
    "native_direct_print": True,
    "minimum_launcher": "1.0.8",
})
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

channel_path = ROOT / "historia-clinica/launcher-v1/app-channel-source.json"
channel = json.loads(channel_path.read_text(encoding="utf-8-sig"))
channel["appVersion"] = "1.3.71"
channel["minimumLauncher"] = "1.0.8"
channel["mandatory"] = True
channel["notes"] = "Historia Clínica 1.3.71: documentos de consulta con diseño profesional, CSS renovado sin caché vieja, Ver sin about:blank e impresión directa nativa sin vista previa del navegador."
for item in channel.get("files", []):
    item["sourcePath"] = str(item["sourcePath"]).replace("v1_3_70_linked_documents", "v1_3_71_document_ui_native_print")
channel_path.write_text(json.dumps(channel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Contratos locales antes de que el workflow pruebe runtime.
assert "about:blank" not in docs
assert "historia-print-url" in app
assert "style.css?v={e(APP_VERSION)}" in app
assert "encounter-document-actions" in app
assert "/api/documentos/impresora" in docs
py_compile.compile(str(app_path), doraise=True)
py_compile.compile(str(docs_path), doraise=True)
print("Historia 1.3.71 candidate generated")
