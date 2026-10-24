"""Private Windows setup window. Never transmit, print or log credentials."""
from __future__ import annotations
import secrets
import tkinter as tk
from tkinter import messagebox, ttk

from clinical_delivery_config import parse_existing, save_local_settings, BUCKET

existing = parse_existing()
root = tk.Tk()
root.title("Dr. Revelo | Preparar envíos clínicos")
root.geometry("820x805")
root.minsize(720,740)
root.configure(bg="#f7fafb")
root.columnconfigure(0, weight=1)
main = ttk.Frame(root,padding=(22,16))
main.grid(row=0,column=0,sticky="nsew")
main.columnconfigure(1,weight=1)

ttk.Label(main,text="Integración segura de documentos y videos",
          font=("Segoe UI",16,"bold")).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,8))
ttk.Label(main,text="Solo en la PC de Recepción. No usa pacientes ni altera las alarmas de citas.",
          font=("Segoe UI",10)).grid(row=1,column=0,columnspan=2,sticky="w",pady=(0,12))
ttk.Label(main,text="Bucket privado verificado: "+BUCKET,
          font=("Segoe UI",10,"bold")).grid(row=2,column=0,columnspan=2,sticky="w",pady=(0,12))

FIELDS = (
  ("CLINICAL_R2_ACCOUNT_ID","Account ID de Cloudflare (32 caracteres)",False),
  ("CLINICAL_R2_ACCESS_KEY_ID","Access Key ID de R2",True),
  ("CLINICAL_R2_SECRET_ACCESS_KEY","Secret Access Key de R2",True),
  ("WHATSAPP_PHONE_NUMBER_ID","Meta: Phone Number ID (opcional por ahora)",False),
  ("WHATSAPP_TEST_PHONE","Tu celular autorizado para la prueba: 09XXXXXXXX",False),
  ("CLINICAL_DELIVERY_LAN_SECRET","Clave privada compartida con la PC de Historia",True),
  ("WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE","Plantilla aprobada: documentos",False),
  ("WHATSAPP_CLINICAL_VIDEO_TEMPLATE","Plantilla aprobada: videocistoscopias",False),
)
fields={}
for index,(key,title,masked) in enumerate(FIELDS,3):
    ttk.Label(main,text=title).grid(row=index,column=0,sticky="w",padx=(0,15),pady=8)
    field=ttk.Entry(main,show="•" if masked else "")
    value=existing.get(key,"")
    if not masked and value:
        field.insert(0,value)
    fields[key]=field
    field.grid(row=index,column=1,sticky="ew",pady=8)
    if masked and value:
        ttk.Label(main,text="Ya está guardada; dejar vacío para conservarla",
            foreground="#4b6474",font=("Segoe UI",8)).grid(
                row=index+100,column=1,sticky="w")

lane=ttk.Frame(main)
lane.grid(row=11,column=0,columnspan=2,sticky="ew",pady=(6,8))
def generate_lan():
    fields["CLINICAL_DELIVERY_LAN_SECRET"].delete(0,tk.END)
    fields["CLINICAL_DELIVERY_LAN_SECRET"].insert(0,secrets.token_hex(32))
    messagebox.showinfo("Clave LAN","Se generó una clave nueva. Deberás configurarla también en Historia Clínica antes de enviar documentos firmados. Nunca la compartas por chats.")
ttk.Button(lane,text="Generar clave LAN aleatoria",command=generate_lan).pack(side=tk.LEFT)
def show_lan():
    e=fields["CLINICAL_DELIVERY_LAN_SECRET"]
    e.configure(show="" if e.cget("show") else "•")
ttk.Button(lane,text="Mostrar/ocultar clave LAN",command=show_lan).pack(side=tk.LEFT,padx=12)

info=tk.Text(main,width=70,height=8,wrap="word",background="#edf5f7",borderwidth=0,
             font=("Segoe UI",9),padx=12,pady=9)
info.grid(row=12,column=0,columnspan=2,sticky="ew",pady=(5,10))
info.insert("1.0",
    "IMPORTANTE:\n"
    "• GitHub NO instala automáticamente las claves en esta PC. Copia las originales solo desde tu gestor privado.\n"
    "• Si ya no conservas la Secret Access Key de R2, crea una clave nueva restringida al mismo bucket.\n"
    "• WhatsApp clínico utiliza el Worker de citas, con autorización independiente y sin token local.\n"
    "• Puedes habilitar únicamente envíos MANUALES con ambas plantillas aprobadas, identidad y consentimiento por cada paciente.\n"
    "• El archivo .env queda LOCAL y el launcher lo conserva. No lo envíes por correo ni GitHub."
)
info.configure(state="disabled")

approval_var=tk.BooleanVar(value=existing.get("WHATSAPP_CLINICAL_TEMPLATES_APPROVED")=="1")
activate_var=tk.BooleanVar(value=existing.get("CLINICAL_DELIVERY_LIVE_ENABLED")=="1")
ttk.Checkbutton(main,variable=approval_var,
    text="Confirmo que AMBAS plantillas figuran APROBADAS en Meta").grid(
    row=13,column=0,columnspan=2,sticky="w",pady=(4,5))
ttk.Checkbutton(main,variable=activate_var,
    text="Habilitar envíos clínicos manuales a pacientes (nunca automáticos)").grid(
    row=14,column=0,columnspan=2,sticky="w",pady=(3,12))
footer=ttk.Frame(main)
footer.grid(row=15,column=0,columnspan=2,sticky="ew")
def save():
    try:
        data={key:entry.get().strip() for key,entry in fields.items() if entry.get().strip()}
        # Keep previously saved secrets when their masked inputs are left empty.
        needed=("CLINICAL_R2_ACCOUNT_ID","CLINICAL_R2_ACCESS_KEY_ID","CLINICAL_R2_SECRET_ACCESS_KEY")
        for key in needed:
            if not (data.get(key) or existing.get(key)):
                raise ValueError("Falta "+key+": debe estar también en la PC, no solo en GitHub.")
        approved=bool(approval_var.get())
        active=bool(activate_var.get())
        document_name=data.get("WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE") or existing.get("WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE","")
        video_name=data.get("WHATSAPP_CLINICAL_VIDEO_TEMPLATE") or existing.get("WHATSAPP_CLINICAL_VIDEO_TEMPLATE","")
        if active:
            if not approved:
                raise ValueError("Debes confirmar que AMBAS plantillas fueron aprobadas en Meta.")
            if document_name!="entrega_documento_clinico" or video_name!="entrega_video_clinico":
                raise ValueError("Los nombres deben corresponder a las dos plantillas clínicas aprobadas.")
            if not (data.get("CLINICAL_DELIVERY_LAN_SECRET") or existing.get("CLINICAL_DELIVERY_LAN_SECRET")):
                raise ValueError("Primero configura la clave LAN compartida con Historia Clínica.")
            if not messagebox.askyesno("Confirmar habilitación clínica",
                    "¿Comprobaste la aprobación de AMBAS plantillas en Meta, la privacidad R2 y que cada envío exigirá identidad y consentimiento?\\n\\n"
                    "Se habilitarán únicamente entregas MANUALES reales a pacientes."):
                return
        data.update({
            "CLINICAL_R2_BUCKET":BUCKET,
            "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED":"1",
            "WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"1" if approved else "0",
            "CLINICAL_DELIVERY_LIVE_ENABLED":"1" if active else "0",
            "WHATSAPP_CLINICAL_LANGUAGE":"es_EC",
            "WHATSAPP_GRAPH_VERSION":existing.get("WHATSAPP_GRAPH_VERSION","v26.0"),
        })
        save_local_settings(data)
    except Exception as exc:
        messagebox.showerror("No se guardó la configuración",str(exc))
        return
    status = ("HABILITADOS" if activate_var.get() else "DESACTIVADOS")
    messagebox.showinfo("Preparación guardada",
        "Configuración guardada únicamente en esta PC.\n"
        "Los envíos clínicos manuales están " + status + ".\n"
        "Comprueba el estado en Recepción antes de enviar documentos.\n"
        "Nunca se enviará nada sin confirmación individual.")
    root.destroy()

ttk.Button(footer,text="Guardar configuración clínica",command=save).pack(side=tk.RIGHT)
ttk.Button(footer,text="Cancelar",command=root.destroy).pack(side=tk.RIGHT,padx=12)
root.mainloop()
