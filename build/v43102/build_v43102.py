from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v43101'
OUT = ROOT / 'updates' / 'v43102'
VERSION = '4.3.102'
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


CSS = r'''/* v4.3.102 — Consulta aislada + procedimientos profesionales */
.modalbox.v492-attention{overflow-x:hidden!important}
.v43102-consult-section{display:block;width:100%;box-sizing:border-box;margin:0 0 14px;padding:12px 13px 13px;border:1px solid #cfe0f5;border-radius:14px;background:linear-gradient(180deg,#f6f9ff 0%,#eef5ff 100%);box-shadow:0 2px 9px rgba(39,85,135,.045)}
.v43102-consult-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin:0 2px 8px}
.v43102-consult-heading h3{margin:0!important;font-size:14px!important;line-height:1.1!important;letter-spacing:-.01em!important;color:#28425f!important}
.v43102-consult-heading small{font-size:8px!important;color:#6f8197!important;font-weight:700!important}
.v43102-consult-slot{display:block;width:100%;min-width:0;box-sizing:border-box}
.v43102-consult-slot .v492-service-card,.v43102-consult-slot .v497-native-consult{order:initial!important;width:100%!important;max-width:none!important;min-width:0!important;min-height:66px!important;margin:0!important;padding:11px 44px 11px 46px!important;display:flex!important;align-items:center!important;border:1px solid #b9d2ee!important;border-radius:12px!important;background:#fff!important;box-shadow:0 2px 8px rgba(31,72,112,.045)!important;visibility:visible!important;opacity:1!important}
.v43102-consult-slot .v492-service-card:hover,.v43102-consult-slot .v497-native-consult:hover{border-color:#8bb5e1!important;background:#fafdff!important}
.v43102-consult-slot .v492-service-card.selected,.v43102-consult-slot .v492-service-card.is-selected,.v43102-consult-slot .v497-native-consult.selected{border-color:#56a47a!important;background:#eff9f3!important;box-shadow:0 0 0 2px rgba(68,155,105,.10)!important}
.v43102-consult-slot .v492-service-mark{display:none!important}
.v43102-consult-slot .service-icon{background:#e7f1fc!important;color:#316b9f!important}
.v43102-consult-slot .selected .service-icon,.v43102-consult-slot .is-selected .service-icon{background:#3f8f63!important;color:#fff!important}
.v43102-consult-slot strong,.v43102-consult-slot b{font-size:12px!important;letter-spacing:.01em!important;color:#243d59!important}
.v43102-consult-slot .service-price{font-size:9.5px!important;color:#617790!important;font-weight:850!important}
.v43102-procedure-head{display:flex!important;align-items:flex-end!important;justify-content:space-between!important;gap:12px!important;margin:2px 2px 9px!important;width:100%!important;box-sizing:border-box!important}
.v43102-procedure-head>div{min-width:0}
.v43102-procedure-head h3{margin:0!important;font-size:16px!important;line-height:1.1!important;letter-spacing:-.015em!important;color:#263c56!important}
.v43102-procedure-head p{margin:3px 0 0!important;font-size:8.5px!important;line-height:1.2!important;color:#7a899b!important}
.v492-services-grid{width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:9px!important;margin:0 0 10px!important;padding:0!important;overflow:visible!important}
.v492-services-grid>.v492-service-card{width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;min-height:62px!important;padding:10px 31px 9px 38px!important}
.v492-services-grid>.v492-consult{display:none!important}
.v492-empty-source,.v497-native-section-empty{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
.v492-sticky-actions{max-width:calc(100% + 34px)!important;box-sizing:border-box!important}
@media(max-width:760px){.v492-services-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}.v43102-consult-heading{align-items:flex-start;flex-direction:column;gap:2px}}
@media(max-width:470px){.v492-services-grid{grid-template-columns:1fr!important}}
'''


def patch_app(s: str) -> str:
    s = replace_once(s, 'APP_VERSION = "4.3.101"', 'APP_VERSION = "4.3.102"', 'versión backend')
    s = replace_once(s, "const VERSION=\\'4.3.101\\';", "const VERSION=\\'4.3.102\\';", 'versión visual')

    # Reemplaza la rutina estructural, no un parche posterior. CONSULTA sale de la
    # grilla y se mueve a su propio bloque; los procedimientos quedan abajo.
    start = s.index(' function buildServices(box){')
    end = s.index(' function hideObservation(box){', start)
    new_build = r''' function buildServices(box){
   let grid=box.querySelector('.v492-services-grid');
   let consultSection=box.querySelector('.v43102-consult-section');
   let consultSlot=box.querySelector('.v43102-consult-slot');
   let head=box.querySelector('.v492-selection-head');

   const nativeCards=[...box.querySelectorAll('button.service-card[data-service]')].filter(b=>!b.disabled);
   const legacyInputs=[...box.querySelectorAll('input[type="checkbox"],input[type="radio"]')].filter(i=>!i.disabled&&i.offsetParent!==null);
   const cards=[];const seen=new Set();
   for(const card of nativeCards){if(card&&!seen.has(card)){seen.add(card);cards.push(card)}}
   if(!cards.length){for(const inp of legacyInputs){const c=serviceCardForInput(inp,box);if(c&&!seen.has(c)){seen.add(c);cards.push(c)}}}
   if(!cards.length)return null;

   const consulta=cards.find(card=>norm(card.dataset?.service||card.textContent)==='consulta')||null;
   const procedures=cards.filter(card=>card!==consulta);
   const sourceRoot=(cards[0]?.closest?.('.service-groups'))||cards[0]?.parentElement||null;

   if(consulta&&!consultSection){
     consultSection=document.createElement('section');consultSection.className='v43102-consult-section';
     consultSection.innerHTML='<div class="v43102-consult-heading"><div><h3>Consulta</h3><small>Atención médica</small></div></div><div class="v43102-consult-slot"></div>';
     consultSlot=consultSection.querySelector('.v43102-consult-slot');
   }
   if(!grid){grid=document.createElement('div');grid.className='v492-services-grid'}
   if(!head){head=document.createElement('div');head.className='v492-selection-head v43102-procedure-head'}
   head.classList.add('v43102-procedure-head');
   head.innerHTML='<div><h3>Procedimientos y servicios</h3><p>Selecciona únicamente lo realizado.</p></div>';

   // Inserta toda la nueva estructura ANTES del contenedor nativo antiguo. Esto
   // evita que los títulos nuevos queden como columnas dentro de .service-groups.
   if(sourceRoot&&sourceRoot.parentElement){
     if(consultSection&&!consultSection.isConnected)sourceRoot.insertAdjacentElement('beforebegin',consultSection);
     const ref=consultSection?.isConnected?consultSection:sourceRoot;
     if(!head.isConnected)ref.insertAdjacentElement('afterend',head);
     if(!grid.isConnected)head.insertAdjacentElement('afterend',grid);
   }else{
     const clinical=box.querySelector('.v492-clinical-head');
     if(consultSection&&!consultSection.isConnected)(clinical||box.firstElementChild)?.insertAdjacentElement('afterend',consultSection);
     if(!head.isConnected)(consultSection||clinical||box.firstElementChild)?.insertAdjacentElement('afterend',head);
     if(!grid.isConnected)head.insertAdjacentElement('afterend',grid);
   }

   if(consulta&&consultSlot){
     consulta.classList.add('v492-service-card','v492-consult','v497-native-consult');
     consulta.classList.remove('v492-empty-source','v493-old-alert','v495-hidden-source','hidden');
     consulta.style.removeProperty('display');consulta.style.removeProperty('height');consulta.style.removeProperty('visibility');
     consultSlot.appendChild(consulta);

     // Presentación limpia: el precio es $40.00; no mostramos la palabra "fijo".
     const walker=document.createTreeWalker(consulta,NodeFilter.SHOW_TEXT);
     const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
     for(const node of nodes){
       const before=String(node.nodeValue||'');
       const after=before.replace(/\$?\s*40(?:[.,]00)?\s*fijo/gi,'$40.00');
       if(after!==before)node.nodeValue=after;
     }
     const price=[...consulta.querySelectorAll('.service-price,small,span,div')].find(el=>el.children.length===0&&norm(el.textContent).includes('$40.00'));
     if(price)price.classList.add('v43102-consult-price');
     consulta.querySelectorAll('.v492-service-mark').forEach(x=>x.remove());
   }

   for(const card of procedures){
     const old=card.parentElement;
     card.classList.add('v492-service-card');
     card.classList.remove('v492-consult','v497-native-consult');
     if(!card.matches('button.service-card[data-service]')&&!card.querySelector('.v492-service-mark')){
       const mark=document.createElement('span');mark.className='v492-service-mark';mark.textContent='+';card.prepend(mark);
     }
     const editable=[...card.querySelectorAll('small,span,div')].find(x=>x.children.length===0&&norm(x.textContent).includes('valor editable'));
     if(editable){editable.textContent='Valor editable';editable.classList.add('v492-editable')}
     grid.appendChild(card);
     if(old&&old!==box&&!old.querySelector('button.service-card[data-service],input[type="checkbox"],input[type="radio"]'))old.classList.add('v492-empty-source');
   }

   if(sourceRoot&&!sourceRoot.querySelector('button.service-card[data-service],input[type="checkbox"],input[type="radio"]'))sourceRoot.classList.add('v492-empty-source');
   box.querySelectorAll('.consultation-service-section,.procedures-service-section,.service-groups').forEach(el=>{
     if(!el.querySelector('button.service-card[data-service],input[type="checkbox"],input[type="radio"]'))el.classList.add('v492-empty-source','v497-native-section-empty');
   });
   return grid;
 }
'''
    s = s[:start] + new_build + s[end:]

    # v4.3.97 intentaba volver a meter CONSULTA dentro de la grilla en cada click.
    # Se adapta esa misma rutina para respetar el bloque aislado nuevo.
    v497_start = s.index(' function repairConsult(){', s.index('V497_ATTENTION_JS'))
    v497_end = s.index(' function installFavicon(){', v497_start)
    new_repair = r''' function repairConsult(){
   const box=boxNow();if(!box)return false;
   const card=nativeConsult(box);if(!card)return false;
   const slot=box.querySelector('.v43102-consult-slot');
   if(slot){
     card.classList.remove('v492-empty-source','v493-old-alert','v495-hidden-source','hidden');
     card.style.removeProperty('display');card.style.removeProperty('height');card.style.removeProperty('visibility');
     card.classList.add('v492-service-card','v492-consult','v497-native-consult');
     if(card.parentElement!==slot)slot.appendChild(card);
     card.querySelectorAll('.v492-service-mark').forEach(el=>el.remove());
     hideEmptyNativeSections(box);
     return true;
   }
   const grid=box.querySelector('.v492-services-grid');if(!grid)return false;
   const oldSection=card.closest('.consultation-service-section');
   card.classList.remove('v492-empty-source','v493-old-alert','v495-hidden-source','hidden');
   card.style.removeProperty('display');card.style.removeProperty('height');card.style.removeProperty('visibility');
   card.classList.add('v492-service-card','v492-consult','v497-native-consult');
   grid.querySelectorAll('.v494-consult-proxy,.v495-consult-card').forEach(el=>{if(el!==card)el.remove()});
   if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   if(oldSection&&!oldSection.querySelector('.service-card'))oldSection.classList.add('v497-native-section-empty');
   hideEmptyNativeSections(box);
   return true;
 }
'''
    s = s[:v497_start] + new_repair + s[v497_end:]

    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1:
        raise SystemExit('overlay marker inesperado')
    inject=(
        'V43102_ATTENTION_CSS = r"""'+CSS+'"""\n'
        'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V43102_ATTENTION_CSS\n\n'+marker
    )
    s=s.replace(marker,inject,1)

    compile(s, 'app.py', 'exec')
    required = [
        'APP_VERSION = "4.3.102"',
        'v43102-consult-section',
        'v43102-consult-slot',
        'Procedimientos y servicios',
        "replace(/\\$?\\s*40(?:[.,]00)?\\s*fijo/gi,'$40.00')",
        "const slot=box.querySelector('.v43102-consult-slot')",
        'grid-template-columns:repeat(3,minmax(0,1fr))',
        'overflow-x:hidden',
        'V497_ATTENTION_JS',
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

    base = 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v43102/'
    latest = {
        'product': 'recepcion-pacientes',
        'version': VERSION,
        'mandatory': True,
        'channel': 'files-v3',
        'message': 'v4.3.102: separa CONSULTA en un bloque propio, muestra $40.00 sin “fijo”, ordena Procedimientos y servicios en 3 columnas y elimina el desbordamiento horizontal.',
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
