from pathlib import Path
import json

root = Path('historia-clinica/app')
app_path = root / 'app.py'
css_path = root / 'static/style.css'
version_path = root / 'historia-version.json'
manifest_path = root / 'update_manifest.json'

app = app_path.read_text(encoding='utf-8')
old = 'f"""<a class="patient-row" href="/paciente/{e(r[\'id\'])}"><div class="avatar">'
new = 'f"""<a class="patient-row patient-search-result" href="/paciente/{e(r[\'id\'])}"><div class="avatar">'
count = app.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one patient search row marker, got {count}')
app = app.replace(old, new, 1)
app_path.write_text(app, encoding='utf-8')

css = css_path.read_text(encoding='utf-8')
marker = '/* v1.3.81 · resultados de búsqueda de pacientes más legibles */'
addition = r'''

/* v1.3.81 · resultados de búsqueda de pacientes más legibles */
.patient-search-result{
  min-height:78px!important;
  padding:15px 20px!important;
  gap:16px!important;
  background:#fff!important;
}
.patient-search-result:hover{
  background:#fff8ed!important;
}
.patient-search-result .avatar{
  width:50px!important;
  height:50px!important;
  border-radius:9px!important;
  font-size:18px!important;
  font-weight:800!important;
}
.patient-search-result .patient-main b{
  font-size:17px!important;
  line-height:1.28!important;
  font-weight:800!important;
  white-space:normal!important;
  overflow:visible!important;
  text-overflow:clip!important;
  color:#18212d!important;
}
.patient-search-result .patient-main span{
  margin-top:5px!important;
  font-size:13px!important;
  line-height:1.35!important;
  color:#626a72!important;
}
.patient-search-result .patient-meta{
  min-width:82px!important;
}
.patient-search-result .patient-meta strong{
  font-size:17px!important;
  line-height:1.1!important;
  color:#173e70!important;
}
.patient-search-result .patient-meta span{
  margin-top:3px!important;
  font-size:11.5px!important;
}
.patient-search-result .chev{
  font-size:28px!important;
  color:#506b8d!important;
}
@media(max-width:700px){
  .patient-search-result{padding:13px 14px!important;gap:11px!important}
  .patient-search-result .avatar{width:44px!important;height:44px!important;font-size:16px!important}
  .patient-search-result .patient-main b{font-size:15.5px!important}
  .patient-search-result .patient-main span{font-size:12px!important}
  .patient-search-result .patient-meta{min-width:62px!important}
}
'''
if marker not in css:
    css = css.rstrip() + addition + '\n'
css_path.write_text(css, encoding='utf-8')

version_path.write_text(json.dumps({'version':'1.3.81'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
for key in ('version','app_version','runtime_version'):
    manifest[key] = '1.3.81'
notes = manifest.setdefault('notes', {})
notes['purpose'] = 'Resultados del buscador de pacientes más grandes y legibles para el doctor.'
notes['previous_version'] = '1.3.80'
notes['functional_changes'] = False
notes['ui_only_release'] = True
notes['clinical_data_changes'] = False
notes['cloud_logic_changes'] = False
notes['printing_changes'] = False
notes['database_schema_changes'] = False
notes['patient_search_results_large'] = True
notes['patient_search_name_font_px'] = 17
notes['patient_search_secondary_font_px'] = 13
notes['patient_search_row_min_height_px'] = 78
notes['patient_search_scope_only'] = True
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
