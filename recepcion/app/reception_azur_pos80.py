"""AZUR XML autorizado -> vista previa/impresión térmica local de 80 mm.

Las únicas peticiones remotas son GETs de AZUR API v2. Nunca envía, altera,
anula ni numera comprobantes. No guarda XML ni claves en Neon.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from xml.etree import ElementTree as ET

import reception_azur_readonly as read
from azur_client import normalize_base_url

core, app = read.core, read.app
_XML_MAX_BYTES = 2 * 1024 * 1024


def _text(node, path: str) -> str:
    if node is None:
        return ""
    value = node.findtext(path)
    return str(value or "").strip()


def _decimal(value: str) -> Decimal:
    try:
        n = Decimal(str(value).strip())
        if not n.is_finite():
            raise ValueError()
        return n
    except (InvalidOperation, ValueError):
        raise core.HTTPException(422, "El XML autorizado contiene un importe no válido")


def _money(value) -> str:
    return f"{_decimal(value):.2f}"


def _safe_xml(raw: bytes) -> ET.Element:
    if not raw or len(raw) > _XML_MAX_BYTES:
        raise core.HTTPException(502, "La respuesta XML de AZUR está vacía o excede el tamaño permitido")
    if b"<!doctype" in raw.lower() or b"<!entity" in raw.lower():
        raise core.HTTPException(502, "El XML recibido no cumple con las restricciones de seguridad")
    try:
        return ET.fromstring(raw)
    except (ET.ParseError, ValueError, TypeError):
        raise core.HTTPException(502, "AZUR devolvió un XML que no se pudo interpretar")


def _authorized_xml_to_ticket(raw: bytes, expected_key: str, expected_number: str) -> dict:
    """Fail closed; require SRI authorization envelope and exact key/document."""
    root = _safe_xml(raw)
    auth = root if root.tag == "autorizacion" else root.find("./autorizacion")
    if auth is None and root.tag == "autorizaciones":
        auth = root.find("./autorizacion")
    if auth is None:
        raise core.HTTPException(409, "El documento devuelto por AZUR no contiene una autorización SRI")
    if _text(auth, "estado").upper() != "AUTORIZADO":
        raise core.HTTPException(409, "El SRI todavía no autorizó el XML; no se imprimirá")
    auth_key = _text(auth, "numeroAutorizacion")
    if auth_key != expected_key or not re.fullmatch(r"[0-9]{49}", auth_key):
        raise core.HTTPException(409, "La clave del XML autorizado no coincide con la de Recepción")
    embedded = auth.find("comprobante")
    if embedded is None or not (embedded.text or "").strip():
        raise core.HTTPException(409, "El XML autorizado no contiene el comprobante firmado")
    invoice = _safe_xml(embedded.text.strip().encode("utf-8"))
    if invoice.tag != "factura":
        raise core.HTTPException(409, "El comprobante autorizado no corresponde a una factura")
    trib = invoice.find("./infoTributaria")
    info = invoice.find("./infoFactura")
    if trib is None or info is None:
        raise core.HTTPException(409, "La factura autorizada no contiene todos sus datos fiscales")
    if _text(trib, "codDoc") != "01" or _text(trib, "claveAcceso") != expected_key:
        raise core.HTTPException(409, "El XML firmado no coincide con la factura autorizada")
    if _text(trib, "ambiente") != "2":
        raise core.HTTPException(409, "Este XML no pertenece al ambiente de producción")
    num = "-".join([_text(trib,"estab"),_text(trib,"ptoEmi"),_text(trib,"secuencial")])
    if read._invoice_norm(num) != read._invoice_norm(expected_number):
        raise core.HTTPException(409, "La numeración del XML no coincide con la factura de Recepción")
    total = _decimal(_text(info, "importeTotal"))
    if total < 0 or total > Decimal("999999999"):
        raise core.HTTPException(422, "El total de la factura está fuera del rango válido")
    lines = []
    for item in invoice.findall("./detalles/detalle"):
        if len(lines) >= 60:
            raise core.HTTPException(422, "El comprobante contiene demasiados servicios para la impresión térmica")
        description = _text(item, "descripcion") or _text(item, "codigoPrincipal")
        if not description:
            raise core.HTTPException(422, "Hay una línea del XML sin descripción")
        lines.append({
            "descripcion": description[:140],
            "cantidad": _money(_text(item, "cantidad")),
            "unitario": _money(_text(item, "precioUnitario")),
            "descuento": _money(_text(item, "descuento") or "0"),
            "total": _money(_text(item, "precioTotalSinImpuesto")),
        })
    if not lines:
        raise core.HTTPException(422, "La factura autorizada no contiene servicios para imprimir")
    taxes = []
    for tax in invoice.findall("./infoFactura/totalConImpuestos/totalImpuesto"):
        taxes.append({
            "codigo": _text(tax, "codigo"),
            "porcentaje": _text(tax, "codigoPorcentaje"),
            "base": _money(_text(tax, "baseImponible") or "0"),
            "valor": _money(_text(tax, "valor") or "0"),
        })
    additional = []
    for field in invoice.findall("./infoAdicional/campoAdicional"):
        name = str(field.attrib.get("nombre") or "").strip()
        if name and (field.text or "").strip():
            additional.append({"nombre": name[:50], "valor": field.text.strip()[:120]})
    payments = []
    for payment in invoice.findall("./infoFactura/pagos/pago"):
        payments.append({"tipo": _text(payment, "formaPago"), "total": _money(_text(payment, "total"))})
    return {
        "numero": num,
        "clave": expected_key,
        "estado": "AUTORIZADA",
        "autorizacion": auth_key,
        "fecha_autorizacion": _text(auth, "fechaAutorizacion"),
        "ambiente": "PRODUCCION",
        "emisor": _text(trib, "razonSocial"),
        "nombre_comercial": _text(trib, "nombreComercial"),
        "ruc": _text(trib, "ruc"),
        "direccion_matriz": _text(trib, "dirMatriz"),
        "direccion_establecimiento": _text(info, "dirEstablecimiento"),
        "obligado_contabilidad": _text(info, "obligadoContabilidad"),
        "contribuyente_especial": _text(info, "contribuyenteEspecial"),
        "regimen": _text(info, "contribuyenteRimpe"),
        "fecha_emision": _text(info, "fechaEmision"),
        "cliente": _text(info, "razonSocialComprador"),
        "identificacion": _text(info, "identificacionComprador"),
        "direccion_cliente": _text(info, "direccionComprador"),
        "subtotal": _money(_text(info, "totalSinImpuestos")),
        "total_descuento": _money(_text(info, "totalDescuento") or "0"),
        "propina": _money(_text(info, "propina") or "0"),
        "total": _money(total),
        "moneda": _text(info, "moneda") or "DOLAR",
        "servicios": lines,
        "impuestos": taxes,
        "pagos": payments,
        "adicional": additional[:10],
    }


def _download_authorized_xml(invoice_id: int) -> bytes:
    """GET /factura/{id}/xml; no redirect, cookies, browser or disk writes."""
    if not read._READ_KEY or read._env_name(read._READ_KEY) != "PRODUCCIÓN":
        raise core.HTTPException(409, "Configura una credencial AZUR v2 de consulta de PRODUCCIÓN")
    try:
        base = normalize_base_url(core.AZUR_BASE_URL)
    except Exception:
        raise core.HTTPException(409, "La dirección de AZUR no está configurada correctamente")
    if not isinstance(invoice_id, int) or not (1 <= invoice_id <= 9999999999999):
        raise core.HTTPException(400, "ID de comprobante AZUR inválido")
    url = base + "/plataforma/api/v2/factura/" + str(invoice_id) + "/xml"
    curl = (shutil.which("curl.exe") or shutil.which("curl")) if os.name == "nt" else None
    code = 0
    body = b""
    if curl:
        cmd = [
            curl, "--silent", "--show-error", "--proto", "=https", "--max-redirs", "0",
            "--connect-timeout", "6", "--max-time", "18", "--request", "GET",
            "--header", "Accept: application/xml", "--config", "-",
            "--write-out", "\n__AZUR_HTTP__:%{http_code}", url
        ]
        try:
            process = subprocess.run(
                cmd, input='header = "X-Api-Key: ' + read._READ_KEY + '"\n',
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=23, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise core.HTTPException(504, "AZUR tardó demasiado en entregar el XML autorizado")
        if "\n__AZUR_HTTP__:" not in (process.stdout or ""):
            raise core.HTTPException(502, "AZUR no pudo entregar el XML autorizado")
        xml_text, status_text = process.stdout.rsplit("\n__AZUR_HTTP__:", 1)
        code = int(status_text.strip() or "0")
        body = xml_text.encode("utf-8")
    else:
        req = Request(url, method="GET", headers={"X-Api-Key": read._READ_KEY, "Accept":"application/xml"})
        try:
            with build_opener(read._NeverRedirect()).open(req, timeout=18) as resp:
                code = int(resp.status)
                body = resp.read(_XML_MAX_BYTES + 1)
        except HTTPError as exc:
            code = int(exc.code)
        except (URLError, TimeoutError, OSError):
            raise core.HTTPException(502, "No se pudo contactar a AZUR para obtener el XML")
    if code in (401,403):
        raise core.HTTPException(403, "AZUR rechazó el permiso de consulta del XML autorizado")
    if code == 404:
        raise core.HTTPException(404, "AZUR no encontró el XML de la factura autorizada")
    if code == 429:
        raise core.HTTPException(429, "AZUR solicita esperar antes de otra consulta")
    if not (200 <= code < 300):
        raise core.HTTPException(502, "No fue posible descargar el XML de AZUR")
    if len(body) > _XML_MAX_BYTES:
        raise core.HTTPException(502, "XML demasiado grande para la impresión térmica")
    return body


def _ticket_for_request(data: read.InvoiceLookupIn, db, user) -> dict:
    """Read-only: verify remote invoice ID+key against locally authorized invoice."""
    info = read.azur_read_verify_invoice(data, db=db, user=user)
    if info.get("environment") != "PRODUCCIÓN":
        raise core.HTTPException(409, "Solo se pueden imprimir documentos de producción")
    record = db.scalar(core.select(core.AzurEmission)
                       .where(core.AzurEmission.patient_id == data.patient_id,
                              core.AzurEmission.fecha == data.fecha,
                              core.AzurEmission.estado == "AUTORIZADA",
                              core.AzurEmission.numero_factura == data.numero_factura))
    if not record or not re.fullmatch(r"[0-9]{49}", record.clave_acceso or ""):
        raise core.HTTPException(409, "No hay autorización inequívoca para esta factura")
    ticket = _authorized_xml_to_ticket(_download_authorized_xml(int(info["azur_id"])),
                                       record.clave_acceso, data.numero_factura)
    return ticket


def _print_ticket_windows(ticket: dict, printer_name: str) -> str:
    if os.name != "nt":
        raise RuntimeError("La impresión térmica directa requiere Windows")
    if not printer_name:
        raise RuntimeError("Configura primero la impresora térmica en Recepción → Configuración → Recibos e impresora")
    import clr  # type: ignore
    clr.AddReference("System.Drawing")
    from System.Drawing import Font, FontStyle, Brushes, RectangleF, StringFormat, StringAlignment, Pen, Color
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    installed = [str(p) for p in PrinterSettings.InstalledPrinters]
    if printer_name not in installed:
        raise RuntimeError("La impresora configurada ya no aparece en Windows")
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = printer_name
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError("Windows no puede utilizar la impresora configurada")
    docs = ticket["servicios"]
    # Receipt paper length in hundredths of inches; auto length for extra items.
    est = max(730, min(3200, 650 + len(docs) * 65 + len(ticket["impuestos"]) * 34 +
                       len(ticket["adicional"]) * 30 + len(ticket["pagos"]) * 26))
    doc.DocumentName = "Factura electronica autorizada 80mm"
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize("Factura RIDE 80 mm", 315, est)
    doc.DefaultPageSettings.Margins = Margins(8, 8, 7, 7)
    fonts = []
    def make_font(size, bold=False):
        f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_small = make_font(7.0)
    f_text = make_font(8.0)
    f_bold = make_font(8.0, True)
    f_title = make_font(10.0, True)
    f_total = make_font(13.0, True)
    pen = Pen(Color.Black, 1)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    def print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        def write(value, font=f_text, align=False, minheight=14):
            nonlocal y
            content = str(value or "").strip()
            if not content:
                return
            height = max(float(minheight), float(g.MeasureString(content,font,int(width - 2)).Height) + 2)
            g.DrawString(content, font, Brushes.Black, RectangleF(0.0, y, width, height + 2),
                         center if align else StringFormat.GenericDefault)
            y += height + 3
        def line():
            nonlocal y
            g.DrawLine(pen, 0.0, y, width, y)
            y += 8
        write(ticket["emisor"], f_title, True)
        if ticket.get("nombre_comercial") and ticket["nombre_comercial"] != ticket["emisor"]:
            write(ticket["nombre_comercial"], f_bold, True)
        write("RUC: " + ticket["ruc"], f_bold, True)
        if ticket["direccion_matriz"]: write("Matriz: " + ticket["direccion_matriz"], f_small)
        if ticket["direccion_establecimiento"]: write("Sucursal: " + ticket["direccion_establecimiento"], f_small)
        if ticket["obligado_contabilidad"]: write("Obligado contabilidad: " + ticket["obligado_contabilidad"], f_small)
        if ticket["contribuyente_especial"]: write("Contribuyente especial: " + ticket["contribuyente_especial"], f_small)
        if ticket["regimen"]: write(ticket["regimen"], f_small)
        line()
        write("FACTURA ELECTRONICA", f_title, True)
        write(ticket["numero"], f_title, True)
        write("AUTORIZADA POR EL SRI", f_bold, True)
        write("Emision: " + ticket["fecha_emision"], f_text)
        write("Autorizacion: " + ticket["fecha_autorizacion"], f_small)
        line()
        write("CLIENTE: " + ticket["cliente"], f_bold)
        write("Identificacion: " + ticket["identificacion"], f_text)
        if ticket["direccion_cliente"]: write("Direccion: " + ticket["direccion_cliente"], f_small)
        line()
        write("DETALLE", f_bold)
        for item in docs:
            write(item["descripcion"], f_bold)
            write("Cant. " + item["cantidad"] + " x $" + item["unitario"] + " = $" + item["total"], f_small)
            if item["descuento"] != "0.00": write("Descuento: $" + item["descuento"], f_small)
        line()
        write("Subtotal sin impuestos: $" + ticket["subtotal"], f_text)
        if ticket["total_descuento"] != "0.00": write("Descuento total: $" + ticket["total_descuento"])
        for tax in ticket["impuestos"]:
            label = "IVA" if tax["codigo"] == "2" else "Impuesto " + tax["codigo"]
            write(label + " (" + tax["porcentaje"] + "): $" + tax["valor"], f_text)
        if ticket["propina"] != "0.00": write("Propina: $" + ticket["propina"])
        write("TOTAL: $" + ticket["total"], f_total, True, 23)
        if ticket["pagos"]:
            line()
            for pago in ticket["pagos"]:
                write("Forma de pago " + pago["tipo"] + ": $" + pago["total"], f_small)
        if ticket["adicional"]:
            line()
            for field in ticket["adicional"]:
                write(field["nombre"] + ": " + field["valor"], f_small)
        line()
        write("CLAVE DE ACCESO / AUTORIZACION", f_bold, True)
        key = ticket["clave"]
        write(key[:25], f_small, True)
        write(key[25:], f_small, True)
        write("Representacion impresa de factura electronica", f_small, True)
        write("Verificable en www.sri.gob.ec", f_small, True)
        # Refuse to silently truncate the tax document if paper width/length fails.
        if y > float(e.MarginBounds.Height) - 10:
            raise RuntimeError("El ticket no cabe en la longitud de papel configurada; no se debe recortar")
        e.HasMorePages = False
    doc.PrintPage += print_page
    try:
        doc.Print()
    finally:
        try: doc.PrintPage -= print_page
        except Exception: pass
        for font in fonts:
            try: font.Dispose()
            except Exception: pass
        try: pen.Dispose()
        except Exception: pass
        try: center.Dispose()
        except Exception: pass
        try: doc.Dispose()
        except Exception: pass
    return printer_name


def _resolve_pos80_printer() -> tuple[str, str]:
    """Use the exact same configured/default Windows printer rule as receipts.

    Never guess a printer from a substring, install drivers or silently select a
    different device if the explicitly configured printer disappeared.
    """
    prefs = core._app_preferences()
    configured = str(prefs.get("printer") or "").strip()
    info = core._windows_printer_info()
    if not info.get("supported"):
        raise core.HTTPException(409, "Windows no informó impresoras disponibles. Revisa Configuración → Recibos e impresora")
    installed = [str(x).strip() for x in (info.get("printers") or []) if str(x).strip()]
    name = configured or str(info.get("default_printer") or "").strip()
    if not name:
        raise core.HTTPException(409, "No hay impresora de recibos ni impresora predeterminada de Windows. Configúrala en Recepción")
    if installed and name not in installed:
        raise core.HTTPException(409, "La impresora seleccionada ya no está instalada en Windows. Configura la impresora de recibos")
    return name, ("Configurada en Recepción" if configured else "Predeterminada de Windows")


@app.post("/api/azur/readonly/pos80-preview")
def azur_pos80_preview(data: read.InvoiceLookupIn, db=core.Depends(core.get_db),
                       user=core.Depends(core.current_user)):
    """Live, read-only AZUR verification and XML preview; zero print jobs."""
    ticket = _ticket_for_request(data, db, user)
    try:
        printer, source = _resolve_pos80_printer()
        printer_ready = True
    except core.HTTPException:
        printer, source, printer_ready = "", "", False
    return {
        "ok": True, "printed": False, "printer_configured": printer_ready,
        "printer": printer, "printer_source": source,
        "source": "XML SRI autorizado, obtenido de AZUR",
        "ticket": ticket,
        "message": "Vista previa fiscal verificada. No se ha impreso nada.",
    }


@app.post("/api/azur/readonly/pos80-print")
def azur_pos80_print(data: read.InvoiceLookupIn, db=core.Depends(core.get_db),
                     user=core.Depends(core.current_user)):
    """Explicit user-triggered local print. Re-validates source, no fiscal POST."""
    printer, _source = _resolve_pos80_printer()
    ticket = _ticket_for_request(data, db, user)
    try:
        chosen = _print_ticket_windows(ticket, printer)
    except Exception:
        raise core.HTTPException(500, "Windows no pudo imprimir la factura. Comprueba la impresora y su papel de 80 mm")
    return {
        "ok": True, "printed": True,
        "printer": chosen, "numero_factura": ticket["numero"],
        "message": "Factura autorizada enviada a la impresora térmica desde Recepción. No se emitió otra factura.",
    }
