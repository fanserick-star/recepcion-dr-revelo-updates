from pathlib import Path
import re

path = Path(__file__).with_name('build_v481.py')
src = path.read_text(encoding='utf-8')
# La primera versión del validador dejó el decorador de /api/patients con
# barras invertidas literales dentro de la lista de regresiones. Retiramos solo
# ese token defectuoso; el workflow valida después el decorador real.
src, n = re.subn(r",\s*'@app\.post\([^']*patients[^']*\)'", "", src, count=1)
if n != 1:
    raise SystemExit('No se encontró el token defectuoso de /api/patients')
ns = {'__name__': '__main__', '__file__': str(path)}
exec(compile(src, str(path), 'exec'), ns)
