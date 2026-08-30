from __future__ import annotations
import build_v441 as b


def replace_between_consume(text: str, start: str, end: str, new: str, label: str) -> str:
    a=text.find(start)
    if a < 0: raise SystemExit(label+': inicio no encontrado')
    p=a+len(start)
    z=text.find(end,p)
    if z < 0: raise SystemExit(label+': fin no encontrado')
    # Los bloques de build_v441 incluyen deliberadamente el marcador final
    # dentro de `new`; consumimos el original para no duplicar decoradores/defs.
    if new.endswith(end):
        return text[:a]+new+text[z+len(end):]
    return text[:a]+new+text[z:]

b.replace_between = replace_between_consume
b.main()
