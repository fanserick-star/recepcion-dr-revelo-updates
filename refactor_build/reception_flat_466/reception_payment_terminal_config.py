from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import json
import os
import urllib.error
import urllib.parse
import urllib.request
previous = _rf_layers['app_patch_4505']
core = previous.core
app = previous.app
APP_VERSION = '4.5.6'
_mod = previous
_seen = set()
for _ in range(140):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
DP_ENV = {'provider': 'RP_DATAPHONE_PROVIDER', 'model': 'RP_DATAPHONE_MODEL', 'environment': 'RP_DATAPHONE_ENVIRONMENT', 'api_base_url': 'RP_DATAPHONE_API_BASE_URL', 'api_key': 'RP_DATAPHONE_API_KEY', 'merchant_id': 'RP_DATAPHONE_MERCHANT_ID', 'terminal_id': 'RP_DATAPHONE_TERMINAL_ID', 'auth_header': 'RP_DATAPHONE_AUTH_HEADER', 'auth_scheme': 'RP_DATAPHONE_AUTH_SCHEME', 'health_path': 'RP_DATAPHONE_HEALTH_PATH', 'create_payment_path': 'RP_DATAPHONE_CREATE_PAYMENT_PATH', 'status_path_template': 'RP_DATAPHONE_STATUS_PATH_TEMPLATE', 'create_body_template': 'RP_DATAPHONE_CREATE_BODY_TEMPLATE', 'response_id_field': 'RP_DATAPHONE_RESPONSE_ID_FIELD', 'response_status_field': 'RP_DATAPHONE_RESPONSE_STATUS_FIELD', 'approved_values': 'RP_DATAPHONE_APPROVED_VALUES', 'declined_values': 'RP_DATAPHONE_DECLINED_VALUES', 'webhook_public_url': 'RP_DATAPHONE_WEBHOOK_PUBLIC_URL', 'webhook_secret': 'RP_DATAPHONE_WEBHOOK_SECRET'}
DEFAULTS = {'provider': 'BENDO', 'model': 'Bendo Smart', 'environment': 'PRODUCCION', 'api_base_url': '', 'api_key': '', 'merchant_id': '', 'terminal_id': '', 'auth_header': 'Authorization', 'auth_scheme': 'Bearer', 'health_path': '', 'create_payment_path': '', 'status_path_template': '', 'create_body_template': '{"amount":"{amount}","currency":"USD","reference":"{reference}","merchant_id":"{merchant_id}","terminal_id":"{terminal_id}"}', 'response_id_field': 'id', 'response_status_field': 'status', 'approved_values': 'APPROVED,COMPLETED,SUCCESS', 'declined_values': 'DECLINED,FAILED,REJECTED,CANCELLED', 'webhook_public_url': '', 'webhook_secret': ''}

class V4506DataphoneConfigIn(core.BaseModel):
    provider: str = 'BENDO'
    model: str = 'Bendo Smart'
    environment: str = 'PRODUCCION'
    api_base_url: str = ''
    api_key: str | None = None
    merchant_id: str = ''
    terminal_id: str = ''
    auth_header: str = 'Authorization'
    auth_scheme: str = 'Bearer'
    health_path: str = ''
    create_payment_path: str = ''
    status_path_template: str = ''
    create_body_template: str = DEFAULTS['create_body_template']
    response_id_field: str = 'id'
    response_status_field: str = 'status'
    approved_values: str = DEFAULTS['approved_values']
    declined_values: str = DEFAULTS['declined_values']
    webhook_public_url: str = ''
    webhook_secret: str | None = None

def _dp_value(name: str) -> str:
    env = DP_ENV[name]
    raw = str(os.getenv(env) or '').strip()
    if raw:
        return raw
    return str(DEFAULTS.get(name, '') or '')

def _dp_mask(value: str) -> str:
    raw = str(value or '')
    if not raw:
        return ''
    if len(raw) <= 6:
        return '•' * len(raw)
    return raw[:3] + '•' * max(4, len(raw) - 6) + raw[-3:]

def _dp_clean_url(value: object, *, allow_blank: bool=True) -> str:
    raw = str(value or '').strip().rstrip('/')
    if not raw and allow_blank:
        return ''
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        raise core.HTTPException(400, 'La URL de la API no es válida.')
    if parsed.scheme.lower() != 'https' or not parsed.netloc:
        raise core.HTTPException(400, 'La API del datáfono debe usar una dirección HTTPS válida.')
    return raw

def _dp_path(value: object, *, allow_template: bool=False) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    if raw.startswith('http://') or raw.startswith('https://'):
        raise core.HTTPException(400, 'En las rutas escribe solo /ruta; la URL base se configura aparte.')
    if not raw.startswith('/'):
        raw = '/' + raw
    if len(raw) > 500:
        raise core.HTTPException(400, 'La ruta es demasiado larga.')
    if not allow_template and '{' in raw:
        raise core.HTTPException(400, 'Esta ruta no admite variables.')
    return raw

def _dp_payload() -> dict:
    api_key = _dp_value('api_key')
    webhook_secret = _dp_value('webhook_secret')
    base_url = _dp_value('api_base_url')
    create_path = _dp_value('create_payment_path')
    status_path = _dp_value('status_path_template')
    merchant = _dp_value('merchant_id')
    terminal = _dp_value('terminal_id')
    credentials_ready = bool(base_url and api_key)
    identity_ready = bool(merchant or terminal)
    contract_ready = bool(create_path and status_path)
    return {'provider': _dp_value('provider') or 'BENDO', 'model': _dp_value('model') or 'Bendo Smart', 'environment': _dp_value('environment') or 'PRODUCCION', 'api_base_url': base_url, 'api_key_saved': bool(api_key), 'api_key_masked': _dp_mask(api_key), 'merchant_id': merchant, 'terminal_id': terminal, 'auth_header': _dp_value('auth_header') or 'Authorization', 'auth_scheme': _dp_value('auth_scheme') or 'Bearer', 'health_path': _dp_value('health_path'), 'create_payment_path': create_path, 'status_path_template': status_path, 'create_body_template': _dp_value('create_body_template'), 'response_id_field': _dp_value('response_id_field') or 'id', 'response_status_field': _dp_value('response_status_field') or 'status', 'approved_values': _dp_value('approved_values'), 'declined_values': _dp_value('declined_values'), 'webhook_public_url': _dp_value('webhook_public_url'), 'webhook_secret_saved': bool(webhook_secret), 'webhook_secret_masked': _dp_mask(webhook_secret), 'credentials_ready': credentials_ready, 'identity_ready': identity_ready, 'contract_ready': contract_ready, 'automatic_charge_ready': bool(credentials_ready and identity_ready and contract_ready), 'card_manual_entry': False, 'public_docs_confirm_terminal_push': False, 'official_api_notification_expected': True, 'requires_official_contract': not contract_ready, 'schema_version': 1}

def _dp_headers() -> dict:
    headers = {'Accept': 'application/json', 'User-Agent': f'Recepcion-Dr-Revelo/{APP_VERSION}', 'Cache-Control': 'no-cache'}
    key = _dp_value('api_key')
    if key:
        header = _dp_value('auth_header') or 'Authorization'
        scheme = _dp_value('auth_scheme')
        headers[header] = (scheme + ' ' + key).strip() if scheme else key
    merchant = _dp_value('merchant_id')
    terminal = _dp_value('terminal_id')
    if merchant:
        headers['X-Merchant-Id'] = merchant
    if terminal:
        headers['X-Terminal-Id'] = terminal
    return headers

def _dp_render_template(template: str, *, amount: float, reference: str) -> dict:
    raw = str(template or DEFAULTS['create_body_template'])
    replacements = {'{amount}': f'{float(amount):.2f}', '{reference}': str(reference or ''), '{merchant_id}': _dp_value('merchant_id'), '{terminal_id}': _dp_value('terminal_id')}
    for key, value in replacements.items():
        raw = raw.replace(key, value)
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise core.HTTPException(400, 'La plantilla JSON de creación no es válida: ' + str(exc))
    if not isinstance(data, dict):
        raise core.HTTPException(400, 'La plantilla de creación debe ser un objeto JSON.')
    return data
try:

    @app.get('/api/v4506/dataphone/config')
    def v4506_dataphone_config(request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Configuración disponible solo en esta PC.')
        return {'ok': True, **_dp_payload()}

    @app.post('/api/v4506/dataphone/config')
    def v4506_save_dataphone_config(data: V4506DataphoneConfigIn, request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Configuración disponible solo en esta PC.')
        provider = ' '.join(str(data.provider or 'BENDO').strip().upper().split())
        model = ' '.join(str(data.model or 'Bendo Smart').strip().split())
        environment = ' '.join(str(data.environment or 'PRODUCCION').strip().upper().split())
        if environment not in {'PRODUCCION', 'SANDBOX', 'PRUEBAS'}:
            raise core.HTTPException(400, 'Entorno inválido.')
        base_url = _dp_clean_url(data.api_base_url)
        health_path = _dp_path(data.health_path)
        create_path = _dp_path(data.create_payment_path)
        status_path = _dp_path(data.status_path_template, allow_template=True)
        auth_header = str(data.auth_header or 'Authorization').strip()
        auth_scheme = str(data.auth_scheme or 'Bearer').strip()
        merchant_id = str(data.merchant_id or '').strip()
        terminal_id = str(data.terminal_id or '').strip()
        webhook_url = _dp_clean_url(data.webhook_public_url, allow_blank=True)
        template = str(data.create_body_template or DEFAULTS['create_body_template']).strip()
        _dp_render_template(template, amount=40.0, reference='TEST-CONFIG')
        values = {DP_ENV['provider']: provider, DP_ENV['model']: model, DP_ENV['environment']: environment, DP_ENV['api_base_url']: base_url, DP_ENV['merchant_id']: merchant_id, DP_ENV['terminal_id']: terminal_id, DP_ENV['auth_header']: auth_header, DP_ENV['auth_scheme']: auth_scheme, DP_ENV['health_path']: health_path, DP_ENV['create_payment_path']: create_path, DP_ENV['status_path_template']: status_path, DP_ENV['create_body_template']: template, DP_ENV['response_id_field']: str(data.response_id_field or 'id').strip(), DP_ENV['response_status_field']: str(data.response_status_field or 'status').strip(), DP_ENV['approved_values']: str(data.approved_values or DEFAULTS['approved_values']).strip(), DP_ENV['declined_values']: str(data.declined_values or DEFAULTS['declined_values']).strip(), DP_ENV['webhook_public_url']: webhook_url}
        new_key = str(data.api_key or '').strip()
        if new_key:
            values[DP_ENV['api_key']] = new_key
        new_webhook_secret = str(data.webhook_secret or '').strip()
        if new_webhook_secret:
            values[DP_ENV['webhook_secret']] = new_webhook_secret
        core._upsert_local_env(values)
        for env_name, value in values.items():
            os.environ[env_name] = value
        return {'ok': True, 'message': 'Configuración del datáfono guardada en esta PC.', **_dp_payload()}

    @app.post('/api/v4506/dataphone/validate')
    def v4506_validate_dataphone(request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Disponible solo en esta PC.')
        cfg = _dp_payload()
        checks = [{'key': 'device', 'ok': bool(cfg['model']), 'label': 'Equipo', 'detail': cfg['model'] or 'Falta modelo'}, {'key': 'api', 'ok': bool(cfg['api_base_url'] and cfg['api_key_saved']), 'label': 'Credenciales API', 'detail': 'Guardadas' if cfg['api_base_url'] and cfg['api_key_saved'] else 'Pendientes de Bendo'}, {'key': 'identity', 'ok': bool(cfg['merchant_id'] or cfg['terminal_id']), 'label': 'Comercio / terminal', 'detail': 'Identificado' if cfg['merchant_id'] or cfg['terminal_id'] else 'Pendiente de vinculación'}, {'key': 'contract', 'ok': bool(cfg['create_payment_path'] and cfg['status_path_template']), 'label': 'Contrato de cobro automático', 'detail': 'Rutas configuradas' if cfg['create_payment_path'] and cfg['status_path_template'] else 'Pendiente de documentación oficial'}]
        return {'ok': True, 'ready': all((x['ok'] for x in checks)), 'checks': checks, 'message': 'Todo listo para activar el cobro automático.' if all((x['ok'] for x in checks)) else 'La estructura está preparada; faltan datos oficiales del terminal/API.'}

    @app.post('/api/v4506/dataphone/test')
    def v4506_test_dataphone(request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Disponible solo en esta PC.')
        base = _dp_value('api_base_url')
        key = _dp_value('api_key')
        health = _dp_value('health_path')
        if not base or not key:
            raise core.HTTPException(400, 'Primero guarda la URL y credencial API entregadas por Bendo.')
        if not health:
            return {'ok': True, 'authenticated': False, 'network_tested': False, 'message': 'Credenciales guardadas. Falta la ruta oficial de prueba/estado para comprobar la API sin generar un cobro.'}
        url = base.rstrip('/') + '/' + health.lstrip('/')
        req = urllib.request.Request(url, headers=_dp_headers(), method='GET')
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                code = int(getattr(response, 'status', 200) or 200)
                response.read(64000)
            return {'ok': 200 <= code < 300, 'authenticated': 200 <= code < 300, 'network_tested': True, 'http_status': code, 'message': 'Bendo respondió correctamente. No se generó ningún cobro.'}
        except urllib.error.HTTPError as exc:
            raise core.HTTPException(502, 'Bendo respondió HTTP ' + str(exc.code) + '. Revisa credenciales o la ruta de prueba.')
        except Exception as exc:
            raise core.HTTPException(502, 'No se pudo comprobar la API: ' + str(exc)[:180])

    @app.post('/api/v4506/dataphone/payment-preview')
    def v4506_dataphone_payment_preview(amount: float, reference: str, request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Disponible solo en esta PC.')
        if amount <= 0:
            raise core.HTTPException(400, 'El valor debe ser mayor a cero.')
        body = _dp_render_template(_dp_value('create_body_template'), amount=amount, reference=reference)
        return {'ok': True, 'sent': False, 'amount': round(float(amount), 2), 'reference': str(reference or ''), 'endpoint': _dp_value('api_base_url').rstrip('/') + '/' + _dp_value('create_payment_path').lstrip('/') if _dp_value('api_base_url') and _dp_value('create_payment_path') else None, 'body_preview': body, 'message': 'Vista previa solamente. No se envió ningún cobro al datáfono.'}
    V4506_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.6"!important;\n  font-size:9px!important;\n  line-height:1!important;\n  font-weight:850!important\n}\n\n/* Corrige la Consulta: v4.5.5 había compactado TODAS las service-card. */\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"],\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"]{\n  min-height:64px!important;\n  height:auto!important;\n  padding:12px 40px!important;\n  border-radius:13px!important;\n  display:flex!important;\n  align-items:center!important\n}\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] b,\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] strong,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] b,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] strong{\n  font-size:12px!important;\n  line-height:1.15!important\n}\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] .service-price,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] .service-price{\n  font-size:11px!important\n}\n\n/* Solo los procedimientos quedan compactos. */\n.attention-form-modal .procedures-service-section .service-card[data-service]{\n  min-height:48px!important;\n  padding:7px 8px!important;\n  border-radius:9px!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service] b,\n.attention-form-modal .procedures-service-section .service-card[data-service] strong{\n  font-size:9px!important;\n  line-height:1.1!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service] .service-price{\n  font-size:9px!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service] small{\n  font-size:7px!important\n}\n\n/* Forma de pago: prioridad visual mayor. */\n.v4504-pay{\n  padding:14px!important\n}\n.v4504-pay-head b{\n  font-size:16px!important\n}\n.v4504-pay-head small{\n  font-size:9.5px!important\n}\n.v4504-pay-option{\n  min-height:61px!important;\n  padding:10px 11px!important\n}\n.v4504-pay-option>span{\n  font-size:20px!important\n}\n.v4504-pay-option>b,\n.v4504-pay-option[data-mode="TARJETA"] b::after{\n  font-size:13px!important\n}\n.v4504-pay-option>small,\n.v4504-pay-option[data-mode="TARJETA"] small::after{\n  font-size:9px!important\n}\n\n/* Configuración Bendo Smart */\n.v4506-dp-section{\n  max-width:980px!important\n}\n.v4506-dp-hero{\n  display:grid;\n  grid-template-columns:minmax(0,1fr) auto;\n  gap:16px;\n  align-items:center;\n  padding:16px 17px;\n  border:1px solid #d9e4ef;\n  border-radius:15px;\n  background:linear-gradient(135deg,#f7fbff 0%,#eef6ff 100%);\n  margin-bottom:12px\n}\n.v4506-dp-hero h3{\n  margin:0 0 4px;\n  font-size:18px;\n  color:#223d5a\n}\n.v4506-dp-hero p{\n  margin:0;\n  color:#647991;\n  font-size:11px;\n  line-height:1.4\n}\n.v4506-dp-pill{\n  padding:6px 10px;\n  border-radius:999px;\n  font-size:9px;\n  font-weight:900;\n  background:#fff3d6;\n  color:#8a6012;\n  border:1px solid #ead49f;\n  white-space:nowrap\n}\n.v4506-dp-pill.ready{\n  background:#e7f7ed;\n  color:#216943;\n  border-color:#b9dfc6\n}\n.v4506-dp-grid{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:10px\n}\n.v4506-dp-card{\n  border:1px solid #dfe7ef;\n  border-radius:13px;\n  background:#fff;\n  padding:13px 14px\n}\n.v4506-dp-card.full{\n  grid-column:1/-1\n}\n.v4506-dp-card h4{\n  margin:0 0 3px;\n  color:#304c69;\n  font-size:13px\n}\n.v4506-dp-card>p{\n  margin:0 0 10px;\n  color:#75879a;\n  font-size:9px;\n  line-height:1.35\n}\n.v4506-dp-fields{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:9px\n}\n.v4506-dp-field{\n  min-width:0\n}\n.v4506-dp-field.full{\n  grid-column:1/-1\n}\n.v4506-dp-field label{\n  display:block;\n  margin:0 0 4px;\n  color:#6e8094;\n  font-size:8px;\n  font-weight:900;\n  text-transform:uppercase;\n  letter-spacing:.04em\n}\n.v4506-dp-field input,\n.v4506-dp-field select,\n.v4506-dp-field textarea{\n  width:100%!important;\n  min-height:35px!important;\n  font-size:10px!important;\n  border-radius:9px!important\n}\n.v4506-dp-field textarea{\n  min-height:80px!important;\n  font-family:Consolas,monospace!important;\n  resize:vertical\n}\n.v4506-dp-actions{\n  display:flex;\n  gap:7px;\n  flex-wrap:wrap;\n  margin-top:11px\n}\n.v4506-dp-actions button{\n  min-height:34px!important;\n  border-radius:9px!important\n}\n.v4506-dp-checks{\n  display:grid;\n  grid-template-columns:repeat(4,minmax(0,1fr));\n  gap:7px\n}\n.v4506-dp-check{\n  padding:9px 10px;\n  border:1px solid #e1e7ee;\n  border-radius:10px;\n  background:#fbfcfe\n}\n.v4506-dp-check b{\n  display:block;\n  font-size:9px;\n  color:#3f5972\n}\n.v4506-dp-check small{\n  display:block;\n  margin-top:3px;\n  font-size:8px;\n  color:#7a8b9e;\n  line-height:1.25\n}\n.v4506-dp-check.ok{\n  border-color:#bfe0ca;\n  background:#f2faf5\n}\n.v4506-dp-check.ok b{\n  color:#276846\n}\n.v4506-dp-info{\n  margin-top:10px;\n  padding:9px 11px;\n  border-radius:10px;\n  background:#f4f7fa;\n  color:#5f7388;\n  font-size:9px;\n  line-height:1.4\n}\n.v4506-dp-info strong{\n  color:#34546f\n}\n.v4506-dp-status{\n  margin-top:9px;\n  min-height:18px;\n  font-size:9px;\n  color:#63788f\n}\n.v4506-dp-status.ok{color:#2c744e}\n.v4506-dp-status.err{color:#a4413b}\n@media(max-width:780px){\n  .v4506-dp-grid,.v4506-dp-fields{grid-template-columns:1fr}\n  .v4506-dp-checks{grid-template-columns:repeat(2,minmax(0,1fr))}\n  .v4506-dp-hero{grid-template-columns:1fr}\n}\n'
    V4506_JS = '\n;(()=>{\n  if(window.__v4506DataphoneConfig)return;\n  window.__v4506DataphoneConfig=true;\n  const VERSION=\'4.5.6\';\n  const q=(s,r=document)=>r.querySelector(s);\n  const qa=(s,r=document)=>[...r.querySelectorAll(s)];\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\n    \'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'\n  }[c]));\n\n  async function call(url,opt={}){\n    if(typeof window.api===\'function\')return window.api(url,opt);\n    const response=await fetch(url,{\n      headers:{\'Content-Type\':\'application/json\',...(opt.headers||{})},\n      ...opt\n    });\n    const data=await response.json().catch(()=>({}));\n    if(!response.ok)throw Error(data.detail||data.message||\'Error\');\n    return data;\n  }\n\n  function ensureTab(){\n    const config=q(\'#config\');\n    const tabs=q(\'.config-tabs\',config);\n    if(!config||!tabs)return null;\n\n    let section=q(\'[data-config-section="dataphone"]\',config);\n    if(!section){\n      section=document.createElement(\'div\');\n      section.dataset.configSection=\'dataphone\';\n      section.className=\'config-section hidden v4506-dp-section\';\n      const fact=q(\'[data-config-section="facturacion"]\',config);\n      (fact||config.lastElementChild)?.after?.(section);\n      if(!section.parentElement)config.appendChild(section);\n    }\n\n    let button=q(\'[data-config-tab="dataphone"]\',tabs);\n    if(!button){\n      button=document.createElement(\'button\');\n      button.type=\'button\';\n      button.dataset.configTab=\'dataphone\';\n      button.textContent=\'Datáfono\';\n      const factButton=q(\'[data-config-tab="facturacion"]\',tabs);\n      factButton?.after(button)||tabs.appendChild(button);\n      button.onclick=()=>{\n        window.showConfigTab?.(\'dataphone\',button);\n        loadConfig();\n      };\n    }\n    return section;\n  }\n\n  function field(id,label,value=\'\',type=\'text\',extra=\'\'){\n    return \'<div class="v4506-dp-field \'+(extra.includes(\'full\')?\'full\':\'\')+\'">\'\n      +\'<label for="\'+id+\'">\'+label+\'</label>\'\n      +\'<input id="\'+id+\'" type="\'+type+\'" value="\'+esc(value)+\'" \'+extra.replace(\'full\',\'\')+\'>\'\n      +\'</div>\';\n  }\n\n  function render(data){\n    const section=ensureTab();\n    if(!section)return;\n\n    const ready=!!data.automatic_charge_ready;\n    section.innerHTML=\n      \'<div class="v4506-dp-hero">\'\n      +\'<div><h3>💳 Bendo Smart</h3>\'\n      +\'<p>Integración preparada para que Recepción envíe el valor al datáfono y reciba el resultado automáticamente cuando Bendo entregue el contrato técnico y credenciales.</p></div>\'\n      +\'<span class="v4506-dp-pill \'+(ready?\'ready\':\'\')+\'">\'\n      +(ready?\'LISTO PARA ACTIVAR\':\'ESPERANDO DATOS DE BENDO\')\n      +\'</span></div>\'\n\n      +\'<div id="v4506DpChecks" class="v4506-dp-checks"></div>\'\n\n      +\'<div class="v4506-dp-grid" style="margin-top:10px">\'\n      +\'<section class="v4506-dp-card"><h4>Equipo y comercio</h4>\'\n      +\'<p>Estos datos identifican el terminal físico y la cuenta de Bendo.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpProvider\',\'Proveedor\',data.provider||\'BENDO\',\'text\',\'readonly\')\n      +field(\'dpModel\',\'Modelo\',data.model||\'Bendo Smart\')\n      +\'<div class="v4506-dp-field"><label>Entorno</label><select id="dpEnvironment">\'\n      +\'<option value="PRODUCCION" \'+(data.environment===\'PRODUCCION\'?\'selected\':\'\')+\'>Producción</option>\'\n      +\'<option value="SANDBOX" \'+(data.environment===\'SANDBOX\'?\'selected\':\'\')+\'>Sandbox</option>\'\n      +\'<option value="PRUEBAS" \'+(data.environment===\'PRUEBAS\'?\'selected\':\'\')+\'>Pruebas</option>\'\n      +\'</select></div>\'\n      +field(\'dpMerchant\',\'Merchant / comercio ID\',data.merchant_id||\'\')\n      +field(\'dpTerminal\',\'Terminal ID\',data.terminal_id||\'\')\n      +\'</div></section>\'\n\n      +\'<section class="v4506-dp-card"><h4>Credenciales API</h4>\'\n      +\'<p>Se guardan únicamente en el .env local de esta PC; nunca en Neon ni GitHub.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpBaseUrl\',\'API base URL\',data.api_base_url||\'\',\'url\',\'full placeholder="https://..."\')\n      +field(\'dpApiKey\',\'API key / token\',\'\',\'password\',\'placeholder="\'+(data.api_key_saved?\'Ya guardada · deja vacío para conservarla\':\'Pendiente\')+\'"\')\n      +field(\'dpAuthHeader\',\'Header\',data.auth_header||\'Authorization\')\n      +field(\'dpAuthScheme\',\'Esquema\',data.auth_scheme||\'Bearer\')\n      +field(\'dpHealthPath\',\'Ruta de prueba\',data.health_path||\'\',\'text\',\'full placeholder="/health o ruta oficial equivalente"\')\n      +\'</div></section>\'\n\n      +\'<section class="v4506-dp-card full"><h4>Contrato de cobro automático</h4>\'\n      +\'<p>Dejé la capa lista sin inventar rutas. Aquí solo se copian las rutas que Bendo entregue oficialmente.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpCreatePath\',\'Crear cobro\',data.create_payment_path||\'\',\'text\',\'placeholder="/..."\')\n      +field(\'dpStatusPath\',\'Consultar estado\',data.status_path_template||\'\',\'text\',\'placeholder="/payments/{transaction_id}"\')\n      +field(\'dpResponseId\',\'Campo ID respuesta\',data.response_id_field||\'id\')\n      +field(\'dpResponseStatus\',\'Campo estado respuesta\',data.response_status_field||\'status\')\n      +field(\'dpApproved\',\'Estados aprobados\',data.approved_values||\'APPROVED,COMPLETED,SUCCESS\')\n      +field(\'dpDeclined\',\'Estados rechazados\',data.declined_values||\'DECLINED,FAILED,REJECTED,CANCELLED\')\n      +\'<div class="v4506-dp-field full"><label>Plantilla JSON para crear cobro</label>\'\n      +\'<textarea id="dpBodyTemplate">\'+esc(data.create_body_template||\'\')+\'</textarea></div>\'\n      +\'</div></section>\'\n\n      +\'<section class="v4506-dp-card full"><h4>Notificación / webhook</h4>\'\n      +\'<p>Bendo establece la API como medio oficial de notificación de transacciones exitosas. Dejamos también preparado este bloque por si el contrato técnico usa webhook.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpWebhookUrl\',\'URL pública de callback\',data.webhook_public_url||\'\',\'url\',\'placeholder="https://..."\')\n      +field(\'dpWebhookSecret\',\'Webhook secret\',\'\',\'password\',\'placeholder="\'+(data.webhook_secret_saved?\'Ya guardado · deja vacío para conservarlo\':\'Pendiente\')+\'"\')\n      +\'</div></section>\'\n      +\'</div>\'\n\n      +\'<div class="v4506-dp-actions">\'\n      +\'<button id="dpSave" type="button" class="primary">Guardar configuración</button>\'\n      +\'<button id="dpValidate" type="button">✓ Validar estructura</button>\'\n      +\'<button id="dpTest" type="button">↻ Probar API sin cobrar</button>\'\n      +\'</div>\'\n      +\'<div class="v4506-dp-info">\'\n      +\'<strong>Automatización prevista:</strong> Recepción calcula el total → envía el cobro → Bendo Smart procesa la tarjeta → la API confirma el resultado → Recepción registra Débito/Crédito, autorización y estado. \'\n      +\'No se guardará número de tarjeta ni CVV.\'\n      +\'</div>\'\n      +\'<div id="dpStatus" class="v4506-dp-status"></div>\';\n\n    q(\'#dpSave\',section)?.addEventListener(\'click\',saveConfig);\n    q(\'#dpValidate\',section)?.addEventListener(\'click\',validateConfig);\n    q(\'#dpTest\',section)?.addEventListener(\'click\',testApi);\n    validateConfig(false);\n  }\n\n  function payload(){\n    return {\n      provider:q(\'#dpProvider\')?.value||\'BENDO\',\n      model:q(\'#dpModel\')?.value||\'Bendo Smart\',\n      environment:q(\'#dpEnvironment\')?.value||\'PRODUCCION\',\n      api_base_url:q(\'#dpBaseUrl\')?.value||\'\',\n      api_key:q(\'#dpApiKey\')?.value||\'\',\n      merchant_id:q(\'#dpMerchant\')?.value||\'\',\n      terminal_id:q(\'#dpTerminal\')?.value||\'\',\n      auth_header:q(\'#dpAuthHeader\')?.value||\'Authorization\',\n      auth_scheme:q(\'#dpAuthScheme\')?.value||\'Bearer\',\n      health_path:q(\'#dpHealthPath\')?.value||\'\',\n      create_payment_path:q(\'#dpCreatePath\')?.value||\'\',\n      status_path_template:q(\'#dpStatusPath\')?.value||\'\',\n      create_body_template:q(\'#dpBodyTemplate\')?.value||\'\',\n      response_id_field:q(\'#dpResponseId\')?.value||\'id\',\n      response_status_field:q(\'#dpResponseStatus\')?.value||\'status\',\n      approved_values:q(\'#dpApproved\')?.value||\'\',\n      declined_values:q(\'#dpDeclined\')?.value||\'\',\n      webhook_public_url:q(\'#dpWebhookUrl\')?.value||\'\',\n      webhook_secret:q(\'#dpWebhookSecret\')?.value||\'\'\n    };\n  }\n\n  function status(text,tone=\'\'){\n    const el=q(\'#dpStatus\');\n    if(!el)return;\n    el.className=\'v4506-dp-status \'+tone;\n    el.textContent=text||\'\';\n  }\n\n  async function loadConfig(){\n    try{\n      const data=await call(\'/api/v4506/dataphone/config\');\n      render(data);\n    }catch(error){\n      status(error?.message||String(error),\'err\');\n    }\n  }\n\n  async function saveConfig(){\n    const button=q(\'#dpSave\');\n    try{\n      if(button){button.disabled=true;button.textContent=\'Guardando…\'}\n      const data=await call(\'/api/v4506/dataphone/config\',{\n        method:\'POST\',\n        body:JSON.stringify(payload())\n      });\n      render(data);\n      status(\'✓ Configuración guardada.\',\'ok\');\n    }catch(error){\n      status(error?.message||String(error),\'err\');\n    }finally{\n      if(button){button.disabled=false;button.textContent=\'Guardar configuración\'}\n    }\n  }\n\n  async function validateConfig(showMessage=true){\n    try{\n      const data=await call(\'/api/v4506/dataphone/validate\',{method:\'POST\',body:\'{}\'});\n      const host=q(\'#v4506DpChecks\');\n      if(host){\n        host.innerHTML=(data.checks||[]).map(item=>\n          \'<div class="v4506-dp-check \'+(item.ok?\'ok\':\'\')+\'">\'\n          +\'<b>\'+(item.ok?\'✓ \':\'○ \')+esc(item.label)+\'</b>\'\n          +\'<small>\'+esc(item.detail)+\'</small></div>\'\n        ).join(\'\');\n      }\n      if(showMessage)status(data.message||\'\',data.ready?\'ok\':\'\');\n    }catch(error){\n      if(showMessage)status(error?.message||String(error),\'err\');\n    }\n  }\n\n  async function testApi(){\n    const button=q(\'#dpTest\');\n    try{\n      if(button){button.disabled=true;button.textContent=\'Probando…\'}\n      const data=await call(\'/api/v4506/dataphone/test\',{method:\'POST\',body:\'{}\'});\n      status(data.message||\'Prueba completada.\',data.ok?\'ok\':\'\');\n    }catch(error){\n      status(error?.message||String(error),\'err\');\n    }finally{\n      if(button){button.disabled=false;button.textContent=\'↻ Probar API sin cobrar\'}\n    }\n  }\n\n  function fixConsultation(){\n    const consult=q(\n      \'.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"],\'\n      +\'.attention-form-modal .consultation-service-section .service-card[data-service="consulta"]\'\n    );\n    if(consult){\n      consult.style.removeProperty(\'min-height\');\n      consult.style.removeProperty(\'height\');\n    }\n  }\n\n  function boot(){\n    qa(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n    ensureTab();\n    fixConsultation();\n  }\n\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  }else{\n    boot();\n  }\n  setTimeout(boot,220);\n  setTimeout(boot,650);\n\n  document.addEventListener(\'click\',event=>{\n    if(event.target?.closest?.(\'.attention-form-modal\')){\n      setTimeout(fixConsultation,25);\n      setTimeout(fixConsultation,140);\n    }\n  },true);\n\n  window.loadDataphoneConfig=loadConfig;\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4506_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4506_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4506/health')
def v4506_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'consultation_card_restored': True, 'procedures_compact': True, 'payment_typography_enlarged': True, 'dataphone_provider': 'BENDO', 'dataphone_model': 'Bendo Smart', 'dataphone_config_tab': True, 'dataphone_test_without_charge': True, 'dataphone_api_contract_not_invented': True, 'manual_card_entry': False, 'database_changes': False, 'database_schema_changes': False, 'neon_writes_added': False, 'azur_contract_changes': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
