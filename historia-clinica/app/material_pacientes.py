from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent
MATERIAL_ROOT = ROOT / "data" / "material_pacientes"
INDEX_PATH = MATERIAL_ROOT / "material_index.json"

CATEGORY_DIRS = {
    "documentos": "documentos",
    "videos": "videos",
    "imagenes": "imagenes",
    "otros": "otros",
}

VIDEO_EXT = {".mp4", ".m4v", ".mov", ".webm", ".avi", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PDF_EXT = {".pdf"}
DOC_EXT = {".doc", ".docx", ".rtf", ".txt", ".odt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}
ALLOWED_EXT = VIDEO_EXT | IMAGE_EXT | PDF_EXT | DOC_EXT | AUDIO_EXT
BLOCKED_EXT = {
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse",
    ".msi", ".msp", ".scr", ".cpl", ".dll", ".sys", ".lnk", ".url", ".hta",
    ".py", ".pyw", ".jar", ".reg",
}
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024

_DIET_TITLE = "Dieta para prevenir formación de cálculos"
_DIET_SECTIONS = (
    (
        "ALIMENTOS QUE NO DEBE CONSUMIR:",
        (
            "CÍTRICOS (NARANJAS, LIMÓN, PIÑA, TOMATE DE ÁRBOL, MORA, FRUTILLA)",
            "ESPINACA, ACELGA, REMOLACHA, ALMENDRAS, MANÍ, CHOCOLATE, TÉ NEGRO",
            "(CÁLCULOS DE OXALATO DE CALCIO)",
        ),
    ),
    (
        "ALIMENTOS QUE DEBE CONSUMIR POCO:",
        ("LECHE, QUESO, VERDE, GUINEO, CARNES ROJAS, SAL.",),
    ),
    (
        "TOMAR 1 LITRO DE AGUA DE PLANTAS:",
        (
            "COLA DE CABALLO",
            "CHANCAPIEDRA (1 CUCHARADA)",
            "PEREJIL",
            "HOJAS DIENTE DE LEÓN",
        ),
    ),
)


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _ensure_dirs() -> None:
    MATERIAL_ROOT.mkdir(parents=True, exist_ok=True)
    for dirname in CATEGORY_DIRS.values():
        (MATERIAL_ROOT / dirname).mkdir(parents=True, exist_ok=True)


def _load_index() -> dict:
    _ensure_dirs()
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("favorites", [])
            data.setdefault("titles", {})
            return data
    except Exception:
        pass
    return {"favorites": [], "titles": {}}


def _save_index(data: dict) -> None:
    _ensure_dirs()
    clean = {
        "favorites": sorted({str(x) for x in data.get("favorites", []) if str(x)}),
        "titles": {str(k): str(v) for k, v in dict(data.get("titles", {})).items() if str(k)},
    }
    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(INDEX_PATH)


def _normal_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    value = value.replace("/", "-").replace("\\", "-")
    value = re.sub(r"[\x00-\x1f<>:\"|?*]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:180] or "archivo"


def _category_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in VIDEO_EXT or suffix in AUDIO_EXT:
        return "videos"
    if suffix in IMAGE_EXT:
        return "imagenes"
    if suffix in PDF_EXT or suffix in DOC_EXT:
        return "documentos"
    return "otros"


def _safe_category(value: str, suffix: str = "") -> str:
    value = str(value or "").strip().lower()
    return value if value in CATEGORY_DIRS else _category_for_suffix(suffix)


def _safe_path(rel_path: str) -> Path:
    _ensure_dirs()
    raw = str(rel_path or "").replace("\\", "/").lstrip("/")
    candidate = (MATERIAL_ROOT / raw).resolve()
    root = MATERIAL_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Ruta de material no permitida") from exc
    return candidate


def _rel(path: Path) -> str:
    return path.resolve().relative_to(MATERIAL_ROOT.resolve()).as_posix()


def _unique_destination(category: str, filename: str) -> Path:
    clean = _normal_name(filename)
    suffix = Path(clean).suffix.lower()
    if not suffix or suffix in BLOCKED_EXT or suffix not in ALLOWED_EXT:
        raise ValueError("Tipo de archivo no permitido. Use documentos, imágenes, audio o videos comunes.")
    category = _safe_category(category, suffix)
    folder = MATERIAL_ROOT / CATEGORY_DIRS[category]
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(clean).stem[:150] or "archivo"
    dest = folder / f"{stem}{suffix}"
    idx = 2
    while dest.exists():
        dest = folder / f"{stem} ({idx}){suffix}"
        idx += 1
    return dest


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXT:
        return "video"
    if suffix in AUDIO_EXT:
        return "audio"
    if suffix in IMAGE_EXT:
        return "imagen"
    if suffix in PDF_EXT:
        return "pdf"
    if suffix in DOC_EXT:
        return "documento"
    return "archivo"


def _scan() -> list[dict]:
    _ensure_dirs()
    idx = _load_index()
    favorites = set(str(x) for x in idx.get("favorites", []))
    titles = dict(idx.get("titles", {}))
    rows = []
    for folder in CATEGORY_DIRS.values():
        base = MATERIAL_ROOT / folder
        for path in base.rglob("*"):
            if not path.is_file() or path.name == INDEX_PATH.name:
                continue
            if path.suffix.lower() not in ALLOWED_EXT:
                continue
            rel = _rel(path)
            try:
                stat = path.stat()
                size = int(stat.st_size)
                modified = int(stat.st_mtime)
            except OSError:
                size = 0
                modified = 0
            rows.append({
                "rel": rel,
                "name": titles.get(rel) or path.stem,
                "filename": path.name,
                "kind": _kind(path),
                "category": rel.split("/", 1)[0] if "/" in rel else "otros",
                "favorite": rel in favorites,
                "size": size,
                "modified": modified,
            })
    rows.sort(key=lambda r: (not r["favorite"], -r["modified"], r["name"].casefold()))
    return rows


def _human_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _nav(path: str) -> str:
    def link(href: str, label: str, active: bool = False) -> str:
        return f"<a class='{'active' if active else ''}' href='{href}'>{label}</a>"
    return (
        "<header class='topbar'><div class='brand'><div class='brand-mark'>H</div>"
        "<div><strong>Historia Clínica</strong><span>Dr. Armando Revelo</span></div></div><nav>"
        + link("/", "Inicio")
        + link("/pacientes", "Pacientes")
        + link("/recetas", "Recetas")
        + link("/certificados", "Certificados")
        + link("/material", "Material", path.startswith("/material"))
        + link("/configuracion", "Configuración")
        + "</nav></header>"
    )


def _shell(title: str, content: str, *, path: str = "/material", extra_head: str = "", script: str = "") -> str:
    return f"""<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{_e(title)} · Historia Clínica</title>
<link rel='stylesheet' href='/static/style.css'>
<style>
.material-wrap{{max-width:1180px;margin:0 auto;padding:24px}}
.material-head{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:16px}}
.material-head h1{{margin:3px 0 4px;color:#173b66;font-size:27px}}
.material-head p{{margin:0;color:#667085}}
.material-actions{{display:flex;gap:8px;flex-wrap:wrap}}
.mat-btn{{border:1px solid #cbd5e1;background:#fff;color:#173b66;border-radius:10px;padding:10px 13px;font-weight:850;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}}
.mat-btn.primary{{background:#2b6aa7;color:#fff;border-color:#2b6aa7}}
.material-search{{display:grid;grid-template-columns:1fr auto auto;gap:8px;margin:14px 0}}
.material-search input,.material-search select{{min-height:44px;border:1px solid #cbd5e1;border-radius:10px;padding:0 12px;font:inherit;background:#fff}}
.material-section{{margin-top:20px}}
.material-section h2{{color:#173b66;font-size:18px;margin:0 0 10px}}
.material-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
.material-card{{background:#fff;border:1px solid #d9e1eb;border-radius:14px;padding:15px;box-shadow:0 4px 16px #173b660c;display:flex;flex-direction:column;gap:9px;min-height:158px}}
.material-card.featured{{border-color:#a8c8e7;background:#f8fbff}}
.material-icon{{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;background:#edf3f9;color:#173b66;font-weight:950;font-size:18px}}
.material-card h3{{margin:0;color:#172b4d;font-size:16px;line-height:1.25}}
.material-meta{{color:#667085;font-size:12px}}
.material-card .row{{display:flex;gap:7px;flex-wrap:wrap;margin-top:auto}}
.material-card .row .mat-btn{{padding:8px 10px;font-size:12px}}
.material-empty{{padding:22px;border:1px dashed #cbd5e1;border-radius:12px;color:#667085;text-align:center;background:#fff}}
.material-note{{padding:12px 14px;border-radius:11px;background:#f7fafc;border:1px solid #dce5ee;color:#536273;font-size:13px;margin-top:12px}}
.material-viewer{{max-width:1180px;margin:0 auto;padding:20px}}
.viewer-box{{background:#111827;border-radius:14px;overflow:hidden;min-height:65vh;display:grid;place-items:center}}
.viewer-box video,.viewer-box img{{max-width:100%;max-height:76vh}}
.viewer-box audio{{width:min(720px,90%)}}
.viewer-box iframe{{width:100%;height:76vh;border:0;background:#fff}}
@media(max-width:900px){{.material-grid{{grid-template-columns:1fr 1fr}}.material-search{{grid-template-columns:1fr}}}}
@media(max-width:620px){{.material-grid{{grid-template-columns:1fr}}.material-head{{display:block}}.material-actions{{margin-top:10px}}}}
{extra_head}
</style>
</head>
<body>{_nav(path)}{content}{script}</body></html>"""


def _diet_html(print_now: bool = False) -> str:
    sections = []
    for heading, lines in _DIET_SECTIONS:
        blocks = "".join(f"<p>{_e(line)}</p>" for line in lines)
        sections.append(f"<section><h2>{_e(heading)}</h2>{blocks}</section>")
    auto = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),350),{once:true});</script>" if print_now else ""
    return f"""<!doctype html>
<html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{_DIET_TITLE}</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;font-family:Arial,Helvetica,sans-serif;color:#111827;background:#eef2f6}}
.toolbar{{width:210mm;max-width:100%;margin:12px auto 8px;display:flex;gap:8px}}
.toolbar button,.toolbar a{{border:0;border-radius:9px;background:#173b66;color:#fff;padding:10px 15px;font-weight:850;text-decoration:none;cursor:pointer}}
.sheet{{width:210mm;min-height:297mm;margin:0 auto;background:#fff;padding:22mm 19mm;box-shadow:0 8px 30px #0f172a20}}
.kicker{{font-family:Georgia,serif;font-size:15pt;font-weight:800;margin-bottom:11mm}}
h1{{font-family:Georgia,serif;font-size:18pt;margin:0 0 11mm;letter-spacing:.2px}}
section{{margin:0 0 8mm}}h2{{font-family:Georgia,serif;font-size:13pt;margin:0 0 4mm}}p{{font-family:Georgia,serif;font-size:12pt;line-height:1.5;margin:0 0 4mm}}
.note{{font-size:9pt;color:#667085;margin-top:16mm}}
@page{{size:A4 portrait;margin:0}}@media print{{html,body{{background:#fff}}.toolbar{{display:none}}.sheet{{margin:0;box-shadow:none;width:210mm;min-height:297mm}}}}
</style></head><body>
<div class='toolbar'><button onclick='window.print()'>Imprimir</button><a href='/material'>Volver a Material</a></div>
<main class='sheet'><div class='kicker'>SERVICIO DE UROLOGÍA</div><h1>DIETA PARA PREVENIR FORMACIÓN DE CÁLCULOS</h1>
{''.join(sections)}
<div class='note'>Documento de indicaciones del consultorio. Contenido conservado según la hoja utilizada por el médico.</div>
</main>{auto}</body></html>"""


def _material_page(message: str = "") -> str:
    rows = _scan()
    cards = []
    for item in rows:
        rel_q = quote(item["rel"], safe="/")
        icon = {"video":"▶", "audio":"♪", "imagen":"▧", "pdf":"PDF", "documento":"DOC"}.get(item["kind"], "•")
        star = "★" if item["favorite"] else "☆"
        cards.append(
            f"<article class='material-card material-file' data-name='{_e((item['name']+' '+item['filename']).casefold())}' data-kind='{_e(item['category'])}'>"
            f"<div class='material-icon'>{_e(icon)}</div><h3>{_e(item['name'])}</h3>"
            f"<div class='material-meta'>{_e(item['filename'])} · {_human_size(item['size'])}</div>"
            "<div class='row'>"
            f"<a class='mat-btn primary' href='/material/ver/{rel_q}'>Ver</a>"
            f"<button class='mat-btn' type='button' onclick='openWindows({json.dumps(item['rel'])})'>Abrir en Windows</button>"
            f"<button class='mat-btn' type='button' onclick='toggleFavorite({json.dumps(item['rel'])},this)'>{star}</button>"
            "</div></article>"
        )
    files_html = "".join(cards) if cards else "<div class='material-empty'>Todavía no hay archivos. Use <b>Agregar archivo</b> o abra la carpeta local.</div>"
    notice = f"<div class='material-note'>{_e(message)}</div>" if message else ""
    content = f"""
<main class='material-wrap'>
  <div class='material-head'><div><span class='eyebrow'>MATERIAL PARA PACIENTES</span><h1>Documentos y multimedia</h1><p>Indicaciones, videos e imágenes disponibles directamente desde la PC del consultorio.</p></div>
  <div class='material-actions'><button class='mat-btn primary' id='upload-btn'>Agregar archivo</button><button class='mat-btn' onclick='openFolder()'>Abrir carpeta</button></div></div>
  {notice}
  <div class='material-search'><input id='material-q' placeholder='Buscar material…'><select id='material-kind'><option value=''>Todo</option><option value='documentos'>Documentos</option><option value='videos'>Videos / audio</option><option value='imagenes'>Imágenes</option></select><button class='mat-btn' onclick='location.reload()'>Actualizar</button></div>
  <section class='material-section'><h2>Acceso rápido</h2><div class='material-grid'>
    <article class='material-card featured'><div class='material-icon'>A4</div><h3>{_DIET_TITLE}</h3><div class='material-meta'>Indicaciones frecuentes · lista del consultorio</div><div class='row'><a class='mat-btn primary' href='/material/dieta-calculos'>Ver</a><a class='mat-btn' href='/material/dieta-calculos?print_now=1'>Imprimir</a></div></article>
  </div></section>
  <section class='material-section'><h2>Archivos de esta PC</h2><div class='material-grid' id='material-grid'>{files_html}</div></section>
  <div class='material-note'><b>Privacidad y rendimiento:</b> estos archivos quedan únicamente en esta PC dentro de la carpeta local de Historia Clínica. No se suben a Neon ni se incluyen en la base de pacientes.</div>
  <input id='upload-input' type='file' hidden accept='.pdf,.doc,.docx,.rtf,.txt,.odt,.ppt,.pptx,.xls,.xlsx,.csv,.mp4,.m4v,.mov,.webm,.avi,.mkv,.jpg,.jpeg,.png,.webp,.gif,.bmp,.mp3,.wav,.m4a,.ogg'>
</main>"""
    script = r"""
<script>
const q=document.getElementById('material-q'), kind=document.getElementById('material-kind');
function applyFilter(){
  const term=(q.value||'').toLocaleLowerCase('es'); const k=kind.value||'';
  document.querySelectorAll('.material-file').forEach(card=>{
    card.style.display=(!term||card.dataset.name.includes(term))&&(!k||card.dataset.kind===k)?'':'none';
  });
}
q.addEventListener('input',applyFilter);kind.addEventListener('change',applyFilter);
async function openFolder(){const r=await fetch('/api/material/open-folder',{method:'POST'});const d=await r.json();if(!r.ok)alert(d.error||'No se pudo abrir la carpeta');}
function encPath(rel){return String(rel||'').split('/').map(encodeURIComponent).join('/');}
async function openWindows(rel){const r=await fetch('/api/material/open/'+encPath(rel),{method:'POST'});const d=await r.json();if(!r.ok)alert(d.error||'No se pudo abrir el archivo');}
async function toggleFavorite(rel,btn){const r=await fetch('/api/material/favorite/'+encPath(rel),{method:'POST'});const d=await r.json();if(r.ok){btn.textContent=d.favorite?'★':'☆';}else alert(d.error||'No se pudo actualizar favorito');}
const input=document.getElementById('upload-input');
document.getElementById('upload-btn').addEventListener('click',()=>input.click());
input.addEventListener('change',async()=>{
  const file=input.files&&input.files[0]; if(!file)return;
  const old=document.getElementById('upload-btn').textContent;
  document.getElementById('upload-btn').disabled=true;document.getElementById('upload-btn').textContent='Copiando…';
  try{
    const url='/api/material/upload?filename='+encodeURIComponent(file.name);
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    const d=await r.json().catch(()=>({})); if(!r.ok||!d.ok)throw new Error(d.error||'No se pudo copiar el archivo'); location.reload();
  }catch(err){alert(err.message||String(err));}
  finally{document.getElementById('upload-btn').disabled=false;document.getElementById('upload-btn').textContent=old;input.value='';}
});
</script>"""
    return _shell("Material para pacientes", content, script=script)


def _viewer_page(rel_path: str) -> HTMLResponse:
    try:
        path = _safe_path(rel_path)
    except ValueError:
        return HTMLResponse(_shell("Material", "<main class='material-viewer'><div class='material-empty'>Ruta no permitida.</div></main>"), status_code=400)
    if not path.is_file() or path.suffix.lower() not in ALLOWED_EXT:
        return HTMLResponse(_shell("Material", "<main class='material-viewer'><div class='material-empty'>Archivo no encontrado.</div></main>"), status_code=404)
    rel = _rel(path)
    rel_q = quote(rel, safe="/")
    kind = _kind(path)
    media_url = f"/material/contenido/{rel_q}"
    if kind == "video":
        viewer = f"<video controls autoplay preload='metadata' src='{media_url}'></video>"
    elif kind == "audio":
        viewer = f"<audio controls autoplay src='{media_url}'></audio>"
    elif kind == "imagen":
        viewer = f"<img src='{media_url}' alt='{_e(path.stem)}'>"
    elif kind == "pdf":
        viewer = f"<iframe src='{media_url}' title='{_e(path.stem)}'></iframe>"
    else:
        viewer = "<div style='color:white;text-align:center;padding:35px'><h2>Este documento se abre con el programa de Windows.</h2><p>Use “Abrir en Windows”.</p></div>"
    content = f"""<main class='material-viewer'><div class='material-head'><div><span class='eyebrow'>MATERIAL</span><h1>{_e(path.stem)}</h1><p>{_e(path.name)}</p></div><div class='material-actions'><a class='mat-btn' href='/material'>Volver</a><button class='mat-btn primary' onclick='openExternal()'>Abrir en Windows</button></div></div><div class='viewer-box'>{viewer}</div></main>"""
    script = f"<script>async function openExternal(){{const r=await fetch('/api/material/open/{rel_q}',{{method:'POST'}});const d=await r.json();if(!r.ok)alert(d.error||'No se pudo abrir el archivo');}}</script>"
    return HTMLResponse(_shell(path.stem, content, script=script))


def _inject_existing_html(text: str, request_path: str) -> str:
    text = re.sub(
        r"<a\b[^>]*href=[\"']/recuperacion/borradores[\"'][^>]*>\s*Recuperaci[oó]n\s*</a>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    if "/material" not in text and "</nav>" in text:
        active = " active" if request_path.startswith("/material") else ""
        material_link = f"<a class='{active.strip()}' href='/material'>Material</a>"
        config_match = re.search(r"<a\b[^>]*href=[\"']/configuracion[\"'][^>]*>.*?</a>", text, flags=re.IGNORECASE | re.DOTALL)
        if config_match:
            text = text[:config_match.start()] + material_link + config_match.group(0) + text[config_match.end():]
        else:
            text = text.replace("</nav>", material_link + "</nav>", 1)

    if request_path.startswith("/configuracion") and "/recuperacion/borradores" not in text:
        nav_marker = "<div class='config-nav'>"
        if nav_marker in text:
            text = text.replace(nav_marker, nav_marker + "<a href='/recuperacion/borradores'>Recuperación</a>", 1)
        tools_marker = "<section class='docs-card' id='herramientas'>"
        recovery_card = (
            "<section class='docs-card' id='recuperacion'><h2>Respaldo y recuperación</h2>"
            "<p>Herramienta de emergencia para buscar borradores recuperables en la copia de nube. "
            "No modifica nada hasta que se elige Restaurar.</p>"
            "<div class='doc-actions'><a class='doc-light' href='/recuperacion/borradores'>Abrir recuperación de borradores</a></div></section>"
        )
        if tools_marker in text:
            text = text.replace(tools_marker, recovery_card + tools_marker, 1)

    if request_path.startswith("/paciente/") and "/nueva" in request_path and "id='open-material'" not in text and 'id="open-material"' not in text:
        button = "<button id='open-material' class='secondary document-action material-action' type='button'>Material</button>"
        cert_marker = "<button id='open-certificate' class='secondary document-action' type='button'>Certificado médico</button>"
        if cert_marker in text:
            text = text.replace(cert_marker, cert_marker + button, 1)
        else:
            tools_marker = "<button id='toggle-macros' class='secondary'>Frases rápidas</button>"
            if tools_marker in text:
                text = text.replace(tools_marker, tools_marker + button, 1)
        helper = """
<script id='material-consult-helper'>
(()=>{const b=document.getElementById('open-material');if(b)b.addEventListener('click',()=>window.open('/material?from=consulta','_blank'));})();
</script>
"""
        if "</body>" in text:
            text = text.replace("</body>", helper + "</body>", 1)
    return text


def _install_on_app(app: FastAPI) -> None:
    if getattr(app.state, "material_pacientes_installed", False):
        return
    app.state.material_pacientes_installed = True
    _ensure_dirs()

    @app.middleware("http")
    async def _material_ui_middleware(request: Request, call_next):
        response = await call_next(request)
        content_type = str(response.headers.get("content-type") or "")
        if "text/html" not in content_type.lower():
            return response
        chunks = []
        try:
            async for chunk in response.body_iterator:
                chunks.append(bytes(chunk))
        except Exception:
            return response
        raw = b"".join(chunks)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return HTMLResponse(raw.decode("utf-8", errors="replace"), status_code=response.status_code)
        new_text = _inject_existing_html(text, request.url.path)
        headers = {
            k: v for k, v in dict(response.headers).items()
            if k.lower() not in {"content-length", "content-type"}
        }
        return HTMLResponse(new_text, status_code=response.status_code, headers=headers)

    @app.get("/material", response_class=HTMLResponse)
    def material_home():
        return HTMLResponse(_material_page())

    @app.get("/material/dieta-calculos", response_class=HTMLResponse)
    def material_diet(print_now: int = Query(default=0)):
        return HTMLResponse(_diet_html(bool(print_now)))

    @app.get("/material/ver/{rel_path:path}", response_class=HTMLResponse)
    def material_view(rel_path: str):
        return _viewer_page(rel_path)

    @app.get("/material/contenido/{rel_path:path}")
    def material_content(rel_path: str):
        try:
            path = _safe_path(rel_path)
        except ValueError:
            return JSONResponse({"ok": False, "error": "Ruta no permitida"}, status_code=400)
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXT:
            return JSONResponse({"ok": False, "error": "Archivo no encontrado"}, status_code=404)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.post("/api/material/open-folder")
    def material_open_folder():
        _ensure_dirs()
        if os.name != "nt":
            return JSONResponse({"ok": False, "error": "Disponible solo en Windows."}, status_code=400)
        try:
            os.startfile(str(MATERIAL_ROOT))
            return JSONResponse({"ok": True})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    @app.post("/api/material/open/{rel_path:path}")
    def material_open_external(rel_path: str):
        if os.name != "nt":
            return JSONResponse({"ok": False, "error": "Disponible solo en Windows."}, status_code=400)
        try:
            path = _safe_path(rel_path)
        except ValueError:
            return JSONResponse({"ok": False, "error": "Ruta no permitida"}, status_code=400)
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXT:
            return JSONResponse({"ok": False, "error": "Archivo no encontrado"}, status_code=404)
        try:
            os.startfile(str(path))
            return JSONResponse({"ok": True})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    @app.post("/api/material/favorite/{rel_path:path}")
    def material_favorite(rel_path: str):
        try:
            path = _safe_path(rel_path)
        except ValueError:
            return JSONResponse({"ok": False, "error": "Ruta no permitida"}, status_code=400)
        if not path.is_file():
            return JSONResponse({"ok": False, "error": "Archivo no encontrado"}, status_code=404)
        rel = _rel(path)
        data = _load_index()
        fav = set(str(x) for x in data.get("favorites", []))
        if rel in fav:
            fav.remove(rel)
            state = False
        else:
            fav.add(rel)
            state = True
        data["favorites"] = sorted(fav)
        _save_index(data)
        return JSONResponse({"ok": True, "favorite": state})

    @app.post("/api/material/upload")
    async def material_upload(request: Request, filename: str = Query(default="", max_length=220), category: str = Query(default="", max_length=30)):
        clean = _normal_name(filename)
        suffix = Path(clean).suffix.lower()
        if suffix in BLOCKED_EXT or suffix not in ALLOWED_EXT:
            return JSONResponse({"ok": False, "error": "Tipo de archivo no permitido."}, status_code=400)
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError:
            content_length = 0
        if content_length > MAX_UPLOAD_BYTES:
            return JSONResponse({"ok": False, "error": "El archivo supera el límite local de 4 GB."}, status_code=413)
        try:
            dest = _unique_destination(category, clean)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        written = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with tmp.open("wb") as fh:
                async for chunk in request.stream():
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        raise ValueError("El archivo supera el límite local de 4 GB.")
                    fh.write(chunk)
            tmp.replace(dest)
            return JSONResponse({"ok": True, "path": _rel(dest), "size": written})
        except Exception as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


def install_fastapi_hook() -> None:
    """Integra Material sin tocar la lógica clínica ni la base de pacientes."""
    if getattr(FastAPI, "_historia_material_hook", False):
        return
    FastAPI._historia_material_hook = True
    original_init = FastAPI.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _install_on_app(self)
        except Exception:
            pass

    FastAPI.__init__ = patched_init
