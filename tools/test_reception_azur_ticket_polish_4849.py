"""AZUR PDF-inspired thermal ticket improvements from authorized XML only.

All values below are synthetic. Never opens patient records, AZUR, Neon or printers.
"""
import ast
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

root=Path(__file__).resolve().parents[1]/"recepcion"/"app"
content=(root/"reception_azur_pos80.py").read_text(encoding="utf-8")
tree=ast.parse(content)
fns={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
for name in ("_format_authorization_datetime","_payment_method_label","_contact_from_additional","_authorized_xml_to_ticket"):
    assert name in fns,name

class Reject(Exception):
    def __init__(self,status_code,message):
        self.status_code=status_code
        super().__init__(message)

def norm(number):
    digits=re.sub(r"\D","",str(number or ""))
    return digits if len(digits)==15 else ""

scope={
    "datetime":datetime,"Decimal":Decimal,"InvalidOperation":InvalidOperation,
    "ET":ET,"re":re,"core":SimpleNamespace(HTTPException=Reject),
    "read":SimpleNamespace(_invoice_norm=norm),"_XML_MAX_BYTES":2097152,
}
for name in ("_text","_decimal","_money","_format_authorization_datetime",
             "_payment_method_label","_contact_from_additional","_safe_xml",
             "_authorized_xml_to_ticket"):
    exec(compile(ast.Module(body=[fns[name]],type_ignores=[]),name,"exec"),scope)

fmt=scope["_format_authorization_datetime"]
assert fmt("2026-10-21T11:15:59-05:00")=="21/10/2026 11:15"
assert fmt("fecha no estandar")=="fecha no estandar"
assert fmt("")==""
label=scope["_payment_method_label"]
assert label("01")=="SIN UTILIZACION DEL SISTEMA FINANCIERO"
assert label("19")=="Forma de pago 19"
assert label("")=="Forma de pago"
phone,email=scope["_contact_from_additional"]([
    {"nombre":"Telefono","valor":"0999999999"},
    {"nombre":"Email","valor":"demo@example.invalid"},
    {"nombre":"RUC Proveedor","valor":"0999999999001"},
])
assert (phone,email)==("0999999999","demo@example.invalid")
assert scope["_contact_from_additional"]([{"nombre":"Origen","valor":"Recepcion"}])==("","")

key="1"*49
xml=f"""<factura><infoTributaria><ambiente>2</ambiente><razonSocial>CLINICA DEMO</razonSocial><ruc>0999999999001</ruc><codDoc>01</codDoc><estab>003</estab><ptoEmi>001</ptoEmi><secuencial>000000123</secuencial><claveAcceso>{key}</claveAcceso><dirMatriz>CALLE 1</dirMatriz></infoTributaria><infoFactura><fechaEmision>21/10/2026</fechaEmision><dirEstablecimiento>CALLE 1</dirEstablecimiento><razonSocialComprador>PACIENTE DEMO</razonSocialComprador><identificacionComprador>0123456789</identificacionComprador><totalSinImpuestos>40.00</totalSinImpuestos><totalDescuento>0.00</totalDescuento><importeTotal>40.00</importeTotal><pagos><pago><formaPago>01</formaPago><total>40.00</total><plazo>0</plazo><unidadTiempo>dias</unidadTiempo></pago></pagos></infoFactura><detalles><detalle><descripcion>CONSULTA DEMO</descripcion><cantidad>1</cantidad><precioUnitario>40.00</precioUnitario><descuento>0</descuento><precioTotalSinImpuesto>40</precioTotalSinImpuesto></detalle></detalles><infoAdicional><campoAdicional nombre="Telefono">0999999999</campoAdicional><campoAdicional nombre="Email">demo@example.invalid</campoAdicional><campoAdicional nombre="RUC Proveedor">0999999999001</campoAdicional></infoAdicional></factura>"""
auth=f"<autorizacion><estado>AUTORIZADO</estado><numeroAutorizacion>{key}</numeroAutorizacion><fechaAutorizacion>2026-10-21T11:15:59-05:00</fechaAutorizacion><comprobante><![CDATA[{xml}]]></comprobante></autorizacion>"
ticket=scope["_authorized_xml_to_ticket"](auth.encode(),key,"003-001-000000123")
assert ticket["telefono_cliente"]=="0999999999"
assert ticket["correo_cliente"]=="demo@example.invalid"
assert ticket["pagos"][0]["tipo"]=="01"
assert ticket["pagos"][0]["plazo"]=="0"
assert ticket["pagos"][0]["unidad_tiempo"]=="dias"
assert ticket["ambiente"]=="PRODUCCION"
assert ticket["total"]=="40.00"
assert any(x["nombre"]=="RUC Proveedor" for x in ticket["adicional"])

# The signed XML remains the only fiscal data source.
printer=ast.get_source_segment(content,fns["_print_ticket_windows"])
for marker in (
  'write("Ambiente: PRODUCCION"',
  '_format_authorization_datetime(ticket["fecha_autorizacion"])',
  '_payment_method_label(pago["tipo"])',
  'ticket.get("telefono_cliente")',
  'ticket.get("correo_cliente")',
  'ticket["direccion_establecimiento"].strip().casefold()',
):
    assert marker in printer, marker
assert "doc.Print()" in printer
assert "azur_emit_invoice" not in content
assert "db.commit(" not in content and "db.delete(" not in content
print("AZUR_XML_TICKET_PDF_INSPIRED_FISCAL_SAFE_4849_OK")
