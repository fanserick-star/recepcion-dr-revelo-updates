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
// WebView 52 / Android 7: prevent a blank TV on legacy kiosk browsers.
if (display.includes('.padStart(')) throw Error('TV legacy: String.padStart is not supported in WebView 52');
if (!display.includes('function pad2(v)')) throw Error('TV legacy: pad2() fallback missing');
if (/\binset\s*:/.test(display)) throw Error('TV legacy: unsupported CSS inset shorthand');
if (!display.includes('width:min(65vh,46vw)') || !display.includes('width:60vh')) {
  throw Error('TV legacy: clock must have modern and old browser width fallbacks');
}
// Keep these independent behaviours intact when adjusting the presentation.
for (const marker of [
  '/api/display-state', 'function ding(s)', 'function announceTurn(turn)',
  'function startVideo(turn)', "if(s.event_id&&s.event_id!==lastEvent)",
  'id="ding"', 'id="voiceAudio"'
]) if (!display.includes(marker)) throw Error('TV: missing call/audio contract: ' + marker);

if (!display.includes('s.exam_review')) throw Error('La TV no muestra revisión de exámenes');
if (!match[1].includes('state.exam_review')) throw Error('La voz no contempla revisión de exámenes');
const httpFile = 'recepcion/app/reception_tv_http.py';
const audioFile = 'recepcion/app/reception_tv_speech.py';
const http = fs.readFileSync(httpFile, 'utf8');
const audio = fs.readFileSync(audioFile, 'utf8');
if (!http.includes('if path == "/api/turn-voice.wav":') || !http.includes('turn_voice_wav(turn, review)'))
  throw Error('La API de WAV para TV sin voces no está conectada');
if (!audio.includes('System.Speech.Synthesis.SpeechSynthesizer') || !audio.includes('getattr(subprocess, "CREATE_NO_WINDOW"'))
  throw Error('La voz local de Windows para Fully no está configurada');
if (!match[1].includes('!nativeVoices.length') || !match[1].includes('playReceptionVoice(n,isExamReview)'))
  throw Error('El TV Box antiguo debe usar voz de Recepción cuando no tiene voces');
if (!display.includes('id="audioEnable"') || !display.includes('function enableAudio()'))
  throw Error('El TV no ofrece activación de audio cuando WebView lo bloquea');
if (!display.includes("if(s.event_id&&s.event_id!==lastEvent)"))
  throw Error('La TV no protege los llamados contra duplicados');

console.log('TV_DISPLAY_AND_VOICE_JAVASCRIPT_OK');
