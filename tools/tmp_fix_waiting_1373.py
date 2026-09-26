from pathlib import Path

path = Path('historia-clinica/updates/v1_3_73_waiting_room_remaster/app.py')
text = path.read_text(encoding='utf-8')
old = '''    if raw in {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}:
        return False

def _v1373_procedure_label(row) -> str:'''
new = '''    if raw in {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}:
        return False
    # Compatibilidad con el puente antiguo: cualquier otro valor era el nombre
    # real del procedimiento (ECOGRAFÍA, CURACIÓN, etc.).
    return True


def _v1373_procedure_label(row) -> str:'''
if text.count(old) != 1:
    raise RuntimeError(f'procedure fallthrough anchor: {text.count(old)}')
text = text.replace(old, new)
old_tail = '''    return fixed


    # Compatibilidad con el puente antiguo: enviaba el nombre real del
    # procedimiento (ECOGRAFÍA, CURACIÓN, etc.) en attention_type.
    return True


def _queue_turn_number'''
new_tail = '''    return fixed


def _queue_turn_number'''
if text.count(old_tail) != 1:
    raise RuntimeError(f'unreachable legacy tail: {text.count(old_tail)}')
text = text.replace(old_tail, new_tail)
compile(text, str(path), 'exec')
assert 'def _v1373_procedure_label' in text
assert 'raw.startswith("PROCEDIMIENTO ")' in text
path.write_text(text, encoding='utf-8')
print('FIX_OK')
