from pathlib import Path

p = Path(__file__).with_name("build_historia_1371.py")
s = p.read_text(encoding="utf-8")
old = r'''new_row = '''        print_kind = "recipe" if kind == "rx" else "certificate"
        rows.append(
            "<div class='encounter-document-row'>"
            f"<span class='encounter-document-icon'>{'Rx' if kind == 'rx' else 'DOC'}</span>"
            f"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>"
            "<span class='encounter-document-actions'>"
            f"<a class='encounter-document-action' href='{url}' target='_blank'>Ver</a>"
            f"<button type='button' class='encounter-document-action primary' data-print-url='{url}' data-print-kind='{print_kind}' onclick=\"historiaNativePrint(this.dataset.printUrl,this.dataset.printKind)\">Imprimir</button>"
            "</span>"
            "</div>"
        )
'''
'''
new = r'''new_row = '''        print_kind = "recipe" if kind == "rx" else "certificate"
        print_button = (
            f"<button type='button' class='encounter-document-action primary' "
            f"data-print-url='{e(url)}' data-print-kind='{e(print_kind)}' "
            "onclick='historiaNativePrint(this.dataset.printUrl,this.dataset.printKind)'>"
            "Imprimir</button>"
        )
        rows.append(
            "<div class='encounter-document-row'>"
            + f"<span class='encounter-document-icon'>{'Rx' if kind == 'rx' else 'DOC'}</span>"
            + f"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>"
            + "<span class='encounter-document-actions'>"
            + f"<a class='encounter-document-action' href='{url}' target='_blank'>Ver</a>"
            + print_button
            + "</span></div>"
        )
'''
'''
if old not in s:
    raise RuntimeError("No encontré el bloque new_row esperado")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("Builder 1.3.71 document row fixed")
