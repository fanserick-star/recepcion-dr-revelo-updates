from __future__ import annotations

import os
import time

import _ABRIR_RECEPCION_451 as _base

LAUNCHER_VERSION = "4.3.54-safe2"


def _handoff_once(update: dict, splash) -> None:
    if not update.get("updated"):
        return
    if os.getenv("RP_LAUNCHER_HANDOFF_DONE") == "1":
        return
    env = os.environ.copy()
    env["RP_LAUNCHER_HANDOFF_DONE"] = "1"
    env["RP_SKIP_UPDATE_ON_HANDOFF"] = "1"
    try:
        splash.set("Aplicando actualización…", "Cargando iniciador actualizado")
        splash.pump()
        py = _base.program_python(prefer_windowless=True)
        splash.close()
        os.execve(str(py), [str(py), str(_base.ROOT / "ABRIR_RECEPCION.py")], env)
    except Exception as exc:
        _base._log_launcher("Handoff del iniciador falló: " + repr(exc))


def main() -> None:
    _base._set_windows_identity()
    handle, already = _base.acquire_launcher_mutex()
    if already:
        # Si ya hay una sesión del lanzador viva, no se inicia otro updater en paralelo.
        for _ in range(50):
            if _base.focus_existing_window():
                return
            time.sleep(0.2)
        if _base.running_version() is not None:
            _base.focus_existing_window()
            return

    splash = _base.Splash()
    try:
        # Regla nueva: un inicio nuevo SIEMPRE consulta la nube antes de reutilizar
        # un backend local que haya quedado vivo en segundo plano.
        if os.getenv("RP_SKIP_UPDATE_ON_HANDOFF") == "1":
            update = {"ok": True, "updated": False, "version": _base.package_version()}
        else:
            splash.set("Verificando actualización…", "Comprobando la versión vigente")
            update = _base.run_automatic_update()

        if update.get("blocked"):
            splash.close()
            _base._message(_base.TITLE, update.get("error") or "La instalación local necesita reparación antes de iniciar.")
            return

        if update.get("deferred"):
            splash.set("Iniciando sistema…", "Actualización pendiente; se reintentará al próximo inicio")
            time.sleep(0.15)

        if update.get("updated"):
            splash.set("Instalando actualización…", f"Versión {update.get('version') or ''}")
            _base.stop_server_on_port()
            _handoff_once(update, splash)

        # Solo DESPUÉS de consultar la nube podemos reutilizar una sesión local.
        if _base.running_version() == _base.expected_server_version() and _base.focus_existing_window():
            return

        version = _base.running_version()
        expected = _base.expected_server_version()
        splash.set("Iniciando sistema…", "Preparando agenda y datos locales")
        if version is None:
            _base.start_server()
            if not _base.wait_for_expected_version(24.0, splash):
                _base.stop_server_on_port()
                _base.start_server()
                _base.wait_for_expected_version(18.0, splash)
        elif version != expected:
            _base.stop_server_on_port()
            _base.start_server()
            _base.wait_for_expected_version(22.0, splash)

        splash.set("Listo", "Abriendo Recepción")
        time.sleep(0.15)
        splash.close()
        _base.open_ui()
    finally:
        splash.close()
        if os.name == "nt" and handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        _base._log_launcher("Fallo general del iniciador safe2: " + repr(exc) + " | " + traceback.format_exc(limit=5).replace("\n", " | "))
        try:
            if _base.running_version() is None:
                _base.start_server()
                deadline = time.time() + 12
                while time.time() < deadline and _base.running_version(timeout=0.8) is None:
                    time.sleep(0.3)
            if _base.running_version() is not None:
                try:
                    _base.open_ui()
                except Exception:
                    import webbrowser
                    webbrowser.open(_base.URL, new=2)
            else:
                _base._message(_base.TITLE, "No se pudo iniciar Recepción. El detalle quedó guardado en data/launcher_errors.log.")
        except Exception:
            pass
