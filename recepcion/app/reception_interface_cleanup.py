from __future__ import annotations

import core_runtime as core

app = core.app
APP_VERSION = getattr(core, "APP_VERSION", "")
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""
FACTURERO_DESTINATION_REMOVED = False

try:
    destinations = getattr(core, "EXTERNAL_DESTINATIONS", None)
    if isinstance(destinations, dict):
        FACTURERO_DESTINATION_REMOVED = destinations.pop("facturero", None) is not None

    # Only compatibility CSS remains. Billing source itself no longer creates
    # these obsolete controls, so there are no loadBilling/setBillingStatus wrappers.
    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + r'''
[data-config-tab="services"],
[data-config-section="services"],
#v458ServicePanel,
#facturacion .billing-filters,
#v482BatchEmit,
#v4470ProcedureManager,
#v4475ProcedureManager,
[data-config-section="procedimientos"] > .v4476-service-old{display:none!important}
'''
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/interface-cleanup/health")
def interface_cleanup_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "facturero_destination_removed": FACTURERO_DESTINATION_REMOVED,
        "billing_dom_sweeps": False,
        "billing_function_wrappers": False,
        "version_painter": False,
    }
