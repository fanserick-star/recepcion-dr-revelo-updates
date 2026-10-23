"""Panel de documentos de UNA ficha clínica: lectura local sin copias ni cambios en Neón.

Las recetas e informes se relacionan por patient_id canónico, incluso si no
tienen encounter_id. Los PDFs PAdES se sirven por la ruta segura de solo lectura.
"""
from __future__ import annotations

import html
import sqlite3
from urllib.parse import quote


def _e(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _kind(certificate_type: str) -> tuple[str, str]:
    kinds = {
        "report_cystoscopy": ("informe", "Informe de cistoscopía"),
        "report_ultrasound": ("informe", "Informe de ecografía"),
        "rest_isolation": ("reposo", "Certificado de reposo"),
    }
    return kinds.get(certificate_type, ("certificado", "Certificado médico"))


def _unsigned_url(item: dict) -> str:
    doc_id = quote(str(item["id"]), safe="")
    kind = item["kind"]
    if kind == "receta":
        return f"/recetas/{doc_id}/vista"
    if kind == "informe":
        return f"/informes/{doc_id}/vista"
    if kind == "reposo":
        return f"/certificados/reposo/{doc_id}/vista"
    return f"/certificados/{doc_id}/vista"


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone())


def read_documents(conn: sqlite3.Connection, patient_id: str) -> list[dict]:
    """Sin JOIN por nombre ni identificación: solo patient_id de ficha activa."""
    patient_id = str(patient_id or "").strip()
    if not patient_id:
        return []
    documents = []
    if _has_table(conn, "prescriptions"):
        rx = conn.execute(
            """SELECT id,issued_at,COALESCE(diagnosis,'') AS diagnosis
               FROM prescriptions WHERE patient_id=?
                 AND COALESCE(deleted_at,'')=''
               ORDER BY issued_at DESC""", (patient_id,),
        ).fetchall()
        documents.extend({
            "id": str(r["id"]), "issued_at": str(r["issued_at"] or ""),
            "description": str(r["diagnosis"] or ""),
            "kind": "receta", "label": "Receta médica",
        } for r in rx)
    if _has_table(conn, "certificates"):
        certs = conn.execute(
            """SELECT id,issued_at,COALESCE(diagnosis,'') AS diagnosis,
                      COALESCE(certificate_type,'medical') AS certificate_type
               FROM certificates WHERE patient_id=?
                 AND COALESCE(deleted_at,'')=''
               ORDER BY issued_at DESC""", (patient_id,),
        ).fetchall()
        for r in certs:
            kind, label = _kind(str(r["certificate_type"]))
            documents.append({
                "id": str(r["id"]), "issued_at": str(r["issued_at"] or ""),
                "description": str(r["diagnosis"] or ""),
                "kind": kind, "label": label,
            })
    if _has_table(conn, "electronic_signatures") and documents:
        # Sólo IDs que ya corresponden al paciente exacto. No cruza fichas.
        relevant_ids = sorted({x["id"] for x in documents})
        signed = set()
        for at in range(0, len(relevant_ids), 300):
            segment = relevant_ids[at:at + 300]
            marks = ",".join("?" for _ in segment)
            signed.update(
                (str(r["document_type"]), str(r["document_id"]))
                for r in conn.execute(
                    f"""SELECT DISTINCT document_type,document_id
                        FROM electronic_signatures
                        WHERE document_id IN ({marks})""", segment
                ).fetchall()
            )
        for item in documents:
            item["signed"] = (item["kind"], item["id"]) in signed
    else:
        for item in documents:
            item["signed"] = False
    documents.sort(key=lambda x: (x["issued_at"], x["id"]), reverse=True)
    return documents


def render_patient_documents(conn: sqlite3.Connection, patient_id: str) -> str:
    docs = read_documents(conn, patient_id)
    counts = {
        "informe": sum(x["kind"] == "informe" for x in docs),
        "certificado": sum(x["kind"] in {"certificado", "reposo"} for x in docs),
        "receta": sum(x["kind"] == "receta" for x in docs),
    }
    chips = (
        f"<span class='cp-docs-chip cp-docs-info'>📄 <strong>{counts['informe']}</strong> Informes</span>"
        f"<span class='cp-docs-chip cp-docs-cert'>✓ <strong>{counts['certificado']}</strong> Certificados</span>"
        f"<span class='cp-docs-chip cp-docs-rx'>Rx <strong>{counts['receta']}</strong> Recetas</span>"
    )
    rows = []
    for d in docs:
        is_signed = bool(d["signed"])
        id_ = quote(d["id"], safe="")
        kind = d["kind"]
        url = (f"/api/firma/original/{kind}/{id_}"
               if is_signed else _unsigned_url(d))
        print_url = url if is_signed else url + "?print_now=1"
        status = ("<span class='cp-docs-status signed'>🔒 Firmado</span>"
                  if is_signed else "<span class='cp-docs-status'>Guardado</span>")
        hint = ("PDF firmado original; el visor permite imprimirlo."
                if is_signed else "Imprimir documento sin firma electrónica.")
        date_text = d["issued_at"][:16].replace("T", " ")
        rows.append(
            "<div class='cp-docs-item'>"
            "<div class='cp-docs-item-copy'>"
            f"<strong>{_e(d['label'])}</strong>"
            f"<span>{_e(date_text)}{(' · ' + _e(d['description'])) if d['description'] else ''}</span>"
            "</div>"
            + status
            + "<div class='cp-docs-item-actions'>"
            f"<a href='{_e(url)}' target='_blank' rel='noopener'>Ver</a>"
            f"<a href='{_e(print_url)}' title='{_e(hint)}' target='_blank' rel='noopener'>"
            + ("Imprimir PDF" if is_signed else "Imprimir")
            + "</a></div></div>"
        )
    contents = "".join(rows) if rows else (
        "<div class='cp-docs-empty'>Todavía no hay documentos guardados para este paciente.</div>"
    )
    return (
        "<section class='cp-patient-documents' aria-label='Documentos del paciente'>"
        "<div class='cp-patient-documents-title'>"
        "<div><span class='cp-docs-kicker'>ARCHIVO CLÍNICO</span>"
        "<h2>Documentos del paciente</h2>"
        "<p>Recetas, certificados e informes de esta ficha, recientes primero.</p></div>"
        f"<strong class='cp-docs-total'>{len(docs)} documento{'s' if len(docs)!=1 else ''}</strong>"
        "</div>"
        f"<div class='cp-docs-counts'>{chips}</div>"
        f"<div class='cp-docs-list'>{contents}</div>"
        "</section>"
    )
