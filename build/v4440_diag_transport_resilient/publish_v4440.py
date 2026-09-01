from __future__ import annotations

import hashlib,json,os,pathlib,subprocess,time,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'updates'/'v4_4_40_diag_transport_resilient'
LATEST=ROOT/'latest-v3.json'; LEGACY=ROOT/'latest.json'

def run(*a): subprocess.run(list(a),cwd=ROOT,check=True)
def sha(b): return hashlib.sha256(b).hexdigest()
def get(url):
    sep='&' if '?' in url else '?'
    req=urllib.request.Request(url+sep+'rp_ts='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'Recepcion-v4440-release'})
    with urllib.request.urlopen(req,timeout=12) as r: return r.read()
def commit(paths,msg):
    run('git','config','user.name','github-actions[bot]'); run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','add',*paths)
    if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode!=0:
        run('git','commit','-m',msg); run('git','pull','--rebase','origin','main'); run('git','push','origin','main')
def verify_payload(c):
    last=None
    for _ in range(90):
        try:
            for x in c['files']:
                b=b''.join(get(u) for u in x['parts']) if x['path']=='ABRIR_RECEPCION.py' else get(x['url'])
                if sha(b)!=x['sha256']: raise RuntimeError('sha '+x['path'])
                if x['path'].endswith('.py'): compile(b.decode('utf-8-sig'),x['path'],'exec')
            print('RAW_V4440_OK'); return
        except Exception as e: last=e; time.sleep(1)
    raise RuntimeError('Raw no propagó: '+repr(last))
def verify_channel():
    url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json'; last=None
    for _ in range(90):
        try:
            d=json.loads(get(url).decode('utf-8-sig'))
            if d.get('version')=='4.4.40' and d.get('app_version')=='4.4.36': print('CHANNEL_V4440_OK'); return
            last=(d.get('version'),d.get('app_version'))
        except Exception as e: last=e
        time.sleep(1)
    raise RuntimeError('Canal no propagó: '+repr(last))
def main():
    if os.getenv('GITHUB_ACTIONS','').lower()!='true': raise SystemExit('Solo GitHub Actions')
    ctext=(OUT/'candidate_latest.json').read_text(encoding='utf-8'); c=json.loads(ctext)
    expected=['ABRIR_RECEPCION.py','app_base_4428.py','app.py','static/app.js','static/index.html','update_manifest.json']
    if c.get('version')!='4.4.40' or [x.get('path') for x in c.get('files',[])]!=expected: raise RuntimeError('Candidato inválido')
    commit(['updates/v4_4_40_diag_transport_resilient'],'payload: v4.4.40 transporte diagnóstico resiliente validado')
    run('git','pull','--rebase','origin','main'); verify_payload(c)
    current=json.loads(LATEST.read_text(encoding='utf-8'))
    if current.get('version') not in {'4.4.39','4.4.40'}: raise RuntimeError('Canal cambió: '+str(current.get('version')))
    LATEST.write_text(ctext,encoding='utf-8'); LEGACY.write_text(ctext,encoding='utf-8')
    commit(['latest-v3.json','latest.json'],'release: v4.4.40 transporte diagnóstico resiliente')
    verify_channel(); print('PUBLISH_V4440_COMPLETE')
if __name__=='__main__': main()
