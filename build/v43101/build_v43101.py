from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v43100'
OUT = ROOT / 'updates' / 'v43101'
VERSION = '4.3.101'
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
    rebuilt = ''.join((OUT / name).read_text(encoding='utf-8') for name in names)
    if rebuilt != text:
        raise SystemExit('reconstrucción inválida ' + prefix)
    return names


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontró {count}')
    return text.replace(old, new, 1)


def patch_app(s: str) -> str:
    s = replace_once(s, 'APP_VERSION = "4.3.100"', 'APP_VERSION = "4.3.101"', 'versión backend')
    s = replace_once(s, "const VERSION=\\'4.3.100\\';", "const VERSION=\\'4.3.101\\';", 'versión visual')

    start = s.index(' function buildServices(box){')
    end = s.index(' function hideObservation(box){', start)
    new_build = r''' function buildServices(box){
   let grid=box.querySelector('.v492-services-grid');

   // v4.3.101: los servicios reales de Nueva atención son BOTONES nativos
   // button.service-card[data-service]. La rutina antigua buscaba checkbox/radio,
   // por eso CONSULTA quedaba fuera del remaster. Trabajamos directamente con
   // esos botones para conservar su onclick/toggleService y el guardado original.
   const nativeCards=[...box.querySelectorAll('button.service-card[data-service]')].filter(b=>!b.disabled);
   const legacyInputs=[...box.querySelectorAll('input[type="checkbox"],input[type="radio"]')].filter(i=>!i.disabled&&i.offsetParent!==null);
   const cards=[];const seen=new Set();

   for(const card of nativeCards){if(card&&!seen.has(card)){seen.add(card);cards.push(card)}}
   if(!cards.length){
     for(const inp of legacyInputs){const c=serviceCardForInput(inp,box);if(c&&!seen.has(c)){seen.add(c);cards.push(c)}}
   }
   if(!cards.length)return null;

   if(!grid){
     grid=document.createElement('div');grid.className='v492-services-grid';
     const title=leaf(box,t=>t==='atención realizada'||t==='selecciona la atención');
     let anchor=title?.parentElement||null;
     const head=document.createElement('div');head.className='v492-selection-head';head.innerHTML='<h3>Atención realizada</h3><span class="v492-selection-count">0 seleccionadas</span>';
     if(anchor)anchor.insertAdjacentElement('beforebegin',head);else box.appendChild(head);
     head.insertAdjacentElement('afterend',grid);
     if(anchor)anchor.classList.add('v492-empty-source');
   }

   // CONSULTA siempre va primero; después conservamos el orden de procedimientos.
   cards.sort((a,b)=>{
     const ak=norm(a.dataset?.service||a.textContent),bk=norm(b.dataset?.service||b.textContent);
     return (ak==='consulta'?-1:0)-(bk==='consulta'?-1:0);
   });

   for(const card of cards){
     const old=card.parentElement;
     card.classList.add('v492-service-card');
     const key=norm(card.dataset?.service||'');
     const txt=norm(card.textContent);
     if(key==='consulta'||(/(^|\s)consulta(\s|$)/.test(txt)&&!txt.includes('cisto'))){
       card.classList.add('v492-consult','v497-native-consult');
     }
     // Los botones nativos ya traen .service-icon; solo creamos el marcador
     // viejo cuando se trata de una estructura legacy.
     if(!card.matches('button.service-card[data-service]')&&!card.querySelector('.v492-service-mark')){
       const mark=document.createElement('span');mark.className='v492-service-mark';mark.textContent='+';card.prepend(mark);
     }
     const editable=[...card.querySelectorAll('small,span,div')].find(x=>x.children.length===0&&norm(x.textContent).includes('valor editable'));
     if(editable){editable.textContent='Valor editable';editable.classList.add('v492-editable')}
     grid.appendChild(card);
     if(old&&old!==box&&!old.querySelector('button.service-card[data-service],input[type="checkbox"],input[type="radio"]'))old.classList.add('v492-empty-source');
   }

   // Al mover los botones, los contenedores antiguos quedan vacíos. Se ocultan
   // completos para que no queden las barras/huecos que se ven en la captura.
   box.querySelectorAll('.service-groups,.service-section,.consultation-service-section,.procedures-service-section').forEach(el=>{
     if(!el.querySelector('button.service-card[data-service],input[type="checkbox"],input[type="radio"]'))el.classList.add('v492-empty-source');
   });

   const consulta=grid.querySelector('button.service-card[data-service="CONSULTA"],button.service-card[data-service="consulta"]');
   if(consulta&&grid.firstElementChild!==consulta)grid.insertBefore(consulta,grid.firstElementChild);
   return grid;
 }
'''
    s = s[:start] + new_build + s[end:]

    start = s.index(' function sync(box){', s.index('V492_ATTENTION_JS'))
    end = s.index(' function enhance(){', start)
    new_sync = r''' function sync(box){
   const cards=[...box.querySelectorAll('.v492-services-grid .v492-service-card')];
   let count=0;
   for(const c of cards){
     const active=c.matches('button.service-card[data-service]')?c.classList.contains('selected'):!!c.querySelector('input:checked');
     c.classList.toggle('is-selected',active);
     if(active)count++;
   }
   const pill=box.querySelector('.v492-selection-count');if(pill)pill.textContent=count===1?'1 seleccionada':`${count} seleccionadas`;
 }
'''
    s = s[:start] + new_sync + s[end:]

    compile(s, 'app.py', 'exec')
    required = [
        'APP_VERSION = "4.3.101"',
        'button.service-card[data-service]',
        "const nativeCards=[...box.querySelectorAll('button.service-card[data-service]')]",
        'const consulta=grid.querySelector(\'button.service-card[data-service="CONSULTA"]',
        "c.classList.contains('selected')",
        'V497_ATTENTION_JS',
        'v497-native-consult',
        'Revisando AZUR',
        'Emitir por lotes',
    ]
    for token in required:
        if token not in s:
            raise SystemExit('app falta ' + token)
    return s


def main() -> None:
    app = patch_app(joined('app.part', 7))
    launcher = joined('ABRIR_RECEPCION.part', 4)
    ap = write_parts(app, 'app.part', 7)
    lp = write_parts(launcher, 'ABRIR_RECEPCION.part', 4)

    index = (SRC / 'static' / 'index.html').read_text(encoding='utf-8')
    index_target = OUT / 'static' / 'index.html'
    index_target.parent.mkdir(parents=True, exist_ok=True)
    index_target.write_text(index, encoding='utf-8', newline='')

    ab, lb, ib = app.encode(), launcher.encode(), index.encode()
    manifest = {
        'product': 'recepcion-pacientes',
        'version': VERSION,
        'app_version': VERSION,
        'runtime_version': VERSION,
        'launcher_version': LAUNCHER_VERSION,
        'updater_version': 'integrado-en-launcher',
        'copy': ['ABRIR_RECEPCION.py', 'app.py', 'static/index.html', 'update_manifest.json'],
    }
    mb = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    (OUT / 'update_manifest.json').write_bytes(mb)

    base = 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v43101/'
    latest = {
        'product': 'recepcion-pacientes',
        'version': VERSION,
        'mandatory': True,
        'channel': 'files-v3',
        'message': 'v4.3.101: corrige Nueva atención desde la rutina estructural: usa los botones nativos de servicios, muestra CONSULTA primero y elimina huecos antiguos.',
        'files': [
            {'path': 'ABRIR_RECEPCION.py', 'parts': [base+x for x in lp], 'sha256': sha(lb), 'encoding': 'utf-8'},
            {'path': 'app.py', 'parts': [base+x for x in ap], 'sha256': sha(ab), 'encoding': 'utf-8'},
            {'path': 'static/index.html', 'url': base+'static/index.html', 'sha256': sha(ib), 'encoding': 'utf-8'},
            {'path': 'update_manifest.json', 'url': base+'update_manifest.json', 'sha256': sha(mb), 'encoding': 'utf-8'},
        ],
    }
    text = json.dumps(latest, ensure_ascii=False, indent=2) + '\n'
    (ROOT / 'latest.json').write_text(text, encoding='utf-8', newline='')
    (ROOT / 'latest-v3.json').write_text(text, encoding='utf-8', newline='')
    print('OK', VERSION, sha(ab), sha(lb))


if __name__ == '__main__':
    main()
