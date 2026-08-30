from pathlib import Path

base = Path(__file__).with_name('build_v43104.py')
source = base.read_text(encoding='utf-8')
old = "const t=norm(el.textContent);return t.startsWith('faltan datos:')||t==='faltan datos';"
new = "const raw=String(el.textContent||'').replace(/^[^A-Za-zÁÉÍÓÚáéíóúÑñ]+/,'');const t=norm(raw);return t.startsWith('faltan datos:')||t==='faltan datos';"
if source.count(old) != 1:
    raise SystemExit(f'detector de faltantes: esperaba 1 coincidencia y encontró {source.count(old)}')
patched = source.replace(old, new, 1)
ns = {'__name__':'v43104_final_builder','__file__':str(base)}
exec(compile(patched, str(base), 'exec'), ns)
ns['main']()
