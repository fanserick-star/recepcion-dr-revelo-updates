from pathlib import Path
import json

root = Path('historia-clinica/app')
css_path = root / 'static/style.css'
version_path = root / 'historia-version.json'
manifest_path = root / 'update_manifest.json'

css = css_path.read_text(encoding='utf-8')
marker = '/* v1.3.80 · sala de espera en tarjetas clínicas */'
addition = r'''

/* v1.3.80 · sala de espera en tarjetas clínicas */
.home-queue-v107 .home-scroll-region{
  display:grid!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:12px!important;
  padding:14px!important;
  align-items:stretch!important;
  background:#f7f4ee!important;
}
.home-queue-v107 .queue-row{
  position:relative!important;
  display:block!important;
  min-width:0!important;
  padding:0!important;
  border:1px solid #c9c1b6!important;
  border-radius:8px!important;
  background:#fff!important;
  box-shadow:0 3px 10px rgba(37,44,52,.06)!important;
  overflow:hidden!important;
  transition:transform .12s ease,box-shadow .12s ease,border-color .12s ease!important;
}
.home-queue-v107 .queue-row:hover{
  transform:translateY(-1px)!important;
  border-color:#9eaaae!important;
  box-shadow:0 7px 16px rgba(37,44,52,.10)!important;
  background:#fff!important;
}
.home-queue-v107 .queue-row:first-child{
  grid-column:1/-1!important;
  border:2px solid #2e6d82!important;
  background:linear-gradient(135deg,#ffffff 0%,#f5fbfc 100%)!important;
  box-shadow:0 8px 18px rgba(33,92,111,.12)!important;
}
.home-queue-v107 .queue-row:first-child:before{
  content:'SIGUIENTE PACIENTE';
  display:block!important;
  padding:6px 14px!important;
  background:#2e6d82!important;
  color:#fff!important;
  font-size:10px!important;
  font-weight:800!important;
  letter-spacing:.10em!important;
}
.home-queue-v107 .queue-row-main{
  display:grid!important;
  grid-template-columns:76px 52px minmax(0,1fr) auto!important;
  grid-template-areas:
    'turn avatar patient time'
    'turn avatar patient action'!important;
  align-items:center!important;
  gap:4px 12px!important;
  min-height:126px!important;
  padding:15px 48px 15px 14px!important;
  color:inherit!important;
  text-decoration:none!important;
}
.home-queue-v107 .queue-turn-number{
  grid-area:turn!important;
  align-self:stretch!important;
  min-height:88px!important;
  display:flex!important;
  flex-direction:column!important;
  align-items:center!important;
  justify-content:center!important;
  border-radius:7px!important;
  background:#eef4f6!important;
  border:1px solid #d1dde1!important;
}
.home-queue-v107 .queue-turn-number span{
  font-size:9px!important;
  font-weight:800!important;
  letter-spacing:.08em!important;
  color:#66767c!important;
}
.home-queue-v107 .queue-turn-number b{
  margin-top:3px!important;
  font-size:24px!important;
  line-height:1!important;
  color:#164e63!important;
}
.home-queue-v107 .queue-avatar{
  grid-area:avatar!important;
  width:50px!important;
  height:50px!important;
  border-radius:50%!important;
  font-size:18px!important;
  background:#eaf2f5!important;
  color:#1b5c73!important;
}
.home-queue-v107 .queue-patient-copy{
  grid-area:patient!important;
  min-width:0!important;
  align-self:center!important;
}
.home-queue-v107 .queue-patient-copy>b{
  display:block!important;
  font-size:17px!important;
  line-height:1.24!important;
  color:#172433!important;
  white-space:normal!important;
}
.home-queue-v107 .queue-patient-meta{
  display:block!important;
  margin-top:5px!important;
  font-size:12.5px!important;
  color:#667078!important;
}
.home-queue-v107 .queue-tags{
  display:flex!important;
  flex-wrap:wrap!important;
  gap:5px!important;
  margin-top:8px!important;
}
.home-queue-v107 .queue-tags>span{
  border-radius:999px!important;
  padding:4px 8px!important;
  font-size:10px!important;
  font-weight:800!important;
  letter-spacing:.02em!important;
}
.home-queue-v107 .queue-type-nuevo{
  background:#e8f1ff!important;
  color:#235b99!important;
}
.home-queue-v107 .queue-type-subsecuente{
  background:#e9f5ef!important;
  color:#23664e!important;
}
.home-queue-v107 .queue-status{
  background:#fff1d8!important;
  color:#8c6017!important;
}
.home-queue-v107 .queue-row-main>time{
  grid-area:time!important;
  align-self:end!important;
  justify-self:end!important;
  font-size:12px!important;
  font-weight:800!important;
  color:#65717b!important;
}
.home-queue-v107 .queue-row-action{
  grid-area:action!important;
  align-self:start!important;
  justify-self:end!important;
  display:inline-flex!important;
  align-items:center!important;
  min-height:34px!important;
  padding:0 12px!important;
  border-radius:6px!important;
  background:#174f73!important;
  color:#fff!important;
  font-size:11.5px!important;
  font-weight:800!important;
  white-space:nowrap!important;
}
.home-queue-v107 .queue-row:first-child .queue-row-action{
  background:#126b62!important;
  font-size:12.5px!important;
  min-height:38px!important;
  padding:0 16px!important;
}
.home-queue-v107 .queue-dismiss-form{
  position:absolute!important;
  top:9px!important;
  right:9px!important;
  z-index:3!important;
}
.home-queue-v107 .queue-row:first-child .queue-dismiss-form{top:36px!important}
.home-queue-v107 .queue-dismiss-btn{
  width:28px!important;
  height:28px!important;
  border-radius:50%!important;
  border:1px solid #d7d0c7!important;
  background:#fff!important;
  color:#8a6c6c!important;
  font-size:17px!important;
  line-height:1!important;
  cursor:pointer!important;
}
.home-queue-v107 .queue-row-new{border-left:4px solid #4c86bc!important}
.home-queue-v107 .queue-row-consultation:not(.queue-row-new){border-left:4px solid #4f8b72!important}
.home-queue-v107 .queue-empty{grid-column:1/-1!important;background:#fff!important;border:1px dashed #c9c1b6!important;border-radius:8px!important}
@media(max-width:1120px){
  .home-queue-v107 .home-scroll-region{grid-template-columns:1fr!important}
  .home-queue-v107 .queue-row:first-child{grid-column:auto!important}
}
@media(max-width:720px){
  .home-queue-v107 .queue-row-main{
    grid-template-columns:64px minmax(0,1fr)!important;
    grid-template-areas:'turn patient' 'avatar patient' 'time action'!important;
    min-height:0!important;
    padding:12px 42px 12px 12px!important;
  }
  .home-queue-v107 .queue-turn-number{min-height:62px!important}
  .home-queue-v107 .queue-avatar{width:42px!important;height:42px!important}
  .home-queue-v107 .queue-patient-copy>b{font-size:15px!important}
}
'''
if marker not in css:
    css_path.write_text(css.rstrip() + addition + '\n', encoding='utf-8')

version_path.write_text(json.dumps({'version':'1.3.80'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
for key in ('version','app_version','runtime_version'):
    manifest[key] = '1.3.80'
notes = manifest.setdefault('notes', {})
notes['purpose'] = 'Sala de espera del doctor en tarjetas clínicas, con el siguiente paciente destacado y estados visuales claros.'
notes['previous_version'] = '1.3.79'
notes['functional_changes'] = False
notes['ui_only_release'] = True
notes['clinical_data_changes'] = False
notes['cloud_logic_changes'] = False
notes['printing_changes'] = False
notes['database_schema_changes'] = False
notes['waiting_room_card_layout'] = True
notes['waiting_room_next_patient_featured'] = True
notes['waiting_room_two_column_cards'] = True
notes['waiting_room_responsive_single_column'] = True
notes['waiting_room_turn_prominent'] = True
notes['waiting_room_status_tags_preserved'] = True
notes['waiting_room_queue_logic_unchanged'] = True
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Historia 1.3.80 candidate applied')
