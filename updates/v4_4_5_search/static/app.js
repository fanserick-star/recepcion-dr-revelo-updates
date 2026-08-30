// v4.4.5 — Restaurar búsqueda dentro de Nueva atención y limpiar acciones externas.
(() => {
  'use strict';

  let attentionPatientSearchTimerV445 = null;
  let attentionPatientSearchSeqV445 = 0;

  function injectAttentionSearchStylesV445() {
    if (document.querySelector('#attentionSearchHotfixV445')) return;
    const style = document.createElement('style');
    style.id = 'attentionSearchHotfixV445';
    style.textContent = `
      .attention-with-search{display:flex;flex-direction:column;gap:12px}
      .attention-search-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}
      .attention-search-head .primary{white-space:nowrap}
      .attention-patient-search{border:1px solid #d7e2f0;border-left:4px solid #77aef3;border-radius:14px;background:#f8fbff;padding:12px 14px}
      .attention-patient-search label{display:block;font-size:12px;font-weight:800;color:#26456d;margin-bottom:6px}
      .attention-patient-search input{width:100%;box-sizing:border-box;border:1px solid #85b3f2;border-radius:12px;background:#fff;padding:12px 14px;font-size:15px;font-weight:700;color:#172f50;outline:none}
      .attention-patient-search input:focus{border-color:#2f7de1;box-shadow:0 0 0 3px rgba(47,125,225,.12)}
      .attention-patient-search .attention-search-help{display:block;margin-top:6px;font-size:11px;color:#657892}
      .attention-patient-results{display:grid;gap:7px;margin-top:8px;max-height:210px;overflow:auto}
      .attention-patient-results.hidden{display:none}
      .attention-search-row{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;border:1px solid #dbe5f1;border-radius:11px;background:#fff;padding:9px 11px;text-align:left;cursor:pointer}
      .attention-search-row:hover,.attention-search-row:focus{border-color:#78aef1;background:#f4f9ff}
      .attention-search-row-main{display:flex;flex-direction:column;gap:2px;min-width:0}
      .attention-search-row-main b{font-size:13px;color:#152f51;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .attention-search-row-main small{font-size:10px;color:#64748b}
      .attention-search-use{font-size:11px;font-weight:800;color:#1264c3;white-space:nowrap}
      .attention-search-empty{padding:8px 4px;font-size:11px;color:#6b7c92}
      @media(max-width:760px){.attention-search-head{flex-direction:column}.attention-search-head .primary{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function attentionModalV445() {
    return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(box =>
      [...box.querySelectorAll('h1,h2,h3')].some(h => String(h.textContent || '').replace(/\s+/g,' ').trim().toLowerCase() === 'nueva atención')
    ) || null;
  }

  function cleanAttentionExternalActionsV445() {
    const box = attentionModalV445();
    if (!box) return;
    [...box.querySelectorAll('button,a')].forEach(el => {
      const text = String(el.textContent || '').replace(/\s+/g,' ').trim().toLowerCase();
      const onclick = String(el.getAttribute('onclick') || '').toLowerCase();
      const href = String(el.getAttribute('href') || '').toLowerCase();
      if (text.includes('facturero móvil') || text.includes('facturero movil') || onclick.includes("openexternalapp('facturero')") || onclick.includes('openexternalapp("facturero")') || href.includes('factureromovil')) {
        el.remove();
      }
    });
  }

  function attentionSearchResultHtmlV445(p) {
    if (typeof isHistoricalPatient === 'function' && isHistoricalPatient(p)) {
      const years = typeof historicalYears === 'function' ? historicalYears(p) : '2020–2025';
      return `<button type="button" class="attention-search-row" onclick="useAttentionHistoricalV445(${Number(p.historical_id)})"><span class="attention-search-row-main"><b>${esc(p.nombre || '')}</b><small>HISTÓRICO ${esc(years)}${p.cedula ? ` · ${esc(p.cedula)}` : ''}${p.celular ? ` · ${esc(formatPhoneValue(p.celular))}` : ''}</small></span><span class="attention-search-use">Usar ficha →</span></button>`;
    }
    return `<button type="button" class="attention-search-row" onclick="useAttentionPatientV445(${Number(p.id)})"><span class="attention-search-row-main"><b>${esc(p.nombre || '')}</b><small>${p.cedula ? `Cédula ${esc(p.cedula)}` : 'Sin cédula'} · ${p.celular ? esc(formatPhoneValue(p.celular)) : 'Sin celular'}</small></span><span class="attention-search-use">Atender →</span></button>`;
  }

  window.useAttentionPatientV445 = async function(patientId) {
    try {
      await attentionFor(Number(patientId));
      setTimeout(cleanAttentionExternalActionsV445, 0);
      setTimeout(cleanAttentionExternalActionsV445, 80);
      setTimeout(cleanAttentionExternalActionsV445, 220);
    } catch (e) {
      alert(e.message || 'No se pudo abrir la atención.');
    }
  };

  window.useAttentionHistoricalV445 = async function(historicalId) {
    try {
      await activateHistoricalPatient(Number(historicalId), 'attention');
      setTimeout(cleanAttentionExternalActionsV445, 0);
      setTimeout(cleanAttentionExternalActionsV445, 80);
      setTimeout(cleanAttentionExternalActionsV445, 220);
    } catch (e) {
      alert(e.message || 'No se pudo abrir la ficha histórica.');
    }
  };

  window.searchAttentionPatientV445 = function(immediate = false) {
    clearTimeout(attentionPatientSearchTimerV445);
    const run = async () => {
      const input = document.querySelector('#attentionPatientSearchV445');
      const box = document.querySelector('#attentionPatientResultsV445');
      if (!input || !box) return;

      const q = String(input.value || '').trim().toUpperCase();
      if (q.length < 2) {
        box.classList.add('hidden');
        box.innerHTML = '';
        return;
      }

      const seq = ++attentionPatientSearchSeqV445;
      box.classList.remove('hidden');
      box.innerHTML = '<div class="attention-search-empty">Buscando paciente…</div>';

      try {
        const rows = await api('/api/patients?q=' + encodeURIComponent(q) + '&limit=18');
        if (seq !== attentionPatientSearchSeqV445) return;
        const usable = (rows || []).slice(0, 14);
        box.innerHTML = usable.length
          ? usable.map(attentionSearchResultHtmlV445).join('')
          : '<div class="attention-search-empty">No encontramos coincidencias. Revisa el nombre o usa “Paciente nuevo”.</div>';
      } catch (e) {
        if (seq !== attentionPatientSearchSeqV445) return;
        box.innerHTML = `<div class="attention-search-empty">${esc(e.message || 'No se pudo buscar.')}</div>`;
      }
    };
    if (immediate) return run();
    attentionPatientSearchTimerV445 = setTimeout(run, 160);
  };

  function installNewAttentionV445() {
    injectAttentionSearchStylesV445();

    window.newAttention = async function() {
      currentPatientSource = 'general';
      attentionWeekAnchor = toISO(new Date());

      openModal(`<div class="new-attention-start-modal attention-with-search">
        <div class="modal-form-heading attention-search-head">
          <div><h2>Nueva atención</h2><p>Confirma el paciente y registra la atención realizada.</p></div>
          <button type="button" class="primary" onclick="newPatient(true)">＋ Paciente nuevo</button>
        </div>

        <div class="attention-patient-search">
          <label for="attentionPatientSearchV445">Buscar paciente</label>
          <input id="attentionPatientSearchV445" class="uppercase-search" type="search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="APELLIDOS Y NOMBRES, CÉDULA O CELULAR" oninput="upperSearchInput(this);searchAttentionPatientV445()">
          <small class="attention-search-help">Puedes escribir nombre, apellido, cédula o celular · mínimo 2 caracteres.</small>
          <div id="attentionPatientResultsV445" class="attention-patient-results hidden"></div>
        </div>

        <div id="attentionWeekBlock" class="attention-week-block">
          <div class="attention-week-head">
            <div><b>Agenda</b><span>Jueves, viernes y sábado</span></div>
            <div class="attention-week-nav">
              <button type="button" title="Semana anterior" onclick="moveAttentionWeek(-1)">‹</button>
              <button type="button" class="week-today" onclick="currentAttentionWeek()">Esta semana</button>
              <button type="button" title="Semana siguiente" onclick="moveAttentionWeek(1)">›</button>
            </div>
            <div class="attention-week-range"><strong id="attentionWeekLabel"></strong><span id="attentionWeekConflict" class="attention-week-conflict-note hidden"></span></div>
          </div>
          <div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda…</div></div>
        </div>
      </div>`);

      loadAttentionWeek(false, attentionWeekAnchor);
      setTimeout(() => document.querySelector('#attentionPatientSearchV445')?.focus(), 70);
    };

    const observer = new MutationObserver(() => cleanAttentionExternalActionsV445());
    observer.observe(document.documentElement, {childList:true, subtree:true});
    document.addEventListener('click', () => {
      setTimeout(cleanAttentionExternalActionsV445, 0);
      setTimeout(cleanAttentionExternalActionsV445, 90);
    }, true);
  }

  function loadStableBaseV445() {
    const script = document.createElement('script');
    script.src = '/static/app_base.js?v=4.4.5';
    script.async = false;
    script.onload = installNewAttentionV445;
    script.onerror = () => {
      console.error('No se pudo cargar la base estable de Recepción.');
    };
    document.head.appendChild(script);
  }

  loadStableBaseV445();
})();
