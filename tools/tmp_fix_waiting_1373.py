from pathlib import Path
import re

path = Path('historia-clinica/updates/v1_3_73_waiting_room_remaster/app.py')
text = path.read_text(encoding='utf-8')
pattern = re.compile(
    r'(    if raw in \{"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"\}:\n        return False\n)'
    r'(def _v1373_procedure_label\(row\) -> str:)'
)
text, n = pattern.subn(
    r'\1    # Compatibilidad con el puente antiguo: cualquier otro valor era el nombre\n'
    r'    # real del procedimiento (ECOGRAFÍA, CURACIÓN, etc.).\n'
    r'    return True\n\n\n\2',
    text,
)
if n != 1:
    raise RuntimeError(f'procedure fallthrough patch: {n}')

tail = re.compile(
    r'(    return fixed\n)\n+' 
    r'    # Compatibilidad con el puente antiguo: enviaba el nombre real del\n'
    r'    # procedimiento \(ECOGRAFÍA, CURACIÓN, etc\.\) en attention_type\.\n'
    r'    return True\n\n\n(def _queue_turn_number)'
)
text, n = tail.subn(r'\1\n\2', text)
if n != 1:
    raise RuntimeError(f'unreachable legacy tail patch: {n}')

compile(text, str(path), 'exec')
assert 'def _v1373_procedure_label' in text
assert 'raw.startswith("PROCEDIMIENTO ")' in text
assert text.count('Compatibilidad con el puente antiguo: cualquier otro valor era el nombre') == 1
path.write_text(text, encoding='utf-8')
print('FIX_OK')
