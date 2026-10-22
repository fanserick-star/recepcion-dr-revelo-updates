"""Only synthetic XML. Validates AZUR->SRI authorized data before print.

No network, secrets, printer, patient records, database or fiscal mutations.
"""
import ast
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

base=Path(__file__).resolve().parents[1]/"recepcion"/"app"
source=(base/"reception_azur_pos80.py").read_text(encoding="utf-8")
tree=ast.parse(source)
fns={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
for k in ("_safe_xml","_authorized_xml_to_ticket","_download_authorized_xml","_print_ticket_windows","_ticket_for_request","azur_pos80_preview","azur_pos80_print"):
    assert k in fns,k
source_get=ast.get_source_segment(source,fns["_download_authorized_xml"])
assert '"GET"' in source_get and '"/xml"' in source_get
assert 'build_opener(read._NeverRedirect())' in source_get
assert '"--max-redirs", "0"' in source_get
assert "X-Api-Key:" in source_get
assert 'POST /factura/emision' not in source
assert 'db.commit(' not in source and 'db.delete(' not in source
assert 'azur_emit_invoice' not in source
assert 'core._app_preferences()' in source
assert 'PrinterSettings.InstalledPrinters' in source
assert 'PaperSize("Factura RIDE 80 mm", 315, est)' in source
assert 'data = read.azur_read_verify_invoice' not in source
assert 'read.azur_read_verify_invoice(data, db=db, user=user)' in source
assert '_authorized_xml_to_ticket(_download_authorized_xml' in source
assert source.index('_ticket_for_request(data, db, user)',source.index('def azur_pos80_print')) < source.index('_print_ticket_windows(ticket, printer)',source.index('def azur_pos80_print'))

class ExpectedReject(Exception):
    def __init__(self,code,message):
        self.status_code=code
        super().__init__(message)

def _norm(number):
    x="".join(c for c in str(number) if c.isdigit())
    return x if len(x)==15 else ""

scope={
    "core":SimpleNamespace(HTTPException=ExpectedReject),
    "ET":ET,
    "re":__import__("re"),
    "Decimal":Decimal,
    "InvalidOperation":InvalidOperation,
    "read":SimpleNamespace(_invoice_norm=_norm),
    "_XML_MAX_BYTES":2*1024*1024,
}
for key in ("_text","_decimal","_money","_contact_from_additional","_safe_xml","_authorized_xml_to_ticket"):
    exec(compile(ast.Module(body=[fns[key]],type_ignores=[]),"<invoice XML unit>","exec"),scope)

key="1"*49
num="001-001-000000123"
invoice=f"""<factura><infoTributaria><ambiente>2</ambiente><razonSocial>CONSULTORIO DE PRUEBA</razonSocial><ruc>0999999999001</ruc><codDoc>01</codDoc><estab>001</estab><ptoEmi>001</ptoEmi><secuencial>000000123</secuencial><claveAcceso>{key}</claveAcceso></infoTributaria><infoFactura><fechaEmision>21/10/2026</fechaEmision><razonSocialComprador>PACIENTE DEMO</razonSocialComprador><identificacionComprador>0999999999</identificacionComprador><totalSinImpuestos>40.00</totalSinImpuestos><totalDescuento>0</totalDescuento><totalConImpuestos><totalImpuesto><codigo>2</codigo><codigoPorcentaje>0</codigoPorcentaje><baseImponible>40</baseImponible><valor>0</valor></totalImpuesto></totalConImpuestos><importeTotal>40.00</importeTotal><pagos><pago><formaPago>01</formaPago><total>40.00</total></pago></pagos></infoFactura><detalles><detalle><descripcion>CONSULTA DEMO</descripcion><cantidad>1.00</cantidad><precioUnitario>40.00</precioUnitario><descuento>0.00</descuento><precioTotalSinImpuesto>40.00</precioTotalSinImpuesto></detalle></detalles></factura>"""
def document(estado="AUTORIZADO",payload=invoice,k=key):
    return f'<autorizacion><estado>{estado}</estado><numeroAutorizacion>{k}</numeroAutorizacion><fechaAutorizacion>21/10/2026 09:00:00</fechaAutorizacion><comprobante><![CDATA[{payload}]]></comprobante></autorizacion>'.encode()
fn=scope["_authorized_xml_to_ticket"]
ticket=fn(document(),key,num)
assert ticket["numero"]==num
assert ticket["estado"]=="AUTORIZADA"
assert ticket["total"]=="40.00"
assert ticket["cliente"]=="PACIENTE DEMO"
assert len(ticket["servicios"])==1
assert ticket["servicios"][0]["descripcion"]=="CONSULTA DEMO"
assert ticket["impuestos"][0]["valor"]=="0.00"
for scenario in [
  lambda:fn(document("NO AUTORIZADO"),key,num),
  lambda:fn(document(), "2"*49,num),
  lambda:fn(document(),key,"001-001-000000999"),
  lambda:fn(document(payload=invoice.replace("<ambiente>2</ambiente>","<ambiente>1</ambiente>")),key,num),
  lambda:fn(b"<!DOCTYPE suspicious [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><autorizacion/>",key,num),
  lambda:fn(b"<html>Not XML of tax receipt</html>",key,num),
]:
    try:scenario()
    except ExpectedReject:pass
    else:raise AssertionError("A malformed or unverified XML reached print preparation")
manifest=json.loads((base/"update_manifest.json").read_text())
assert manifest["version"] in {"4.8.47","4.8.48","4.8.49","4.8.50","4.8.51","4.8.52","4.8.53","4.8.54"}
for field in ("copy","required_dependencies"):assert "reception_azur_pos80.py" in manifest[field]
assert "import reception_azur_pos80 as _azur_pos80" in (base/"app.py").read_text()
print("AZUR_AUTHORIZED_XML_POS80_SAFE_PARSER_4847_OK")
