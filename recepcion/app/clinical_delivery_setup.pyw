"""Private Windows setup window. Never transmit, print or log credentials."""
from __future__ import annotations
import secrets
import tkinter as tk
from tkinter import messagebox, ttk

from clinical_delivery_config import parse_existing, save_local_settings, BUCKET

existing = parse_existing()
root = tk.Tk()
root.title("Dr. Revelo | Preparar envíos clínicos")
root.geometry("780x680")
root.minsize(670,600)
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
  ("WHATSAPP_ACCESS_TOKEN","Meta: Access Token (opcional por ahora)",True),
  ("WHATSAPP_TEST_PHONE","Tu celular autorizado para la prueba: 09XXXXXXXX",False),
  ("CLINICAL_DELIVERY_LAN_SECRET","Clave privada compartida con la PC de Historia",True),
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
lane.grid(row=10,column=0,columnspan=2,sticky="ew",pady=(6,8))
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
info.grid(row=11,column=0,columnspan=2,sticky="ew",pady=(5,10))
info.insert("1.0",
    "IMPORTANTE:\n"
    "• GitHub NO instala automáticamente las claves en esta PC. Copia las originales solo desde tu gestor privado.\n"
    "• Si ya no conservas la Secret Access Key de R2, crea una clave nueva restringida al mismo bucket.\n"
    "• WhatsApp del Worker y sus recordatorios no se modificarán. El acceso de Meta aquí es independiente.\n"
    "• Esta preparación deja DESACTIVADOS los envíos clínicos hasta que Meta apruebe ambas plantillas y se verifique la configuración.\n"
    "• El archivo .env queda LOCAL y el launcher lo conserva. No lo envíes por correo ni GitHub."
)
info.configure(state="disabled")

footer=ttk.Frame(main)
footer.grid(row=12,column=0,columnspan=2,sticky="ew")
def save():
    try:
        data={key:entry.get().strip() for key,entry in fields.items() if entry.get().strip()}
        # Keep previously saved secrets when their masked inputs are left empty.
        needed=("CLINICAL_R2_ACCOUNT_ID","CLINICAL_R2_ACCESS_KEY_ID","CLINICAL_R2_SECRET_ACCESS_KEY")
        for key in needed:
            if not (data.get(key) or existing.get(key)):
                raise ValueError("Falta "+key+": debe estar también en la PC, no solo en GitHub.")
        # Hard stop on every setup run. Never infer approval just because a
        # template name exists; a deliberate future activation is required.
        data.update({
            "CLINICAL_R2_BUCKET":BUCKET,
            "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED":"1",
            "CLINICAL_DELIVERY_LIVE_ENABLED":"0",
            "WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"0",
            "WHATSAPP_CLINICAL_LANGUAGE":"es_EC",
            "WHATSAPP_GRAPH_VERSION":existing.get("WHATSAPP_GRAPH_VERSION","v26.0"),
        })
        save_local_settings(data)
    except Exception as exc:
        messagebox.showerror("No se guardó la configuración",str(exc))
        return
    messagebox.showinfo("Preparación guardada",
        "Configuración guardada únicamente en esta PC.\n"
        "Los envíos clínicos siguen DESACTIVADOS.\n"
        "Cierra y vuelve a abrir Recepción para cargarla; desde Documentos médicos podrás comprobar R2.\n"
        "Faltan aprobación de Meta y verificación de Historia antes del primer envío.")
    root.destroy()

ttk.Button(footer,text="Guardar preparación (sin activar envíos)",command=save).pack(side=tk.RIGHT)
ttk.Button(footer,text="Cancelar",command=root.destroy).pack(side=tk.RIGHT,padx=12)
root.mainloop()
