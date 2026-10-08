import fs from 'node:fs';
import vm from 'node:vm';

function checkHtmlScripts(file, html) {
  const chunks = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
  if (!chunks.length) throw Error(file + ': no hay scripts para validar');
  for (const [i, chunk] of chunks.entries()) {
    new vm.Script(chunk[1], {filename: file + ':script-' + (i + 1)});
  }
  return chunks.length;
}

const displayFile = 'recepcion/app/tv_display.html';
const selectorFile = 'recepcion/app/reception_tv_voice_selector.py';
const display = fs.readFileSync(displayFile, 'utf8');
const source = fs.readFileSync(selectorFile, 'utf8');
const match = source.match(/DISPLAY_VOICE_SCRIPT\s*=\s*r"""([\s\S]*?)"""/);
if (!match) throw Error('No se pudo extraer el selector de voz de TV');
checkHtmlScripts(displayFile, display);
checkHtmlScripts(selectorFile, match[1]);
if (!display.includes('s.exam_review')) throw Error('La TV no muestra revisión de exámenes');
if (!match[1].includes('state.exam_review')) throw Error('La voz no contempla revisión de exámenes');
console.log('TV_DISPLAY_AND_VOICE_JAVASCRIPT_OK');
