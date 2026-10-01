from __future__ import annotations

# Deterministic current runtime. No historical release registry.
import json
import os
import re
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
import reception_history_cancellation
import reception_payment_terminal_feedback
import reception_payment_terminal_panel
import reception_history_identity_consolidated
import reception_tv_turns

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
    reception_history_cancellation,
    reception_payment_terminal_feedback,
    reception_payment_terminal_panel,
    reception_history_identity_consolidated,
    reception_tv_turns,
)


def _install_history_exact_name_search_hotfix() -> None:
    """Keep old exact Historia records visible even when broad token search is crowded."""
    module = reception_history_identity_consolidated
    base_search = module._search_candidates
    if getattr(base_search, "__exact_name_hotfix__", False):
        return

    def patched(cur, demo, query, limit):
        rows = list(base_search(cur, demo, query, limit) or [])
        typed_name = module._fuzzy_text(query or demo.get("name"))
        tokens = [token for token in typed_name.split() if len(token) >= 2]
        if len(tokens) < 2:
            return rows

        name_expr = (
            "TRANSLATE(UPPER(COALESCE(p.name_search,p.name,'')),"
            "'ÁÉÍÓÚÜÑZ','AEIOUUNS')"
        )
        cur.execute(
            """
            SELECT p.id,p.name,p.name_search,p.national_id,p.national_id_search,
                   p.birth_date,p.phone,p.email,p.address,p.merged_into_patient_id
            FROM public.patients p
            WHERE p.deleted_at IS NULL
              AND """ + name_expr + " = %s LIMIT 20",
            (typed_name,),
        )

        exact_rows = []
        for raw in cur.fetchall() or []:
            item = module._dict_row(cur, raw)
            canonical_id = (
                module._clean(item.get("merged_into_patient_id"), 120)
                or module._clean(item.get("id"), 120)
            )
            if canonical_id != module._clean(item.get("id"), 120):
                canonical = module._patient_row(cur, canonical_id)
                if canonical:
                    item = canonical
            item.update(module._history_summary(cur, item["id"]))
            score, reasons = module._candidate_score(item, demo, query)
            item["match_score"] = score
            item["match_reasons"] = reasons
            exact_rows.append(item)

        if not exact_rows:
            return rows

        combined = []
        seen = set()
        for item in exact_rows + rows:
            patient_id = str(item.get("id") or "")
            if not patient_id or patient_id in seen:
                continue
            combined.append(item)
            seen.add(patient_id)

        combined.sort(
            key=lambda item: (
                int(item.get("match_score") or 0),
                int(item.get("history_date_count") or 0),
                module._clean(item.get("last_history_date"), 20),
            ),
            reverse=True,
        )
        return combined[: max(1, min(int(limit or 30), 40))]

    patched.__exact_name_hotfix__ = True
    module._search_candidates = patched


_install_history_exact_name_search_hotfix()


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
        html = re.sub(r'(/static/app\.js\?v=)[^"\']+', rf'\g<1>{version}', html, count=1)
        addon = (
            f'<link rel="stylesheet" href="/v460/overlay.css?v={version}">'
            f'<link rel="stylesheet" href="/static/configuration.css?v={version}">'
            f'<script defer src="/v460/overlay.js?v={version}"></script>'
            f'<script defer src="/static/configuration.js?v={version}"></script>'
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


def _strip_legacy_configuration_overlays() -> None:
    """Retire only superseded Configuration UI blocks; backend endpoints stay available."""
    css = getattr(core_runtime, "V460_OVERLAY_CSS", "") or ""
    js = getattr(core_runtime, "V460_OVERLAY_JS", "") or ""
    blocks = [
        (reception_update_restart, ("V4482_CSS", "V4482_JS")),
        (reception_update_launcher, ("V4483_CSS", "V4483_JS")),
        (reception_system_status, ("V4501_JS",)),
        (reception_payment_terminal_config, ("V4506_JS",)),
        (reception_version_display, ("V4518_CSS", "V4518_JS")),
        (reception_version_sidebar, ("V4519_CSS", "V4519_JS")),
    ]
    for module, attrs in blocks:
        for attr in attrs:
            block = getattr(module, attr, "") or ""
            if not block:
                continue
            if attr.endswith("_CSS"):
                css = css.replace(block, "")
            else:
                js = js.replace(block, "")
    core_runtime.V460_OVERLAY_CSS = css
    core_runtime.V460_OVERLAY_JS = js


_strip_legacy_configuration_overlays()


_install_versioned_overlay_home()

CURRENT_APP_VERSION = _read_current_app_version()
core_runtime.APP_VERSION = CURRENT_APP_VERSION
for _feature_module in FEATURE_MODULES:
    _feature_module.APP_VERSION = CURRENT_APP_VERSION
del _feature_module
