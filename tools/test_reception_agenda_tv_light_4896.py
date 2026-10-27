from pathlib import Path
import json
root = Path(__file__).resolve().parents[1] / 'recepcion/app'
html = (root/'static/index.html').read_text(encoding='utf-8')
css = (root/'static/home_remaster_4886.css').read_text(encoding='utf-8')
tv = (root/'tv_control.html').read_text(encoding='utf-8')
version = json.loads((root/'recepcion-version.json').read_text())['version']
assert tuple(map(int, version.split('.'))) >= (4, 8, 96)
assert '/static/home_remaster_4886.css?v=' + version in html
assert 'agendaNativeGrid' in html and 'data-agenda-range="afternoon"' in html
assert 'background:#f5f8fc!important' in css and 'color-scheme:light!important' in css
assert 'native-slot.occupied.confirmed' in css and 'native-slot.occupied.cancelled' in css
assert 'data-tab="live"' in tv and 'data-tab="test"' in tv
assert 'v4.8.96' in tv and '--bg:#f5f8fc' in tv
assert 'previewFrame' in tv and 'uploadVideo' in tv
print('RECEPTION_AGENDA_TV_LIGHT_4896_OK')
