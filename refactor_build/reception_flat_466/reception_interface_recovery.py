from __future__ import annotations
import reception_attention_identity as _dep_attention_identity
core = _dep_attention_identity.core
app = _dep_attention_identity.app
APP_VERSION = '4.4.73'
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _js.replace("const VERSION='4.4.70';", "const VERSION='4.4.73';")
    core.V460_OVERLAY_JS = _js
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.73 stable recovery patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4473/recovery-health')
def v4473_recovery_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'base_ui': '4.4.70', 'imports_v4471': False, 'imports_v4472': False, 'white_screen_recovery': True, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
