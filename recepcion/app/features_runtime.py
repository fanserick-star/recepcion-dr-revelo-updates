from __future__ import annotations

# Deterministic current runtime. No historical release registry.
import json
import os
from pathlib import Path

import core_runtime
import reception_payments_and_agenda
import reception_billing_non_billable
import reception_receipt_thermal_layout
import reception_receipt_classification
import reception_receipt_preview
import reception_receipt_margins
import reception_receipt_unified_layout
import reception_receipt_raster
import reception_receipt_readability
import reception_receipt_size
import reception_receipt_width
import reception_attention_identity
import reception_interface_recovery
import reception_printing_queue
import reception_attention_transaction
import reception_billing_history
import reception_billing_discard
import reception_billing_actions
import reception_interface_cleanup
import reception_billing_issued_filters
import reception_billing_modal_cleanup
import reception_update_restart
import reception_update_launcher
import reception_billing_optional_email
import reception_payment_proof
import reception_printing_menu
import reception_payment_proof_margins
import reception_payment_proof_layout
import reception_billing_data_form
import reception_billing_data_form_compact
import reception_billing_data_form_layout
import reception_system_status
import reception_consultation_discount
import reception_payment_terminal
import reception_payment_terminal_interface
import reception_payment_terminal_config
import reception_payment_terminal_manual
import reception_history_bridge
import reception_launcher_status
import reception_version_display
import reception_version_sidebar
import reception_history_transport
import reception_history_attention_type
import reception_history_cancellation
import reception_payment_terminal_feedback
import reception_history_patient_details
import reception_payment_terminal_panel
import reception_history_identity_consolidated
import reception_history_requeue_guard

FEATURE_MODULES = (
    reception_payments_and_agenda,
    reception_billing_non_billable,
    reception_receipt_thermal_layout,
    reception_receipt_classification,
    reception_receipt_preview,
    reception_receipt_margins,
    reception_receipt_unified_layout,
    reception_receipt_raster,
    reception_receipt_readability,
    reception_receipt_size,
    reception_receipt_width,
    reception_attention_identity,
    reception_interface_recovery,
    reception_printing_queue,
    reception_attention_transaction,
    reception_billing_history,
    reception_billing_discard,
    reception_billing_actions,
    reception_interface_cleanup,
    reception_billing_issued_filters,
    reception_billing_modal_cleanup,
    reception_update_restart,
    reception_update_launcher,
    reception_billing_optional_email,
    reception_payment_proof,
    reception_printing_menu,
    reception_payment_proof_margins,
    reception_payment_proof_layout,
    reception_billing_data_form,
    reception_billing_data_form_compact,
    reception_billing_data_form_layout,
    reception_system_status,
    reception_consultation_discount,
    reception_payment_terminal,
    reception_payment_terminal_interface,
    reception_payment_terminal_config,
    reception_payment_terminal_manual,
    reception_history_bridge,
    reception_launcher_status,
    reception_version_display,
    reception_version_sidebar,
    reception_history_transport,
    reception_history_attention_type,
    reception_history_cancellation,
    reception_payment_terminal_feedback,
    reception_history_patient_details,
    reception_payment_terminal_panel,
    reception_history_identity_consolidated,
    reception_history_requeue_guard,
)


def _read_current_app_version() -> str:
    version_doc = json.loads(
        Path(__file__).with_name("recepcion-version.json").read_text(encoding="utf-8-sig")
    )
    version = str(version_doc.get("version") or "").strip()
    if not version:
        raise RuntimeError("recepcion-version.json does not contain a valid version")
    return version


def _install_versioned_overlay_home() -> None:
    """Serve overlay assets with the canonical app version as cache-buster."""
    app = core_runtime.app
    for route in list(app.router.routes):
        if (
            getattr(route, "path", None) == "/"
            and "GET" in set(getattr(route, "methods", set()) or set())
        ):
            app.router.routes.remove(route)

    @app.get("/", response_class=core_runtime.HTMLResponse)
    def _versioned_overlay_home():
        with open(
            os.path.join(core_runtime.BASE_DIR, "static", "index.html"),
            encoding="utf-8",
        ) as handle:
            html = handle.read()
        version = _read_current_app_version()
        addon = (
            '<link rel="stylesheet" href="/v458/settings.css?v=4.3.58">'
            '<script defer src="/v458/settings.js?v=4.3.58"></script>'
            '<link rel="stylesheet" href="/v459/settings.css?v=4.3.59">'
            '<script defer src="/v459/settings.js?v=4.3.59"></script>'
            f'<link rel="stylesheet" href="/v460/overlay.css?v={version}">'
            f'<script defer src="/v460/overlay.js?v={version}"></script>'
        )
        return (
            html.replace("</head>", addon + "</head>", 1)
            if "</head>" in html
            else html + addon
        )

    try:
        app.openapi_schema = None
    except Exception:
        pass


_install_versioned_overlay_home()

CURRENT_APP_VERSION = _read_current_app_version()
core_runtime.APP_VERSION = CURRENT_APP_VERSION
for _feature_module in FEATURE_MODULES:
    _feature_module.APP_VERSION = CURRENT_APP_VERSION
del _feature_module
