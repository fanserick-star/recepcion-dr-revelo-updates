from __future__ import annotations
from pathlib import Path

base = Path(__file__).with_name('build_v43100.py')
source = base.read_text(encoding='utf-8')
old = '''def _can_bind_port(port: int) -> bool:\n    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n    try:\n        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)\n        sock.bind(("0.0.0.0", int(port)))\n        return True\n    except OSError:\n        return False\n    finally:\n        try: sock.close()\n        except Exception: pass\n'''
new = '''def _can_bind_port(port: int) -> bool:\n    # Primero comprobamos si ya hay un listener accesible en loopback. En Windows\n    # un bind a 0.0.0.0 puede no detectar correctamente un listener ligado solo\n    # a 127.0.0.1, así que usamos ambas comprobaciones.\n    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n    try:\n        probe.settimeout(0.20)\n        if probe.connect_ex(("127.0.0.1", int(port))) == 0:\n            return False\n    except Exception:\n        pass\n    finally:\n        try: probe.close()\n        except Exception: pass\n    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n    try:\n        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)\n        sock.bind(("0.0.0.0", int(port)))\n        return True\n    except OSError:\n        return False\n    finally:\n        try: sock.close()\n        except Exception: pass\n'''
if source.count(old) != 1:
    raise SystemExit(f'_can_bind_port: esperaba 1 bloque y encontro {source.count(old)}')
patched = source.replace(old, new, 1)
ns = {'__name__': 'v43100_final_builder', '__file__': str(base)}
exec(compile(patched, str(base), 'exec'), ns)
ns['main']()
