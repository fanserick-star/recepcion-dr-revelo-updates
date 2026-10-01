from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse


def _inject_material_card(text: str, request_path: str) -> str:
    """Coloca Consentimiento informado en el mismo Acceso rápido que la dieta."""
    if request_path.rstrip("/") != "/material":
        return text
    if "consentimiento-material-card" in text:
        return text

    anchor = "<section class='material-section'><h2>Acceso rápido</h2><div class='material-grid'>"
    card = (
        "<article id='consentimiento-material-card' class='material-card featured'>"
        "<div class='material-icon'>A4</div>"
        "<h3>Consentimiento informado</h3>"
        "<div class='material-meta'>Formulario del consultorio · 3 páginas · editable e imprimible</div>"
        "<div class='row'>"
        "<a class='mat-btn primary' href='/consentimiento/nuevo'>Abrir</a>"
        "<a class='mat-btn' href='/consentimiento/nuevo?print_now=1'>Imprimir en blanco</a>"
        "</div></article>"
    )
    if anchor in text:
        return text.replace(anchor, anchor + card, 1)
    return text


def _install_on_app(app: FastAPI) -> None:
    if getattr(app.state, "material_consentimiento_patch_installed", False):
        return
    app.state.material_consentimiento_patch_installed = True

    @app.middleware("http")
    async def _material_consentimiento_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.rstrip("/") != "/material":
            return response
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

        new_text = _inject_material_card(text, request.url.path)
        headers = {
            k: v for k, v in dict(response.headers).items()
            if k.lower() not in {"content-length", "content-type"}
        }
        return HTMLResponse(new_text, status_code=response.status_code, headers=headers)


def install_fastapi_hook() -> None:
    """Instala únicamente el acceso visual desde Material; no toca datos clínicos."""
    if getattr(FastAPI, "_historia_material_consentimiento_hook", False):
        return
    FastAPI._historia_material_consentimiento_hook = True
    original_init = FastAPI.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _install_on_app(self)
        except Exception:
            pass

    FastAPI.__init__ = patched_init
