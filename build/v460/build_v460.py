from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parents[2]
oldroot=ROOT/'updates'/'v459'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
OLD_SHA='edb50022e37bc08e0ce2cfc23cc2e0c9d4be32fe7ea0353b4f47860549361321'
NEW_SHA='63f5171cc66d04eb82d0b9e2b0dd4c13a4822be1a6cd391c4c75a7b2d5c088a3'
if hashlib.sha256(raw).hexdigest()!=OLD_SHA: raise SystemExit('La base v4.3.59 no coincide con la publicada')
s=raw.decode('utf-8')
s=s.replace('APP_VERSION = "4.3.59"','APP_VERSION = "4.3.60"',1)
s=s.replace('UPDATE_BACKUP_DIR = os.path.join(DATA_DIR, "update_backups")','UPDATE_BACKUP_DIR = os.path.join(BASE_DIR, "_update_backups")',1)
old='''        '<link rel="stylesheet" href="/v459/settings.css?v=4.3.59">'\n        '<script defer src="/v459/settings.js?v=4.3.59"></script>'\n'''
new=old+'''        '<link rel="stylesheet" href="/v460/overlay.css?v=4.3.60">'\n        '<script defer src="/v460/overlay.js?v=4.3.60"></script>'\n'''
if old not in s: raise SystemExit('No se encontró la inyección UI v4.3.59')
s=s.replace(old,new,1)
insert='''\n\n# ---------------------------------------------------------------------------\n# v4.3.60 — visibilidad de versión + estados de Agenda con alto contraste\n# ---------------------------------------------------------------------------\nV460_OVERLAY_CSS = r"""\n#connectionBadge .v460-version{margin-left:auto;padding-left:8px;border-left:1px solid currentColor;font-size:9px;font-weight:900;letter-spacing:.035em;white-space:nowrap;opacity:.88}\n.native-slot.occupied.pending{background:#fff1b8!important;border-color:#dfaa14!important;box-shadow:inset 5px 0 0 #c88c00!important;color:#624800!important}\n.native-slot.occupied.pending b,.native-slot.occupied.pending span{color:#624800!important}.native-slot.occupied.pending span{font-weight:850!important}\n.native-slot.occupied.confirmed{background:#cdf2db!important;border-color:#35a967!important;box-shadow:inset 5px 0 0 #138c46!important;color:#0d5b2c!important}\n.native-slot.occupied.confirmed b,.native-slot.occupied.confirmed span{color:#0d5b2c!important}.native-slot.occupied.confirmed span{font-weight:900!important}\n.native-slot.occupied.cancelled{background:#ffd5da!important;border-color:#df5d6e!important;box-shadow:inset 5px 0 0 #c82e43!important;color:#81202d!important}\n.native-slot.occupied.cancelled b,.native-slot.occupied.cancelled span{color:#81202d!important}.native-slot.occupied.cancelled span{font-weight:900!important}\n.native-slot.occupied.rescheduled{background:#dce9ff!important;border-color:#648fd6!important;box-shadow:inset 5px 0 0 #356cc0!important;color:#214d91!important}\n.native-slot.occupied.rescheduled b,.native-slot.occupied.rescheduled span{color:#214d91!important}.native-slot.occupied.rescheduled span{font-weight:900!important}\n.native-detail-status.confirmed{background:#cdf2db!important;border:1px solid #35a967!important;color:#0d5b2c!important;font-weight:900!important}\n.native-detail-status.cancelled{background:#ffd5da!important;border:1px solid #df5d6e!important;color:#81202d!important;font-weight:900!important}\n.native-detail-status.pending{background:#fff1b8!important;border:1px solid #dfaa14!important;color:#624800!important;font-weight:900!important}\n.native-detail-status.rescheduled{background:#dce9ff!important;border:1px solid #648fd6!important;color:#214d91!important;font-weight:900!important}\n.v459-wa-step.success .v459-wa-copy{border-left:3px solid #2e9d5a;padding-left:8px}\n.v459-wa-step.danger .v459-wa-copy{border-left:3px solid #cf3345;padding-left:8px}\n"""\n\nV460_OVERLAY_JS = r"""\n(()=>{\n'use strict';\nconst VERSION='4.3.60';\nfunction paintVersion(){\n  const badge=document.querySelector('#connectionBadge');\n  if(badge){\n    let v=badge.querySelector('.v460-version');\n    if(!v){v=document.createElement('span');v.className='v460-version';badge.appendChild(v)}\n    if(v.textContent!==`v${VERSION}`)v.textContent=`v${VERSION}`;\n  }\n  const configBadge=document.querySelector('#currentVersionBadge');\n  if(configBadge&&configBadge.textContent!==`v${VERSION}`)configBadge.textContent=`v${VERSION}`;\n}\nfunction watch(){\n  paintVersion();\n  const badge=document.querySelector('#connectionBadge');\n  if(badge&&!badge.dataset.v460Watch){badge.dataset.v460Watch='1';new MutationObserver(paintVersion).observe(badge,{childList:true})}\n  const root=document.querySelector('#config')||document.body;\n  if(root&&!root.dataset.v460VersionWatch){root.dataset.v460VersionWatch='1';new MutationObserver(paintVersion).observe(root,{childList:true,subtree:true})}\n}\nif(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watch,{once:true});else watch();\nsetTimeout(watch,250);\n})();\n"""\n\n@app.get("/v460/overlay.css")\ndef v460_overlay_css():\n    return Response(content=V460_OVERLAY_CSS, media_type="text/css; charset=utf-8", headers={"Cache-Control":"no-store"})\n\n@app.get("/v460/overlay.js")\ndef v460_overlay_js():\n    return Response(content=V460_OVERLAY_JS, media_type="application/javascript; charset=utf-8", headers={"Cache-Control":"no-store"})\n'''
marker='''@app.get("/api/update/info")\ndef update_info(user: User = Depends(current_user)):\n'''
if marker not in s: raise SystemExit('No se encontró punto de inserción')
s=s.replace(marker,insert+'\n\n'+marker,1)
final=s.encode('utf-8')
got=hashlib.sha256(final).hexdigest()
if got!=NEW_SHA: raise SystemExit(f'SHA final inesperado {got}')
out=ROOT/'updates'/'v460';out.mkdir(parents=True,exist_ok=True)
for p in out.glob('app.part*'): p.unlink()
chunks=[];cur=[];size=0
for ch in s:
    b=len(ch.encode('utf-8'))
    if cur and size+b>70000: chunks.append(''.join(cur));cur=[ch];size=b
    else: cur.append(ch);size+=b
if cur: chunks.append(''.join(cur))
for i,ch in enumerate(chunks,1):(out/f'app.part{i}').write_text(ch,encoding='utf-8',newline='')
assert b''.join((out/f'app.part{i}').read_bytes() for i in range(1,len(chunks)+1))==final
manifest={"product":"recepcion-pacientes","version":"4.3.60","app_version":"4.3.60","runtime_version":"4.3.60","launcher_version":"4.3.57-standalone-1","updater_version":"integrado-en-launcher","copy":["ABRIR_RECEPCION.py","app.py","update_manifest.json"]}
(out/'update_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='')
(out/'test_v460.py').write_bytes((ROOT/'build'/'v460'/'test_v460.py').read_bytes())
print('V460_BUILT',len(final),got,len(chunks))
