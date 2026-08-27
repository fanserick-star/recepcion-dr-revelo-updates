from __future__ import annotations
APP_VERSION="4.3.47"
import base64,hashlib,json,os,sys,urllib.request,zipfile,zlib
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent; BACKUP=ROOT/"data"/"update_backups"
BASE='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v446/'
TARGET={'app': 'd856e2e6b8dc2bea28d2b06b4b593b7cf5dd091eeafb1c67a9ba28ef62cd8ad3', 'js': '506ca2da6d5bf04f5bb8ace243f74cd7af69f001e127e6a2133712bd98b49e97', 'css': 'c951ccad0ed69de106e0f5f0ddea40e364c7cfc82310f46e5a4bfd5e05e95f9f', 'index': 'f09d2b85877f6c6ba389ec91afd848552b071f2ed364c37e773ac7893d0ad34a', 'report': '1f20e9b1cb3e7b547e24af6edb86e2a4da93adb5f6cde60684af0ad8ae5591b2'}
APP_MAP={'b29ba2ca4ec2723956b38e35c369d7cf0326fd5eb3e6490791d87885105f0cbf': 'app_442_443.patch', '40d045f0ae7f961b033d2f6232305550a47ed25c67b5740eb1e661ffa980c6c9': 'app_442_443.patch', '452e31012480dfcfaa3dac54943502e88427fc66080d9dc2c85a0152ec9d4501': 'app_444_445.patch', '8f1c42a403c33e81bf62a82e955704c2bd144d817326e595a8373a4d37164742': 'app_444_445.patch'}
JS_MAP={'c682d934ec8d4dbbdd9ea1cb4872f16030b332563c31db11ff8ef1b0f1101f96': 'js_442.patch', 'ff8615f4213a7a8532b0742e97c75f20db505c1029bcce0933a12420e59fb6bc': 'js_443.patch', '3c9d6490f50cc95cf1ee56a72605a2f55b713e1465fe372918655112b06fb766': 'js_444_445.patch'}
PATCH_SHA={'app_442_443.patch': 'e2025bc18f5c66d84d61e7fa015f5b8c1b6393433af524a4567977250e12d458', 'app_444_445.patch': 'db831cb5c2037ee3791f51c6a0453cac4b3254dae7f7ff569555b1456b0b2619', 'js_442.patch': '49c793d1b0a3438fbd213abe6c49b83866b6bf31f64b3eab97c65f0448fd9e7d', 'js_443.patch': '007ba606b23b53ac585dec39b8ffcdc4309f239348a4761644cec3c9e961fcd9', 'js_444_445.patch': 'bd8f28bd89b85c7c1710fd7666b27d53a258c72dce1b5a9bd919d1ac8eae2be6'}
CSS_BASE='71591db70705df09cdbbb938d4ddf96bce415b1b53415bcd5cf7d17880d9c260'; CSS_PATCH='eNqtUlFy2yAQvQpx/lKjoMp2YvSVczj+QLCSGCPQALKVeDrTQ/SEPUlXljx14k7TacsHA7uPt++xu9mkjD3MT9tm9mxn89n9HdkvkixZrMj3r9+IFFaCEVI7C4HsddCFwUN0ShAjSIBGWEE+kacKLIYUkKeIJ/AkaCu9s/pVYPzu/kSeiIjZiGT0ALCj3h2SsYIBdTxBCCmE3FXedVbx27IsWcludNM6H4WN+RnjPNag0hnn+S2sClzXKNn5gHkFpehM/BVLT0MtlDtwi/6uAa5F5/GFJ+vPY+jLxzZ47fbg57/HlE524f8b/sDQH6gn77NRN3CcyorVAtdP1r/hawF7Yklx5nwsszRLL5RG6CNVIJ0XwytutAUaa/yfqn6fxLiWO5zMwNO2/wc5oRHGnCUV7K3NvHQ2IlxXdeRrdtkdA0jnaRjmxFY8YdkSmkmHRYl7oGNtal2EYyN8pVG1a3nK2j5vhVLDu3XbkxQd5FObvVC6CyPmejom1GCZBGe0ItNA5JOBdZoVWTHKDvoVkChZItWlj4cly09fW4/3NFkMurfb7Q9OUXBv'
IDX_BASE='4e73b78fba4da18cc7819b19f92de31754c3790c3ac1e0c08fe2421c83284300'; IDX_PATCH='eNp9UstO5DAQ/JVWznlIJOIhmSBAe0DigDjsYWfm0NhNYtZxLNuJxP4N38KPbSeeGdgVwherH1VdLvdmc5qf5ZsMQBhtf4Mnc7nNQnw1FHqiuM2g9/TMuSpEjFpWa62UIVzNl01Zl83pNmu3Ntvt8s1FnV80K1s6QukZpMEQmAA7sgoLyywzFYaWkKEiOLSt0Mc+NUZwXNO2W8qVbh+WiGwkUaXmryBytM/aD6T2oNsUo8LvUJ6C7ElN5oh7pCT0e5xEK8l8oG7XGNV4AFX89IMtJ/VZflKffzLmP2tW7V3BQDJFT7iyLgSir9trGSc0+g9KPVoKoMiA82PncWCJ3CDckWiY4irpHgPYiWa+ZvIhAQMBOqNZOuAUx+H9jf8Th8XYEn4Y+HX3AANaHgZB+5nY0mFcHHJo1FiKyu2ftToCWi3KJ++Z4GcacoOqI16Zg5z97OIp5ds5LcyXHjXsUbN4JIL02kUIXn5aO3SufPln55hlbUwMu791i++6'
REPORT='eNp1kkFuE0EQRfc+RR3AGaIQvERqxhZYihwUJxt25Z6y06ine+juGSVZcQe4AEsWrDiCb8JJ+N3jDEIIyQvbXfWr/vt1I1o6bY4/HS1DRSq07BpPNzKI9fTr81caLquX1eViNlNvV5ulovf17IxqdlosB+odkzaJ6ZHJebJMYk1r8G8jZFwrjeHkK7RcnQo/9dIwDSaanRUSR8F/9KS9I4mJMbtWm3p1pZbX1PSBXRJKHh2QjoLtOIvdPY/V4yJNmR6FOqgLcRLXSMAOEb/QyQf8UXba9DJwKSius9iyVPX/Sv7R2wUTss7e6Hsmf9Ib7buimFvn2UaUMBSGYinIwcQU/KRZSCiLulbc018Co7l5ngKCnZGn7Al52Alp5hBREMu0mO2MXZEyp2B8kEjROFRqiHesjeAhzk+GvcO7M7RnncD2RGC23qzr9TW9JnWLiFc3Y1r/ZUb7XgK2K8Q4HCYEmdkgTznizA7UJPvdyuQATJDJnvEK3XtG4rQ4R/GhB7JYOjvfHH8wtR7kni/Md4Ynj+M1xWeoJ1uQbHvJPbDP7c4cv7vpvB4LFdbj/hitxguBeVXf3qmr9QdVr49fNpA+HTzCw3aglJfGKOTAffLt8Vsy2lO57HycHPS9GbA7Mu2sJHwbsCYuhbOjzgfavlNnF68WxUBJrfVNKSg3ZRzmWJ7OceOnd6rEDXNqOPGLOb1R2xUt8VG311u6OL9YVA82PuRAIbPLUC1yz4htucTeJg9g1ew3IfZc/g=='

def hb(b):return hashlib.sha256(b).hexdigest()
def hf(p):return hb(p.read_bytes()) if p.exists() else ""
def edits(blob):return json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
def patch(base,blob):
 lines=base.decode("utf-8").splitlines(keepends=True)
 for a,b,r in reversed(edits(blob)):lines[int(a):int(b)]=r
 return "".join(lines).encode("utf-8")
def getpatch(name):
 req=urllib.request.Request(BASE+name,headers={"User-Agent":"Recepcion-Dr-Revelo-v446"})
 with urllib.request.urlopen(req,timeout=15) as r:data=r.read(200000)
 if hb(data)!=PATCH_SHA[name]:raise RuntimeError("SHA inválido en "+name)
 return data.decode("ascii")
def _env_data_dir():
 raw=(os.getenv("RP_DATA_DIR") or "").strip()
 if not raw and (ROOT/".env").exists():
  try:
   for line in (ROOT/".env").read_text(encoding="utf-8-sig",errors="ignore").splitlines():
    if line.strip().startswith("RP_DATA_DIR="):
     raw=line.split("=",1)[1].strip().strip('"').strip("'");break
  except Exception:pass
 if not raw:return None
 p=Path(os.path.expandvars(os.path.expanduser(raw)))
 return p if p.is_absolute() else ROOT/p
def _backup_files():
 dirs=[BACKUP]
 d=_env_data_dir()
 if d:dirs.append(d/"update_backups")
 dirs += [ROOT.parent/"data"/"update_backups"]
 seen=set(); out=[]
 for d in dirs:
  try:
   for z in d.glob("auto_antes_actualizacion_*.zip"):
    k=str(z.resolve()).lower()
    if k not in seen:seen.add(k);out.append(z)
  except Exception:pass
 try:
  for z in ROOT.rglob("auto_antes_actualizacion_*.zip"):
   k=str(z.resolve()).lower()
   if k not in seen:seen.add(k);out.append(z)
 except Exception:pass
 return sorted(out,key=lambda p:p.stat().st_mtime,reverse=True)
def previous_app():
 found=[]
 for z in _backup_files():
  try:
   with zipfile.ZipFile(z) as q:
    names=q.namelist()
    cand=next((n for n in names if n.replace('\\','/').endswith("app.py")),None)
    if cand:
     b=q.read(cand); h=hb(b); found.append(h[:12])
     if h in APP_MAP or h=='f63a9466fef0c24f977a48d08e347504b7d582cc36aca465b07d004c43c02fd6':return b
  except Exception:pass
 extra=("; respaldos vistos: "+", ".join(found[:6])) if found else ""
 raise RuntimeError("No hallé respaldo compatible v4.3.42–v4.3.46"+extra)
def build_known(path,target,mapping):
 b=path.read_bytes(); s=hb(b)
 if s==target:return b
 name=mapping.get(s)
 if not name:raise RuntimeError("Archivo no reconocido: "+str(path.relative_to(ROOT)))
 out=patch(b,getpatch(name))
 if hb(out)!=target:raise RuntimeError("SHA final inválido: "+str(path.relative_to(ROOT)))
 return out
def build_single(path,target,base,blob):
 b=path.read_bytes();s=hb(b)
 if s==target:return b
 if s!=base:raise RuntimeError("Archivo base no reconocido: "+str(path.relative_to(ROOT)))
 out=patch(b,blob)
 if hb(out)!=target:raise RuntimeError("SHA final inválido: "+str(path.relative_to(ROOT)))
 return out
def aw(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);t=path.with_name(path.name+".v446_tmp");t.write_bytes(data);os.replace(t,path)
def bridge_backup(paths):
 if not paths:return None
 BACKUP.mkdir(parents=True,exist_ok=True);z=BACKUP/("v446_puente_antes_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
 with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as q:
  for p in paths:
   if p.exists():q.write(p,p.relative_to(ROOT).as_posix())
 return z
def restore(z):
 if not z:return
 try:
  with zipfile.ZipFile(z) as q:
   for n in q.namelist():aw(ROOT/n,q.read(n))
 except Exception:pass
def main():
 old=previous_app(); oh=hb(old)
 if oh=='f63a9466fef0c24f977a48d08e347504b7d582cc36aca465b07d004c43c02fd6':final_app=old
 else:final_app=patch(old,getpatch(APP_MAP[oh]))
 final_app=final_app.replace(b'APP_VERSION = "4.3.46"',b'APP_VERSION = "4.3.47"',1)
 if hb(final_app)!=TARGET["app"]:raise RuntimeError("SHA final inválido: app.py")
 jp=ROOT/"static"/"app.js";cp=ROOT/"static"/"style.css";ip=ROOT/"static"/"index.html";rp=ROOT/"REPORTE_v4_3_46_AGENDA_CANCELADAS_SINCRONIZADA.txt"
 fj=build_known(jp,TARGET["js"],JS_MAP);fc=build_single(cp,TARGET["css"],CSS_BASE,CSS_PATCH);fi=build_single(ip,TARGET["index"],IDX_BASE,IDX_PATCH);fr=zlib.decompress(base64.b64decode(REPORT))
 if hb(fr)!=TARGET["report"]:raise RuntimeError("SHA final inválido: reporte")
 z=bridge_backup([p for p,k in [(jp,"js"),(cp,"css"),(ip,"index")] if hf(p)!=TARGET[k]])
 try:
  aw(jp,fj);aw(cp,fc);aw(ip,fi);aw(rp,fr)
  if hf(jp)!=TARGET["js"] or hf(cp)!=TARGET["css"] or hf(ip)!=TARGET["index"]:raise RuntimeError("Verificación final de recursos falló")
  aw(ROOT/"app.py",final_app)
  if hf(ROOT/"app.py")!=TARGET["app"]:raise RuntimeError("Verificación final de app.py falló")
 except Exception:restore(z);raise
 if os.getenv("RP_V447_NO_EXEC")=="1":print("v4.3.47 reconstruida y verificada");return 0
 os.execv(sys.executable,[sys.executable,str(ROOT/"app.py"),*sys.argv[1:]])
if __name__=="__main__":
 try:raise SystemExit(main())
 except Exception as e:print("No se pudo completar v4.3.47:",e,file=sys.stderr);raise
