from pathlib import Path

p = Path(__file__).with_name("build_historia_1371.py")
s = p.read_text(encoding="utf-8")
start_marker = "new_row = '''"
end_marker = "app = rep(app, old_row, new_row, label=\"history document professional actions\")"
start = s.find(start_marker)
end = s.find(end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError("No encontré los límites del bloque new_row")

replacement = """new_row = '''        print_kind = \"recipe\" if kind == \"rx\" else \"certificate\"\n        print_button = (\n            f\"<button type='button' class='encounter-document-action primary' \"\n            f\"data-print-url='{e(url)}' data-print-kind='{e(print_kind)}' \"\n            \"onclick='historiaNativePrint(this.dataset.printUrl,this.dataset.printKind)'>\"\n            \"Imprimir</button>\"\n        )\n        rows.append(\n            \"<div class='encounter-document-row'>\"\n            + f\"<span class='encounter-document-icon'>{'Rx' if kind == 'rx' else 'DOC'}</span>\"\n            + f\"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>\"\n            + \"<span class='encounter-document-actions'>\"\n            + f\"<a class='encounter-document-action' href='{url}' target='_blank'>Ver</a>\"\n            + print_button\n            + \"</span></div>\"\n        )\n'''\n"""

s = s[:start] + replacement + s[end:]
p.write_text(s, encoding="utf-8")
print("Builder 1.3.71 document row fixed")
