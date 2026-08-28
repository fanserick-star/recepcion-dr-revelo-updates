from pathlib import Path

p=Path(__file__).with_name('build_v461.py')
s=p.read_text(encoding='utf-8')
lines=[]
for line in s.splitlines(True):
    if line.startswith('old_js = '):
        line = r'''old_js = r"if(template!==\'recordatorio_cita\'){alert(\'Esa plantilla todavía está pendiente de Meta. Por ahora probaremos Confirmación · recordatorio_cita.\');return}"''' + '\n'
    elif line.startswith('new_js = '):
        line = r'''new_js = r"if(![\'recordatorio_cita\',\'cita_agendada\',\'recordatorio_hoy\'].includes(template)){alert(\'Plantilla de prueba no válida.\');return}"''' + '\n'
    elif 's2,n=re.subn(pattern,repl,s,count=1,flags=re.S)' in line:
        line = line.replace('s2,n=re.subn(pattern,repl,s,count=1,flags=re.S)','s2,n=re.subn(pattern,lambda _m: repl,s,count=1,flags=re.S)')
    lines.append(line)
fixed=''.join(lines)
exec(compile(fixed,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
