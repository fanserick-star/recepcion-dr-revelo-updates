from __future__ import annotations

import hashlib, json, os, pathlib, subprocess, time, urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'updates'/'v4_4_39_diag_transport'
LATEST=ROOT/'latest-v3.json'; LEGACY=ROOT/'latest.json'
EXPECTED=['ABRIR_RECEPCION.py','app_base_4428.py','app.py','static/app.js','static/index.html','update_manifest.json']

def run(*a): subprocess.run(list(a),cwd=ROOT,check=True)
def sha(b): return hashlib.sha256(b).hexdigest()
def get(url,timeout=12):
    sep='&' if '?' in url else '?'; req=urllib.request.Request(url+sep+'rp_ts='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'Recepcion-v4439-release'})
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read()

def commit_push(paths,msg):
    run('git','config','user.name','github-actions[bot]'); run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'); run('git','add',*paths)
    if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode!=0:
        run('git','commit','-m',msg); run('git','pull','--rebase','origin','main'); run('git','push','origin','main')

def verify_raw(c):
    last=None
    for _ in range(90):
        try:
            for x in c['files']:
                data=b''.join(get(u) for u in x['parts']) if x['path']=='ABRIR_RECEPCION.py' else get(x['url'])
                if sha(data)!=x['sha256']: raise RuntimeError('SHA Raw '+x['path'])
                if x['path'].endswith('.py'): compile(data.decode('utf-8-sig'),x['path'],'exec')
            print('RAW_PAYLOAD_V4439_OK'); return
        except Exception as e: last=e; time.sleep(1)
    raise RuntimeError(f'Payload v4.4.39 no propagó: {last}')

def verify_channel():
    url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json'; last=None
    for _ in range(90):
        try:
            d=json.loads(get(url,10).decode('utf-8-sig')); paths=[x.get('path') for x in d.get('files',[])]
            if d.get('version')=='4.4.39' and d.get('app_version')=='4.4.36' and paths==EXPECTED:
                print('CHANNEL_V4439_OK'); return
            last=(d.get('version'),d.get('app_version'),paths)
        except Exception as e: last=e
        time.sleep(1)
    raise RuntimeError(f'Canal v4.4.39 no propagó: {last}')

def main():
    if os.getenv('GITHUB_ACTIONS','').lower()!='true': raise SystemExit('Solo GitHub Actions')
    txt=(OUT/'candidate_latest.json').read_text(encoding='utf-8'); c=json.loads(txt)
    if c.get('version')!='4.4.39' or c.get('app_version')!='4.4.36' or [x.get('path') for x in c.get('files',[])]!=EXPECTED: raise RuntimeError('Candidato v4.4.39 inválido')
    commit_push(['updates/v4_4_39_diag_transport'],'payload: v4.4.39 transporte diagnóstico validado')
    run('git','pull','--rebase','origin','main'); verify_raw(c)
    current=json.loads(LATEST.read_text(encoding='utf-8'))
    if current.get('version') not in {'4.4.38','4.4.39'}: raise RuntimeError('Canal cambió inesperadamente: '+str(current.get('version')))
    LATEST.write_text(txt,encoding='utf-8'); LEGACY.write_text(txt,encoding='utf-8')
    commit_push(['latest-v3.json','latest.json'],'release: v4.4.39 transporte diagnóstico compatible con Neon')
    verify_channel(); print('PUBLISH_V4439_COMPLETE')

if __name__=='__main__': main()
