from __future__ import annotations
import hashlib, json, math, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v43102'
OUT = ROOT / 'updates' / 'v43103'
VERSION = '4.3.103'
LAUNCHER_VERSION = '4.3.100-standalone-7'


def joined(prefix: str, n: int) -> str:
    parts = sorted(SRC.glob(prefix + '*'), key=lambda p: int(p.name.replace(prefix, '')))
    if len(parts) != n:
        raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(parts)}')
    return ''.join(p.read_text(encoding='utf-8') for p in parts)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_parts(text: str, prefix: str, n: int) -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob(prefix + '*'):
        p.unlink()
    step = math.ceil(len(text) / n)
    names = []
    for i in range(n):
        name = f'{prefix}{i+1}'
        (OUT / name).write_text(text[i*step:(i+1)*step], encoding='utf-8', newline='')
        names.append(name)
    if ''.join((OUT / x).read_text(encoding='utf-8') for x in names) != text:
        raise SystemExit('reconstrucción inválida ' + prefix)
    return names


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontró {count}')
    return text.replace(old, new, 1)


CLEAN_CSS = r'''/* v4.3.103 — servicios nativos, sin proxies ni reordenamientos */
.modalbox.v492-attention{overflow-x:hidden!important}
.v492-attention .service-title.enhanced{display:none!important}
.v492-attention .service-groups{display:grid!important;grid-template-columns:1fr!important;gap:13px!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0 0 10px!important;padding:0!important;box-sizing:border-box!important}
.v492-attention .service-section{width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;border-radius:14px!important;box-shadow:0 2px 9px rgba(34,61,91,.035)!important}
.v492-attention .consultation-service-section{padding:12px 13px 13px!important;border:1px solid #c7dcf2!important;background:linear-gradient(180deg,#f6f9ff 0%,#eef5ff 100%)!important}
.v492-attention .consultation-service-section .service-group-heading{margin-bottom:9px!important}
.v492-attention .consultation-service-section .service-group-heading b{font-size:15px!important;color:#274462!important;letter-spacing:-.01em!important}
.v492-attention .consultation-service-section .service-group-heading span{font-size:9px!important;color:#70849a!important}
.v492-attention .consultation-grid{display:grid!important;grid-template-columns:1fr!important;gap:0!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important}
.v492-attention .consultation-card{display:grid!important;grid-template-columns:auto 1fr auto!important;grid-template-areas:'icon title check' 'icon price check'!important;column-gap:10px!important;row-gap:2px!important;align-items:center!important;width:100%!important;max-width:100%!important;min-width:0!important;min-height:66px!important;box-sizing:border-box!important;padding:11px 42px 11px 12px!important;border:1px solid #b8d2ee!important;border-radius:12px!important;background:#fff!important;box-shadow:0 2px 8px rgba(30,68,108,.045)!important;color:#223b58!important}
.v492-attention .consultation-card:hover{border-color:#86b2df!important;background:#fafdff!important}
.v492-attention .consultation-card.selected{border-color:#55a379!important;background:#eff9f3!important;box-shadow:0 0 0 2px rgba(67,150,102,.10)!important}
.v492-attention .consultation-card .service-icon{grid-area:icon!important;background:#e5f0fc!important;color:#2d6ca6!important}
.v492-attention .consultation-card.selected .service-icon{background:#3d8e62!important;color:#fff!important}
.v492-attention .consultation-card strong{grid-area:title!important;font-size:13px!important;line-height:1.05!important;color:#203a56!important}
.v492-attention .consultation-card .service-price{grid-area:price!important;font-size:10.5px!important;font-weight:850!important;color:#58718a!important}
.v492-attention .consultation-card .service-check{grid-area:check!important;right:9px!important;top:50%!important;transform:translateY(-50%)!important}
.v492-attention .procedures-service-section{padding:12px 12px 13px!important;border:1px solid #dfe7f0!important;background:#fbfcfe!important}
.v492-attention .procedures-service-section .service-group-heading{margin-bottom:9px!important}
.v492-attention .procedures-service-section .service-group-heading b{font-size:16px!important;color:#263d57!important;letter-spacing:-.012em!important}
.v492-attention .procedures-service-section .service-group-heading span{font-size:9px!important;color:#7b899a!important}
.v492-attention .procedures-service-section .service-grid{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:9px!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important;padding:0!important;box-sizing:border-box!important}
.v492-attention .procedures-service-section .service-card{width:100%!important;max-width:100%!important;min-width:0!important;min-height:62px!important;box-sizing:border-box!important;margin:0!important}
.v492-attention .v43102-consult-section,.v492-attention .v43102-procedure-head,.v492-attention .v492-services-grid,.v492-attention .v495-consult-card,.v492-attention .v494-consult-proxy,.v492-attention .v495-consult-card{display:none!important}
@media(max-width:760px){.v492-attention .procedures-service-section .service-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
@media(max-width:470px){.v492-attention .procedures-service-section .service-grid{grid-template-columns:1fr!important}}
'''


def patch_app(s: str) -> str:
    s = replace_once(s, 'APP_VERSION = "4.3.102"', 'APP_VERSION = "4.3.103"', 'versión backend')
    s = replace_once(s, "const VERSION=\\'4.3.102\\';", "const VERSION=\\'4.3.103\\';", 'versión visual')

    # Dejamos de reparentar servicios desde el remaster. La estructura nativa ya
    # contiene Consulta y Procedimientos como secciones separadas y conserva la
    # lógica original de toggleService/selectedServices.
    start = s.index(' function buildServices(box){')
    end = s.index(' function hideObservation(box){', start)
    new_build = r''' function buildServices(box){
   const groups=box.querySelector('.service-groups');
   if(!groups)return null;
   groups.classList.add('v43103-native-services');

   // Elimina restos creados por versiones antiguas si la modal fue reutilizada.
   box.querySelectorAll('.v495-consult-card,.v494-consult-proxy,.v495-consult-card,.v43102-consult-section,.v43102-procedure-head,.v492-services-grid').forEach(el=>el.remove());

   const consultation=groups.querySelector('.consultation-service-section');
   const procedures=groups.querySelector('.procedures-service-section');
   consultation?.classList.remove('v492-empty-source','v497-native-section-empty','v495-hidden-source','hidden');
   procedures?.classList.remove('v492-empty-source','v497-native-section-empty','v495-hidden-source','hidden');
   groups.classList.remove('v492-empty-source','v497-native-section-empty','v495-hidden-source','hidden');

   const consult=groups.querySelector('button.service-card[data-service="CONSULTA"],button.service-card[data-service="consulta"]');
   if(consult){
     consult.classList.remove('v492-service-card','v492-consult','v497-native-consult','v492-empty-source','v495-hidden-source','hidden');
     consult.style.removeProperty('display');consult.style.removeProperty('height');consult.style.removeProperty('visibility');consult.style.removeProperty('opacity');
     const price=consult.querySelector('.service-price');if(price)price.textContent='$40.00';
   }
   const procHeading=procedures?.querySelector('.service-group-heading b');if(procHeading)procHeading.textContent='Procedimientos y servicios';
   return groups;
 }
'''
    s = s[:start] + new_build + s[end:]

    # Sin grilla artificial no necesitamos sincronización visual del remaster.
    start = s.index(' function sync(box){', s.index('V492_ATTENTION_JS'))
    end = s.index(' function enhance(){', start)
    new_sync = r''' function sync(box){
   const consult=box.querySelector('.service-groups button.service-card[data-service="CONSULTA"],.service-groups button.service-card[data-service="consulta"]');
   if(consult)consult.classList.toggle('is-selected',consult.classList.contains('selected'));
 }
'''
    s = s[:start] + new_sync + s[end:]

    # Desactiva únicamente los overlays históricos de Consulta/servicios. El resto
    # de mejoras (encabezado, advertencias, facturación, etc.) permanece intacto.
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker) != 1:
        raise SystemExit('overlay marker inesperado')
    inject = (
        'V43103_SERVICES_CSS = r"""' + CLEAN_CSS + '"""\n'
        'for _legacy_services_js in (globals().get("V493_ATTENTION_JS", ""), globals().get("V494_ATTENTION_JS", ""), globals().get("V495_ATTENTION_JS", ""), globals().get("V497_ATTENTION_JS", "")):\n'
        '    if _legacy_services_js:\n'
        '        V460_OVERLAY_JS = (V460_OVERLAY_JS or "").replace(_legacy_services_js, "")\n'
        'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V43103_SERVICES_CSS\n\n' + marker
    )
    s = s.replace(marker, inject, 1)

    compile(s, 'app.py', 'exec')
    for token in [
        'APP_VERSION = "4.3.103"',
        "const groups=box.querySelector('.service-groups')",
        "price.textContent='$40.00'",
        "procHeading.textContent='Procedimientos y servicios'",
        'V43103_SERVICES_CSS',
        'replace(_legacy_services_js, "")',
        'Revisando AZUR',
        'Emitir por lotes',
    ]:
        if token not in s:
            raise SystemExit('app falta ' + token)
    return s


def build_static_app() -> str:
    base = ROOT / 'installer_clean' / 'base' / 'clean_base_resources.zip'
    with zipfile.ZipFile(base) as z:
        js = z.read('static/app.js').decode('utf-8-sig')
    js = replace_once(js, '<span class="service-price">$40 fijo</span>', '<span class="service-price">$40.00</span>', 'precio Consulta static/app.js')
    js = replace_once(js, '<b>Procedimientos</b><span>Selecciona uno o varios si corresponde</span>', '<b>Procedimientos y servicios</b><span>Selecciona uno o varios si corresponde</span>', 'título procedimientos static/app.js')
    for token in ['data-service="CONSULTA"', "toggleService('CONSULTA')", '<span class="service-price">$40.00</span>', '<b>Procedimientos y servicios</b>']:
        if token not in js:
            raise SystemExit('static/app.js falta ' + token)
    if '$40 fijo' in js:
        raise SystemExit('static/app.js conserva "$40 fijo"')
    return js


def main() -> None:
    app = patch_app(joined('app.part', 7))
    launcher = joined('ABRIR_RECEPCION.part', 4)
    static_app = build_static_app()

    ap = write_parts(app, 'app.part', 7)
    lp = write_parts(launcher, 'ABRIR_RECEPCION.part', 4)

    index = (SRC / 'static' / 'index.html').read_text(encoding='utf-8')
    index_target = OUT / 'static' / 'index.html'
    index_target.parent.mkdir(parents=True, exist_ok=True)
    index_target.write_text(index, encoding='utf-8', newline='')
    appjs_target = OUT / 'static' / 'app.js'
    appjs_target.write_text(static_app, encoding='utf-8', newline='')

    ab, lb, ib, jb = app.encode(), launcher.encode(), index.encode(), static_app.encode()
    manifest = {
        'product': 'recepcion-pacientes', 'version': VERSION, 'app_version': VERSION,
        'runtime_version': VERSION, 'launcher_version': LAUNCHER_VERSION,
        'updater_version': 'integrado-en-launcher',
        'copy': ['ABRIR_RECEPCION.py','app.py','static/index.html','static/app.js','update_manifest.json'],
    }
    mb = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    (OUT / 'update_manifest.json').write_bytes(mb)

    base = 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v43103/'
    latest = {
        'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3',
        'message':'v4.3.103: restaura la estructura nativa de Consulta y Procedimientos; elimina proxies antiguos, muestra $40.00 y deja Consulta aislada en su bloque azul.',
        'files':[
            {'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},
            {'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},
            {'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},
            {'path':'static/app.js','url':base+'static/app.js','sha256':sha(jb),'encoding':'utf-8'},
            {'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'},
        ],
    }
    txt = json.dumps(latest, ensure_ascii=False, indent=2) + '\n'
    (ROOT/'latest.json').write_text(txt, encoding='utf-8', newline='')
    (ROOT/'latest-v3.json').write_text(txt, encoding='utf-8', newline='')
    print('OK', VERSION, sha(ab), sha(jb))


if __name__ == '__main__':
    main()
