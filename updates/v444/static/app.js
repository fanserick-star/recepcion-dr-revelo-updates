// v4.4.4 — Hotfix buscador de Atención/Inicio.
// Carga la base estable v4.4.3 con un nombre nuevo para evitar cualquier JS viejo en caché
// y después normaliza el buscador superior como texto libre (nombre/cédula/celular/correo).
(() => {
  'use strict';

  function normalizeGlobalPatientSearch() {
    const current = document.querySelector('#globalSearch');
    if (!current) return;

    // Sustituimos solo el input para descartar listeners viejos que pudieran
    // convertir la búsqueda en "solo cédula". Conservamos valor, clases e id.
    const input = current.cloneNode(true);
    const value = String(current.value || '');
    input.removeAttribute('oninput');
    input.removeAttribute('onfocus');
    input.removeAttribute('pattern');
    input.removeAttribute('maxlength');
    input.removeAttribute('inputmode');
    input.type = 'search';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = 'Buscar paciente por nombre, cédula, celular o correo…';
    input.value = value;
    current.replaceWith(input);

    const wrap = input.closest('.global-search-wrap') || input.parentElement;
    if (wrap) {
      wrap.querySelectorAll('label, small, span, [data-search-label]').forEach(el => {
        const t = String(el.textContent || '').trim().toUpperCase();
        if (t === 'CÉDULA' || t === 'CEDULA') el.textContent = 'PACIENTE';
      });
    }

    const runSearch = (force = false) => {
      try {
        if (typeof upperSearchInput === 'function') upperSearchInput(input);
        else {
          const start = input.selectionStart, end = input.selectionEnd;
          input.value = String(input.value || '').toUpperCase();
          try { if (start != null) input.setSelectionRange(start, end); } catch {}
        }
        if (typeof globalSearchPatients === 'function') globalSearchPatients(force);
      } catch (err) {
        console.error('Hotfix búsqueda paciente:', err);
      }
    };

    input.addEventListener('input', () => runSearch(false));
    input.addEventListener('focus', () => runSearch(true));
  }

  function loadStableBase() {
    const script = document.createElement('script');
    script.src = '/static/app_base.js?v=4.4.4';
    script.async = false;
    script.onload = () => {
      normalizeGlobalPatientSearch();
      // Algunas vistas restauran placeholder al navegar; lo reafirmamos sin
      // crear peticiones ni temporizadores permanentes.
      document.addEventListener('click', () => {
        const input = document.querySelector('#globalSearch');
        if (input) input.placeholder = 'Buscar paciente por nombre, cédula, celular o correo…';
      }, true);
    };
    script.onerror = () => {
      console.error('No se pudo cargar la base estable del programa.');
      const input = document.querySelector('#globalSearch');
      if (input) input.placeholder = 'No se pudo cargar el buscador · reinicia Recepción';
    };
    document.head.appendChild(script);
  }

  loadStableBase();
})();
