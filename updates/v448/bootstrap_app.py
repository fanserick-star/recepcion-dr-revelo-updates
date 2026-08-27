from __future__ import annotations
APP_VERSION = "4.3.48"
import base64,hashlib,json,os,sys,urllib.request,zipfile,zlib
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BACKUP=ROOT/"data"/"update_backups"
BASE="https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v446/"
TARGET={'app': '5ec6b484e2bdf6a15a798a276a3bafa7415d64a6f0c98d7eefc5ca20983247b6', 'js': 'fa6ca367f2de636ddc5caf58f3e660b9786c6ee9d66f147dbb18d262942e459a', 'css': '0bef8b1601f45908775448e4b821f20d383072b930ede14e7ab09f4fafa010c8', 'idx': 'f09d2b85877f6c6ba389ec91afd848552b071f2ed364c37e773ac7893d0ad34a'}
APP_OLD={
 "b29ba2ca4ec2723956b38e35c369d7cf0326fd5eb3e6490791d87885105f0cbf":"app_442_443.patch",
 "40d045f0ae7f961b033d2f6232305550a47ed25c67b5740eb1e661ffa980c6c9":"app_442_443.patch",
 "452e31012480dfcfaa3dac54943502e88427fc66080d9dc2c85a0152ec9d4501":"app_444_445.patch",
 "8f1c42a403c33e81bf62a82e955704c2bd144d817326e595a8373a4d37164742":"app_444_445.patch"}
JS_OLD={
 "c682d934ec8d4dbbdd9ea1cb4872f16030b332563c31db11ff8ef1b0f1101f96":"js_442.patch",
 "ff8615f4213a7a8532b0742e97c75f20db505c1029bcce0933a12420e59fb6bc":"js_443.patch",
 "3c9d6490f50cc95cf1ee56a72605a2f55b713e1465fe372918655112b06fb766":"js_444_445.patch"}
PATCH_SHA={
 "app_442_443.patch":"e2025bc18f5c66d84d61e7fa015f5b8c1b6393433af524a4567977250e12d458",
 "app_444_445.patch":"db831cb5c2037ee3791f51c6a0453cac4b3254dae7f7ff569555b1456b0b2619",
 "js_442.patch":"49c793d1b0a3438fbd213abe6c49b83866b6bf31f64b3eab97c65f0448fd9e7d",
 "js_443.patch":"007ba606b23b53ac585dec39b8ffcdc4309f239348a4761644cec3c9e961fcd9",
 "js_444_445.patch":"bd8f28bd89b85c7c1710fd7666b27d53a258c72dce1b5a9bd919d1ac8eae2be6"}
APP_446="f63a9466fef0c24f977a48d08e347504b7d582cc36aca465b07d004c43c02fd6"
APP_447="d856e2e6b8dc2bea28d2b06b4b593b7cf5dd091eeafb1c67a9ba28ef62cd8ad3"
JS_446="506ca2da6d5bf04f5bb8ace243f74cd7af69f001e127e6a2133712bd98b49e97"
CSS_442="71591db70705df09cdbbb938d4ddf96bce415b1b53415bcd5cf7d17880d9c260"
CSS_446="c951ccad0ed69de106e0f5f0ddea40e364c7cfc82310f46e5a4bfd5e05e95f9f"
IDX_442="4e73b78fba4da18cc7819b19f92de31754c3790c3ac1e0c08fe2421c83284300"
IDX_446="f09d2b85877f6c6ba389ec91afd848552b071f2ed364c37e773ac7893d0ad34a"
JS_DELTA='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'
CSS_PATCH={CSS_442:'eNqtV2uumzgU3oqn1Uh9XFLeBCJV03V0+sNgGzwFjGzncRtFmkXMXub/LGVW0mMgCRBIbqcT6V4RY5/H953zHefzZ8e2o6f23+dXv9evnl59eId2/spb+SH698+/UIbrjJY446KmCu244mkJD1oQjEqMFK1wjdF79CmnNSwRij5peKISKV5nUtT8G4b1dx9a4yus4a0GY9ae0q+WFPtV56Gk5NhuQSjF2ddcim1NkteMMZvZv/CqEVLjWm/Oe4QEH1YmSiGT1zRM4XO7K9tKBe8JZXhb6jkrB0sVmIh9UkN+txtEA5nr52QVu93S6XEaSSF2VD7d38NEtlX/f8IPEnpB9Gj6VvOKHnu3OPThc7X6X+w1FDipUXq2uWae4zmDSDU9aIvQTEhsTiUlr6mlC8AnL6YvYZ1nX6EyVeI0h58IR1W4LM8hpfY4zQ0TtYbtPC90EttDdkoK5qSlTJ3UebKyvYBWfRw1hLijVufbqoWmxwrLnEPUokkcuzlsGkyIORc3B+RABpueZokJ36puz2119LtMykiJkhPUF8SmTyB2vNRLu7AV/0bB0CoAU8M8osDetNAW3Xdn5Z/GArBG//x97utqS5WWGBUAvORCIUmx0YH30PEaoKOokYJRBbji0qgAw5newgG81UKONSDlJTjOLXhVmHeUWMYIL61U18cK8NlzoovENemfxmf6jaqgVB8JV02Jn5NccrLJMWAaQpJXA/D0JlyDkae1u9u/nTdVUCkullhJDxtc8ry2uKaVSjKoFSo74/6AMGd9IWtIA2E0Ys6UxXDMokEdSys3r8H8G8cLCM2fXrOIxSx7MiTD5064qytyx7EuZGsaEe8lzihjmHkPnCkg+dhh6Zsk+lJpnw1UiY1s1H6bZGygGrEDTxkdYzqsaxpTyoJz+QZOGERsUL6uOyneOLBfBA+azWjomTAW0Ojs2Ykj33eXTQPOzfNt3bmjsrNPi0c/glDUx2FfwslW06C5asWErJJtA5qUYUVvxCWc9jBo0TnyyFnbcfggclS4vQQll4NO6Ma+OwTbAy9T15DhclaoubEaplEa20MFchZ7WeOrMpaU6cRoxqXTIiON9k2JxXE824FZRqAHxqLpspBdtDFwQ7wONxMOJsV1k79voN8XUMDtGoXxupe4uZPRcpOmMfWy9bj+MVtT9pIqVDQzw+t4EaLA4BPOYkEdGoHVSW8GtzPlrivgGZOxQv6xVZqzZ0ioNsM0aSGxUqphpNZXJR4KaQoFbbTozKuVCq1F1dbFpid/uNQHfV4aJEWYw4LHEaOfarXgTqut3djG3umu83To2TRUf9b1vHXgdXG08CTSmJ9Px+jLRGzgnwV4wgpUItjcVjVQyiSCvw74xZnJOC3JrXZ5w6lmL9xDnGnNtKNqruQi4McfieFyMP2t64pU/CMUtS15psQGSoIRYevgVoc7ryNu3KsRh3muTzbm9s5KsbdMgye4ft6D0NGlgpM7DqVfcjVzHYlmRLM/8dP91A/REXP2w65ZiCYpsdJWVvDyolW9Cftu3h8J381OwyVHN005HezA2rhVli3N1M65GoLYxf7SyY9LvdnxP5+wFnDL/RHShlzBDXqzcPPvFtxrx7XfpxfK02w4N2A6P6Rw18S7u8NU7pacavhRnw/cugNLTuT5wQKEuJVHdZziZsC0AKLTwgGUbqEUhz8MHPcicr9VlHD8psKH/l1k3r09zv9geHRHOw5Za+OCUS51e9ft5KAd+o9vMKE90wOtnC8q+N15cjcwwmW3NenMtU3ozzbhaEINhpAJ+hH+Pfa2/evJYP/ly5fvF7uV7w==',CSS_446:'eNqlV9tu4zYQ/RUiQYHsbuTV/WYgaL8jzQMlDmW2uoGiY6eGv6vv/bIOJdmWZMlOsAFiW6Q5lzNzztCvr5Zpe8/ty+vDz+/k3V05Kzck//1L/sigZJQUW2iUpGRTSSpF1RAJNIeG/CAMFM1zILWsODSiKmmOa4TTVG3xAN2qSop/KNr4/vPP8uH5YZWIPBdlZuDWRu8BM7QRkRuJKg+FKI2dYGoT25ZZ74/jM/0Xmw2AOjDR1Dn9iDMp2DqjdWz59X59MYCfnvwQjTyH9vvu27ypDcjqbInnsF/TXGSlIRQUTZxCqUB2xl00XlPG8HBshfiQVJKBjK16T5oqF4w8Mg4Bt/oNQ1Imtk0XVULTvzNZbUsWo3eg0sj0Npp/shyPQfb8yAMe8RTf278b4a4uyB16V2mVVzJ+TEMImPMZZ8A55c4dZw0W+dBh6eokNiCyjeo+a6hik5ikfZpkrKEaVQc/pTDGdBDkI0QA3Fv3WXiW7wV8zatSGQ1mGdu2dqgfd10EkWd+Ch4ym9HQM+Pcg+Dk2YoC17WXTSPO9cd139mjtjOPi0dfmpqWh0tiusPXCvbKQHKVDa9kEW/rGmRKG1jnoBAoA8+kuudWvjeFwTRPkQdWaEb+ncjJxj4UVGaijM8HLd+OXHsItoNepq4xw+WsSH1l1U+CJDIHVi1rkcuKKugNGDlwFWvNODMtQHa1MI1bLIqiWQamKUMOjJqL29znybm5bJ+G/npSg0lzXeXvauh3G2zgdg3istpJWt/IaJmkSQROGo77n/IQ+Ge6sIFUocgezkLkaXz8WSzAggCtTrjpjdVIK8BNV1hnysYK+de2UYJ/YELI5FLFLSRGAmoHUF6UeCikCTa01qJTXY2kUqoq2r5Y98UfLvVBn5YGSTFuce9+xOSXqObdoFpoRyZ1jjedJ0PPmlD9WdtxQs/p4mjhiaU2P5+O1peJ2OCLgXjiCnYi2twWJZaUS4L/HfCLM5MLyNm1djnDqWbqZrKu9dya9kw7quZaLsD6uCMxXA6GNAVeHQZIRV8pUUvJU0lMLIk3KljoXetw53VUG/tixOKO7bJ19Q6S59XO0ASPafmxQ6GDpYaT7wJbPxfNzHUkmBHN/sQv86kfoqPKmXdZsxBNnNNGGelG5Get6k2YN/N+YeJ9dhouOboi5XSwY9XGVFm2NNM7p27wIpu6SydflrjZ1X8+YVXhLfcrRRvWCm/QJ4lTVUfRswy2C/aFce3z9EJ5nA3nCkzrSwp3Sby7O0zlbsmpklWZDdzaA0tW4LjeAoS0lcfmMMVNg2kgRMeFAyTZYisOfxhY9lnkfi+ACfpU0H2/F+i9b4f5Hwz37miHYdXauHCUS9XedTs5aIf+/RuMb85woJXzRQW/OU9uBsaE7L4ad+ZaErqzJBxNqMEQ0kHfw7/H3jR/O2rs397e/geeiSll'}
IDX_PATCH={IDX_442:'eNp9UstO5DAQ/JVWznlIJOIhmSBAe0DigDjsYWfm0NhNYtZxLNuJxP4N38KPbSeeGdgVwherH1VdLvdmc5qf5ZsMQBhtf4Mnc7nNQnw1FHqiuM2g9/TMuSpEjFpWa62UIVzNl01Zl83pNmu3Ntvt8s1FnV80K1s6QukZpMEQmAA7sgoLyywzFYaWkKEiOLSt0Mc+NUZwXNO2W8qVbh+WiGwkUaXmryBytM/aD6T2oNsUo8LvUJ6C7ElN5oh7pCT0e5xEK8l8oG7XGNV4AFX89IMtJ/VZflKffzLmP2tW7V3BQDJFT7iyLgSir9trGSc0+g9KPVoKoMiA82PncWCJ3CDckWiY4irpHgPYiWa+ZvIhAQMBOqNZOuAUx+H9jf8Th8XYEn4Y+HX3AANaHgZB+5nY0mFcHHJo1FiKyu2ftToCWi3KJ++Z4GcacoOqI16Zg5z97OIp5ds5LcyXHjXsUbN4JIL02kUIXn5aO3SufPln55hlbUwMu791i++6'}
def hb(b):return hashlib.sha256(b).hexdigest()
def edits(blob):return json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
def patch(base,blob):
 lines=base.decode("utf-8").splitlines(keepends=True)
 for a,b,r in reversed(edits(blob)):lines[int(a):int(b)]=r
 return "".join(lines).encode("utf-8")
def remote(name):
 req=urllib.request.Request(BASE+name,headers={"User-Agent":"Recepcion-Dr-Revelo-v448"})
 with urllib.request.urlopen(req,timeout=20) as r:data=r.read(200000)
 if hb(data)!=PATCH_SHA[name]:raise RuntimeError("SHA inválido en "+name)
 return data.decode("ascii")
def make_app():
 b=(ROOT/"app.py").read_bytes(); h=hb(b)
 if h==TARGET["app"]:return b
 if h in APP_OLD:b=patch(b,remote(APP_OLD[h]));h=hb(b)
 if h==APP_446:b=b.replace(b'APP_VERSION = "4.3.46"',b'APP_VERSION = "4.3.48"',1)
 elif h==APP_447:b=b.replace(b'APP_VERSION = "4.3.47"',b'APP_VERSION = "4.3.48"',1)
 if hb(b)!=TARGET["app"]:raise RuntimeError("app.py no reconocido para v4.3.48")
 return b
def make_js():
 p=ROOT/"static"/"app.js";b=p.read_bytes();h=hb(b)
 if h==TARGET["js"]:return b
 if h in JS_OLD:b=patch(b,remote(JS_OLD[h]));h=hb(b)
 if h!=JS_446:raise RuntimeError("static/app.js no reconocido para v4.3.48")
 b=patch(b,JS_DELTA)
 if hb(b)!=TARGET["js"]:raise RuntimeError("SHA final inválido: static/app.js")
 return b
def make_simple(rel,target,mapping,already=None):
 p=ROOT/rel;b=p.read_bytes();h=hb(b)
 if h==target:return b
 if already and h==already and already==target:return b
 blob=mapping.get(h)
 if not blob:raise RuntimeError(rel+" no reconocido para v4.3.48")
 b=patch(b,blob)
 if hb(b)!=target:raise RuntimeError("SHA final inválido: "+rel)
 return b
def aw(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+".v448_tmp");tmp.write_bytes(data);os.replace(tmp,path)
def backup(paths):
 BACKUP.mkdir(parents=True,exist_ok=True);z=BACKUP/("v448_antes_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
 with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as q:
  for p in paths:
   if p.exists():q.write(p,p.relative_to(ROOT).as_posix())
 return z
def restore(z):
 try:
  with zipfile.ZipFile(z) as q:
   for n in q.namelist():aw(ROOT/n,q.read(n))
 except Exception:pass
def main():
 fa=make_app();fj=make_js();fc=make_simple("static/style.css",TARGET["css"],CSS_PATCH);fi=make_simple("static/index.html",TARGET["idx"],IDX_PATCH,IDX_446)
 paths=[ROOT/"app.py",ROOT/"static"/"app.js",ROOT/"static"/"style.css",ROOT/"static"/"index.html"]
 z=backup(paths)
 try:
  aw(ROOT/"static"/"app.js",fj);aw(ROOT/"static"/"style.css",fc);aw(ROOT/"static"/"index.html",fi)
  if hb((ROOT/"static"/"app.js").read_bytes())!=TARGET["js"] or hb((ROOT/"static"/"style.css").read_bytes())!=TARGET["css"] or hb((ROOT/"static"/"index.html").read_bytes())!=TARGET["idx"]:raise RuntimeError("Verificación final de interfaz falló")
  aw(ROOT/"app.py",fa)
  if hb((ROOT/"app.py").read_bytes())!=TARGET["app"]:raise RuntimeError("Verificación final de app.py falló")
 except Exception:restore(z);raise
 if os.getenv("RP_V448_NO_EXEC")=="1":print("v4.3.48 reconstruida y verificada");return 0
 os.execv(sys.executable,[sys.executable,str(ROOT/"app.py"),*sys.argv[1:]])
if __name__=="__main__":
 try:raise SystemExit(main())
 except Exception as e:print("No se pudo completar v4.3.48:",e,file=sys.stderr);raise
