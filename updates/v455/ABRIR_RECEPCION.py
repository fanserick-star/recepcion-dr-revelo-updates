from __future__ import annotations

import os
import time

import _ABRIR_RECEPCION_451 as _base

LAUNCHER_VERSION = "4.3.55-safe3"


class Splash:
    """Splash liviano: sin dependencias extra y sin retrasar el arranque."""
    def __init__(self):
        self.root = None
        self.label = None
        self.detail = None
        self.elapsed_label = None
        self.canvas = None
        self._phase_started = time.monotonic()
        self._created = self._phase_started
        self._text = "Abriendo Recepción…"
        self._detail = "Iniciando sistema…"
        self._warned = False
        self._spin = 0
        try:
            import tkinter as tk
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            w, h = 470, 214
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
            root.configure(bg="#13213c")

            outer = tk.Frame(root, bg="#13213c", padx=24, pady=19)
            outer.pack(fill="both", expand=True)
            top = tk.Frame(outer, bg="#13213c")
            top.pack(fill="x")

            c = tk.Canvas(top, width=54, height=54, bg="#ffffff", highlightthickness=0)
            c.pack(side="left", padx=(0, 13))
            c.create_oval(8, 8, 24, 34, fill="#70b957", outline="")
            c.create_oval(30, 8, 46, 34, fill="#70b957", outline="")
            c.create_arc(16, 22, 38, 48, start=200, extent=140, style="arc", width=3, outline="#0d6d88")
            c.create_oval(18, 38, 36, 49, outline="#1683ad", width=2)

            titles = tk.Frame(top, bg="#13213c")
            titles.pack(side="left", fill="x", expand=True)
            tk.Label(titles, text="RECEPCIÓN", font=("Segoe UI", 10, "bold"), fg="#8fb5ff", bg="#13213c").pack(anchor="w")
            tk.Label(titles, text="Dr. Armando Revelo", font=("Segoe UI", 18, "bold"), fg="white", bg="#13213c").pack(anchor="w", pady=(1, 0))

            body = tk.Frame(outer, bg="#13213c")
            body.pack(fill="x", pady=(17, 0))
            self.label = tk.Label(body, text=self._text, font=("Segoe UI", 11, "bold"), fg="white", bg="#13213c")
            self.label.pack(anchor="w")
            self.detail = tk.Label(body, text=self._detail, font=("Segoe UI", 9), fg="#b9c8df", bg="#13213c")
            self.detail.pack(anchor="w", pady=(4, 0))
            self.elapsed_label = tk.Label(body, text="", font=("Segoe UI", 8), fg="#7f93b0", bg="#13213c")
            self.elapsed_label.pack(anchor="w", pady=(5, 0))

            self.canvas = tk.Canvas(outer, width=420, height=4, bg="#233653", highlightthickness=0)
            self.canvas.pack(fill="x", pady=(12, 0))
            root.update_idletasks()
            root.update()
            self.root = root
        except Exception:
            self.root = None

    def set(self, text, detail=""):
        self._text = str(text or "Abriendo Recepción…")
        self._detail = str(detail or "")
        self._phase_started = time.monotonic()
        self._warned = False
        try:
            if self.label:
                self.label.config(text=self._text)
            if self.detail:
                self.detail.config(text=self._detail)
        except Exception:
            pass
        self.pump()

    def pump(self):
        try:
            now = time.monotonic()
            phase_elapsed = now - self._phase_started
            total_elapsed = now - self._created
            if phase_elapsed >= 7.0 and not self._warned:
                self._warned = True
                if self.detail:
                    self.detail.config(text="Está tardando más de lo normal, por favor espera…")
            if self.elapsed_label:
                self.elapsed_label.config(text=f"{total_elapsed:.0f} s" if total_elapsed >= 2 else "")
            if self.canvas:
                self._spin = (self._spin + 1) % 28
                self.canvas.delete("progress")
                width = max(70, int(self.canvas.winfo_width() or 420) // 4)
                full = max(1, int(self.canvas.winfo_width() or 420))
                x = int((self._spin / 27.0) * (full + width)) - width
                self.canvas.create_rectangle(x, 0, min(full, x + width), 4, fill="#5f9cff", outline="", tags="progress")
            if self.root:
                self.root.update_idletasks()
                self.root.update()
        except Exception:
            pass

    def close(self):
        try:
            if self.root:
                self.root.destroy()
        except Exception:
            pass
        self.root = None


_base.Splash = Splash


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
        _base._log_launcher("Handoff del iniciador safe3 falló: " + repr(exc))


def main() -> None:
    _base._set_windows_identity()
    handle, already = _base.acquire_launcher_mutex()
    if already:
        for _ in range(50):
            if _base.focus_existing_window():
                return
            time.sleep(0.2)
        if _base.running_version() is not None:
            _base.focus_existing_window()
            return

    splash = Splash()
    try:
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
            time.sleep(0.10)

        if update.get("updated"):
            splash.set("Instalando actualización…", f"Versión {update.get('version') or ''}")
            _base.stop_server_on_port()
            _handoff_once(update, splash)

        if _base.running_version() == _base.expected_server_version() and _base.focus_existing_window():
            return

        version = _base.running_version()
        expected = _base.expected_server_version()
        splash.set("Iniciando sistema…", "Preparando datos locales")

        if version is None:
            _base.start_server()
            splash.set("Cargando agenda…", "Esperando al servidor local")
            if not _base.wait_for_expected_version(24.0, splash):
                _base.stop_server_on_port()
                _base.start_server()
                splash.set("Verificando conexión…", "Reintentando el inicio local")
                _base.wait_for_expected_version(18.0, splash)
        elif version != expected:
            _base.stop_server_on_port()
            _base.start_server()
            splash.set("Verificando conexión…", "Sincronizando la versión local")
            _base.wait_for_expected_version(22.0, splash)

        splash.set("Abriendo pantalla principal…", "Recepción está lista")
        time.sleep(0.08)
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
        _base._log_launcher("Fallo general del iniciador safe3: " + repr(exc) + " | " + traceback.format_exc(limit=5).replace("\n", " | "))
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
