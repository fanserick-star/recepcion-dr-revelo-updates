from __future__ import annotations

import json
import urllib.error
import urllib.request

AUTH_URL = "https://ep-shiny-scene-a66ta52d.neonauth.us-west-2.aws.neon.tech/neondb/auth/token/anonymous"
API_URL = "https://ep-sweet-mud-arlsk7qa.apirest.c-4.us-west-2.aws.neon.tech/neondb/rest/v1"
ORIGIN = "https://fanserick-star.github.io"
TEST_TOKEN = "historia-mobile-ci-probe-20261003"


def call(url, *, method="GET", jwt="", body=None, extra=None):
    headers={"Accept":"application/json","Origin":ORIGIN,"Cache-Control":"no-store"}
    if jwt:
        headers["Authorization"]="Bearer "+jwt
    if body is not None:
        headers["Content-Type"]="application/json"
        data=json.dumps(body,separators=(",",":")).encode()
    else:
        data=None
    if extra:
        headers.update(extra)
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as resp:
            raw=resp.read().decode("utf-8","replace")
            return resp.status,dict(resp.headers.items()),raw
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode("utf-8","replace")
        return exc.code,dict(exc.headers.items()),raw


def cors_headers(headers):
    return {k.lower():v for k,v in headers.items() if k.lower().startswith("access-control-")}


def main():
    ah,_,araw=call(AUTH_URL)
    auth=json.loads(araw or "{}")
    jwt=str(auth.get("token") or "")
    if ah!=200 or jwt.count(".")!=2:
        raise SystemExit("AUTH_FAILED")

    oh,ohdr,_=call(
        API_URL+"/rpc/status",
        method="OPTIONS",
        extra={
            "Access-Control-Request-Method":"POST",
            "Access-Control-Request-Headers":"authorization,content-type",
        },
    )
    sh,shdr,sraw=call(
        API_URL+"/rpc/status",
        method="POST",
        jwt=jwt,
        body={"p_token":TEST_TOKEN},
    )
    qh,qhdr,qraw=call(
        API_URL+"/rpc/search",
        method="POST",
        jwt=jwt,
        body={"p_token":TEST_TOKEN,"p_query":"KURE BUSTAMANTE"},
    )

    try: status=json.loads(sraw or "{}")
    except Exception: status={}
    try: rows=json.loads(qraw or "[]")
    except Exception: rows=[]

    result={
        "auth_http":ah,
        "options_http":oh,
        "status_http":sh,
        "search_http":qh,
        "status_ok":isinstance(status,dict) and bool(status.get("ok")),
        "source":status.get("source") if isinstance(status,dict) else None,
        "search_count":len(rows) if isinstance(rows,list) else -1,
        "options_cors":cors_headers(ohdr),
        "status_cors":cors_headers(shdr),
        "search_cors":cors_headers(qhdr),
    }
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    ok=(
        ah==200 and oh in (200,204)
        and sh==200 and qh==200
        and result["status_ok"] and result["source"]=="historia_neon"
        and result["search_count"]>=1
    )
    if not ok:
        raise SystemExit("HISTORIA_MOBILE_DIRECT_FAILED")
    print("HISTORIA_MOBILE_DIRECT_RPC_OK")


if __name__=="__main__":
    main()
