from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v495'
OUT=ROOT/'updates'/'v496'
VERSION='4.3.96'
LAUNCHER_VERSION='4.3.96-standalone-4'

def joined(prefix,n):
    ps=sorted(SRC.glob(prefix+'*'),key=lambda p:int(p.name.replace(prefix,'')))
    if len(ps)!=n: raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(ps)}')
    return ''.join(p.read_text(encoding='utf-8') for p in ps)

def sha(b): return hashlib.sha256(b).hexdigest()

def write_parts(text,prefix,n):
    OUT.mkdir(parents=True,exist_ok=True)
    for p in OUT.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/n); names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text:
        raise SystemExit('reconstruccion invalida '+prefix)
    return names

def replace_once(text,old,new,label):
    c=text.count(old)
    if c!=1: raise SystemExit(f'{label}: esperaba 1 coincidencia y encontro {c}')
    return text.replace(old,new,1)

def patch_app(s):
    s=replace_once(s,'APP_VERSION = "4.3.95"','APP_VERSION = "4.3.96"','version backend')
    s=replace_once(s,"const VERSION=\\'4.3.95\\';","const VERSION=\\'4.3.96\\';",'version visual')
    s=replace_once(s,'from urllib.parse import urlparse\n','from urllib.parse import urlparse, urlunparse, unquote\nimport ssl\n','imports postgres portable')
    s=replace_once(s,'import psycopg\n', '''try:\n    import pg8000.dbapi as pg8000_dbapi\n    _POSTGRES_DRIVER = "pg8000"\nexcept Exception:\n    pg8000_dbapi = None\n    import psycopg\n    _POSTGRES_DRIVER = "psycopg"\n''','driver postgres portable')

    old_norm='''def normalize_cloud_url(url: str) -> str:\n    if url.startswith("postgres://"):\n        return url.replace("postgres://", "postgresql+psycopg://", 1)\n    if url.startswith("postgresql://"):\n        return url.replace("postgresql://", "postgresql+psycopg://", 1)\n    return url\n'''
    new_norm='''def normalize_cloud_url(url: str) -> str:\n    """Normaliza Neon al driver PostgreSQL disponible en esta instalacion."""\n    if not url:\n        return url\n    parsed = urlparse(url)\n    scheme = parsed.scheme.lower()\n    if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+pg8000"}:\n        driver = "pg8000" if _POSTGRES_DRIVER == "pg8000" else "psycopg"\n        query = "" if driver == "pg8000" else parsed.query\n        parsed = parsed._replace(scheme=f"postgresql+{driver}", query=query)\n        return urlunparse(parsed)\n    return url\n'''
    s=replace_once(s,old_norm,new_norm,'normalize_cloud_url')
    s=replace_once(s,'cloud_connect_args = {"connect_timeout": 12}\n','''cloud_connect_args = (\n    {"timeout": 12, "ssl_context": ssl.create_default_context()}\n    if _POSTGRES_DRIVER == "pg8000"\n    else {"connect_timeout": 12}\n)\n''','connect args')

    old_raw='''def _raw_psycopg_url() -> str:\n    """Devuelve la URL sin el prefijo de driver de SQLAlchemy."""\n    url = CONFIGURED_DB_URL\n    if url.startswith("postgresql+psycopg://"):\n        return url.replace("postgresql+psycopg://", "postgresql://", 1)\n    return url\n'''
    new_raw='''def _raw_psycopg_url() -> str:\n    """Devuelve una URL PostgreSQL limpia para la sonda directa de Neon."""\n    url = CONFIGURED_DB_URL\n    for prefix in ("postgresql+psycopg://", "postgresql+pg8000://", "postgres://"):\n        if url.startswith(prefix):\n            return "postgresql://" + url[len(prefix):]\n    return url\n'''
    s=replace_once(s,old_raw,new_raw,'url directa neon')

    old_probe='''    # Conexión nueva e independiente del pool. SELECT 1 no modifica ningún dato.\n    with psycopg.connect(raw_url, connect_timeout=12, autocommit=True) as conn:\n        with conn.cursor() as cur:\n            cur.execute("SELECT 1")\n            row = cur.fetchone()\n            if not row or int(row[0]) != 1:\n                raise RuntimeError("Neon no respondió correctamente a la prueba")\n'''
    new_probe='''    # Conexión nueva e independiente del pool. SELECT 1 no modifica ningún dato.\n    if _POSTGRES_DRIVER == "pg8000":\n        parsed = urlparse(raw_url)\n        database = unquote((parsed.path or "").lstrip("/"))\n        if not parsed.hostname or not parsed.username or not database:\n            raise RuntimeError("La URL de Neon está incompleta")\n        conn = pg8000_dbapi.connect(\n            user=unquote(parsed.username),\n            password=unquote(parsed.password or ""),\n            host=parsed.hostname,\n            port=parsed.port or 5432,\n            database=database,\n            timeout=12,\n            ssl_context=ssl.create_default_context(),\n        )\n        try:\n            conn.autocommit = True\n            cur = conn.cursor()\n            try:\n                cur.execute("SELECT 1")\n                row = cur.fetchone()\n            finally:\n                cur.close()\n        finally:\n            conn.close()\n    else:\n        with psycopg.connect(raw_url, connect_timeout=12, autocommit=True) as conn:\n            with conn.cursor() as cur:\n                cur.execute("SELECT 1")\n                row = cur.fetchone()\n    if not row or int(row[0]) != 1:\n        raise RuntimeError("Neon no respondió correctamente a la prueba")\n'''
    s=replace_once(s,old_probe,new_probe,'sonda neon')
    compile(s,'app.py','exec')
    for token in ['_POSTGRES_DRIVER = "pg8000"','postgresql+pg8000','pg8000_dbapi.connect','APP_VERSION = "4.3.96"','V495_ATTENTION_JS','v495-consult-card','Revisando AZUR','Emitir por lotes']:
        if token not in s: raise SystemExit('falta '+token)
    return s

def patch_launcher(s):
    if 'DISABLE_SQLALCHEMY_CEXT_RUNTIME' not in s:
        old='    env = os.environ.copy()\n    env["RP_DESKTOP_LAUNCH"] = "1"\n'
        new='    env = os.environ.copy()\n    env["RP_DESKTOP_LAUNCH"] = "1"\n    env["DISABLE_SQLALCHEMY_CEXT_RUNTIME"] = "1"\n'
        s=replace_once(s,old,new,'launcher runtime puro')
    compile(s,'ABRIR_RECEPCION.py','exec')
    return s

def main():
    app=patch_app(joined('app.part',7)); launcher=patch_launcher(joined('ABRIR_RECEPCION.part',4))
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode(); lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode(); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v496/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.96: corrige el arranque en instalaciones portables usando pg8000 cuando psycopg no esta disponible.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb))

if __name__=='__main__': main()
