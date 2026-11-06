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
  'function startVideo(turn)', "function shouldRingForSnapshot(s)",
  'id="ding"', 'id="voiceAudio"'
]) if (!display.includes(marker)) throw Error('TV: missing call/audio contract: ' + marker);

// Public TV and voice must NOT reveal the attention type for exam-review turns.
if (/REVISI[ÓO]N DE EX[ÁA]MENES/i.test(display) || /revisión de exámenes/i.test(match[1]))
  throw Error('La TV no debe decir revisión de exámenes en anuncios de turnos');
if (!display.includes("function syncYoutubeAudio()") || !display.includes("v.muted=videoAudioBlocked&&!audioUnlocked"))
  throw Error('La publicidad debe intentar sonido y ofrecer desbloqueo manual');
if (!source.includes("windowsVoiceSelect") || !source.includes("windows_voice_name"))
  throw Error('El panel debe permitir seleccionar una voz Windows para Fully');
const httpFile = 'recepcion/app/reception_tv_http.py';
const audioFile = 'recepcion/app/reception_tv_speech.py';
const http = fs.readFileSync(httpFile, 'utf8');
const audio = fs.readFileSync(audioFile, 'utf8');
if (!http.includes('if path == "/api/turn-voice.wav":') || !http.includes('audio = turn_voice_wav('))
  throw Error('La API de WAV para TV sin voces no está conectada');
if (!audio.includes('System.Speech.Synthesis.SpeechSynthesizer') || !audio.includes('getattr(subprocess, "CREATE_NO_WINDOW"'))
  throw Error('La voz local de Windows para Fully no está configurada');
if (!match[1].includes('!nativeVoices.length') || !match[1].includes('playReceptionVoice(n,isExamReview,fromCall)'))
  throw Error('El TV Box antiguo debe usar voz de Recepción cuando no tiene voces');
if (!source.includes('voiceAnnounceSurnames') || !match[1].includes('announce_surnames'))
  throw Error('El anuncio opcional de dos apellidos debe tener control explícito desde Recepción');
if (!http.includes('surnames_for_queue(queue_id)') || !http.includes('int(requested_event) == int(live.get("event_id") or 0)'))
  throw Error('No se debe anunciar apellidos fuera del evento de llamado activo y verificado');
if (!audio.includes('uuid.uuid5(uuid.NAMESPACE_URL, "historia-queue:" + str(event_id))') ||
    !audio.includes('_first_two_surnames(payload.get("display_name"))'))
  throw Error('Los apellidos deben resolverse sólo mediante correspondencia exacta en la cola LAN local');
if (display.includes('display_name') || display.includes('surnames') || match[1].includes('display_name'))
  throw Error('La pantalla TV jamás debe recibir nombres de pacientes en texto');
if (!display.includes('id="audioEnable"') || !display.includes('function enableAudio()'))
  throw Error('El TV no ofrece activación de audio cuando WebView lo bloquea');
if (!display.includes("if(pollPending)return") || !display.includes("function shouldRingForSnapshot(s)"))
  throw Error('La TV no debe permitir consultas de estado superpuestas ni llamados repetidos');

// Run the actual client-side call gate against synthetic TV events.
const script = display.match(/<script>([\s\S]*?)<\/script>/)?.[1];
if (!script) throw Error('TV call script missing');
const start = script.indexOf('function shouldRingForSnapshot(s)');
const stop = script.indexOf('function poll(){', start);
if (start < 0 || stop <= start) throw Error('Missing isolated call gate');
const context = {
  lastSource:'', lastBootId:'', seenEvents:{live:null,test:null},
  Number, String, isFinite
};
vm.runInNewContext(script.slice(start,stop), context);
const ring = s => context.shouldRingForSnapshot(s);
const live = {
  tv_boot_id:'server-A', display_mode:'live', history_online:true,
  mode:'calling', turn:6, event_id:10, sound:true, sound_test:false,
  doctor_call_event_id:'manual-event-10'
};
const assertGate = (snapshot, expected, reason) => {
  const actual = ring({...live,...snapshot});
  if (actual !== expected) throw Error(reason + ': expected ' + expected + ' got ' + actual);
};
assertGate({}, false, 'Restart of Fully must not replay old active call');
assertGate({event_id:10}, false, 'Repeated polling must not ding');
assertGate({event_id:11,doctor_call_event_id:'manual-event-11'}, true, 'New explicit doctor call must ring');
assertGate({event_id:10}, false, 'Stale response must not replay bell');
assertGate({event_id:11}, false, 'Same explicit event never rings twice');
assertGate({event_id:12,doctor_call_event_id:''}, false, 'No verified doctor token means no live chime');
assertGate({event_id:13,history_online:false}, false, 'Disconnected Historia does not ring');
assertGate({event_id:14,mode:'attending'}, false, 'Opening a chart is silent');
assertGate({event_id:15,doctor_call_event_id:'manual-event-15'}, true, 'Next explicit call still rings');
assertGate({display_mode:'test',event_id:3,doctor_call_event_id:''}, false, 'Switching to test must be silent');
assertGate({display_mode:'test',event_id:4,doctor_call_event_id:''}, true, 'New simulated call must ring in test mode');
assertGate({display_mode:'live',event_id:15}, false, 'Returning to live must never replay old bell');
assertGate({display_mode:'live',event_id:16,doctor_call_event_id:'manual-event-16'}, true, 'New live call after mode change must ring');
assertGate({tv_boot_id:'server-B',event_id:1}, false, 'Reception restart must reset counter silently');
assertGate({tv_boot_id:'server-B',event_id:2,doctor_call_event_id:'manual-event-B2'}, true, 'New call after Reception restart must ring');
assertGate({tv_boot_id:'server-B',event_id:2}, false, 'Repeated call after restart must remain silent');

const serviceSource = fs.readFileSync('recepcion/app/reception_tv_service.py','utf8');
const turnsSource = fs.readFileSync('recepcion/app/reception_tv_turns.py','utf8');
if (!serviceSource.includes('self.tv_boot_id = uuid.uuid4().hex') ||
    !serviceSource.includes('out["tv_boot_id"] = self.tv_boot_id'))
  throw Error('New Reception TV boot ID missing from snapshots');
if (!serviceSource.includes('"doctor_call_event_id": ""') ||
    !turnsSource.includes('self.live["doctor_call_event_id"] = event_id'))
  throw Error('Doctor-only event token missing');
if (!display.includes("let settled=false") || !display.includes("pollPending=false"))
  throw Error('Async old WebView polling must be serialized and settled once');

console.log('TV_DISPLAY_AND_VOICE_JAVASCRIPT_OK');
